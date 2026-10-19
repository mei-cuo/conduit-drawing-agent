"""Deterministic guards shared by both orchestration frameworks."""
# 确定性业务校验：将 Observation + 本页 OCR 转成最终记录及问题列表。
# 处理顺序：验文字引用 → 选候选井 → 名称分组 → 检查连接 → 合成16字段。
# 不调用模型、不按像素估算米数、不按邻井插值桩号；缺证据的字段保守输出无法判断。
# 是否需要重新识别或人工复核，由 workflow.py 根据本模块的 issues 决定。
import re
from collections import Counter, defaultdict

from .schema import UNKNOWN, Observation, OCRLine, Record, Ref

# 桩号允许可选字母前缀、公里数、加号及1~3位米数（可含小数）；完整值用fullmatch检查。
STATION = re.compile(r"(?<![A-Za-z0-9])[A-Z]*K\d+\+\d{1,3}(?:\.\d+)?(?![\d.])")
# 数量后缀只用于同标注多符号组的导出名称；正则本身不会创建新的管井。
MULTIPLIER = re.compile(r"(?:[×xX]\s*\d+|[二两三四五六七八九十\d]+\s*个)\s*$")
NUMBER = re.compile(r"(?:\d+#|#\d+)")


# 输入是一页 Observation 字典及独立 OCR 行，返回(records, issues)。
# records 为16字段中文字典列表；issues 带页号、井id、问题码、说明和可修复标记。
# 该函数能发现无来源值和规则冲突，不能证明模型描述的图像关联一定正确。
def validate_page(observation: dict, ocr: list[dict], page_index: int, strict_names=False):
    # 先执行结构检查，再建立OCR索引；同页重复文字id会破坏Ref的唯一含义。
    obs = Observation.model_validate(observation)
    lines_list = [OCRLine.model_validate(x) for x in ocr]
    if len({x.id for x in lines_list}) != len(lines_list):
        raise ValueError("OCR 行 ID 重复")
    lines = {x.id: x for x in lines_list}
    issues: list[dict] = []
    # 同一问题既进入统一审计列表，也可按井汇集到最终备注。
    per_well: dict[str, list[str]] = defaultdict(list)

    # 统一登记问题；有 well_id 时同步加入该井备注。
    # repair=True 仅表示可以尝试再次提取，不表示重试一定能得到新证据。
    def issue(code, message, well_id="", repair=False):
        issues.append(dict(page_index=page_index, well_id=well_id, code=code,
                           message=message, repairable=repair))
        if well_id:
            per_well[well_id].append(message)

    # 通过 Ref 找到本页原文，并检查提取值确实是原文子串。
    # 低 OCR 置信度时普通字段降级；名称保留完整原文并加疑似，便于人工辨认。
    def read(ref: Ref | None, field: str, wid=""):
        if ref is None:
            return UNKNOWN
        line = lines.get(ref.text_id)
        if not line or not ref.value or ref.value not in line.text:
            issue("invalid_reference", f"{field}缺少匹配的 OCR 文字证据，需人工复核", wid, True)
            return UNKNOWN
        if line.confidence < .65:
            issue("low_ocr_confidence", f"{field}文字识别不清，需人工复核", wid)
            return UNKNOWN if field != "管井名称" else "疑似" + line.text
        # A name always preserves the entire original label.
        return line.text if field == "管井名称" else ref.value

    # 桩号必须同时通过文字引用、完整格式匹配和关联说明检查。
    # 不会从前后井推算缺失值；格式合法也不等于视觉对应关系已被独立证实。
    def station(ref, evidence, field, wid=""):
        value = read(ref, field, wid)
        if value == UNKNOWN:
            return UNKNOWN
        if not evidence or not STATION.fullmatch(value):
            issue("station_evidence", f"{field}没有明确桩号及引线对应证据，需人工复核", wid, True)
            return UNKNOWN
        return value

    # 只接受明确数值和米/毫米单位，并要求说明尺寸对应的两个端点。
    # 毫米除以1000，返回以米为单位的字符串；不从 bbox 或线段像素长度换算。
    def distance(ref, evidence, field, wid=""):
        value = read(ref, field, wid)
        if value == UNKNOWN:
            return UNKNOWN
        # Explicit unit is required. Pixel distances never enter this function.
        match = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*(米|m|M|毫米|mm|MM)\s*", value)
        if not evidence or not match:
            issue("distance_evidence", f"{field}缺少明确实际距离或单位，需人工复核", wid, True)
            return UNKNOWN
        meters = float(match[1]) / (1000 if match[2] in ("毫米", "mm", "MM") else 1)
        return format(meters, "g")

    # 印刷页号与源文件中的第几页是两回事；不能拿 page_index 补一个看似确定的页号。
    page = read(obs.page_number, "页号")
    match = re.search(r"第\s*(\d+)\s*页", page)
    page = f"第{match[1]}页" if match else (f"第{page}页" if page.isdigit() else UNKNOWN)
    road = read(obs.road_title, "所属路段") if obs.title_source != UNKNOWN else UNKNOWN
    page_notes = []
    if page == UNKNOWN:
        page_notes.append("印刷页号无法识别，需人工复核")
        issue("missing_page", page_notes[-1])
    if road == UNKNOWN:
        page_notes.append("所属路段无法识别，需人工复核")
        issue("missing_road", page_notes[-1])
    if obs.notes:
        for note in obs.notes:
            issue("page_note", note)

    # 第一步只选有名称/图例依据且实际看到符号的候选，后续连接也只能引用保留的井。
    candidates = []
    raw_names = {}
    for w in obs.wells:
        name = read(w.name, "管井名称", w.id)
        raw_names[w.id] = name
        # strict_names复现较窄的关键词范围；默认广义范围还允许分歧/直通或带图例的纯桩号名。
        keywords = ("人孔", "手孔", "接头管箱") if strict_names else ("人孔", "手孔", "管箱", "分歧", "直通")
        keyword_match = any(k in name for k in keywords)
        station_legend = bool(STATION.fullmatch(name) and w.legend_type != UNKNOWN and w.legend_evidence)
        if not w.symbol_evidence or name == UNKNOWN or not (keyword_match or (not strict_names and station_legend)):
            issue("excluded_candidate", f"候选 {w.id} 没有符合范围的名称及实际符号证据，未导出，需人工复核", repair=True)
            continue
        candidates.append(w)
    if not candidates:
        issue("no_wells", "本页没有可确认的管井，需人工复核")
    # 按引线组和原OCR标签共同分组，两个文字相同的独立标注不会被合并编号。
    groups = defaultdict(list)
    for w in candidates:
        # Include label ID to prevent accidental merging of different identical labels.
        groups[(w.group_id, w.name.text_id)].append(w)
    export_names = {}
    for group in groups.values():
        # 组内按左边界、上边界和id稳定排序；每个新组都从1编号。
        group.sort(key=lambda w: (w.bbox[0], w.bbox[1], w.id))
        for i, w in enumerate(group, 1):
            name = raw_names[w.id]
            if len(group) > 1:
                name = f"{MULTIPLIER.sub('', name).rstrip()}-{i}"
            export_names[w.id] = name
        text = raw_names[group[0].id]
        count = re.search(r"[×xX]\s*(\d+)|([二两三四五六七八九十\d]+)\s*个\s*$", text)
        if count:
            raw_count = count[1] or count[2]
            expected = int(raw_count) if raw_count.isdigit() else {"二": 2, "两": 2, "三": 3, "四": 4, "五": 5}.get(raw_count)
            # 标注数量与可确认符号数不一致时只报问题，仍只导出真正记录到的符号。
            if expected and expected != len(group):
                for w in group:
                    issue("count_mismatch", f"标注数量 {expected} 与可确认符号数量 {len(group)} 不一致，需人工复核", w.id, True)

    # 第二步构造关系索引：全体邻井、局部邻井、局部分支和设备关联分别保存。
    well_ids = {w.id for w in candidates}
    devices = {d.id: d for d in obs.devices}
    adjacent = defaultdict(set)
    local_neighbors = defaultdict(set)
    branches = defaultdict(set)
    associations = defaultdict(dict)
    # 重复的井间边用set去重；无证据、自连接或端点不存在的边不能增加连通数量。
    for e in obs.edges:
        endpoints = {e.source, e.target}
        if e.source == e.target or not e.evidence:
            issue("invalid_edge", "连接缺少视觉/文字证据或为自连接，需人工复核", e.source, True)
            continue
        if e.basis == "文本" and read(e.text_ref, "连接文本", e.source) == UNKNOWN:
            continue
        # 井—井连接必须有清晰管线依据；文本或邻近不能直接作为确定管线。
        if e.kind == "管线":
            if not endpoints <= well_ids:
                issue("dangling_edge", "连接端点不属于已记录管井，需人工复核", e.source, True)
                continue
            if e.basis != "引线":
                issue("uncertain_pipe", "管井间连接缺少清晰管线证据，需人工复核", e.source)
                continue
            for a, b in ((e.source, e.target), (e.target, e.source)):
                adjacent[a].add(b)
                if e.local:
                    local_neighbors[a].add(b)
                    # 沿主线前后贯通不自动算分歧，只有局部非主线关系才进入分支集合。
                    if not e.along_mainline:
                        branches[a].add(b)
        else:
            ws, ds = endpoints & well_ids, endpoints & devices.keys()
            if len(ws) != 1 or len(ds) != 1:
                issue("dangling_edge", "井—设备连接端点无效，需人工复核", e.source, True)
                continue
            wid, did = next(iter(ws)), next(iter(ds))
            previous = associations[wid].get(did)
            # 同一井—设备若重复出现多种依据，只保留当前优先级最高的一条。
            ranking = {"邻近": 0, "文本": 1, "引线": 2}
            if previous is None or ranking[e.basis] > ranking[previous.basis]:
                associations[wid][did] = e

    # 先验证所有井桩号，后面设备继承只能使用这些已检查过的值。
    stations = {w.id: station(w.main_station, w.station_evidence, "主线桩号", w.id) for w in candidates}
    for wid, value in stations.items():
        if value == UNKNOWN:
            issue("missing_station", "主线桩号无法确定，需人工复核", wid)
    # 同一设备可能关联多个井；收集各井桩号，用于识别继承值冲突。
    connected_station = defaultdict(set)
    for wid, assoc in associations.items():
        for did, e in assoc.items():
            if e.basis != "邻近":
                connected_station[did].add(stations[wid])
    number_usage = Counter(w.number.text_id for w in candidates if w.number)
    records = []
    # 第三步逐井合成最终字段；排序只决定输出顺序，不用于推断桩号或拓扑。
    for w in sorted(candidates, key=lambda w: (w.bbox[0], w.bbox[1], w.id)):
        raw = raw_names[w.id]
        # 井类型依次采用明确名称、图例说明、形状；仍不确定时保留无法判断。
        typ = next((t for keyword, t in (("人孔", "人孔"), ("手孔", "手孔"), ("管箱", "接头管箱")) if keyword in raw), UNKNOWN)
        if typ == UNKNOWN and w.legend_evidence:
            typ = w.legend_type
        if typ == UNKNOWN:
            typ = {"圆形": "人孔", "正方形": "手孔"}.get(w.shape, UNKNOWN)
        if typ == UNKNOWN:
            issue("unknown_well_type", "管井类型无法确定，需人工复核", w.id)
        # 显式名称优先；名称写分歧但邻井证据不足时保留名称判断并同时要求复核。
        explicit = "分歧" if "分歧" in raw else ("直通" if "直通" in raw else "")
        if explicit:
            connectivity = explicit
            if explicit == "分歧" and len(local_neighbors[w.id]) < 2:
                issue("branch_recheck", "名称为分歧，但尚未确认连接两个及以上已记录管井，需人工复核", w.id, True)
        # 自动判分歧需要局部分支且至少两个不同的已记录邻井；重复边不能凑数。
        elif branches[w.id] and len(local_neighbors[w.id]) >= 2:
            connectivity = "分歧"
        elif adjacent[w.id] and w.connections_complete:
            connectivity = "直通"
        else:
            connectivity = UNKNOWN
            issue("unclear_connections", "连接关系不完整或不清晰，需人工复核", w.id)

        # 编号引用与名称是不同字段；共享专号不会把多个真实符号合并成一口井。
        number = read(w.number, "管井编号", w.id)
        if number == UNKNOWN and NUMBER.search(raw):
            number = raw
        if w.number and (number_usage[w.number.text_id] > 1 or w.number_relation == "最近"):
            issue("shared_number", "该专号可能对应多个管井，需人工复核", w.id)
        number = number if w.number_relation != UNKNOWN or NUMBER.search(raw) else UNKNOWN
        if number == UNKNOWN:
            issue("missing_number", "管井编号不明确，需人工复核", w.id)
        # 位置先读取明确文字，缺少文字时仅在有位置证据说明的情况下使用视觉分类。
        position_text = raw + " " + (read(w.position, "位置类型", w.id) if w.position else "")
        position = next((v for k, v in (("路侧", "路侧"), ("中分带", "路中"), ("中央分隔带", "路中"), ("匝道", "匝道")) if k in position_text), UNKNOWN)
        if position == UNKNOWN and w.position_evidence:
            position = w.visual_position
        direction = read(w.direction, "方向", w.id)
        if direction != UNKNOWN and not re.search(r"上行|下行|东|南|西|北", direction):
            issue("direction_evidence", "方向没有明确标注，需人工复核", w.id, True)
            direction = UNKNOWN
        offset = distance(w.offset_m, w.offset_evidence, "距中心线偏移量", w.id)
        # 不涉及匝道用空串；涉及匝道却缺桩号用无法判断，保留业务语义差别。
        is_ramp = w.is_ramp or position == "匝道"
        ramp = station(w.ramp_station, w.station_evidence, "匝道桩号", w.id) if is_ramp else ""
        if is_ramp and ramp == UNKNOWN:
            issue("missing_ramp_station", "涉及匝道但桩号无法确定，需人工复核", w.id)

        # 同一井的多设备字段按相同顺序生成，用中文分号连接，防止名称与桩号错位。
        dev_names, dev_stations, dev_distances = [], [], []
        confirmed = False
        for did, edge in sorted(associations[w.id].items()):
            d = devices[did]
            name = read(d.name, "设备名称", w.id)
            # 文本关联或邻近的设备名称都加疑似；文本仍允许确认关联，纯邻近不允许。
            if edge.basis != "引线":
                name = "疑似" + name
                issue("suspected_device", "疑似关联，需人工复核" if edge.basis == "邻近" else "设备仅有文本关联，缺少明确连接线，需人工复核", w.id)
            if d.only_code:
                issue("code_only_device", "设备仅有编号，暂按设备记录，需人工复核", w.id)
            if edge.basis != "邻近":
                confirmed = True
            # 设备独立桩号优先；没有时，纯邻近不继承，明确文本/引线才检查关联井桩号集合。
            if d.station:
                ds = station(d.station, d.station_evidence, "设备主线桩号", w.id)
            elif edge.basis == "邻近":
                ds = UNKNOWN
            else:
                ds_set = connected_station[did]
                # 只在所有明确关联得到同一个值时继承；多个不同值不任选一个。
                ds = next(iter(ds_set)) if len(ds_set) == 1 else UNKNOWN
                if len(ds_set) > 1:
                    issue("device_station_conflict", "设备关联多个不同桩号管井，需人工复核", w.id)
            dev_names.append(name)
            dev_stations.append(ds)
            dev_distances.append(distance(edge.distance_m, edge.distance_evidence, "管井与设备间距", w.id))
        # 确认关联为是；无设备且连接检查完整才为否，其余情况保留无法判断。
        has_device = "是" if confirmed else (UNKNOWN if dev_names or not w.connections_complete else "否")
        # 截断、跨页、低置信度和模型备注都留下复核线索，不用缺失线条推断无连接。
        if w.edge_truncated:
            issue("edge_truncated", "边缘截断，信息不完整", w.id)
        if w.cross_page:
            issue("cross_page", "连接关系可能受图纸截断影响", w.id)
        if w.confidence < .7:
            issue("low_confidence", "视觉识别置信度较低，需人工复核", w.id)
        for note in w.notes:
            issue("model_note", note, w.id)
        # 中文输出由Record的alias保证；dict.fromkeys去重备注且保持第一次出现的顺序。
        records.append(Record(page=page, name=export_names[w.id], well_type=typ,
                              connectivity=connectivity, road=road, number=number,
                              position=position, direction=direction, offset=offset,
                              main_station=stations[w.id], ramp_station=ramp,
                              has_device=has_device, device_name="；".join(dev_names),
                              device_station="；".join(dev_stations), device_distance="；".join(dev_distances),
                              notes="；".join(dict.fromkeys(per_well[w.id] + obs.notes + page_notes))))
    return [r.model_dump(by_alias=True) for r in records], issues
