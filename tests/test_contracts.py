import pytest
from pydantic import ValidationError

from drawflow.config import identifier
from drawflow.contracts import Evidence, MemoryProposal, Review
from drawflow.validation import validate


def test_clean_evidence(batch, ocr):
    assert validate(batch, ocr) == []
    assert len(batch.records[0].record.model_dump(by_alias=True)) == 16


def test_ocr_cannot_be_changed(batch, ocr):
    batch.evidence[0].text = "K999+999"
    assert any("改写" in i["message"] for i in validate(batch, ocr))


def test_station_cannot_use_substring(batch, ocr):
    batch.records[0].record.main_station = "K116+26"
    assert any(i["field"] == "主线桩号" and i["severity"] == "error" for i in validate(batch, ocr))


def test_cross_page_reference(batch, ocr):
    batch.evidence[-1].page = "p2"
    assert any("不同页面" in i["message"] for i in validate(batch, ocr))


def test_branch_requires_recorded_neighbors(batch, ocr):
    batch.records[0].record.connection = "分歧"
    batch.records[0].neighbor_ids = ["missing"]
    assert any(i["field"] == "连通类型" for i in validate(batch, ocr))


def test_group_names_are_independent(batch, ocr):
    batch.records[1].group_id = "another-label"
    batch.records[1].record.name = batch.records[1].raw_name
    batch.records[2].record.name = "桥梁两端电力手孔-2"
    assert validate(batch, ocr) == []


def test_yes_device_requires_relation(batch, ocr):
    batch.records[0].record.connected_equipment = "是"
    assert any("DeviceRelation" in i["message"] for i in validate(batch, ocr))


@pytest.mark.parametrize(
    "box", [[0, 0, 0, 1], [0, 4, 2, 3], [-1, 0, 2, 3], [0, 0, float("nan"), 3]]
)
def test_bad_boxes_rejected(box):
    with pytest.raises(ValidationError):
        Evidence(evidence_id="a", kind="vision", page="p1", text="x", bbox=box)


@pytest.mark.parametrize("value", ["../escape", "a/b", "", "a" * 81])
def test_run_paths_are_identifiers(value):
    with pytest.raises(ValueError):
        identifier(value)


def test_review_needs_real_boolean():
    with pytest.raises(ValidationError):
        Review(approved="false", reason="checked", reviewer="tester")


def test_memory_excludes_drawing_station():
    with pytest.raises(ValidationError):
        MemoryProposal(key="station", content="每张图都用 K116+266")


def test_quantity_suffix_preserves_plain_numeric_name():
    from drawflow.validation import display_base

    assert display_base("电力手孔2") == "电力手孔2"
    assert display_base("桥梁两端电力手孔2个") == "桥梁两端电力手孔"
    assert display_base("桥梁两端电力手孔两个") == "桥梁两端电力手孔"


def test_same_group_id_on_another_page_has_own_sequence(batch, ocr):
    from copy import deepcopy

    from drawflow.contracts import Extraction

    other = deepcopy(batch)
    for evidence in other.evidence:
        evidence.page = "p2"
        evidence.evidence_id = "other-" + evidence.evidence_id
    for item in other.records:
        item.object_id = "other-" + item.object_id
        item.page_id = "p2"
        item.neighbor_ids = ["other-" + n for n in item.neighbor_ids]
        item.field_evidence = {
            k: ["other-" + e for e in refs] for k, refs in item.field_evidence.items()
        }
    joined = Extraction(
        records=[*batch.records, *other.records], evidence=[*batch.evidence, *other.evidence]
    )
    assert validate(joined, [*ocr, *[e for e in other.evidence if e.kind == "ocr"]]) == []
