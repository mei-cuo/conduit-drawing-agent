import pytest
from PIL import Image

from drawflow.config import ASSETS
from drawflow.imaging import call_ocr, checked_region, prepare, sidecar
from drawflow.memory import ProjectMemory
from drawflow.retrieval import KnowledgeIndex
from drawflow.skills import SkillRegistry
from drawflow.storage import write_json
from drawflow.tools import build_tools


def test_tiling_and_pdf_pages(tmp_path):
    image = tmp_path / "wide.png"
    Image.new("RGB", (3300, 1800)).save(image)
    pages = prepare(image, tmp_path / "images")
    assert 1 <= len(pages[0]["tiles"]) <= 6
    import fitz

    with fitz.open() as doc:
        doc.new_page()
        doc.new_page()
        doc.save(tmp_path / "two.pdf")
    pages = prepare(tmp_path / "two.pdf", tmp_path / "pdf")
    assert [p["page_id"] for p in pages] == ["p1", "p2"]


def test_sidecar_sha_and_crop_bounds(tmp_path):
    pages = prepare(ASSETS / "demo/drawing.png", tmp_path / "pages")
    ocr = sidecar(ASSETS / "demo/ocr.json", pages)
    assert len(ocr) == 5
    write_json(
        tmp_path / "bad.json",
        {"pages": [{"page_id": "p1", "sha256": "wrong", "evidence": ocr}]},
    )
    with pytest.raises(ValueError, match="摘要"):
        sidecar(tmp_path / "bad.json", pages)
    with pytest.raises(ValueError):
        checked_region(pages[0], [True, 0, 2, 3])
    with pytest.raises(ValueError):
        checked_region(pages[0], [0, 0, 9999, 3])


def test_region_remaps_coordinates(tmp_path, monkeypatch):
    pages = prepare(ASSETS / "demo/drawing.png", tmp_path / "pages")

    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {
                "width": 200,
                "height": 100,
                "lines": [{"text": "K1+100", "bbox": [0.1, 0.1, 0.8, 0.5]}],
            }

    monkeypatch.setattr("drawflow.imaging.httpx.post", lambda *a, **kw: Response())
    rows = call_ocr(pages[0], [100, 50, 300, 150])
    assert rows[0]["bbox"] == [120, 60, 260, 100]


def test_context_bound_tools_and_skill_registry(settings, tmp_path):
    pages = prepare(ASSETS / "demo/drawing.png", tmp_path / "pages")
    index = KnowledgeIndex(settings)
    try:
        index.ingest()
        skills = SkillRegistry()
        assert "table-layout" in skills.select("两端手孔×3")
        tools = build_tools(
            index,
            ProjectMemory(settings.runtime / "memory.sqlite"),
            skills,
            {
                "pages": pages,
                "project": "a",
                "ocr": sidecar(ASSETS / "demo/ocr.json", pages),
                "mode": "demo",
            },
        )
        assert tools["validate_chainage"].invoke({"value": "K116+266", "page_id": "p1"})[
            "supported"
        ]
        assert not tools["validate_chainage"].invoke({"value": "K116+266", "page_id": "p2"})[
            "supported"
        ]
        with pytest.raises(ValueError):
            tools["ocr_region"].invoke(
                {
                    "page_id": "../../other",
                    "left": 0,
                    "top": 0,
                    "right": 10,
                    "bottom": 10,
                }
            )
        assert tools["load_skill"].invoke({"name": "station-audit"})["version"] == "1.0"
    finally:
        index.close()
