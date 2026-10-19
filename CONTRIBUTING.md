# 参与开发

按 README 创建虚拟环境，执行 `python -m pip install -e ".[dev]"`。

修改后运行 `python -m pytest -q`，再运行离线 mock 和参考回放。新识别规则需说明证据来源，避免将人工转录结果描述为模型准确率。

提交前检查 `git status --short` 和 `git diff --cached`。不提交密钥、客户图纸、运行日志、数据库或未经授权的数据。模型与 OCR 配置只写入本机 `.env`；新增配置同时更新 `.env.example` 和相关文档。

说明问题时附复现命令、Python 版本、预期及实际行为，并移除敏感内容。提交改动时说明原因与验证方式。
