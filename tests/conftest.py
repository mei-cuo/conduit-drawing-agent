# pytest 共用数据：page 是一页教学观察，state 是完整任务的起始状态。
# 每次测试获取独立副本和临时输出目录，避免测试间修改同一对象或覆盖真实结果。
from copy import deepcopy
from conduit.paths import PROJECT_ROOT

import pytest

from conduit.io import load_json

ROOT = PROJECT_ROOT


# 每个测试重新读取并深复制一页demo；测试可放心修改嵌套字典，不影响其他用例。
@pytest.fixture
def page():
    return deepcopy(load_json(ROOT / "data/examples/demo_scene.json")["pages"][0])


# 构造使用教学数据的起始状态，输出指向pytest临时目录，修复上限默认为1。
@pytest.fixture
def state(tmp_path):
    return {"workflow": "langgraph", "settings": {
        "mock": True, "fixture": str(ROOT / "data/examples/demo_scene.json"),
        "out": str(tmp_path / "out"), "knowledge_dir": str(ROOT / "data/knowledge"),
        "strict_names": False, "max_repairs": 1, "human_review": False,
        "simulate_error": False}}
