"""Single entry point for the drawing recognition workflow."""
# 图纸项目的日常运行入口；本文件只转交参数，完整逻辑见 conduit.cli.main。
# 从项目目录运行：python .\scripts\run.py --mock。
# 模型调用使用 LangChain，流程控制使用 LangGraph，二者运行在同一套代码中。

from conduit.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
