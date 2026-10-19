"""Verify actual OCR HTTP inference, persist response, and compare sample stations."""
# 实际验证已经启动的 OCR HTTP 服务：查健康状态 → 发图 → 核对文字。
# 只统计参考图片表格中12个桩号是否被逐字读出，不评估井与桩号的关联正确率。
# 输出到 runtime/logs/ocr-service，便于检查首次加载耗时和服务返回值。
import base64
import json
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]


# 用同一参考图请求本机接口，保存原响应及桩号逐字匹配统计；初次调用可能包含模型加载。
def main():
    started = time.perf_counter()
    with httpx.Client(timeout=240) as client:
        health = client.get("http://127.0.0.1:8008/health")
        health.raise_for_status()
        result = client.post("http://127.0.0.1:8008/ocr", json={
            "image_base64": base64.b64encode((ROOT / "data/examples/reference_drawing.png").read_bytes()).decode("ascii")})
        result.raise_for_status()
        data = result.json()
        loaded = client.get("http://127.0.0.1:8008/health").json()
    # 这里只设置本张参考图可核对的12个桩号，不把它当作完整标注集。
    expected = {"K9+043", "K9+163", "K9+285", "K9+315", "K9+395", "K9+475",
                "K9+525", "K9+635", "K9+745", "K9+775", "K9+850", "K9+966"}
    # 用集合做逐字匹配，只检查文字出现过，不检查出现位置、重复次数或井号关联。
    texts = {line["text"] for line in data["lines"]}
    report = {"health_before": health.json(), "health_after": loaded, "line_count": len(data["lines"]),
              "elapsed_seconds": round(time.perf_counter() - started, 2),
              "expected_reference_stations": sorted(expected), "exactly_matched_stations": sorted(expected & texts),
              "missing_stations": sorted(expected - texts),
              "note": "仅核对这张样例表格的12个已读桩号，不是完整图纸识别准确率"}
    output = ROOT / "runtime/logs/ocr-service"
    output.mkdir(parents=True, exist_ok=True)
    (output / "sample_response.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    (output / "verification.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
