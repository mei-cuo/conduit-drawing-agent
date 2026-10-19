# 验证外部智能体响应确实属于当前图片及当前 OCR，避免错误复用旧观察。
import json
from copy import deepcopy

import pytest

from conduit.agent_bridge import ocr_digest, read_response_page
from conduit.io import save_json


# 先验证匹配的响应可读取，再分别修改OCR和图片摘要，检查两种串用都会被拒绝。
def test_agent_response_is_bound_to_image_and_ocr(page, tmp_path):
    path = tmp_path / "agent.json"
    context = {"index": 1, "source_sha256": "source-one"}
    entry = {"page_index": 1, "source_sha256": "source-one", "ocr_sha256": ocr_digest(page["ocr"]),
             "layout": {}, "observation": page["observation"]}
    save_json(path, {"pages": [entry]})
    settings = {"agent_response": str(path)}
    assert read_response_page(context, page["ocr"], settings)["page_index"] == 1
    modified = deepcopy(page["ocr"])
    modified[0]["text"] = "other drawing"
    with pytest.raises(ValueError, match="不一致"):
        read_response_page(context, modified, settings)
    with pytest.raises(ValueError, match="不一致"):
        read_response_page({**context, "source_sha256": "other"}, page["ocr"], settings)
