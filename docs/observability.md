# LangSmith 与评估

## 追踪配置

在工作目录的 .env 填写 LANGSMITH_TRACING=true、LANGSMITH_API_KEY 和 LANGSMITH_PROJECT。每次图调用携带 run_id、project 与 mode。模型及工具使用 LangChain 原生 callback，知识入库与混合检索使用 @traceable 标记。

建议在同一个项目中按提示词版本、Embedding 后端与图纸类别比较运行。audit.json 保存每个 Prompt 的 SHA-256、规则 content_hash、Skill 版本和工具耗时，可与任务 ID 一起检索。

开启云端追踪后，模型与工具输入输出会进入配置的 LangSmith 服务；图像可能包含在模型消息中。根据图纸资料的使用范围决定追踪配置。需要减少上传内容时，可使用 LangSmith 的 LANGSMITH_HIDE_INPUTS=true、LANGSMITH_HIDE_OUTPUTS=true 环境变量。

## 本地评估

`python -m drawflow evaluate` 在临时工作目录构建独立 Qdrant 索引和检查点，测量：

- retrieval_hit_at_3：目标来源是否出现在前三个结果。
- retrieval_mrr：目标来源首次命中的倒数排名均值。
- record_exact_match：合成图纸记录与预期 JSON 的逐条完全匹配率。
- schema_valid、remaining_errors、repair_attempts、tools_used：执行过程指标。

内置数据标记为 bundled-synthetic-v1，三条规则问题与三口手孔覆盖字段流转、检索和修复路径。拓展真实图纸评估时，建议固定图纸、OCR 版本、人工标注和模型配置，分别记录字段准确率、漏井、设备关联、桩号归属及人工复核比例。

## 官方资料

- [LangGraph Interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts)
- [LangGraph Persistence](https://docs.langchain.com/oss/python/langgraph/persistence)
- [LangSmith tracing quickstart](https://docs.langchain.com/langsmith/observability-quickstart)
- [Qdrant client](https://python-client.qdrant.tech/)
