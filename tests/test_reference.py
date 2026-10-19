# 用人工转录的12列参考样例检查字段流转、表格对应和最终页号。
# 它验证程序处理这份样例的行为，不证明自动视觉识别有同样的准确率。
from conduit.paths import PROJECT_ROOT
from conduit.workflow import build_graph


# 回放人工转录样例，检查12条记录、三个代表桩号及印刷页号都按证据传递。
def test_reference_fixture_has_12_table_columns(state):
    state["settings"]["fixture"] = str(PROJECT_ROOT / "data/examples/reference_scene.json")
    result = build_graph().invoke(state)
    assert len(result["records"]) == 12
    by_number = {r["管井编号"]: r for r in result["records"]}
    assert by_number["34#"]["主线桩号"] == "K9+043"
    assert by_number["38#"]["主线桩号"] == "K9+395"
    assert by_number["45#"]["主线桩号"] == "K9+966"
    assert all(r["页号"] == "第17页" for r in result["records"])

