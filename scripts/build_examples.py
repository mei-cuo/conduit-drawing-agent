"""Build synthetic fixtures and a manually transcribed reference fixture.

Neither is the output of PaddleOCR or Doubao. Both deliberately exercise workflow plumbing.
"""
# 生成两种教学数据：完全合成的 demo，以及人工转录的暂定参考样例。
# 这些数据用于调试流程，不能称作 PaddleOCR/豆包的真实输出或准确率标准答案。
# 直接运行会重写 demo_scene、reference_scene、reference_ocr_manual，日常识别不需要执行。
from pathlib import Path

from conduit.io import save_json
from conduit.schema import Device, Edge, Observation, OCRLine, Ref, Well

ROOT = Path(__file__).resolve().parents[1]


# 创建可回溯文字的 Ref，教学数据中的值也必须引用对应 OCR 行。
def ref(tid, value):
    return Ref(text_id=tid, value=value)


# 构造7个教学管井，覆盖两组同名标注、主线、局部分歧及两类设备关系。
# 数量和坐标均为合成，用来让规则及修复流程具有可重复的输入。
def build_demo():
    texts = [
        ("page", "第6页 共87页"), ("road", "示例高速公路通信管道施工图"),
        ("group_a", "桥梁两端电力手孔×3"), ("group_b", "桥梁两端电力手孔×3"),
        ("station1", "K116+266"), ("station2", "K116+324"), ("station3", "K116+382"),
        ("station4", "K117+266"), ("station5", "K117+324"), ("station6", "K117+382"),
        ("branch", "中央分歧1#人孔"), ("branch_station", "K116+300"),
        ("camera", "遥控摄像机"), ("offset", "距中心线 3m"), ("device_distance", "井与摄像机 2m"),
        ("survey", "交通调查站"), ("survey_link", "桥梁两端电力手孔接交通调查站"),
    ]
    ocr = [OCRLine(id=tid, text=text).model_dump() for tid, text in texts]
    wells = []
    for i in range(1, 7):
        # 两组三口井的标签文字相同、组id不同，用于验证名称编号必须按组重新开始。
        group = "a" if i <= 3 else "b"
        station = dict(texts)[f"station{i}"]
        wells.append(Well(id=f"w{i}", name=ref(f"group_{group}", "桥梁两端电力手孔×3"),
                          group_id=group, bbox=(i / 10, .3, i / 10 + .02, .32),
                          symbol_evidence=f"实际第{i}个正方形符号及引线", shape="正方形",
                          main_station=ref(f"station{i}", station),
                          station_evidence=f"矩形框内第{i}个符号与对应桩号引线", connections_complete=True))
    wells.append(Well(id="w7", name=ref("branch", "中央分歧1#人孔"), group_id="branch",
                      bbox=(.35, .4, .37, .42), symbol_evidence="圆形支路节点", shape="圆形",
                      main_station=ref("branch_station", "K116+300"), station_evidence="节点独立桩号引线",
                      connections_complete=True))
    wells[0].offset_m = ref("offset", "3m")
    wells[0].offset_evidence = "尺寸线明确从道路中心线到 w1 中心"
    devices = [Device(id="d1", name=ref("camera", "遥控摄像机")),
               Device(id="d2", name=ref("survey", "交通调查站"))]
    edges = [Edge(source=f"w{i}", target=f"w{i+1}", kind="管线", basis="引线",
                  evidence="沿主线可追踪的连续管线", along_mainline=True) for i in range(1, 6)]
    # w7的两条局部支路与主线贯通边分开，测试分歧判断是否使用独立邻井。
    edges += [Edge(source="w7", target=wid, kind="管线", basis="引线", evidence="局部支路连接") for wid in ("w1", "w2")]
    edges += [Edge(source="w1", target="d1", kind="设备", basis="引线", evidence="井到摄像机明确连线",
                   distance_m=ref("device_distance", "2m"), distance_evidence="尺寸线两端为井与摄像机"),
              Edge(source="w3", target="d2", kind="设备", basis="文本", evidence="局部标注明确描述连接",
                   text_ref=ref("survey_link", "桥梁两端电力手孔接交通调查站"))]
    obs = Observation(page_number=ref("page", "第6页 共87页"), road_title=ref("road", texts[1][1]),
                      title_source="标题栏", wells=wells, devices=devices, edges=edges)
    save_json(ROOT / "data/examples/demo_scene.json", {"provenance": "synthetic_fixture_not_real_recognition",
              "pages": [{"ocr": ocr, "observation": obs.model_dump()}]})


# 把参考图中34#~45#的人工阅读整理成教学对象，保留位置词与井类型歧义。
# 它与实际 PaddleOCR/子智能体数据是不同文件，不能互相冒充识别结果。
def build_reference():
    # Manually read from the supplied image. This fixture is provisional, not a gold dataset.
    stations = ["K9+043", "K9+163", "K9+285", "K9+315", "K9+395", "K9+475",
                "K9+525", "K9+635", "K9+745", "K9+775", "K9+850", "K9+966"]
    kinds = ["直通手孔", "直通手孔", "中墩两侧", "中墩两侧", "分歧人孔", "开口两侧",
             "开口两侧", "直通手孔", "中墩两侧", "中墩两侧", "直通手孔", "直通手孔"]
    xs = [.237, .32, .403, .425, .48, .535, .57, .646, .721, .743, .798, .875]
    ocr = [OCRLine(id="page", text="17", bbox=(.914, .066, .93, .085)),
           OCRLine(id="road", text="广州至珠海（西线）高速公路海南至碧江段", bbox=(.2, .93, .37, .96), confidence=.85)]
    wells = []
    for number, station, kind, x in zip(range(34, 46), stations, kinds, xs):
        ocr += [OCRLine(id=f"n{number}", text=f"{number}#", bbox=(x-.015, .635, x+.015, .655)),
                OCRLine(id=f"s{number}", text=station, bbox=(x-.02, .664, x+.02, .686)),
                OCRLine(id=f"k{number}", text=kind, bbox=(x-.025, .692, x+.025, .712))]
        # 表格中的中墩两侧/开口两侧是位置描述，不能直接改写成一个确定的井类型名称。
        has_name = "手孔" in kind or "人孔" in kind
        name = ref(f"k{number}", kind) if has_name else ref(f"s{number}", station)
        notes = ["人工转录样例，未执行 PaddleOCR/豆包；仅用于工作流回放"]
        if not has_name:
            notes += [f"表格原文为{kind}，采用桩号名；图例人（手）孔符号类型需人工复核"]
        wells.append(Well(id=f"w{number}", name=name, group_id=f"column-{number}",
                          bbox=(x-.005, .299, x+.005, .307), symbol_evidence=f"上部道路 {number}# 小圆形及通向表格列的虚线",
                          shape="圆形", legend_type="人孔" if not has_name else "无法判断",
                          legend_evidence="左下图例人（手）孔圆形；类型存在歧义需复核" if not has_name else "",
                          number=ref(f"n{number}", f"{number}#"), number_relation="明确",
                          main_station=ref(f"s{number}", station), station_evidence=f"底部表格 {number}# 列中心桩号行，虚线对应上方符号",
                          connections_complete=number != 38, visual_position="路中", position_evidence="上部道路中央管线",
                          notes=notes))
    edges = [Edge(source=f"w{i}", target=f"w{i+1}", kind="管线", basis="引线", evidence="人工阅读上部连续主干管道", along_mainline=True)
             for i in range(34, 45)]
    obs = Observation(page_number=ref("page", "17"), road_title=ref("road", ocr[1].text),
                      title_source="标题栏", wells=wells, edges=edges,
                      notes=["38# 处竖向结构及紧急电话平台的关联未确证，需人工复核"])
    save_json(ROOT / "data/examples/reference_scene.json", {"provenance": "manual_transcription_provisional_not_model_output",
              "pages": [{"drawing_style": "表格对应型", "table_mapping": ["34#～45# 列编号通过虚线与上部符号对应"],
                         "ocr": [x.model_dump() for x in ocr], "observation": obs.model_dump()}]})
    save_json(ROOT / "data/examples/reference_ocr_manual.json", {"provenance": "manual_transcription_not_paddleocr",
              "pages": [{"page_index": 1, "width": 1987, "height": 1406,
                         "lines": [x.model_dump() for x in ocr]}]})


if __name__ == "__main__":
    build_demo()
    build_reference()
