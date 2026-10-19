"""Raster/PDF pages, image tiles, and canonical OCR evidence in page pixels."""

from __future__ import annotations

import base64
import io
import os
from pathlib import Path

import httpx
from PIL import Image, ImageOps

from .contracts import Evidence
from .storage import digest, read_json


def prepare(source: Path, target: Path, max_pages=12):
    target.mkdir(parents=True, exist_ok=True)
    pages = []
    if source.suffix.lower() == ".pdf":
        import fitz

        with fitz.open(source) as pdf:
            if len(pdf) > max_pages:
                raise ValueError(f"一次任务最多 {max_pages} 页")
            for i, page in enumerate(pdf):
                pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
                image = Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB")
                pages.append(save_page(image, target, i + 1))
    else:
        with Image.open(source) as original:
            image = ImageOps.exif_transpose(original).convert("RGB")
            pages.append(save_page(image, target, 1))
    return pages


def save_page(image, target, index):
    path = target / f"page-{index:04}.png"
    image.save(path)
    width, height = image.size
    tiles = []
    # Keep a global overview plus up to six overlapping original-resolution tiles.
    if max(width, height) > 1600:
        for y in range(0, height, 1280):
            for x in range(0, width, 1280):
                if len(tiles) >= 6:
                    break
                box = [x, y, min(x + 1600, width), min(y + 1600, height)]
                tile = target / f"page-{index:04}-{x}-{y}.png"
                image.crop(box).save(tile)
                tiles.append({"path": str(tile.resolve()), "bbox": box})
    return {
        "page_id": f"p{index}",
        "index": index,
        "path": str(path.resolve()),
        "width": width,
        "height": height,
        "sha256": digest(path.read_bytes()),
        "tiles": tiles,
    }


def checked_region(page, box):
    if len(box) != 4 or any(type(v) is not int for v in box):
        raise ValueError("局部区域必须为四个整数像素坐标")
    left, top, right, bottom = box
    if not (0 <= left < right <= page["width"] and 0 <= top < bottom <= page["height"]):
        raise ValueError("局部 OCR 区域超出当前页")
    return box


def call_ocr(page, box=None):
    box = checked_region(page, box or [0, 0, page["width"], page["height"]])
    with Image.open(page["path"]) as image:
        crop = image.crop(tuple(box))
        buffer = io.BytesIO()
        crop.save(buffer, format="PNG")
    headers = {}
    if os.getenv("OCR_API_KEY"):
        headers["Authorization"] = "Bearer " + os.environ["OCR_API_KEY"]
    response = httpx.post(
        os.getenv("OCR_ENDPOINT", "http://127.0.0.1:8008/ocr"),
        json={"image_base64": base64.b64encode(buffer.getvalue()).decode()},
        headers=headers,
        timeout=180,
    )
    response.raise_for_status()
    data = response.json()
    width, height = box[2] - box[0], box[3] - box[1]
    if data["width"] != width or data["height"] != height:
        raise ValueError("OCR 服务返回的图像尺寸与请求不一致")
    region_id = "-".join(map(str, box))
    output = []
    for i, line in enumerate(data["lines"]):
        x1, y1, x2, y2 = line["bbox"]
        if not 0 <= x1 < x2 <= 1 or not 0 <= y1 < y2 <= 1:
            raise ValueError("OCR 服务 bbox 需要归一化到 [0,1]")
        output.append(
            Evidence(
                evidence_id=f"{page['page_id']}-ocr-{region_id}-{i}",
                kind="ocr",
                page=page["page_id"],
                text=line["text"],
                bbox=[
                    box[0] + x1 * width,
                    box[1] + y1 * height,
                    box[0] + x2 * width,
                    box[1] + y2 * height,
                ],
            ).model_dump()
        )
    return output


def sidecar(path, pages):
    data = read_json(path)
    if "pages" not in data:
        if len(pages) != 1:
            raise ValueError("多页输入需要 pages 结构 OCR sidecar")
        items = data["evidence"]
    else:
        by_id = {p["page_id"]: p for p in pages}
        if {p["page_id"] for p in data["pages"]} != set(by_id):
            raise ValueError("OCR 页与输入页不一致")
        items = []
        for entry in data["pages"]:
            page = by_id[entry["page_id"]]
            if entry.get("sha256") and entry["sha256"] != page["sha256"]:
                raise ValueError("OCR sidecar 图像摘要不匹配")
            items.extend(entry["evidence"])
    evidence = [Evidence.model_validate(e) for e in items]
    if len({e.evidence_id for e in evidence}) != len(evidence):
        raise ValueError("OCR 证据 ID 重复")
    lookup = {p["page_id"]: p for p in pages}
    for e in evidence:
        if e.kind != "ocr" or e.page not in lookup or e.bbox is None:
            raise ValueError("OCR sidecar 需要合法页、OCR 类型和区域")
        p = lookup[e.page]
        if e.bbox[2] > p["width"] or e.bbox[3] > p["height"]:
            raise ValueError("OCR 坐标超出输入页")
    return [e.model_dump() for e in evidence]
