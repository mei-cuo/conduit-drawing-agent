# 唯一的正式工作流：prepare → ocr → layout → extract → validate。
# validate 后可转向 repair、review 或 export；repair 完成后重新校验。
# 本文件决定什么时候执行；实际业务操作在 service.py，模型调用在 extract.py。
from typing import TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from conduit.schema import Observation
from conduit.service import RecognitionService


# 跨节点传递并可持久化的状态字典。total=False 允许起始任务只提供少量字段。
# 没有声明列表 reducer，因此节点返回的新列表覆盖旧列表；history 的追加由业务函数显式完成。
class DrawingState(TypedDict, total=False):
    # 流程标记与运行参数；配置是普通字典，不把模型客户端放进检查点。
    workflow: str
    settings: dict
    # 按页排列的输入证据及模型中间结果，各列表同一位置属于同一页。
    pages: list[dict]
    ocr_pages: list[list[dict]]
    layouts: list[dict]
    observations: list[dict]
    # 最终记录与待处理问题，validate会重新生成并覆盖这两项。
    records: list[dict]
    issues: list[dict]
    # 已执行修复轮数及逐轮问题历史，用来控制上限并保留审计信息。
    attempts: int
    history: list[dict]
    # 人工决策及最终产物路径；暂停时artifacts通常还未生成。
    review_decision: dict | None
    artifacts: dict


# 组装并编译工作流，返回可调用 invoke 的图对象。
# checkpointer 可传 SQLite 或内存保存器；service 可注入测试替身，默认使用正式业务实现。
def build_graph(checkpointer=None, service=None):
    # 注入业务对象便于测试；状态图本身只引用对象方法，不在这里复制识别逻辑。
    service = service or RecognitionService()
    # DrawingState 声明图中有哪些状态字段；各阶段只需返回自己的更新。
    builder = StateGraph(DrawingState)
    for name in ("prepare", "ocr", "layout", "extract", "validate", "repair", "export"):
        builder.add_node(name, getattr(service, name))

    # 校验后的分流规则，优先级是有限修复 → 人工复核 → 导出。
    # 只有 repairable=True 的问题能触发修复，并且 attempts 必须小于 max_repairs。
    def route(state):
        if any(x["repairable"] for x in state["issues"]) and state["attempts"] < state["settings"]["max_repairs"]:
            return "repair"
        if state["issues"] and state["settings"]["human_review"]:
            return "review"
        return "export"

    # 人工复核节点：interrupt 发出复核材料并暂停，恢复值作为 decision 返回。
    # approve=True 表示允许导出当前保守结果；如果附 observations，则先重新验证修订。
    def review(state):
        # No writes or model calls before interrupt: this node restarts on resume.
        # 恢复时此节点会从头执行，因此 interrupt 之前不能收费调用模型或写入外部系统。
        decision = interrupt({"message": "请核对证据；approve=true 保留保守结果，或提交完整 observations 修订。",
                              "records": state["records"], "issues": state["issues"],
                              "observations": state["observations"], "ocr_pages": state["ocr_pages"]})
        # 只有明确批准并提供理由，才继续导出；审核结论也会进入 audit.json。
        if not isinstance(decision, dict) or decision.get("approve") is not True or not decision.get("reason"):
            raise ValueError("人工决策必须包含 approve=true 和非空 reason")
        updates = {"review_decision": decision}
        # 人工可修改观察对象，但不能跳过 Schema 和独立 OCR 引用检查。
        if "observations" in decision:
            if len(decision["observations"]) != len(state["pages"]):
                raise ValueError("人工修订必须按页提供完整 observations")
            observations = [Observation.model_validate(x).model_dump() for x in decision["observations"]]
            checked = service.validate({**state, "observations": observations})
            updates.update(observations=observations, **checked)
        return updates

    builder.add_node("review", review)
    builder.add_edge(START, "prepare")
    for a, b in zip(("prepare", "ocr", "layout", "extract"), ("ocr", "layout", "extract", "validate")):
        builder.add_edge(a, b)
    # 条件边按 route 返回的名称选下一节点；修复完成后回到校验，而不是直接导出。
    builder.add_conditional_edges("validate", route, {"repair": "repair", "review": "review", "export": "export"})
    builder.add_edge("repair", "validate")
    builder.add_edge("review", "export")
    builder.add_edge("export", END)
    # 传入 checkpointer 才能持久化执行状态；CLI 使用 SQLite，部分测试使用内存保存器。
    return builder.compile(checkpointer=checkpointer)
