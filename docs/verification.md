# 验证记录

日期：2026-10-19。环境：Windows、Python 3.14，独立虚拟环境。

| 验证项 | 结果 |
|---|---|
| pytest | 36 项通过 |
| Ruff lint / format | 通过 |
| Demo 故障修复 | 三条结果，四次工具调用，一次修复，零遗留问题 |
| 人工复核 | 暂停、无效修订重试、跨命令恢复、驳回路径通过 |
| Memory | 人工复核写入、后续任务读取、跨项目隔离通过 |
| Qdrant | 本地持久化、混合检索、重建删除失效点、指纹检查通过 |
| Embedding 缓存 | 重开实例复用缓存通过 |
| API | 健康检查、密钥认证、任务创建、状态、结果与待复核状态通过 |
| 模型边界 | 图像消息、工具绑定、结构化 Schema 与注入模型执行通过 |
| 输入处理 | PDF 分页、重叠切片、坐标映射、OCR 摘要与边界检查通过 |
| wheel | 构建成功；独立环境安装，从项目外目录执行演示和评估通过 |
| 依赖一致性 | pip check 通过 |

## 内置评估集

数据集：bundled-synthetic-v1。三条规则检索问题、三口手孔合成样例。

- Hit@3：1.0
- MRR：1.0
- 记录完全匹配：1.0
- Schema：通过
- 运行状态：completed

机器可读样例见 `examples/evaluation-result.json`；本机最新报告保存在 `outputs/evaluation-final.json`。

## 外部集成验证

视觉模型工具与结构化输出边界通过测试替身验证；真实模型、PaddleOCR 推理、远程 Embedding 和 LangSmith 云端追踪按部署文档配置后运行。GitHub Actions 矩阵与 Docker 配置随源码交付，执行状态以对应环境运行结果为准。
