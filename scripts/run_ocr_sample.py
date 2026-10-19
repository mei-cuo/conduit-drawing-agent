"""Run actual PaddleOCR on the supplied drawing and save inspectable evidence."""
# 直接在 OCR 环境识别参考图片，保存原始结果、可视化和统一格式结果。
# 与 probe_ocr_service.py 的区别：这里直接调用引擎，不经过 HTTP。
# 输出包含真实 OCR 证据；脚本会写入固定样例目录，通常不需要每次识别都运行。
import json
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
# 便于直接执行脚本时从同目录导入服务引擎；这里需要OCR环境，不能用未装Paddle的主环境。
sys.path.insert(0, str(ROOT / "scripts"))
from serve_paddleocr import engine


# 直接识别参考图，保存可回放 sidecar 数据和人工可检查的检测图；记录总耗时。
def main():
    started = time.perf_counter()
    file = ROOT / "data/examples/reference_drawing.png"
    out = ROOT / "outputs/paddleocr_reference"
    out.mkdir(parents=True, exist_ok=True)
    with Image.open(file) as im:
        width, height = im.size
        array = np.asarray(im.convert("RGB"))[:, :, ::-1].copy()
    predictions = list(engine().predict(array, text_det_limit_side_len=2000, text_det_limit_type="max"))
    if len(predictions) != 1:
        raise ValueError("预期一个页面结果")
    result = predictions[0]
    # 原始JSON和可视化用于追查OCR行为；统一sidecar另存，避免丢掉引擎原始信息。
    result.save_to_json(str(out / "raw.json"))
    result.save_to_img(str(out))
    raw = result.json
    if isinstance(raw, str):
        raw = json.loads(raw)
    res = raw.get("res", raw)
    lines = [{"id": f"t{i:04d}", "text": text, "confidence": float(score),
              "bbox": [float(box[0]) / width, float(box[1]) / height, float(box[2]) / width, float(box[3]) / height]}
             for i, (text, score, box) in enumerate(zip(res["rec_texts"], res["rec_scores"], res["rec_boxes"]), 1) if text.strip()]
    # 记录来源为实际推理，并保存本次原图尺寸；后续sidecar读取会核对这些尺寸。
    normalized = {"provenance": "actual_paddleocr_inference", "input": str(file),
                  "elapsed_seconds": round(time.perf_counter() - started, 2),
                  "pages": [{"page_index": 1, "width": width, "height": height, "lines": lines}]}
    (out / "ocr.json").write_text(json.dumps(normalized, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"line_count": len(lines), "elapsed_seconds": normalized["elapsed_seconds"],
                      "output": str(out), "station_candidates": [x["text"] for x in lines if "K9+" in x["text"]]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
