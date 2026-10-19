# 把已保存的 PaddleOCR 原始 JSON 转成工作流可读的 sidecar JSON。
# 需要同时提供原图尺寸，才能把像素坐标归一化；不会重新运行 OCR 或视觉模型。
import argparse
from pathlib import Path

from PIL import Image

from conduit.io import load_json, paddle_lines, save_json


# 读取 --raw 和 --image，复用正式 paddle_lines 转换逻辑，保存单页 sidecar 文件到 --out。
def main():
    p = argparse.ArgumentParser()
    p.add_argument("--raw", required=True)
    p.add_argument("--image", required=True)
    p.add_argument("--out", required=True)
    args = p.parse_args()
    with Image.open(args.image) as image:
        width, height = image.size
    lines = paddle_lines(load_json(args.raw), width, height)
    save_json(args.out, {"provenance": "actual_paddleocr_inference", "input": str(Path(args.image).resolve()),
                         "pages": [{"page_index": 1, "width": width, "height": height, "lines": lines}]})
    print(f"已转换 {len(lines)} 行实际 OCR")


if __name__ == "__main__":
    main()
