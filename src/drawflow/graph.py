"""Persistent agent graph with bounded tools, repair and human review."""

from __future__ import annotations

import json
import operator
import time
from pathlib import Path
from typing import Annotated, TypedDict

from langchain_core.messages import BaseMessage, HumanMessage, ToolMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.types import interrupt
from pydantic import ValidationError

from .config import ASSETS
from .contracts import Evidence, Extraction, Review
from .imaging import call_ocr, prepare, sidecar
from .models import image_blocks
from .retrieval import context_text
from .storage import digest, write_json
from .tools import build_tools
from .validation import validate_task


class AgentState(TypedDict, total=False):
    run_id: str
    project: str
    mode: str
    image: str
    ocr_json: str
    task: str
    review_policy: str
    max_tools: int
    max_rounds: int
    max_repairs: int
    simulate_error: bool
    force_review: bool
    pages: list[dict]
    ocr: list[dict]
    documents: list[dict]
    memories: list[dict]
    active_skills: list[dict]
    messages: Annotated[list[BaseMessage], add_messages]
    timeline: Annotated[list[dict], operator.add]
    tool_events: list[dict]
    tools_used: int
    agent_rounds: int
    repairs: int
    batch: dict
    issues: list[dict]
    status: str
    reviewed: bool
    review_reason: str
    reviewer: str
    memory_proposals: list[dict]
    output_dir: str


def build_graph(settings, index, memory, skills, agent, checkpointer):
    def prepare_node(s):
        output = settings.home / "outputs" / s["run_id"]
        pages = prepare(Path(s["image"]), output / "pages")
        ocr = (
            sidecar(s["ocr_json"], pages)
            if s.get("ocr_json")
            else [e for p in pages for e in call_ocr(p)]
        )
        return {
            "pages": pages,
            "ocr": ocr,
            "output_dir": str(output),
            "tools_used": 0,
            "agent_rounds": 0,
            "repairs": 0,
            "tool_events": [],
            "status": "prepared",
            "reviewed": False,
        }

    def retrieve_node(s):
        text = s["task"] + " " + " ".join(e["text"] for e in s["ocr"])
        documents = index.search(text, k=4)
        active = [skills.load(name) for name in skills.select(text)]
        memories = memory.recall(s["project"], s["task"])
        evidence = {
            "task": s["task"],
            "ocr": s["ocr"],
            "skills": active,
            "project_memory": memories,
            "rules": context_text(documents),
            "memory_policy": "记忆用于项目约定；当前图纸事实以当页证据为准",
        }
        return {
            "documents": documents,
            "active_skills": active,
            "memories": memories,
            "messages": [
                HumanMessage(
                    content=[
                        {
                            "type": "text",
                            "text": json.dumps(evidence, ensure_ascii=False),
                        },
                        *image_blocks(s["pages"]),
                    ]
                )
            ],
            "status": "retrieved",
        }

    def reason_node(s):
        registry = build_tools(index, memory, skills, s)
        allow = s["tools_used"] < s["max_tools"] and s["agent_rounds"] < s["max_rounds"]
        reply = agent.think(s, registry, allow_tools=allow)
        return {
            "messages": [reply],
            "agent_rounds": s["agent_rounds"] + 1,
            "status": "reasoned",
        }

    def tools_node(s):
        registry = build_tools(index, memory, skills, s)
        used = s["tools_used"]
        replies = []
        events = list(s["tool_events"])
        ocr = {e["evidence_id"]: e for e in s["ocr"]}
        for call in s["messages"][-1].tool_calls:
            start = time.perf_counter()
            error = False
            try:
                if used >= s["max_tools"] or s["agent_rounds"] > s["max_rounds"]:
                    raise ValueError("工具预算已用完")
                used += 1
                if call["name"] not in registry:
                    raise ValueError("工具不在注册表中")
                if call["name"] == "ocr_region" and any(
                    type(call["args"].get(k)) is not int for k in ("left", "top", "right", "bottom")
                ):
                    raise ValueError("局部 OCR 坐标必须为整数")
                result = registry[call["name"]].invoke(call["args"])
                for row in result.get("ocr", []):
                    old = ocr.get(row["evidence_id"])
                    if old and old != row:
                        raise ValueError("OCR 证据 ID 冲突")
                    ocr[row["evidence_id"]] = row
            except Exception as exc:
                error = True
                result = {"error": f"{type(exc).__name__}: {exc}"}
            replies.append(
                ToolMessage(
                    content=json.dumps(result, ensure_ascii=False),
                    tool_call_id=call["id"],
                )
            )
            events.append(
                {
                    "name": call["name"],
                    "args": call["args"],
                    "error": error,
                    "elapsed_ms": round((time.perf_counter() - start) * 1000, 2),
                }
            )
        return {
            "messages": replies,
            "tools_used": used,
            "tool_events": events,
            "ocr": list(ocr.values()),
            "status": "tools_completed",
        }

    def extract_node(s):
        return {"batch": agent.extract(s), "status": "extracted"}

    def validate_node(s):
        batch = Extraction.model_validate(s["batch"])
        issues = validate_task(batch, [Evidence.model_validate(e) for e in s["ocr"]], s["pages"])
        return {"issues": issues, "status": "validated"}

    def route_validation(s):
        if any(i["severity"] == "error" for i in s["issues"]) and s["repairs"] < s["max_repairs"]:
            return "repair"
        if s["review_policy"] == "always" or s["issues"]:
            return "review"
        return "export"

    def repair_node(s):
        return {
            "batch": agent.extract(s, repair=True),
            "repairs": s["repairs"] + 1,
            "status": "repaired",
        }

    def review_node(s):
        error = ""
        while True:
            payload = interrupt(
                {
                    "run_id": s["run_id"],
                    "project": s["project"],
                    "issues": s["issues"],
                    "batch": s["batch"],
                    "review_error": error,
                    "schema": Review.model_json_schema(),
                }
            )
            try:
                decision = Review.model_validate(payload)
                if not decision.reason.strip() or not decision.reviewer.strip():
                    raise ValueError("复核原因与复核人不能为空")
                if not decision.approved:
                    return {
                        "status": "rejected",
                        "reviewed": True,
                        "review_reason": decision.reason,
                        "reviewer": decision.reviewer,
                    }
                batch = Extraction.model_validate(s["batch"])
                by_id = {c.object_id: c for c in batch.records}
                for fix in decision.corrections:
                    if fix.object_id not in by_id:
                        raise ValueError("复核对象 ID 不存在")
                    item = by_id[fix.object_id]
                    record = item.record.model_dump(by_alias=True)
                    if fix.field not in record:
                        raise ValueError("修订字段不在 16 字段契约中")
                    record[fix.field] = fix.value
                    item.record = item.record.model_validate(record)
                    item.field_evidence[fix.field] = fix.evidence_ids
                issues = validate_task(
                    batch, [Evidence.model_validate(e) for e in s["ocr"]], s["pages"]
                )
                if any(i["severity"] == "error" for i in issues):
                    raise ValueError(
                        "复核修订仍含证据错误：" + json.dumps(issues, ensure_ascii=False)
                    )
                return {
                    "batch": batch.model_dump(by_alias=True),
                    "issues": issues,
                    "status": "reviewed",
                    "reviewed": True,
                    "review_reason": decision.reason,
                    "reviewer": decision.reviewer,
                    "memory_proposals": [m.model_dump() for m in decision.memories],
                }
            except (ValueError, ValidationError) as exc:
                error = str(exc)

    def memory_node(s):
        from .contracts import MemoryProposal

        memory.remember(
            s["project"],
            [MemoryProposal.model_validate(m) for m in s.get("memory_proposals", [])],
            s["run_id"],
            s["reviewer"],
        )
        return {"status": "memory_updated"}

    def export_node(s):
        from pathlib import Path

        output = Path(s["output_dir"])
        batch = Extraction.model_validate(s["batch"])
        write_json(
            output / "results.json",
            [c.record.model_dump(by_alias=True) for c in batch.records],
        )
        write_json(
            output / "evidence.json",
            {"pages": s["pages"], "batch": s["batch"], "ocr_snapshot": s["ocr"]},
        )
        write_json(
            output / "audit.json",
            {
                "run_id": s["run_id"],
                "project": s["project"],
                "mode": s["mode"],
                "status": "completed",
                "reviewed": s["reviewed"],
                "reviewer": s.get("reviewer"),
                "review_reason": s.get("review_reason"),
                "issues": s["issues"],
                "tools_used": s["tools_used"],
                "agent_rounds": s["agent_rounds"],
                "repairs": s["repairs"],
                "tool_events": s["tool_events"],
                "retrieval": [
                    {k: d[k] for k in ("id", "citation", "score", "content_hash")}
                    for d in s["documents"]
                ],
                "skills": [
                    {"name": v["name"], "version": v["version"]} for v in s["active_skills"]
                ],
                "prompt_hashes": {
                    p.name: digest(p.read_bytes()) for p in (ASSETS / "prompts").glob("*.md")
                },
                "embedding": index.embedding.fingerprint,
                "timeline": s.get("timeline", []),
                "record_count": len(batch.records),
            },
        )
        return {"status": "completed"}

    def timed(name, fn):
        def node(s):
            start = time.perf_counter()
            value = fn(s)
            value["timeline"] = [
                {
                    "node": name,
                    "elapsed_ms": round((time.perf_counter() - start) * 1000, 2),
                }
            ]
            return value

        node.__name__ = name
        return node

    graph = StateGraph(AgentState)
    for name, fn in [
        ("prepare", prepare_node),
        ("retrieve", retrieve_node),
        ("agent", reason_node),
        ("tools", tools_node),
        ("extract", extract_node),
        ("validate", validate_node),
        ("repair", repair_node),
        ("review", review_node),
        ("memory", memory_node),
        ("export", export_node),
    ]:
        graph.add_node(name, timed(name, fn))
    graph.add_edge(START, "prepare")
    graph.add_edge("prepare", "retrieve")
    graph.add_edge("retrieve", "agent")
    graph.add_conditional_edges(
        "agent",
        lambda s: "tools" if s["messages"][-1].tool_calls else "extract",
        {"tools": "tools", "extract": "extract"},
    )
    graph.add_conditional_edges(
        "tools",
        lambda s: "extract" if s["agent_rounds"] >= s["max_rounds"] else "agent",
        {"agent": "agent", "extract": "extract"},
    )
    graph.add_edge("extract", "validate")
    graph.add_conditional_edges(
        "validate",
        route_validation,
        {"repair": "repair", "review": "review", "export": "export"},
    )
    graph.add_edge("repair", "validate")
    graph.add_conditional_edges(
        "review",
        lambda s: "reject" if s["status"] == "rejected" else "memory",
        {"reject": END, "memory": "memory"},
    )
    graph.add_edge("memory", "export")
    graph.add_edge("export", END)
    return graph.compile(checkpointer=checkpointer)
