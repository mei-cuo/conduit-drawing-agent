# 验证坐标归一化、真实参考图切片，以及多页 PDF 的页处理；不进行真实模型识别。
from conduit.paths import PROJECT_ROOT
from pathlib import Path
from conduit.io import paddle_lines, prepare_pages


# 用100×100像素的简例检查框除以宽高、置信度保持不变。
def test_paddle_3x_result_coordinates():
    lines = paddle_lines({"res": {"rec_texts": ["手孔"], "rec_scores": [.92], "rec_boxes": [[10, 20, 30, 40]]}}, 100, 100)
    assert lines[0]["bbox"] == (.1, .2, .3, .4)
    assert lines[0]["confidence"] == .92



# 对真实尺寸的参考PNG进行输入准备，检查整页与局部文件确实生成，未调用识别模型。
def test_real_reference_preprocessing_has_full_page_and_tiles(tmp_path):
    source = PROJECT_ROOT / "data/examples/reference_drawing.png"
    pages = prepare_pages({"mock": False, "input": str(source), "out": str(tmp_path), "tile_size": 1600})
    assert (pages[0]["width"], pages[0]["height"]) == (1987, 1406)
    assert len(pages[0]["views"]) >= 3
    assert all(Path(v["path"]).exists() for v in pages[0]["views"])



# 创建两页临时PDF，检查两页都被处理且按1、2编号，而不是只读取第一页。
def test_multi_page_pdf_prepare(tmp_path):
    import pymupdf
    file = tmp_path / "two.pdf"
    with pymupdf.open() as document:
        for _ in range(2):
            document.new_page(width=100, height=80)
        document.save(file)
    pages = prepare_pages({"mock": False, "input": str(file), "out": str(tmp_path / "render"), "dpi": 72})
    assert [p["index"] for p in pages] == [1, 2]

