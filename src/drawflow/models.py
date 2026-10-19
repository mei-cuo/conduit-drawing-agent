"""Live tool-calling vision model and a deterministic demonstration driver."""

import base64
import json
import os
from copy import deepcopy
from pathlib import Path

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from .config import ASSETS
from .contracts import Extraction
from .storage import read_json


def image_blocks(pages):
    blocks = []
    for page in pages:
        blocks.append(
            {
                "type": "text",
                "text": f"当前页 {page['page_id']}；原图 {page['width']}×{page['height']} 像素；切片坐标需映射到原图。",
            }
        )
        for source in [
            {"path": page["path"], "bbox": [0, 0, page["width"], page["height"]]},
            *page["tiles"],
        ]:
            blocks.append({"type": "text", "text": f"区域：{source['bbox']}"})
            encoded = base64.b64encode(Path(source["path"]).read_bytes()).decode()
            blocks.append(
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/png;base64,{encoded}",
                        "detail": "high",
                    },
                }
            )
    return blocks


class VisionAgent:
    def __init__(self):
        key = os.getenv("OPENAI_API_KEY")
        name = os.getenv("VISION_MODEL")
        if not key or not name:
            raise ValueError("live 模式需要 OPENAI_API_KEY 与 VISION_MODEL")
        self.model = ChatOpenAI(
            model=name,
            api_key=key,
            base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
            temperature=0,
            timeout=float(os.getenv("MODEL_TIMEOUT", "120")),
            max_retries=2,
            max_tokens=12000,
        )

    def think(self, state, tools, allow_tools=True):
        model = self.model.bind_tools(list(tools.values())) if allow_tools else self.model
        system = (ASSETS / "prompts/agent.md").read_text(encoding="utf-8")
        return model.invoke([SystemMessage(content=system), *state["messages"]])

    def extract(self, state, repair=False):
        system = (ASSETS / "prompts/extract.md").read_text(encoding="utf-8")
        extractor = self.model.with_structured_output(
            Extraction, method=os.getenv("STRUCTURED_METHOD", "function_calling")
        )
        messages = [
            SystemMessage(content=system),
            *state["messages"],
            HumanMessage(
                content="提交完整 Extraction。保留全部原始 OCR。"
                + (
                    json.dumps(
                        {"previous": state["batch"], "issues": state["issues"]},
                        ensure_ascii=False,
                    )
                    if repair
                    else ""
                )
            ),
        ]
        return extractor.invoke(messages).model_dump(by_alias=True)


class DemoAgent:
    """Scripted decisions exercise the same graph and real tool implementations."""

    def think(self, state, tools, allow_tools=True):
        if allow_tools and state.get("agent_rounds", 0) == 0:
            return AIMessage(
                content="检索桩号与拓扑规则，核对局部文字及项目约定。",
                tool_calls=[
                    {
                        "name": "search_knowledge",
                        "args": {"query": "主线桩号证据与直通分歧判断"},
                        "id": "demo-search",
                    },
                    {
                        "name": "ocr_region",
                        "args": {
                            "page_id": "p1",
                            "left": 80,
                            "top": 100,
                            "right": 620,
                            "bottom": 180,
                        },
                        "id": "demo-region",
                    },
                    {
                        "name": "validate_chainage",
                        "args": {"value": "K116+266", "page_id": "p1"},
                        "id": "demo-station",
                    },
                    {
                        "name": "recall_project_memory",
                        "args": {"query": "命名 复核"},
                        "id": "demo-memory",
                    },
                ],
            )
        return AIMessage(content="三口手孔沿主线连续连接，按标注组从左到右编号，依据独立桩号导出。")

    def extract(self, state, repair=False):
        batch = deepcopy(read_json(ASSETS / "demo/batch.json"))
        batch["evidence"] = [
            *deepcopy(state["ocr"]),
            *[e for e in batch["evidence"] if e["kind"] == "vision"],
        ]
        if state.get("simulate_error") and not repair:
            batch["records"][0]["record"]["主线桩号"] = "K999+999"
        if state.get("force_review"):
            batch["records"][0]["record"]["主线桩号"] = "无法判断"
            batch["records"][0]["record"]["备注"] = "桩号待人工确认"
        return batch
