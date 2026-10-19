"""Standalone PaddleOCR 3.x adapter; run in a separate OCR virtual environment."""

import base64
import io
import os
from threading import Lock

from fastapi import FastAPI, Header, HTTPException
from PIL import Image
from pydantic import BaseModel

app = FastAPI(title="DrawFlow OCR")
_engine = None
_lock = Lock()


class Request(BaseModel):
    image_base64: str


@app.get("/health")
def health():
    return {"status": "ok", "engine_loaded": _engine is not None}


@app.post("/ocr")
def ocr(request: Request, authorization: str = Header(default="")):
    import secrets

    expected = os.getenv("OCR_API_KEY", "")
    if expected and not secrets.compare_digest(authorization, "Bearer " + expected):
        raise HTTPException(401, "OCR key 不匹配")
    try:
        image = Image.open(
            io.BytesIO(base64.b64decode(request.image_base64, validate=True))
        ).convert("RGB")
        if image.width * image.height > 60_000_000:
            raise ValueError("图像像素超出上限")
    except Exception as exc:
        raise HTTPException(400, "图像内容不合法") from exc
    import numpy as np
    from paddleocr import PaddleOCR

    global _engine
    with _lock:
        if _engine is None:
            _engine = PaddleOCR(
                use_doc_orientation_classify=False,
                use_doc_unwarping=False,
                use_textline_orientation=False,
            )
        result = list(
            _engine.predict(
                np.array(image)[:, :, ::-1],
                text_det_limit_side_len=2000,
                text_det_limit_type="max",
            )
        )[0].json
    import json

    if isinstance(result, str):
        result = json.loads(result)
    data = result.get("res", result)
    width, height = image.size
    texts, scores, boxes = data["rec_texts"], data["rec_scores"], data["rec_boxes"]
    if not len(texts) == len(scores) == len(boxes):
        raise HTTPException(500, "OCR 输出数组不一致")
    return {
        "width": width,
        "height": height,
        "lines": [
            {
                "text": text,
                "confidence": float(score),
                "bbox": [
                    float(box[0]) / width,
                    float(box[1]) / height,
                    float(box[2]) / width,
                    float(box[3]) / height,
                ],
            }
            for text, score, box in zip(texts, scores, boxes)
            if text.strip()
        ],
    }
