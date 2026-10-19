# 业务规则回归测试：针对捏造桩号、共享标注、重复连接和设备歧义构造反例。
# 多数测试先修改一小处教学数据，再检查字段是否降级、是否留下对应问题。
from copy import deepcopy

import pytest

from conduit.rules import validate_page
from conduit.schema import Observation, Record


# 缩短测试调用方式，统一把一页的观察和OCR送入正式校验函数。
def checked(page):
    return validate_page(page["observation"], page["ocr"], 1)


# 只改观察中的桩号，不改OCR；即使格式合法也必须降级为无法判断并记录无效引用。
def test_invented_station_is_removed(page):
    page["observation"]["wells"][0]["main_station"]["value"] = "K999+999"
    records, issues = checked(page)
    assert records[0]["主线桩号"] == "无法判断"
    assert any(x["code"] == "invalid_reference" for x in issues)


# 删除一口井的桩号引用，检查校验器不会拿相邻桩号插值补齐。
def test_no_station_interpolation(page):
    page["observation"]["wells"][0]["main_station"] = None
    records, _ = checked(page)
    assert records[0]["主线桩号"] == "无法判断"


# 两个同名标签组应各自从-1编号，而不是跨组连续编号到-4。
def test_names_numbering_restart_for_each_label_group(page):
    records, _ = checked(page)
    names = [x["管井名称"] for x in records]
    assert names.count("桥梁两端电力手孔-1") == 2
    assert "桥梁两端电力手孔-4" not in names


# 删除一个真实候选但保留×3文字，检查只报数量不符，不补造第七个符号。
def test_multiplicity_does_not_generate_unseen_wells(page):
    page["observation"]["wells"].pop(0)
    records, issues = checked(page)
    assert len(records) == 6
    assert any(x["code"] == "count_mismatch" for x in issues)


# 去掉局部分支后，沿主线连接前后两个邻井仍应为直通。
def test_two_mainline_neighbors_remain_straight(page):
    page["observation"]["edges"] = [x for x in page["observation"]["edges"] if x["source"] != "w7"]
    records, _ = checked(page)
    record = next(x for x in records if x["主线桩号"] == "K116+324")
    assert record["连通类型"] == "直通"


# 重复一条边并追加幽灵端点，检查它们都不能增加有效邻井数量。
def test_branch_requires_distinct_recorded_neighbors(page):
    page["observation"]["edges"] = [x for x in page["observation"]["edges"] if x["source"] != "w7"]
    edge = {"source": "w7", "target": "w1", "kind": "管线", "basis": "引线", "evidence": "明确支路"}
    page["observation"]["edges"] += [edge, deepcopy(edge), {**edge, "target": "ghost"}]
    _, issues = checked(page)
    assert any(x["code"] == "branch_recheck" for x in issues)
    assert any(x["code"] == "dangling_edge" for x in issues)


# 明确米数与端点说明时可输出距离；删掉尺寸依据后偏移必须降级。
def test_device_distance_requires_dimensions(page):
    records, _ = checked(page)
    assert records[0]["距中心线偏移量（米）"] == "3"
    assert records[0]["管井与设备间距（米）"] == "2"
    page["observation"]["wells"][0]["offset_evidence"] = ""
    records, _ = checked(page)
    assert records[0]["距中心线偏移量（米）"] == "无法判断"


# 把明确引线改成邻近关系，设备名应为疑似、连接状态未知，并禁止继承桩号。
def test_nearby_device_is_suspected_and_does_not_inherit_station(page):
    edge = next(x for x in page["observation"]["edges"] if x["target"] == "d1")
    edge["basis"] = "邻近"
    records, _ = checked(page)
    assert records[0]["设备名称"] == "疑似遥控摄像机"
    assert records[0]["是否连接设备"] == "无法判断"
    assert records[0]["设备主线桩号"] == "无法判断"


# 明确文本可以确认关联并继承井桩号，但因缺少明确连接线，设备名仍需疑似提示。
def test_text_link_can_inherit_but_is_suspected(page):
    records, _ = checked(page)
    r = next(x for x in records if x["主线桩号"] == "K116+382")
    assert r["设备名称"] == "疑似交通调查站"
    assert r["设备主线桩号"] == "K116+382"
    assert r["是否连接设备"] == "是"


# 让一个设备明确连接两口不同桩号的井，检查不会从集合中随意选一个值。
def test_shared_device_conflicting_well_stations_not_arbitrary(page):
    page["observation"]["edges"].append({"source": "w2", "target": "d1", "kind": "设备",
                                           "basis": "引线", "evidence": "第二个明确连接"})
    records, issues = checked(page)
    assert records[0]["设备主线桩号"] == "无法判断"
    assert any(x["code"] == "device_station_conflict" for x in issues)


# 补充设备自己的OCR桩号和对应依据，检查独立值优先于继承管井桩号。
def test_device_independent_station_has_priority(page):
    page["ocr"].append({"id": "ds", "text": "K118+001"})
    page["observation"]["devices"][0].update(station={"text_id": "ds", "value": "K118+001"}, station_evidence="设备独立引线")
    records, _ = checked(page)
    assert records[0]["设备主线桩号"] == "K118+001"


# 缺少方向不能猜测，非匝道的桩号保持空串，并确认每条记录始终有16个字符串字段。
def test_direction_and_missing_fields_not_guessed(page):
    records, _ = checked(page)
    assert all(x["方向"] == "无法判断" and x["匝道桩号"] == "" for x in records)
    assert all(len(x) == 16 and all(isinstance(v, str) for v in x.values()) for x in records)
    for r in records:
        Record.model_validate(r)


# 只有被标为匝道的井才输出未知匝道桩号；普通井该字段仍为空串。
def test_ramp_unknown_is_different_from_not_applicable(page):
    page["observation"]["wells"][0]["is_ramp"] = True
    records, _ = checked(page)
    assert records[0]["匝道桩号"] == "无法判断"
    assert records[1]["匝道桩号"] == ""


# 两口实际井共享一个专号时，都保留并提示复核，不因编号相同去重丢井。
def test_one_number_can_have_multiple_distinct_wells(page):
    page["ocr"].append({"id": "shared_number", "text": "专号1"})
    for w in page["observation"]["wells"][:2]:
        w.update(number={"text_id": "shared_number", "value": "专号1"}, number_relation="最近")
    records, _ = checked(page)
    assert len(records) == 7
    assert records[0]["管井编号"] == records[1]["管井编号"] == "专号1"
    assert all("该专号可能对应多个管井" in r["备注"] for r in records[:2])


# 让设备使用已存在的井id，检查Observation在进入规则前拒绝对象身份冲突。
def test_duplicate_object_ids_rejected(page):
    page["observation"]["devices"][0]["id"] = "w1"
    with pytest.raises(ValueError, match="ID 必须"):
        Observation.model_validate(page["observation"])


# 同一纯桩号名称在广义范围可由图例支持进入，严格关键词范围则排除。
def test_strict_scope_excludes_station_only_names(page):
    w = page["observation"]["wells"][0]
    w.update(name={"text_id": "station1", "value": "K116+266"}, legend_type="手孔", legend_evidence="图例匹配")
    broad, _ = validate_page(page["observation"], page["ocr"], 1)
    strict, _ = validate_page(page["observation"], page["ocr"], 1, strict_names=True)
    assert len(broad) == 7 and len(strict) == 6


# 把对象框换成像素坐标，检查模型直接拒绝，避免后续把像素数再次乘整页宽高。
def test_pixel_coordinates_cannot_be_mixed_with_normalized_boxes(page):
    page["observation"]["wells"][0]["bbox"] = [100, 200, 130, 230]
    with pytest.raises(ValueError, match="归一化"):
        Observation.model_validate(page["observation"])
