# 数据契约：OCRLine 保存文字证据；Layout/Observation 保存模型观察；Record 保存最终16字段。
# 读取顺序建议：Ref → Well/Device/Edge → Observation → Record。
# Pydantic 检查结构、类型和坐标范围；内容是否有图纸证据，要交给 rules.py 继续判断。
# 不要随意修改类文档字符串或 Field(description=...)：这些内容会进入模型接收的 JSON Schema。
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

UNKNOWN = "无法判断"


# 所有内部模型的共同基类。extra=forbid 拒绝未声明字段，尽早发现拼写错误或额外输出。
class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


# 一行独立文字证据。id 只要求页内唯一，后续 Ref 通过这个 id 找回原文。
class OCRLine(StrictModel):
    id: str
    text: str
    # (x0,y0,x1,y1)相对于整页宽高归一化；confidence是OCR分数，不是最终识别准确率。
    bbox: tuple[float, float, float, float] = (0, 0, 1, 1)
    confidence: float = Field(default=1.0, ge=0, le=1)

    # 验证四个坐标位于0~1，且左<右、上<下；拒绝零面积框、反向框和像素坐标。
    # 这里只验证矩形是否合法，不验证矩形是否真的框住对应文字。
    @field_validator("bbox")
    @classmethod
    def normalized_box(cls, value):
        if not all(0 <= coordinate <= 1 for coordinate in value) or not (value[0] < value[2] and value[1] < value[3]):
            raise ValueError("bbox 必须是整页归一化有效矩形")
        return value


# 文字属性的引用：text_id 指向 OCR 行，value 是从该行提取的文字片段。
# 规则层会检查 value 是否确实出现在原文；它不是允许模型随意生成事实的容器。
class Ref(StrictModel):
    """A value copied from exactly one OCR line; not a generated fact."""
    # 例如{text_id: t0001, value: K9+043}；值可以是原行中的一部分，但必须逐字匹配。
    text_id: str
    value: str


# 第一轮模型观察：先分析图例、表格行列及关联方式，供第二轮对象提取使用。
class Layout(StrictModel):
    drawing_style: Literal["文字引线型", "表格对应型", "混合型", "无法判断"]
    legend_summary: str
    # 记录表格中编号、类型和桩号如何对应，保留OCR id便于第二阶段追踪。
    table_mapping: list[str] = Field(default_factory=list, description="编号列、类型行、桩号行的对应方式及 OCR IDs")
    # 关系线索与不确定说明，作为上下文使用，不自动变成最终事实。
    relation_hints: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


# 一个实际管井候选的内部记录，比最终输出保留更多坐标、引用和不确定性。
# 每个候选应对应一个可见符号；标注×3不能在没有三个符号时凭空扩成三口井。
class Well(StrictModel):
    # 对象身份、名称引用和标注组：对象id用于连接，group_id用于同标注多井编号。
    id: str
    name: Ref
    group_id: str = Field(description="同一原始标注的引线组，不同标注必须不同组")
    # 整页中的符号框及视觉说明；symbol_evidence描述实际看见的符号和引线。
    bbox: tuple[float, float, float, float]
    symbol_evidence: str = Field(description="实际符号/引线位置的视觉描述，不能用×N替代")
    # 形状与图例类型分别保存，避免简单地把所有圆圈都当成某一种确定井型。
    shape: Literal["圆形", "正方形", "其他", "无法判断"] = "无法判断"
    legend_type: Literal["人孔", "手孔", "接头管箱", "无法判断"] = "无法判断"
    legend_evidence: str = ""
    # 专号及其对应依据；最近只表示邻近匹配，规则会保留复核提示。
    number: Ref | None = None
    number_relation: Literal["明确", "最近", "无法判断"] = "无法判断"
    # 主线/匝道桩号引用独立OCR证据，station_evidence解释它为什么属于这口井。
    main_station: Ref | None = None
    ramp_station: Ref | None = None
    is_ramp: bool = False
    station_evidence: str = Field(default="", description="引线和桩号的对应，矩形内多桩号逐井匹配")
    # 文字位置与视觉位置分开；使用视觉分类时还需要position_evidence。
    position: Ref | None = None
    visual_position: Literal["路侧", "路中", "匝道", "无法判断"] = "无法判断"
    position_evidence: str = ""
    # 方向和偏移量须引用实际标注；offset_evidence说明尺寸对应的端点。
    direction: Ref | None = None
    offset_m: Ref | None = None
    offset_evidence: str = ""
    # 连接检查是否完整、是否靠图边截断、是否可能跨页，影响未知值与复核判断。
    connections_complete: bool = False
    edge_truncated: bool = False
    cross_page: bool = False
    # 这是模型自报的候选置信度，只作复核线索，不能当作已测得的准确率。
    confidence: float = Field(default=1, ge=0, le=1)
    notes: list[str] = Field(default_factory=list)

    # 管井框沿用 OCRLine 的整页坐标约定，避免文字框和对象框混用两套单位。
    @field_validator("bbox")
    @classmethod
    def normalized_box(cls, value):
        return OCRLine.normalized_box(value)


# 设备独立建模；设备与哪个管井相关，由 Edge 表示，而不是由列表邻近顺序决定。
class Device(StrictModel):
    id: str
    name: Ref
    # 设备可有独立桩号；没有时由规则按明确关联决定能否继承管井桩号。
    station: Ref | None = None
    station_evidence: str = ""
    # 只有设备编号却没有明确名称时，保留为待复核设备，不能补出具体类型。
    only_code: bool = False


# 观察到的一条井—井或井—设备关系。source/target 使用对象 id，不使用列表下标。
# 是否导出这条关系还要检查端点、依据、证据和主线/局部属性。
class Edge(StrictModel):
    source: str
    target: str
    # kind区分井间管线与设备关联；basis区分实际引线、明确文本和单纯邻近。
    kind: Literal["管线", "设备"]
    basis: Literal["引线", "文本", "邻近"]
    evidence: str
    # 以文本作为关联依据时，同时保存可核对的文字引用。
    text_ref: Ref | None = None
    # 只有局部且非沿主线的有效连接，才参与局部分支判断。
    local: bool = True
    along_mainline: bool = False
    # 名称带_m，但Ref仍保存原始带单位文字；实际转米由规则函数完成。
    distance_m: Ref | None = None
    distance_evidence: str = ""


# 一页的完整视觉观察：页号、路段、井、设备和边。它是校验前的中间数据。
class Observation(StrictModel):
    """Intermediate page observation, not the final Chinese JSON array."""
    # 印刷页号和标题栏路段必须来自当前页OCR，不用文件名或相邻页面猜测。
    page_number: Ref | None = None
    road_title: Ref | None = None
    title_source: Literal["标题栏", "底部说明", "无法判断"] = "无法判断"
    # 对象和关系分开存储；完整观察会随evidence导出，以便查看被规则否决的候选。
    wells: list[Well] = Field(default_factory=list)
    devices: list[Device] = Field(default_factory=list)
    edges: list[Edge] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)

    # 在所有子模型验证结束后，统一检查本页井与设备的 id 是否有冲突。
    # 边的端点是否合法由规则层检查，这个验证器只负责唯一性。
    @model_validator(mode="after")
    def unique_ids(self):
        ids = [x.id for x in self.wells] + [x.id for x in self.devices]
        if len(ids) != len(set(ids)):
            raise ValueError("井/设备 ID 必须页内唯一")
        return self


# 对外输出的16字段契约，全部使用字符串。alias 定义用户要求的中文字段名。
# 不适用的设备/匝道字段通常为空串；适用却缺证据时用无法判断，二者不能混为一谈。
class Record(StrictModel):
    # 允许用英文属性名构造，也允许用中文alias校验；导出用model_dump(by_alias=True)。
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    # 基础身份字段：页号、名称、井型、连通类型、路段与编号。
    page: str = Field(default=UNKNOWN, alias="页号")
    name: str = Field(alias="管井名称")
    well_type: str = Field(default=UNKNOWN, alias="管井类型")
    connectivity: str = Field(default=UNKNOWN, alias="连通类型")
    road: str = Field(default=UNKNOWN, alias="所属路段")
    number: str = Field(default=UNKNOWN, alias="管井编号")
    # 位置与中心线关系字段，偏移量的字段名已经声明单位为米。
    position: str = Field(default=UNKNOWN, alias="位置类型")
    direction: str = Field(default=UNKNOWN, alias="方向")
    offset: str = Field(default=UNKNOWN, alias="距中心线偏移量（米）")
    # 主线桩号默认未知；匝道桩号空串表示不适用，未知表示适用但没看清。
    main_station: str = Field(default=UNKNOWN, alias="主线桩号")
    ramp_station: str = Field(default="", alias="匝道桩号")
    # 多设备名称、桩号和距离保持同序并以中文分号连接；没有对应数据时为空串。
    has_device: str = Field(default=UNKNOWN, alias="是否连接设备")
    device_name: str = Field(default="", alias="设备名称")
    device_station: str = Field(default="", alias="设备主线桩号")
    device_distance: str = Field(default="", alias="管井与设备间距（米）")
    # 汇集该井、当前页和模型留下的问题，保留无法确认字段的原因。
    notes: str = Field(default="", alias="备注")
