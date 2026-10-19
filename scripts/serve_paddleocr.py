"""Independent PaddleOCR environment. Run from repository root.

This is this project's small HTTP adapter, not PaddleX's official serving API.
"""
# 本机 OCR HTTP 适配器，使用独立 .ocr-venv 环境，避免与主环境的推理依赖混装。
# 启动：在项目目录运行 start_ocr.ps1；GET /health 查状态，POST /ocr 提交图片。
# 本服务只提供文字、坐标和分数，不负责认井、判断连线或生成最终记录。
import base64
import io
import json
import os
from functools import lru_cache
from threading import Lock

import numpy as np
from fastapi import FastAPI, HTTPException
from PIL import Image
from pydantic import BaseModel

app = FastAPI(title="Conduit PaddleOCR adapter")
# 同一进程中的推理请求串行进入模型，避免并发请求同时初始化或复用推理资源。
lock = Lock()


# HTTP 请求体，只接收图片文件的纯 Base64 字符串，不包含 data:image/... 前缀。
class Request(BaseModel):
    image_base64: str


# 首次识别时加载固定的检测/识别模型，lru_cache 让后续请求复用同一引擎。
# 关闭方向和去畸变组件，保持结果坐标与当前输入图一致；此处配置 CPU 和线程数。
@lru_cache(maxsize=1)
def engine():
    from paddleocr import PaddleOCR
    return PaddleOCR(use_doc_orientation_classify=False, use_doc_unwarping=False,
                     use_textline_orientation=False,
                     text_detection_model_name=os.getenv("PADDLE_DET_MODEL", "PP-OCRv5_server_det"),
                     text_recognition_model_name=os.getenv("PADDLE_REC_MODEL", "PP-OCRv5_server_rec"),
                     device="cpu", cpu_threads=int(os.getenv("OCR_CPU_THREADS", "8")), enable_mkldnn=False)


# 返回服务存活状态以及引擎是否已缓存，不主动加载模型。
# 因此服务刚启动时 engine_loaded=False 是正常状态，不代表 OCR 已完成验证。
@app.get("/health")
def health():
    return {"status": "ok", "engine_loaded": engine.cache_info().currsize > 0}


# 解码图片 → 串行调用引擎 → 解析单页结果 → 归一化框 → 返回文字证据。
# 异常作为 HTTP 422 返回；调用方应检查状态码，不能把失败响应当成空识别结果。
@app.post("/ocr")
def ocr(request: Request):
    try:
        data = base64.b64decode(request.image_base64, validate=True)
        with Image.open(io.BytesIO(data)) as im:
            # PIL先转RGB，再反转最后一维为BGR并复制，给引擎明确的图像数组。
            image = np.asarray(im.convert("RGB"))[:, :, ::-1].copy()
            width, height = im.size
        if width * height > 60_000_000:
            raise ValueError("图像超过 6000 万像素")
        # 锁覆盖引擎获取和推理；健康检查不获取模型，因此不会为查状态下载/加载权重。
        with lock:
            results = list(engine().predict(image, text_det_limit_side_len=int(os.getenv("OCR_DET_SIDE", "2000")),
                                            text_det_limit_type="max"))
        if len(results) != 1:
            raise ValueError("单页 OCR 返回数量不正确")
        # 兼容结果提供字符串或字典两种形式，以及外层res包装。
        raw = results[0].json
        if isinstance(raw, str):
            raw = json.loads(raw)
        result = raw.get("res", raw)
        texts, scores, boxes = result["rec_texts"], result["rec_scores"], result["rec_boxes"]
        if not (len(texts) == len(scores) == len(boxes)):
            raise ValueError("OCR 返回数组长度不一致")
        # 按返回顺序生成页内行id，过滤空白文字，并用整页宽高归一化矩形框。
        lines = [{"id": f"t{i:04d}", "text": text, "confidence": float(score),
                  "bbox": [float(box[0]) / width, float(box[1]) / height, float(box[2]) / width, float(box[3]) / height]}
                 for i, (text, score, box) in enumerate(zip(texts, scores, boxes), 1) if text.strip()]
        return {"width": width, "height": height, "lines": lines}
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"OCR failed: {type(exc).__name__}: {exc}") from exc
