"""Application boundary shared by CLI and HTTP API."""

from contextlib import ExitStack
from pathlib import Path
from uuid import uuid4

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command

from .config import ASSETS, identifier
from .graph import build_graph
from .memory import ProjectMemory
from .models import DemoAgent, VisionAgent
from .retrieval import KnowledgeIndex
from .skills import SkillRegistry
from .storage import write_json


class Runner:
    def __init__(self, settings):
        self.settings = settings

    def execute(
        self,
        *,
        run_id=None,
        project="demo",
        image=None,
        ocr_json=None,
        mode="demo",
        task="识别通信管井、独立桩号、连接关系并核对设备",
        review_policy="issues",
        simulate_error=False,
        force_review=False,
        resume=None,
        max_tools=6,
        max_rounds=3,
        max_repairs=1,
    ):
        run_id = identifier(run_id or uuid4().hex[:16])
        identifier(project)
        if mode not in ("demo", "live") or review_policy not in ("issues", "always"):
            raise ValueError("mode 或 review_policy 不合法")
        if not 0 <= max_tools <= 20 or not 1 <= max_rounds <= 8 or not 0 <= max_repairs <= 3:
            raise ValueError("预算超出允许范围")
        settings = self.settings
        config = {
            "configurable": {"thread_id": run_id},
            "recursion_limit": 80,
            "tags": ["drawflow", mode],
            "metadata": {"run_id": run_id, "project": project},
        }
        with ExitStack() as stack:
            saver = stack.enter_context(SqliteSaver.from_conn_string(str(settings.checkpoints)))
            index = KnowledgeIndex(settings)
            stack.callback(index.close)
            memory = ProjectMemory(settings.runtime / "memory.sqlite")
            # Read the mode from the existing checkpoint when resuming.
            probe = build_graph(settings, index, memory, SkillRegistry(), DemoAgent(), saver)
            snapshot = probe.get_state(config)
            if resume is not None:
                if not snapshot.next or not any(t.interrupts for t in snapshot.tasks):
                    raise ValueError("该运行没有等待复核的中断")
                mode = snapshot.values["mode"]
                project = snapshot.values["project"]
                config["tags"] = ["drawflow", mode, "review"]
                config["metadata"]["project"] = project
                value = Command(resume=resume)
            else:
                if snapshot.values:
                    raise ValueError("run_id 已存在，请使用新 ID 或 resume")
                if not index.client.collection_exists(index.collection):
                    index.ingest()
                if mode == "demo":
                    image = ASSETS / "demo/drawing.png"
                    ocr_json = ASSETS / "demo/ocr.json"
                if not image or not Path(image).is_file():
                    raise ValueError("请提供存在的图像或 PDF")
                if mode == "live" and (simulate_error or force_review):
                    raise ValueError("故障演示参数仅用于 demo 模式")
                value = {
                    "run_id": run_id,
                    "project": project,
                    "mode": mode,
                    "image": str(Path(image).resolve()),
                    "ocr_json": str(Path(ocr_json).resolve()) if ocr_json else "",
                    "task": task,
                    "review_policy": review_policy,
                    "simulate_error": simulate_error,
                    "force_review": force_review,
                    "max_tools": max_tools,
                    "max_rounds": max_rounds,
                    "max_repairs": max_repairs,
                }
            graph = build_graph(
                settings,
                index,
                memory,
                SkillRegistry(),
                DemoAgent() if mode == "demo" else VisionAgent(),
                saver,
            )
            # Do not hold stale executable behavior across separate CLI invocations.
            result = graph.invoke(value, config)
            current = graph.get_state(config)
            pending = [i.value for t in current.tasks for i in t.interrupts]
            summary = {
                "run_id": run_id,
                "project": project,
                "status": "awaiting_review" if pending else result["status"],
                "output_dir": result["output_dir"],
                "checkpoint": str(settings.checkpoints),
            }
            if pending:
                summary["review_request"] = pending[0]
                write_json(Path(summary["output_dir"]) / "review_request.json", pending[0])
            write_json(
                Path(summary["output_dir"]) / "run.json",
                {k: v for k, v in summary.items() if k != "review_request"},
            )
            return summary
