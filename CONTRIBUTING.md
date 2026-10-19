# 开发指南

```powershell
python -m pip install -e ".[dev,api]"
python -m pytest -q
python -m drawflow evaluate
python -m build
```

规则变更同时维护 knowledge、Skill、结构化 Prompt 和相应用例。修改证据契约时，同步示例、复核文件和 contracts 文档。工具参数始终绑定任务上下文；长期记忆通过人工复核提交，保持项目隔离。

新增模型后端实现 think / extract 接口，Embedding 后端遵循 LangChain Embeddings。新增 OCR 后端应返回规范化 Evidence，并说明像素/归一化坐标转换。

提交说明包含问题、变化和验证方式。运行日志、检查点、密钥及个人图纸保留在本机忽略目录。
