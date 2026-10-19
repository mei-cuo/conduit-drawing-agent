# 输入输出层：图片/PDF 转页、局部切片、OCR 适配及 JSON 保存。
# 各 OCR 后端统一返回 OCRLine 字典：id、text、bbox、confidence。
# bbox=(左,上,右,下)，以整页宽高归一化到0~1；它不是米，也不是局部切片坐标。
import base64
import hashlib
import json
from pathlib import Path

from PIL import Image, ImageOps

from .schema import OCRLine


# 读取 JSON；utf-8-sig 同时兼容普通 UTF-8 和 Windows 工具写入的 UTF-8 BOM。
def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


# 创建父目录，先写同目录临时文件，再 replace 到目标文件。
# 降低单次写入中断留下半个 JSON 的风险；并发写同一目标仍应由调用方避免。
def save_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


# 把已标准化的 PNG 文件编码成 data URL，让模型接收到图像内容，而不是本地路径字符串。
def image_data(path):
    return "data:image/png;base64," + base64.b64encode(Path(path).read_bytes()).decode("ascii")


# 把单页图片或多页 PDF 转成统一的页面字典列表。
# 真实页包含整页 PNG、视觉视图、尺寸、页序号和源摘要；mock 页只载入教学数据。
def prepare_pages(settings):
    if settings["mock"]:
        # 教学分支不打开图片、不渲染PDF；后续从 mock_data 读取预设OCR和观察。
        scene = load_json(settings["fixture"])
        return [{"index": i + 1, "image": "", "views": [], "width": 1, "height": 1,
                 "mock_data": page} for i, page in enumerate(scene["pages"])]
    source = Path(settings["input"]).resolve()
    if not source.is_file():
        raise FileNotFoundError(f"图纸不存在：{source}")
    # 使用源文件SHA-256前16位分隔页缓存，并将该标记随外部智能体请求传递。
    digest = hashlib.sha256(source.read_bytes()).hexdigest()[:16]
    cache = Path(settings["out"]) / "pages" / digest
    cache.mkdir(parents=True, exist_ok=True)
    pages = []

    # 保存单页并生成两种视图：缩小整页帮助理解版式，重叠切片帮助查看细字和线条。
    # 切片 bbox 始终表示它在原始整页中的区域，后续对象坐标也按整页解释。
    def store(image, index):
        # 先按EXIF方向纠正再保存为RGB PNG，保证OCR、视图和对象坐标基于同一页图。
        image = ImageOps.exif_transpose(image).convert("RGB")
        width, height = image.size
        if width * height > 60_000_000:
            raise ValueError("图纸超过 6000 万像素，请降低 PDF DPI 或拆页")
        full = cache / f"page-{index:04d}.png"
        image.save(full)
        overview = image.copy()
        # 总览只缩小副本，完整PNG仍保持原尺寸，供OCR和证据回看使用。
        overview.thumbnail((3200, 3200))
        overview_path = cache / f"page-{index:04d}-overview.png"
        overview.save(overview_path)
        views = [{"path": str(overview_path.resolve()), "bbox": [0, 0, 1, 1], "purpose": "整页上下文"}]
        # 相邻切片重叠240像素，减轻符号或引线恰好落在切片边缘时的信息断裂。
        tile, step = settings.get("tile_size", 1600), settings.get("tile_size", 1600) - 240
        if step <= 0:
            raise ValueError("tile_size 必须大于 240")
        if max(width, height) > tile:
            xs = list(range(0, max(1, width - tile + 1), step))
            ys = list(range(0, max(1, height - tile + 1), step))
            # 显式补上最右/最下起点，避免整页尺寸不能被步长整除时漏掉边缘。
            xs = sorted(set(xs + [max(0, width - tile)]))
            ys = sorted(set(ys + [max(0, height - tile)]))
            # 超过上限就报错，不能悄悄少切几块后仍让模型以为看到了全图。
            if len(xs) * len(ys) > settings.get("max_tiles", 32):
                raise ValueError("切片数量超过限制，未截断图纸；请降低 DPI 或增大 tile_size")
            for y in ys:
                for x in xs:
                    right, bottom = min(width, x + tile), min(height, y + tile)
                    path = cache / f"page-{index:04d}-tile-{x}-{y}.png"
                    image.crop((x, y, right, bottom)).save(path)
                    views.append({"path": str(path.resolve()), "bbox": [x / width, y / height, right / width, bottom / height], "purpose": "原分辨率局部"})
        pages.append(dict(index=index, image=str(full.resolve()), views=views, width=width,
                          height=height, source_sha256=digest))

    # PDF按1开始编号逐页处理；印刷页号另外从OCR读取，不能直接用文件页序代替。
    if source.suffix.lower() == ".pdf":
        import pymupdf
        with pymupdf.open(source) as doc:
            if doc.needs_pass:
                raise ValueError("PDF 已加密，请先提供已解密的图纸")
            for i, page in enumerate(doc, 1):
                # PDF坐标单位为1/72英寸，因此以 dpi/72 设置渲染缩放。
                scale = settings.get("dpi", 200) / 72
                if page.rect.width * page.rect.height * scale * scale > 60_000_000:
                    raise ValueError("PDF 页面渲染后过大，请降低 DPI")
                pixmap = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False)
                store(Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples), i)
    else:
        with Image.open(source) as image:
            # 拒绝只读多帧图片第一帧造成漏页，要求先明确拆页或转换PDF。
            if getattr(image, "n_frames", 1) != 1:
                raise ValueError("多帧图片请先拆成单页图片或 PDF")
            store(image, 1)
    return pages


# 将 PaddleOCR 的文本、分数和像素框统一为 OCRLine 字典列表。
# 若没有矩形框，就取多边形的外接矩形；宽高必须属于同一张输入图片。
def paddle_lines(result, width, height):
    """Normalize PaddleOCR 3.x Result.json/res or serving prunedResult."""
    if isinstance(result, str):
        result = json.loads(result)
    result = result.get("res", result)
    texts, scores, boxes = result["rec_texts"], result["rec_scores"], result.get("rec_boxes")
    # 兼容只有文字多边形坐标的结果，用外接矩形统一为四个边界值。
    if boxes is None:
        boxes = []
        for poly in result["rec_polys"]:
            xs, ys = [p[0] for p in poly], [p[1] for p in poly]
            boxes.append([min(xs), min(ys), max(xs), max(ys)])
    if not (len(texts) == len(scores) == len(boxes)):
        raise ValueError("PaddleOCR 文本、分数、坐标数量不一致")
    return [OCRLine(id=f"t{i:04d}", text=t, confidence=float(s),
                    bbox=(float(b[0]) / width, float(b[1]) / height,
                          float(b[2]) / width, float(b[3]) / height)).model_dump()
            for i, (t, s, b) in enumerate(zip(texts, scores, boxes), 1) if t.strip()]


# 可替换的 OCR 适配器，对上层统一提供 read(page, settings)。
# 主环境通常选择 HTTP 模式，直接 Paddle 模式只适用于已安装推理依赖的环境。
class OCRProvider:
    # 延迟创建直接推理用的 PaddleOCR 对象，避免不使用该模式时导入重依赖。
    def __init__(self):
        self.paddle = None

    # 按配置选择教学、旁路 JSON、直接 Paddle、HTTP Paddle 或 Tesseract。
    # 各分支最后统一检查模型字段、页内 id 唯一性及空结果，再返回行列表。
    def read(self, page, settings):
        import os
        if settings["mock"]:
            lines = page["mock_data"]["ocr"]
        # 复用已有实际OCR时必须按页号和页面尺寸配对，避免把坐标贴到另一页。
        elif settings["ocr"] == "sidecar":
            data = load_json(settings["ocr_json"])
            entry = next((p for p in data["pages"] if p["page_index"] == page["index"]), None)
            if not entry:
                raise ValueError(f"OCR 旁路文件缺少第 {page['index']} 页")
            if (entry["width"], entry["height"]) != (page["width"], page["height"]):
                raise ValueError("OCR 旁路坐标尺寸与渲染页面不一致")
            lines = entry["lines"]
        # 直接推理需要本进程的环境安装PaddleOCR；主环境一般改用独立HTTP服务。
        elif settings["ocr"] == "paddle":
            try:
                from paddleocr import PaddleOCR
            except ImportError as exc:
                raise RuntimeError("未安装 PaddleOCR；使用兼容的独立 OCR 环境或 --ocr paddle-http") from exc
            if self.paddle is None:
                self.paddle = PaddleOCR(use_doc_orientation_classify=False, use_doc_unwarping=False,
                                        use_textline_orientation=False)
            predictions = list(self.paddle.predict(page["image"]))
            if len(predictions) != 1:
                raise ValueError("单页 OCR 应返回一个结果")
            lines = paddle_lines(predictions[0].json, page["width"], page["height"])
        # 通过HTTP隔离Python/推理依赖；请求发送纯Base64，响应须符合本项目适配器契约。
        elif settings["ocr"] == "paddle-http":
            import httpx
            endpoint = os.environ.get("OCR_ENDPOINT")
            if not endpoint:
                raise ValueError("请配置 OCR_ENDPOINT，如 http://127.0.0.1:8008/ocr")
            headers = {}
            if os.environ.get("OCR_API_KEY"):
                headers["Authorization"] = "Bearer " + os.environ["OCR_API_KEY"]
            with httpx.Client(timeout=180) as client:
                response = client.post(endpoint, headers=headers,
                                       json={"image_base64": base64.b64encode(Path(page["image"]).read_bytes()).decode("ascii")})
                response.raise_for_status()
                lines = response.json()["lines"]
        # 可选后端：Tesseract需单独安装程序和语言包，此处把词框也统一为OCRLine。
        elif settings["ocr"] == "tesseract":
            import pytesseract
            if os.environ.get("TESSERACT_CMD"):
                pytesseract.pytesseract.tesseract_cmd = os.environ["TESSERACT_CMD"]
            with Image.open(page["image"]) as image:
                data = pytesseract.image_to_data(image, lang=os.getenv("OCR_LANG", "chi_sim+eng"),
                                                output_type=pytesseract.Output.DICT)
            lines = []
            for i, text in enumerate(data["text"]):
                if not text.strip() or float(data["conf"][i]) < 0:
                    continue
                x, y = data["left"][i], data["top"][i]
                lines.append(dict(id=f"t{i:04d}", text=text, confidence=float(data["conf"][i]) / 100,
                                  bbox=[x / page["width"], y / page["height"],
                                        (x + data["width"][i]) / page["width"], (y + data["height"][i]) / page["height"]]))
        else:
            raise ValueError("未知 OCR 模式")
        # 所有后端走同一个出口验证，不能因为来自本机服务就跳过基本数据检查。
        validated = [OCRLine.model_validate(x).model_dump() for x in lines]
        if len({x["id"] for x in validated}) != len(validated):
            raise ValueError("OCR 行 ID 必须页内唯一")
        if not validated:
            raise ValueError(f"第 {page['index']} 页没有 OCR 文本，请检查识别器/图像质量")
        return validated
