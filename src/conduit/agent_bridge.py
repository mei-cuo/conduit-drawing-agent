"""An explicit file boundary for Codex subagent/manual vision workers.

This module does not claim to call Codex's internal API from the application.
"""
# 子智能体文件接口：export_request 准备材料，read_response_page 验收返回的数据。
# 没有豆包 API 时，外部智能体可以按请求中的 Schema 看图并写响应文件。
# 应用只读写文件，不会自动启动 Codex 子智能体；图片和 OCR 摘要用于避免串用旧结果。
import hashlib
import json
import sys
from pathlib import Path

from .extract import load_knowledge
from .io import load_json, save_json
from .schema import Layout, Observation
from .service import RecognitionService


# 先固定字典键顺序和 JSON 分隔符，再计算 OCR 行列表的 SHA-256。
# 对象键的书写顺序不影响摘要；行顺序、文字、坐标或分数变化都会使摘要变化。
def ocr_digest(lines):
    text = json.dumps(lines, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# 执行准备和 OCR，导出图像路径、规则、Schema 及证据摘要给外部智能体。
# 返回请求字典并保存 agent_request.json；不执行模型识别或最终导出。
def export_request(state):
    service = RecognitionService()
    # 这里手动合并阶段更新，因为请求导出只执行前两个阶段，不经过整个状态图。
    state = {**state, **service.prepare(state)}
    state = {**state, **service.ocr(state)}
    prompt = Path(__file__).with_name("prompts").joinpath("extract.md").read_text(encoding="utf-8")
    request = {"version": 1, "purpose": "外部视觉智能体分别完成 Layout 分析及 Observation 提取",
               "instructions": prompt, "knowledge": load_knowledge(state["settings"].get("knowledge_dir")),
               # 将正式Schema一并交给外部智能体，使其响应可被同一套模型与规则接收。
               "layout_schema": Layout.model_json_schema(), "observation_schema": Observation.model_json_schema(),
               "pages": [{"page_index": page["index"], "image": page["image"], "views": page["views"],
                          "source_sha256": page["source_sha256"], "ocr_sha256": ocr_digest(ocr), "ocr": ocr}
                         for page, ocr in zip(state["pages"], state["ocr_pages"])]}
    output = Path(state["settings"]["out"]) / "agent_request.json"
    save_json(output, request)
    print(f"已导出智能体请求：{output}", file=sys.stderr)
    return request


# 按 page_index 找到唯一响应，再校验源图片摘要和当前 OCR 摘要。
# 返回该页条目；具体 Layout/Observation 的字段验证由 Extractor 继续执行。
def read_response_page(page, ocr, settings):
    response = load_json(settings["agent_response"])
    matches = [p for p in response["pages"] if p["page_index"] == page["index"]]
    # 既拒绝漏页，也拒绝同页重复响应，避免随机选中一份互相冲突的结果。
    if len(matches) != 1:
        raise ValueError("智能体响应必须为每页提供唯一结果")
    entry = matches[0]
    # 只修改图像或OCR中的任一部分，旧响应都会被拒绝；这不能证明观察本身正确。
    if entry["source_sha256"] != page["source_sha256"] or entry["ocr_sha256"] != ocr_digest(ocr):
        raise ValueError("智能体响应与本次图纸或 OCR 证据不一致，请重新导出请求")
    return entry
