from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .config import Settings
from .retrieval import KnowledgeIndex
from .runner import Runner
from .storage import read_json, write_json


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(prog="drawflow", description="DrawFlow · 通信图纸 Agent")
    p.add_argument("--home", default=None, help="工作目录，默认当前目录")
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("ingest", help="构建内置知识索引").add_argument("--directory", type=Path)
    search = sub.add_parser("search")
    search.add_argument("query")
    search.add_argument("-k", type=int, default=4)
    for name in ("demo", "run"):
        c = sub.add_parser(name)
        c.add_argument("--run-id")
        c.add_argument("--project", default="demo" if name == "demo" else "default")
        c.add_argument("--task", default="识别通信管井、独立桩号、连接关系并核对设备")
        c.add_argument("--review", choices=["issues", "always"], default="issues")
        c.add_argument("--max-tools", type=int, default=6)
        if name == "run":
            c.add_argument("--input", type=Path, required=True)
            c.add_argument("--ocr-json", type=Path)
        else:
            c.add_argument("--simulate-error", action="store_true")
            c.add_argument("--force-review", action="store_true")
    resume = sub.add_parser("resume")
    resume.add_argument("--run-id", required=True)
    resume.add_argument("--decision", type=Path, required=True)
    memory = sub.add_parser("memory")
    memory.add_argument("--project", required=True)
    sub.add_parser("skills")
    status = sub.add_parser("status")
    status.add_argument("--run-id", required=True)
    evalp = sub.add_parser("evaluate")
    evalp.add_argument("--report", type=Path, default=Path("outputs/evaluation.json"))
    args = p.parse_args(argv)
    try:
        settings = Settings.load(args.home)
        command = args.command
        if command in ("ingest", "search"):
            index = KnowledgeIndex(settings)
            try:
                value = (
                    index.ingest(args.directory)
                    if command == "ingest"
                    else index.search(args.query, args.k)
                )
            finally:
                index.close()
        elif command in ("demo", "run", "resume"):
            if command == "resume":
                value = Runner(settings).execute(
                    run_id=args.run_id, resume=read_json(args.decision)
                )
            else:
                value = Runner(settings).execute(
                    run_id=args.run_id,
                    project=args.project,
                    mode="demo" if command == "demo" else "live",
                    image=getattr(args, "input", None),
                    ocr_json=getattr(args, "ocr_json", None),
                    task=args.task,
                    review_policy=args.review,
                    max_tools=args.max_tools,
                    simulate_error=getattr(args, "simulate_error", False),
                    force_review=getattr(args, "force_review", False),
                )
        elif command == "memory":
            from .memory import ProjectMemory

            value = ProjectMemory(settings.runtime / "memory.sqlite").recall(args.project)
        elif command == "skills":
            from .skills import SkillRegistry

            value = [
                {"name": s.name, "version": s.version, "description": s.description}
                for s in SkillRegistry().skills.values()
            ]
        elif command == "status":
            from .config import identifier

            value = read_json(settings.home / "outputs" / identifier(args.run_id) / "run.json")
        elif command == "evaluate":
            from .evaluation import evaluate

            value = evaluate(settings)
            write_json(args.report, value)
        display = dict(value) if isinstance(value, dict) else value
        if isinstance(display, dict) and "review_request" in display:
            display.pop("review_request")
            display["review_request_file"] = str(
                Path(display["output_dir"]) / "review_request.json"
            )
        print(json.dumps(display, ensure_ascii=False, indent=2))
        if isinstance(value, dict) and value.get("status") == "awaiting_review":
            return 2
        if isinstance(value, dict) and value.get("status") == "rejected":
            return 3
        return 0
    except Exception as exc:
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
