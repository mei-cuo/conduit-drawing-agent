# 项目约定

- 安装：`python -m pip install -e ".[dev,api]"`；验证：`python -m pytest -q`。
- Agent 流程在 graph.py，CLI/API 共用 runner.py。
- 知识、Prompt、Skill 和演示资源在 src/drawflow/assets，需随 wheel 打包。
- OCR 原始快照不可被模型覆盖；字段修订再次运行证据校验。
- 长期记忆按项目隔离，只从通过的人工复核写入。
- 工具调用绑定任务页；模型参数不选择本机任意路径。
- 运行产物放 outputs/ 和 runtime/，密钥使用 .env。
- 配置变更同步 .env.example 与 docs/deployment.md。
- 设计见 docs/architecture.md，字段见 docs/contracts.md。
