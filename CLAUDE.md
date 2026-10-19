# 项目约定

- 从仓库根目录安装：`python -m pip install -e ".[dev]"`；验证：`python -m pytest -q`。
- CLI 为 `python -m conduit`；业务逻辑位于 `src/conduit/`。
- 默认运行产物放入 `outputs/` 和 `runtime/`，不要提交 `.env`、数据库、日志或 `work_records/`。
- 新配置同步更新 `.env.example` 和对应部署文档。
- 图纸、OCR、代理响应通过摘要绑定；不要用旧响应识别新图纸。
- 不将合成数据或历史回放描述为实时识别或准确率结果。
- 架构见 `docs/workflow_design.md`，安装见 `README.md`。
