"""Check the local SDK, or explicitly send a small synthetic trace with --send."""
# 检查追踪 SDK，而不是执行图纸识别；默认只在本地计算2+3。
# 只有显式使用 --send，脚本才尝试认证并发送一条合成追踪。
# 报告只说明密钥是否存在，不打印密钥；不需要豆包模型即可验证 LangSmith 接入。

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from importlib.metadata import version
from pathlib import Path
from uuid import uuid4

from dotenv import load_dotenv
from langchain_core.runnables import RunnableLambda
from langsmith import Client, tracing_context
from langsmith.utils import LangSmithNotFoundError


# 默认关闭当前调用的追踪并验证 Runnable；--send 则认证、上传、flush，并读取同一 run_id。
# 云端读取保留有限等待时间，以容纳追踪入库延迟；不调用任何视觉模型。
def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--send", action="store_true", help="Upload one synthetic trace to LangSmith")
    args = parser.parse_args()
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    report = {
        "langsmith_version": version("langsmith"),
        "api_key_configured": bool(os.getenv("LANGSMITH_API_KEY")),
        "tracing_setting": os.getenv("LANGSMITH_TRACING", "false"),
        "project": os.getenv("LANGSMITH_PROJECT") or "conduit-drawing-workflows",
        "endpoint": os.getenv("LANGSMITH_ENDPOINT") or "https://api.smith.langchain.com",
        "workspace_id_configured": bool(os.getenv("LANGSMITH_WORKSPACE_ID")),
        "mode": "send" if args.send else "local",
    }
    # 显式发送但没有密钥时直接返回2，避免产生难以理解的后台认证报错。
    if args.send and not report["api_key_configured"]:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        print("请先在项目根目录 .env 填写 LANGSMITH_API_KEY，再使用 --send。")
        return 2

    chain = RunnableLambda(lambda value: {"sum": value["a"] + value["b"]}).with_config(
        run_name="langsmith-install-check"
    )
    if args.send:
        # Fail early on connection/authentication errors; the input is synthetic.
        client = Client(timeout_ms=10_000)
        list(client.list_projects(limit=1))
        run_id = uuid4()
        with tracing_context(enabled=True, client=client, project_name=report["project"]):
            result = chain.invoke({"a": 2, "b": 3}, config={"run_id": run_id})
        # 等待队列中的追踪完成提交；随后读取同一id，确认服务端确实能找到记录。
        client.flush()
        # Reading the exact run verifies persistence, beyond merely queuing an upload.
        deadline = time.monotonic() + 20
        while True:
            try:
                saved_run = client.read_run(run_id)
                break
            # 仅对尚未查到记录做短暂重试，鉴权或连接错误不会在这里被掩盖。
            except LangSmithNotFoundError:
                if time.monotonic() >= deadline:
                    raise
                time.sleep(2)
        report["cloud_trace_verified"] = str(saved_run.id) == str(run_id)
        report["run_id"] = str(run_id)
    else:
        # The local check remains offline even if the user's shell enables tracing.
        # 即使终端已设置LANGSMITH_TRACING=true，默认本地检查仍不上传本次数据。
        with tracing_context(enabled=False):
            result = chain.invoke({"a": 2, "b": 3})
        report["cloud_trace_verified"] = False
    assert result == {"sum": 5}
    report["result"] = result
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if not args.send:
        print("本地 SDK 和 LangChain 调用检查通过；使用 --send 可验证云端追踪。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
