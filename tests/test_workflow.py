from pathlib import Path

import pytest

from drawflow.config import ASSETS
from drawflow.memory import ProjectMemory
from drawflow.runner import Runner
from drawflow.storage import read_json


def decision():
    # Keep the public fixture contract checked by every review regression.
    return read_json(Path(__file__).parents[1] / "examples/review.json")


def test_repair_tools_and_export(settings):
    result = Runner(settings).execute(run_id="repair", simulate_error=True)
    assert result["status"] == "completed"
    out = Path(result["output_dir"])
    audit = read_json(out / "audit.json")
    assert audit["tools_used"] == 4 and audit["repairs"] == 1 and not audit["issues"]
    assert audit["prompt_hashes"] and audit["retrieval"] and audit["skills"]
    assert {e["name"] for e in audit["tool_events"]} == {
        "ocr_region",
        "search_knowledge",
        "validate_chainage",
        "recall_project_memory",
    }
    actual = read_json(out / "results.json")
    expected = [c["record"] for c in read_json(ASSETS / "demo/batch.json")["records"]]
    assert actual == expected


def test_budget_applies_to_multi_call_message(settings):
    result = Runner(settings).execute(run_id="budget", max_tools=1)
    audit = read_json(Path(result["output_dir"]) / "audit.json")
    assert audit["tools_used"] == 1
    assert sum(e["error"] for e in audit["tool_events"]) == 3


def test_review_rejects_bad_fix_then_recovers(settings):
    first = Runner(settings).execute(run_id="review", project="highway-a", force_review=True)
    assert first["status"] == "awaiting_review"
    bad = decision()
    bad["corrections"][0]["value"] = "K999+999"
    second = Runner(settings).execute(run_id="review", resume=bad)
    assert second["status"] == "awaiting_review"
    assert second["review_request"]["review_error"]
    memory = ProjectMemory(settings.runtime / "memory.sqlite")
    assert memory.recall("highway-a") == []
    third = Runner(settings).execute(run_id="review", resume=decision())
    assert third["status"] == "completed" and third["project"] == "highway-a"
    assert memory.recall("highway-a")[0]["reviewer"] == "portfolio-reviewer"
    assert memory.recall("highway-b") == []


def test_rejected_has_no_results_or_memory(settings):
    Runner(settings).execute(run_id="rejected", force_review=True)
    output = Runner(settings).execute(
        run_id="rejected",
        resume={"approved": False, "reviewer": "tester", "reason": "重新识别"},
    )
    assert output["status"] == "rejected"
    assert not (Path(output["output_dir"]) / "results.json").exists()
    assert ProjectMemory(settings.runtime / "memory.sqlite").recall("demo") == []


def test_no_silent_overwrite_and_no_resume_completed(settings):
    runner = Runner(settings)
    runner.execute(run_id="unique")
    with pytest.raises(ValueError, match="已存在"):
        runner.execute(run_id="unique")
    with pytest.raises(ValueError, match="没有等待"):
        runner.execute(run_id="unique", resume=decision())


def test_always_review_and_project_memory_used_next_run(settings):
    first = Runner(settings).execute(run_id="review-all", project="sample", review_policy="always")
    assert first["status"] == "awaiting_review"
    Runner(settings).execute(run_id="review-all", resume=decision())
    assert Runner(settings).execute(run_id="next", project="sample")["status"] == "completed"
    from langgraph.checkpoint.sqlite import SqliteSaver

    from drawflow.graph import build_graph
    from drawflow.models import DemoAgent
    from drawflow.retrieval import KnowledgeIndex
    from drawflow.skills import SkillRegistry

    index = KnowledgeIndex(settings)
    try:
        with SqliteSaver.from_conn_string(str(settings.checkpoints)) as saver:
            graph = build_graph(
                settings,
                index,
                ProjectMemory(settings.runtime / "memory.sqlite"),
                SkillRegistry(),
                DemoAgent(),
                saver,
            )
            state = graph.get_state({"configurable": {"thread_id": "next"}}).values
            assert state["memories"][0]["key"] == "group-naming"
    finally:
        index.close()
