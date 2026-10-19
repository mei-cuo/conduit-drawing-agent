"""Deterministic evidence and topology checks over model candidates."""

import re

from .contracts import UNKNOWN, Candidate, Evidence, Extraction


def display_base(raw_name):
    return re.sub(r"(?:[×xX]\s*\d+|[一二三四五六七八九十两]+个?|\d+个)\s*$", "", raw_name).strip()


def validate(batch: Extraction, original_ocr: list[Evidence]) -> list[dict]:
    issues: list[dict] = []

    def issue(object_id: str, field: str, message: str, severity: str = "error"):
        issues.append(dict(object_id=object_id, field=field, message=message, severity=severity))

    source = {item.evidence_id: item for item in original_ocr}
    evidence = {item.evidence_id: item for item in batch.evidence}
    ids = {item.object_id for item in batch.records}
    if len(evidence) != len(batch.evidence):
        issue("page", "evidence", "证据 ID 重复")
    if len(ids) != len(batch.records):
        issue("page", "object_id", "管井内部 ID 重复")
    for eid, item in source.items():
        if eid not in evidence or evidence[eid] != item:
            issue("page", "evidence", f"原始 OCR 被遗漏或改写：{eid}")
    for item in batch.evidence:
        if item.kind == "ocr" and (
            item.evidence_id not in source or item != source[item.evidence_id]
        ):
            issue("page", "evidence", f"模型伪造或改写 OCR：{item.evidence_id}")
        if item.kind == "vision" and item.bbox is None:
            issue("page", "evidence", f"视觉观察缺少区域：{item.evidence_id}")

    # 文本性字段需要原文直接支持；此检查不证明引线归属正确。
    text_fields = {
        "页号",
        "所属路段",
        "管井编号",
        "方向",
        "距中心线偏移量（米）",
        "主线桩号",
        "匝道桩号",
        "设备主线桩号",
        "管井与设备间距（米）",
    }
    for item in batch.records:
        values = item.record.model_dump(by_alias=True)
        for field, refs in item.field_evidence.items():
            if field not in values:
                issue(item.object_id, field, "未知字段的证据引用")
            for ref in refs:
                if ref not in evidence:
                    issue(item.object_id, field, f"不存在的证据：{ref}")
        for field, value in values.items():
            if field == "备注" or value in ("", UNKNOWN):
                continue
            refs = [evidence[r] for r in item.field_evidence.get(field, []) if r in evidence]
            if not refs:
                issue(item.object_id, field, "具体值没有证据引用")
                continue
            if any(ref.page != item.page_id for ref in refs):
                issue(item.object_id, field, "引用了不同页面的证据")
            if field in text_fields:
                supported = any(value in ref.text for ref in refs if ref.kind == "ocr")
                if field in {"主线桩号", "匝道桩号", "设备主线桩号"}:
                    supported = all(
                        any(
                            part
                            in re.findall(
                                r"(?<![A-Za-z0-9])([A-Z]*K\d+\+\d{3}(?:\.\d+)?)(?![\d.])",
                                ref.text,
                            )
                            for ref in refs
                            if ref.kind == "ocr"
                        )
                        for part in value.split("；")
                    )
                if not supported:
                    issue(item.object_id, field, "当前页 OCR 不支持该具体值")
            if field in {"主线桩号", "匝道桩号"} and not re.fullmatch(
                r"[A-Z]*K\d+\+\d{3}(?:\.\d+)?", value
            ):
                issue(item.object_id, field, "桩号格式不符合通信图纸规则")
        name_refs = [evidence[r] for r in item.field_evidence.get("管井名称", []) if r in evidence]
        if not any(item.raw_name in ref.text for ref in name_refs if ref.kind == "ocr"):
            issue(item.object_id, "管井名称", "原始名称没有 OCR 原文支持")
        if not any(word in item.raw_name for word in ("人孔", "手孔", "接头管箱")):
            issue(item.object_id, "管井类型", "图例类型待核对", "warning")
        if set(item.neighbor_ids) - ids or item.object_id in item.neighbor_ids:
            issue(item.object_id, "连通类型", "邻居不存在或引用自身")
        if item.record.connection == "分歧" and (
            len(set(item.neighbor_ids)) < 2 or item.branch_visible is not True
        ):
            issue(item.object_id, "连通类型", "分歧缺少两个已记录邻居或支路观察")
        if item.record.main_station == UNKNOWN:
            issue(item.object_id, "主线桩号", "关键桩号无法确定", "warning")
        equipment_fields = [
            item.record.equipment_name,
            item.record.equipment_station,
            item.record.equipment_distance,
        ]
        if item.record.connected_equipment == "否" and any(
            value != "" for value in equipment_fields
        ):
            issue(
                item.object_id,
                "是否连接设备",
                "已确定不连接设备时，设备字段应填不适用的空字符串",
            )
        if item.record.connected_equipment == UNKNOWN and any(
            value == "" for value in equipment_fields
        ):
            issue(
                item.object_id,
                "是否连接设备",
                "连接关系未知时，不能把设备字段填写为空来表示确定不适用",
            )
        if item.record.position == "匝道" and item.record.ramp_station == "":
            issue(item.object_id, "匝道桩号", "已位于匝道，桩号未知时不能填不适用")
        if item.bbox[2] < item.bbox[0] or item.bbox[3] < item.bbox[1]:
            issue(item.object_id, "bbox", "边界框坐标顺序错误")
    for item in batch.records:
        links = item.device_links
        if item.record.connected_equipment == "是" and not links:
            issue(item.object_id, "是否连接设备", "关联设备需要 DeviceRelation 证据")
        if item.record.connected_equipment == "否" and links:
            issue(item.object_id, "是否连接设备", "无关联设备与 device_links 冲突")
        if links:
            if item.record.equipment_name != "；".join(d.name for d in links):
                issue(item.object_id, "设备名称", "设备名称顺序与关联对象不一致")
            if item.record.equipment_station != "；".join(d.station for d in links):
                issue(item.object_id, "设备主线桩号", "设备桩号顺序与关联对象不一致")
            if item.record.equipment_distance != "；".join(d.distance for d in links):
                issue(
                    item.object_id,
                    "管井与设备间距（米）",
                    "设备距离顺序与关联对象不一致",
                )
        for device in links:
            refs = [evidence[x] for x in device.evidence_ids if x in evidence]
            if len(refs) != len(device.evidence_ids) or any(e.page != item.page_id for e in refs):
                issue(item.object_id, "设备名称", "设备引用不存在或不在同页")
            if not any(device.name in e.text for e in refs if e.kind == "ocr"):
                issue(item.object_id, "设备名称", "设备名称缺少 OCR 原文")
            if device.relation == "proximity":
                issue(item.object_id, "是否连接设备", "空间邻近关联待复核", "warning")
            elif not any(e.kind == "vision" for e in refs):
                issue(item.object_id, "是否连接设备", "关联缺少引线或局部布局观察")
        if item.record.offset not in (UNKNOWN, "") and not re.fullmatch(
            r"\d+(?:\.\d+)?", item.record.offset
        ):
            issue(item.object_id, "距中心线偏移量（米）", "米字段应为非负数值字符串")
    groups: dict[tuple[str, str], list[Candidate]] = {}
    for item in batch.records:
        groups.setdefault((item.page_id, item.group_id), []).append(item)
    for members in groups.values():
        if len({item.raw_name for item in members}) != 1:
            issue("page", "管井名称", "同一个标注组使用了不同原名")
        for index, item in enumerate(sorted(members, key=lambda row: row.bbox[0]), start=1):
            expected = (
                f"{display_base(item.raw_name)}-{index}" if len(members) > 1 else item.raw_name
            )
            if item.record.name != expected:
                issue(item.object_id, "管井名称", f"显示名称应为：{expected}")
    if not batch.records:
        issue("page", "records", "空结果需人工确认不是漏识别", "warning")
    return issues


def validate_task(batch, original_ocr, pages):
    issues = validate(batch, original_ocr)
    by_page = {p["page_id"]: p for p in pages}
    for item in [*batch.records, *batch.evidence]:
        pid = item.page_id if hasattr(item, "page_id") else item.page
        page = by_page.get(pid)
        if page is None or (
            item.bbox and (item.bbox[2] > page["width"] or item.bbox[3] > page["height"])
        ):
            issues.append(
                {
                    "object_id": getattr(item, "object_id", "page"),
                    "field": "bbox",
                    "message": "对象或证据区域超出任务页面",
                    "severity": "error",
                }
            )
    return issues
