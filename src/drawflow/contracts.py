"""业务契约：模型内部保留证据，最终导出用户指定的 16 字段。"""

import math
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictStr,
    model_validator,
)

UNKNOWN = "无法判断"


class StrictModel(BaseModel):
    @model_validator(mode="after")
    def valid_bbox(self):
        box = getattr(self, "bbox", None)
        if box is not None and (
            not all(math.isfinite(v) and v >= 0 for v in box)
            or box[0] >= box[2]
            or box[1] >= box[3]
        ):
            raise ValueError("bbox 必须是有限、非负、有面积的像素区域")
        return self

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class WellRecord(StrictModel):
    page: StrictStr = Field(alias="页号")
    name: StrictStr = Field(alias="管井名称")
    well_type: Literal["人孔", "手孔", "接头管箱", "无法判断"] = Field(alias="管井类型")
    connection: Literal["直通", "分歧", "无法判断"] = Field(alias="连通类型")
    section: StrictStr = Field(alias="所属路段")
    number: StrictStr = Field(alias="管井编号")
    position: Literal["路侧", "路中", "匝道", "无法判断"] = Field(alias="位置类型")
    direction: StrictStr = Field(alias="方向")
    offset: StrictStr = Field(alias="距中心线偏移量（米）")
    main_station: StrictStr = Field(alias="主线桩号")
    ramp_station: StrictStr = Field(alias="匝道桩号")
    connected_equipment: Literal["是", "否", "无法判断"] = Field(alias="是否连接设备")
    equipment_name: StrictStr = Field(alias="设备名称")
    equipment_station: StrictStr = Field(alias="设备主线桩号")
    equipment_distance: StrictStr = Field(alias="管井与设备间距（米）")
    notes: StrictStr = Field(alias="备注")


class Evidence(StrictModel):
    evidence_id: str
    kind: Literal["ocr", "vision"]
    page: str
    text: str
    bbox: list[float] | None = Field(
        default=None,
        min_length=4,
        max_length=4,
        description="原图像素坐标 [x1,y1,x2,y2]；切片需先转换到原图坐标",
    )


class DeviceRelation(StrictModel):
    name: str
    station: str = UNKNOWN
    distance: str = UNKNOWN
    relation: Literal["line", "text", "proximity"]
    evidence_ids: list[str] = Field(min_length=1)


class Candidate(StrictModel):
    object_id: str
    page_id: str = Field(description="内部页面标识，独立于图纸上可读的页号")
    bbox: list[float] = Field(min_length=4, max_length=4)
    group_id: str = Field(description="同一处标注对应多个井时共用此 ID，不同标注分组")
    raw_name: str = Field(description="完整原始标注，包括数量符号；不能被显示名称覆盖")
    record: WellRecord
    field_evidence: dict[str, list[str]] = Field(description="中文字段名到证据 ID 列表")
    device_links: list[DeviceRelation] = Field(default_factory=list)
    neighbor_ids: list[str] = Field(description="实际确认相连的其他管井 object_id，不能填设备 ID")
    branch_visible: bool | None = Field(description="是否有离开主线的支路证据；未知为 null")


class Extraction(StrictModel):
    records: list[Candidate]
    evidence: list[Evidence]


class Correction(StrictModel):
    object_id: str
    field: str
    value: str
    evidence_ids: list[str]


class Review(StrictModel):
    approved: StrictBool
    reason: str = Field(min_length=1)
    reviewer: str = Field(min_length=1)
    memories: list["MemoryProposal"] = Field(default_factory=list)
    corrections: list[Correction] = Field(default_factory=list)


class MemoryProposal(StrictModel):
    @model_validator(mode="after")
    def convention_only(self):
        import re

        if re.search(r"[A-Z]*K\d+\+\d{3}", self.content):
            raise ValueError("项目记忆只保存约定；具体桩号留在当前任务证据中")
        return self

    key: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,64}$")
    content: str = Field(min_length=1, max_length=1200)
    kind: Literal["convention", "review_policy"] = "convention"


Review.model_rebuild()
