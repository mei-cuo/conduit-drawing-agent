"""Reproducible retrieval and workflow evaluation, with locally measured metrics."""

from pathlib import Path
from tempfile import TemporaryDirectory

from .config import ASSETS, Settings
from .contracts import WellRecord
from .retrieval import KnowledgeIndex
from .runner import Runner
from .storage import read_json

CASES = [
    ("主线桩号引线和表格列如何对应", "chainage.md"),
    ("沿主线连接两个邻井如何区分直通分歧支路", "topology.md"),
    ("同名多井标注分组从左到右编号", "naming.md"),
]


def evaluate(settings):
    # Evaluation always gets a fresh local index and checkpoint namespace.
    with TemporaryDirectory(prefix="drawflow-eval-") as temp:
        config = Settings(Path(temp), settings.embedding_backend)
        index = KnowledgeIndex(config)
        try:
            index.ingest()
            retrieval = []
            for query, source in CASES:
                documents = index.search(query, k=3)
                sources = [d["source"] for d in documents]
                rank = sources.index(source) + 1 if source in sources else None
                retrieval.append(
                    {
                        "query": query,
                        "expected_source": source,
                        "sources": sources,
                        "rank": rank,
                        "hit_at_3": rank is not None,
                    }
                )
        finally:
            index.close()
        run = Runner(config).execute(run_id="eval-agent", simulate_error=True)
        base = Path(run["output_dir"])
        records = read_json(base / "results.json")
        audit = read_json(base / "audit.json")
        expected = [c["record"] for c in read_json(ASSETS / "demo/batch.json")["records"]]
        exact = sum(a == b for a, b in zip(records, expected))
        return {
            "dataset": "bundled-synthetic-v1",
            "retrieval_cases": retrieval,
            "retrieval_hit_at_3": sum(c["hit_at_3"] for c in retrieval) / len(retrieval),
            "retrieval_mrr": sum(1 / c["rank"] if c["rank"] else 0 for c in retrieval)
            / len(retrieval),
            "record_exact_match": exact / len(expected),
            "record_count": len(records),
            "schema_valid": all(WellRecord.model_validate(r) is not None for r in records),
            "remaining_errors": sum(i["severity"] == "error" for i in audit["issues"]),
            "repair_attempts": audit["repairs"],
            "tools_used": audit["tools_used"],
            "workflow_status": run["status"],
        }
