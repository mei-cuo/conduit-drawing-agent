# 流程回归测试：修复上限、人工复核、SQLite 持久化及命令行恢复。
# 使用教学观察和测试替身，不请求真实模型或本机 OCR 服务。
from conduit.paths import PROJECT_ROOT
import json
from copy import deepcopy
from pathlib import Path
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command
from conduit.workflow import build_graph
from conduit.cli import main
from conduit.io import load_json
from conduit.service import RecognitionService


# 首次故意使用不存在的OCR引用；一次修复应恢复原桩号，同时保留第一次问题历史。
def test_graph_repairs_only_one_initial_reference_error(state):
    state["settings"]["simulate_error"] = True
    result = build_graph().invoke(state)
    assert result["attempts"] == 1
    assert result["records"][0]["主线桩号"] == "K116+266"
    assert any(x["code"] == "invalid_reference" for x in result["history"][0]["issues"])
    assert not any(x["code"] == "invalid_reference" for x in result["issues"])



# 注入始终不能修好的替身服务，检查流程恰好执行到max_repairs，缺证据字段保留未知。
def test_unrepairable_model_is_bounded(state):
    # 故障替身用于测试路由终止条件，不代表正式模型的行为。
    class FailingService(RecognitionService):
        # 在正常教学观察中替换一个无效桩号引用，保证规则一定产生可修复问题。
        def extract(self, state):
            updates = super().extract(state)
            updates["observations"][0]["wells"][0]["main_station"] = {"text_id": "fake", "value": "K1+001"}
            return updates
        # 只递增轮数，不修正观察，用来检查状态图不会无限循环。
        def repair(self, state):
            return {"attempts": state["attempts"] + 1}
    state["settings"]["max_repairs"] = 2
    result = build_graph(service=FailingService()).invoke(state)
    assert result["attempts"] == 2
    assert result["records"][0]["主线桩号"] == "无法判断"



# 先在一个SQLite保存器中暂停，再创建新的保存器和图恢复，模拟进程重新启动。
# 审核后仍有问题时，审计不能因为approve=True就变成完全确定。
def test_sqlite_review_survives_new_graph_and_saver(state, tmp_path):
    state["settings"]["human_review"] = True
    config = {"configurable": {"thread_id": "restart-test"}}
    db = str(tmp_path / "checkpoints.sqlite")
    with SqliteSaver.from_conn_string(db) as saver:
        paused = build_graph(saver).invoke(state, config)
    assert paused["__interrupt__"]
    assert not (Path(state["settings"]["out"]) / "results.json").exists()
    with SqliteSaver.from_conn_string(db) as saver:
        resumed = build_graph(saver).invoke(Command(resume={"approve": True, "reason": "测试：已检查保守输出"}), config)
    assert resumed["artifacts"]
    assert resumed["review_decision"]["approve"] is True
    # Human acknowledgment does not erase uncertainty.
    assert load_json(resumed["artifacts"]["audit"])["requires_review"] is True



# 给人工修订塞入没有OCR证据的桩号，检查审核入口也必须重新执行业务校验。
def test_human_edits_are_revalidated(state):
    state["settings"]["human_review"] = True
    graph = build_graph(InMemorySaver())
    config = {"configurable": {"thread_id": "edited"}}
    paused = graph.invoke(state, config)
    observations = deepcopy(paused["observations"])
    observations[0]["wells"][0]["main_station"] = {"text_id": "station1", "value": "K999+999"}
    resumed = graph.invoke(Command(resume={"approve": True, "reason": "测试非法人工输入", "observations": observations}), config)
    assert resumed["records"][0]["主线桩号"] == "无法判断"



# 两次调用main分别启动和恢复任务；暂停返回2，带明确审核结论恢复后返回0并写结果。
def test_cli_pause_and_resume_different_invocations(tmp_path):
    root = PROJECT_ROOT
    out, checkpoint = tmp_path / "cli", tmp_path / "cli.sqlite"
    args = ["--mock", "--fixture", str(root / "data/examples/demo_scene.json"),
            "--knowledge-dir", str(root / "data/knowledge"), "--out", str(out), "--checkpoint", str(checkpoint),
            "--thread-id", "cli-test", "--human-review"]
    assert main(args) == 2
    decision = tmp_path / "decision.json"
    decision.write_text(json.dumps({"approve": True, "reason": "测试已检查"}), encoding="utf-8")
    assert main(["--checkpoint", str(checkpoint), "--thread-id", "cli-test", "--resume", str(decision)]) == 0
    assert load_json(out / "results.json")

