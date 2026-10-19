"""Drawing recognition operations used by the single LangGraph workflow."""
# 业务阶段层：把输入处理、OCR、模型观察、规则和导出封装成节点函数。
# 每个节点接收当前 state，返回要更新的字段；LangGraph 负责将这些字段合并到状态。
# pages、ocr_pages、layouts、observations 按同一页序排列，配对时不能打乱顺序。
import sys
from pathlib import Path

from .extract import Extractor, load_knowledge
from .io import OCRProvider, prepare_pages, save_json
from .rules import validate_page
from .schema import Record


# 组织可复用的阶段操作，保持模型处理与流程路由分离。
# 这个对象持有 OCR/模型适配器；客户端不写入持久化状态。
class RecognitionService:
    # 创建可复用适配器；模型链和直接 Paddle 引擎在真正需要时才初始化。
    def __init__(self):
        self.ocr_provider = OCRProvider()
        self.extractor = Extractor()

    # 进度写入 stderr，和结果 JSON 文件分开；workflow 只是日志/审计中的流程标记。
    @staticmethod
    def log(step, state):
        print(f"[{state.get('workflow', '?')}] {step}", file=sys.stderr)

    # 根据 settings 建立页面及切片，同时重置本次任务的修复计数和审核历史。
    # 返回值会合并到 state；这里只做输入准备，不识别文字。
    def prepare(self, state):
        self.log("预处理", state)
        return {"pages": prepare_pages(state["settings"]), "attempts": 0,
                "history": [], "review_decision": None}

    # 按页取得独立 OCR 证据，保持与 pages 相同顺序，供模型及校验器引用。
    def ocr(self, state):
        self.log("OCR", state)
        result = [self.ocr_provider.read(p, state["settings"]) for p in state["pages"]]
        return {"ocr_pages": result}

    # 逐页分析图例、表格和引线关系，产出与 pages 一一对应的 layouts。
    def layout(self, state):
        self.log("图例与表格分析", state)
        return {"layouts": [self.extractor.layout(p, ocr, state["settings"])
                             for p, ocr in zip(state["pages"], state["ocr_pages"])]}

    # 将每页图片、OCR 和布局一起交给 Extractor，产出待校验的 observations。
    def extract(self, state):
        self.log("符号、属性与连接提取", state)
        return {"observations": [self.extractor.extract(p, ocr, state["settings"], layout=layout)
                                 for p, ocr, layout in zip(state["pages"], state["ocr_pages"], state["layouts"])]}

    # 逐页调用确定性规则，将所有页面的 records/issues 汇总，再追加本轮校验历史。
    # 返回新结果覆盖上一轮结果，避免修复后同时保留两份对象；history 仍保留过程。
    def validate(self, state):
        self.log("规则校验", state)
        # 页数不一致会使 zip 静默丢掉多余项，这里先明确拒绝不完整观察。
        if len(state["observations"]) != len(state["pages"]):
            raise ValueError("观察数据与页面数量不一致")
        records, issues = [], []
        for page, obs, ocr in zip(state["pages"], state["observations"], state["ocr_pages"]):
            page_records, page_issues = validate_page(obs, ocr, page["index"], state["settings"].get("strict_names", False))
            records.extend(page_records)
            issues.extend(page_issues)
        # 追加本轮的问题快照；修复后即使字段正确，也能查到先前发生过什么。
        history = state.get("history", []) + [{"attempt": state.get("attempts", 0), "issues": issues}]
        return {"records": records, "issues": issues, "history": history}

    # 只重新提取含可修复问题的页面，并携带原观察和本页反馈。
    # 本节点不重跑 OCR、不重新分析 layout；attempts 按整轮重试加1。
    def repair(self, state):
        self.log("基于反馈重新识别", state)
        observations = list(state["observations"])
        # 非可修复问题不会单独触发模型重试；按页去重，防止一页多个问题造成重复调用。
        affected = {x["page_index"] for x in state["issues"] if x["repairable"]}
        for i, (page, ocr, layout) in enumerate(zip(state["pages"], state["ocr_pages"], state["layouts"])):
            if page["index"] in affected:
                feedback = [x for x in state["issues"] if x["page_index"] == page["index"]]
                observations[i] = self.extractor.extract(page, ocr, state["settings"],
                                                          previous=observations[i], feedback=feedback, layout=layout)
        return {"observations": observations, "attempts": state["attempts"] + 1}

    # 写出三类文件：results 给业务使用，evidence 便于回看原图，audit 记录问题和过程。
    # 即使人工允许导出，只要 issues 仍非空，requires_review 仍为 True。
    def export(self, state):
        self.log("JSON 与审计文件导出", state)
        root = Path(state["settings"]["out"]).resolve()
        # 导出前再核对最终契约，并用中文 alias 生成对外字段名。
        records = [Record.model_validate(x).model_dump(by_alias=True) for x in state["records"]]
        save_json(root / "results.json", records)
        # 证据文件保留原图、视图、OCR、布局及未裁剪的模型观察，便于追查字段来源。
        evidence = [{"page_index": p["index"], "image": p["image"], "views": p["views"], "ocr": ocr,
                     "layout": layout, "observation": obs}
                    for p, ocr, layout, obs in zip(state["pages"], state["ocr_pages"], state["layouts"], state["observations"])]
        save_json(root / "evidence.json", evidence)
        # 区分教学回放、真实OCR+外部观察以及真实模型API，避免把演示结果误当实测。
        mode = "fixture_replay" if state["settings"]["mock"] else ("live_ocr_external_agent" if state["settings"].get("vision_backend") == "agent-file" else "live_api")
        report = {"workflow": state["workflow"], "mode": mode,
                  "record_count": len(records), "repair_attempts": state.get("attempts", 0),
                  "requires_review": bool(state["issues"]), "review_decision": state.get("review_decision"),
                  "issues": state["issues"], "history": state["history"],
                  # settings 来自命令行参数，模型密钥通过环境读取；这里不主动将环境变量写入审计。
                  "settings": state["settings"],
                  "knowledge_sources": [x["source"] for x in load_knowledge(state["settings"].get("knowledge_dir"))]}
        save_json(root / "audit.json", report)
        return {"artifacts": {"results": str(root / "results.json"), "audit": str(root / "audit.json"),
                              "evidence": str(root / "evidence.json")}}
