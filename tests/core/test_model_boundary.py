# 保留真实的消息模板和 LCEL 调用过程，只把外部模型替换为可检查的 FakeModel。
# 验证图片内容块、OCR 上下文及三种结构化输出参数，不消耗模型 API。
import json

import pytest
from langchain_core.runnables import RunnableLambda

from conduit.extract import Extractor
from conduit.schema import Layout, Observation


# 参数化覆盖工具调用、JSON Schema和JSON模式；检查图文块、OCR和阶段调用顺序。
@pytest.mark.parametrize("method", ["function_calling", "json_schema", "json_mode"])
def test_real_message_construction_with_stubbed_model(monkeypatch, page, tmp_path, method):
    """Exercise the real LCEL prompt/parser path without making a paid request."""
    from PIL import Image
    import langchain_openai
    calls = []
    image = tmp_path / "small.png"
    Image.new("RGB", (20, 20), "white").save(image)

    # 代替外部聊天模型的最小测试对象，返回正式Schema对象而不发出网络请求。
    class FakeModel:
        # 确认Extractor确实把测试密钥传给模型构造器，没有绕过配置层。
        def __init__(self, **kwargs):
            assert kwargs["api_key"] == "test-only-key"
        # 模拟结构化接口，仍返回可参与真实LCEL组合的Runnable。
        def with_structured_output(self, schema, **kwargs):
            assert kwargs["method"] == method
            # 检查最终两条消息及Base64图片；按请求Schema分别生成布局和对象观察。
            def answer(prompt):
                messages = prompt.to_messages()
                assert len(messages) == 2 and isinstance(messages[1].content, list)
                blocks = messages[1].content
                assert blocks[-1]["image_url"]["url"].startswith("data:image/png;base64,")
                data = json.loads(blocks[0]["text"])
                assert data["ocr"][0]["id"] == "page"
                if method == "json_mode":
                    assert "JSON Schema" in messages[0].content
                calls.append(schema.__name__)
                if schema is Layout:
                    return Layout(drawing_style="表格对应型", legend_summary="测试输出")
                return Observation.model_validate(page["observation"])
            return RunnableLambda(answer)

    monkeypatch.setattr(langchain_openai, "ChatOpenAI", FakeModel)
    monkeypatch.setenv("ARK_API_KEY", "test-only-key")
    monkeypatch.setenv("VISION_MODEL", "test-model")
    monkeypatch.setenv("STRUCTURED_METHOD", method)
    settings = {"mock": False}
    context = {"index": 1, "views": [{"path": str(image), "bbox": [0, 0, 1, 1], "purpose": "整页"}]}
    extractor = Extractor()
    layout = extractor.layout(context, page["ocr"], settings)
    observation = extractor.extract(context, page["ocr"], settings, layout=layout)
    assert len(observation["wells"]) == 7
    assert calls == ["Layout", "Observation"]
