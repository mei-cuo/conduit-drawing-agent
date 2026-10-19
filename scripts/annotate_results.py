"""Render exported well locations for visual review, not another recognition step."""
# 将 evidence.json 中模型观察到的管井框画到原图，方便人工定位核对。
# 画框取自 observation.wells，可能包含最终校验未导出的候选；框的位置本身不证明识别正确。
# 本工具不改写业务结果，不执行第二次识别。
import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from conduit.io import load_json


# 逐页读取 observation 中的 bbox，乘整页宽高转回像素，再画框和对象 id。
# 输出单独的 PNG 供复核，保留证据 JSON 和原始图片。
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    pages = load_json(args.evidence)
    for page in pages:
        with Image.open(page["image"]) as original:
            image = original.convert("RGB")
        drawing = ImageDraw.Draw(image)
        # 这里只写内部对象id（如w34），使用Windows现有Arial字体；正文中文不在此图中排版。
        font = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 20)
        for well in page["observation"]["wells"]:
            box = well["bbox"]
            # 归一化坐标乘宽高得到像素；外扩4像素仅为了框更醒目，不改变原观察bbox。
            x0, y0, x1, y1 = box[0] * image.width, box[1] * image.height, box[2] * image.width, box[3] * image.height
            drawing.rectangle((x0 - 4, y0 - 4, x1 + 4, y1 + 4), outline="#d1242f", width=3)
            drawing.text((x0, y0 - 28), well["id"], fill="#d1242f", font=font)
        output = Path(args.out)
        output.mkdir(parents=True, exist_ok=True)
        image.save(output / f"page-{page['page_index']:04d}-wells.png")


if __name__ == "__main__":
    main()
