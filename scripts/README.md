# 运行脚本

从仓库根目录执行，先安装项目并激活虚拟环境。

| 文件 | 用途 |
|---|---|
| `run.py` | 图纸工作流的唯一入口 |
| `start_ocr.ps1`、`stop_ocr.ps1` | 启动或停止本机 OCR 服务 |
| `serve_paddleocr.py` | HTTP OCR 适配器，使用独立 `.ocr-venv` |
| `run_ocr_sample.py` | 在 OCR 环境中直接识别参考图纸 |
| `probe_ocr_service.py` | 验证 OCR HTTP 接口和样例桩号 |
| `check_langsmith.py` | 本地 SDK 检查；`--send` 发送合成追踪 |
| `normalize_ocr_result.py` | 转换实际 OCR 原始结果 |
| `annotate_results.py` | 在图纸上绘制已记录管井的位置 |
| `build_examples.py` | 生成合成/人工转录教学数据，会重写对应样例；日常运行不需要 |

正式识别、业务规则与流程代码均在 [src/conduit/](../src/conduit/)。
