"""Context-bound LangChain tools; model arguments never select filesystem paths."""

import re

from langchain_core.tools import tool

from .imaging import call_ocr, checked_region


def build_tools(index, memory, skills, state):
    pages = {p["page_id"]: p for p in state["pages"]}

    @tool
    def search_knowledge(query: str) -> dict:
        """检索施工图规则，返回引用、父段落及检索分数。"""
        return {"documents": index.search(query)}

    @tool
    def recall_project_memory(query: str) -> dict:
        """读取当前项目已经人工确认的命名约定和复核策略。"""
        return {"memories": memory.recall(state["project"], query)}

    @tool
    def load_skill(name: str) -> dict:
        """按名称加载已注册的领域 skill 操作步骤。"""
        return skills.load(name)

    @tool
    def validate_chainage(value: str, page_id: str) -> dict:
        """检查桩号格式，并定位当前页支持该桩号的 OCR 行。"""
        pattern = r"(?<![A-Za-z0-9])([A-Z]*K\d+\+\d{3}(?:\.\d+)?)(?![\d.])"
        ids = [
            e["evidence_id"]
            for e in state["ocr"]
            if e["page"] == page_id and value in re.findall(pattern, e["text"])
        ]
        return {
            "value": value,
            "format_valid": bool(re.fullmatch(r"[A-Z]*K\d+\+\d{3}(?:\.\d+)?", value)),
            "evidence_ids": ids,
            "supported": bool(ids),
        }

    @tool
    def ocr_region(page_id: str, left: int, top: int, right: int, bottom: int) -> dict:
        """复核当前任务指定页的局部文字；区域使用原图整数像素坐标。"""
        if page_id not in pages:
            raise ValueError("局部复核只能选择当前任务页面")
        page = pages[page_id]
        box = checked_region(page, [left, top, right, bottom])
        if state["mode"] == "demo":
            # Replay only the OCR lines in this crop, retaining original provenance.
            rows = [
                e
                for e in state["ocr"]
                if e["page"] == page_id
                and e["bbox"]
                and e["bbox"][0] >= left
                and e["bbox"][1] >= top
                and e["bbox"][2] <= right
                and e["bbox"][3] <= bottom
            ]
        else:
            rows = call_ocr(page, box)
        return {
            "page_id": page_id,
            "region": box,
            "ocr": rows,
            "source": "fixture_crop" if state["mode"] == "demo" else "paddle_http",
        }

    return {
        t.name: t
        for t in [
            search_knowledge,
            recall_project_memory,
            load_skill,
            validate_chainage,
            ocr_region,
        ]
    }
