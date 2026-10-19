from langchain_core.messages import AIMessage

from drawflow.config import ASSETS
from drawflow.contracts import Extraction
from drawflow.imaging import prepare
from drawflow.models import VisionAgent
from drawflow.storage import read_json


def test_live_model_binds_tools_images_and_schema(monkeypatch, tmp_path):
    calls = []
    expected = Extraction.model_validate(read_json(ASSETS / "demo/batch.json"))

    class Model:
        structured = False

        def __init__(self, **kwargs):
            calls.append(("init", kwargs["model"]))

        def bind_tools(self, tools):
            calls.append(("tools", tools))
            return self

        def with_structured_output(self, schema, method):
            calls.append(("schema", schema, method))
            self.structured = True
            return self

        def invoke(self, messages):
            calls.append(("invoke", messages))
            return expected if self.structured else AIMessage(content="完成复核")

    monkeypatch.setenv("OPENAI_API_KEY", "test-model-key")
    monkeypatch.setenv("VISION_MODEL", "vision-test")
    monkeypatch.setattr("drawflow.models.ChatOpenAI", Model)
    from langchain_core.messages import HumanMessage

    from drawflow.models import image_blocks

    state = {
        "messages": [
            HumanMessage(
                content=image_blocks(prepare(ASSETS / "demo/drawing.png", tmp_path / "pages"))
            )
        ]
    }
    agent = VisionAgent()
    agent.think(state, {"one": "typed-tool"})
    result = agent.extract(state)
    assert calls[1] == ("tools", ["typed-tool"])
    assert any(c[0] == "schema" and c[1] is Extraction for c in calls)
    assert result["records"][0]["record"]["主线桩号"] == "K116+266"
    content = state["messages"][0].content
    assert any(
        b["type"] == "image_url" and b["image_url"]["url"].startswith("data:image/png;base64,")
        for b in content
    )


def test_live_runner_uses_injected_model_and_persistent_state(settings, monkeypatch):
    from drawflow.models import DemoAgent
    from drawflow.runner import Runner

    class InjectedVision(DemoAgent):
        def think(self, state, tools, allow_tools=True):
            return AIMessage(content="基于输入图像完成候选提取")

    monkeypatch.setattr("drawflow.runner.VisionAgent", InjectedVision)
    value = Runner(settings).execute(
        run_id="live-test",
        mode="live",
        image=ASSETS / "demo/drawing.png",
        ocr_json=ASSETS / "demo/ocr.json",
    )
    assert value["status"] == "completed"
    from pathlib import Path

    audit = read_json(Path(value["output_dir"]) / "audit.json")
    assert audit["mode"] == "live"
