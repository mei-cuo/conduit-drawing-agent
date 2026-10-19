# 图纸识别工作流

使用 LangChain 与 LangGraph 识别高速公路通信管道平面图中的管井、设备、桩号和连接关系，输出 16 个中文字段，并保存 OCR 证据与复核问题。

支持图片与多页 PDF、PaddleOCR HTTP 服务、OpenAI 兼容视觉 API、外部代理响应文件、有限自动修复及人工复核恢复。

![工作流](docs/images/workflow.svg)

## 安装

主程序需要 Python 3.11 或更高版本。以下命令从克隆后的仓库根目录执行。

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
Copy-Item .env.example .env
```

Linux/macOS 激活环境使用 `source .venv/bin/activate`，复制配置使用 `cp .env.example .env`。若 PowerShell 不允许激活，可直接使用 `.\.venv\Scripts\python.exe` 执行后续 Python 命令。

## 无密钥运行

```powershell
python -m conduit --mock --simulate-error --out outputs/demo
```

模拟数据演示校验与修复流程，不调用模型或 OCR 服务。

回放仓库中的参考图纸、历史 OCR 和视觉观察：

```powershell
python -m conduit --input data/examples/reference_drawing.png --ocr sidecar --ocr-json data/examples/reference_ocr_paddle.json --vision-backend agent-file --agent-response data/examples/reference_agent_response.json --out outputs/reference-replay
```

参考回放生成 12 条记录，不调用新的视觉模型。38# 平台关系、部分井类型和完整路段名称仍需复核；它不是自动识别准确率评测。

输出目录包含 `results.json`（字段结果）、`evidence.json`（观察与证据）、`audit.json`（模式与问题）以及页面切片。

## 识别新图纸

1. 按 [PaddleOCR 部署](docs/paddleocr_deployment.md) 创建独立 OCR 环境并启动服务。
2. 在 `.env` 填写 `ARK_API_KEY` 或 `OPENAI_API_KEY`、`VISION_MODEL`，核对 `OPENAI_BASE_URL` 与 `STRUCTURED_METHOD`。端点需支持图像输入及所选结构化输出方式。
3. 执行识别：

```powershell
python -m conduit --input path/to/drawing.pdf --ocr paddle-http --out outputs/live
```

没有模型 API 时，可按 [外部代理文件桥接](docs/agent_bridge.md) 导出请求并提供匹配的响应。LangSmith 追踪默认关闭，配置见 [接入说明](docs/langsmith_setup.md)。

## 人工复核

添加 `--human-review` 后，存在待复核问题时返回退出码 2，并保存 `review_request.json`、`run.json` 和 SQLite 检查点。使用 `run.json` 中的同一 thread ID 和 checkpoint 恢复：

```powershell
python -m conduit --thread-id YOUR_THREAD_ID --checkpoint path/to/checkpoints.sqlite --resume data/examples/review_decision.example.json
```

复核文件需包含 `approve: true` 与非空 `reason`，可附完整 `observations` 修订。退出码 0 表示导出成功，1 表示运行异常；结果是否仍有问题请查看 `audit.json`。

## 项目结构

```text
src/conduit/       识别、证据校验、工作流与 CLI
scripts/           OCR 服务及辅助工具
data/             样例、提示词与识别规则
docs/             教程、架构、部署与上传说明
tests/            业务规则、输入、模型边界与工作流测试
requirements/     主环境和独立 OCR 环境的依赖记录
.github/workflows/ GitHub 自动验证
```

`outputs/`、`runtime/` 和 `work_records/` 为本机产物，由 Git 忽略；运行时按需创建。`.env`、虚拟环境及缓存也不提交。

## 开发与验证

```powershell
python -m pytest -q
python -m conduit --help
```

GitHub Actions 在 Windows 和 Ubuntu 的 Python 3.11、3.12 上安装源码、运行测试及离线回放。OCR 模型下载和真实视觉 API 调用不属于离线验证。

- [文档目录](docs/README.md)
- [LangChain / LangGraph 教程](docs/langchain_tutorial.md)
- [工作流设计](docs/workflow_design.md)
- [上传 GitHub](docs/github_upload.md)
- [参与开发](CONTRIBUTING.md)

## 许可与样例来源

项目尚未指定开源许可证；公开仓库不自动授予他人开源使用权。发布者应选择适合的许可证，并确认参考图纸、原提示词及派生 OCR/观察数据的再分发授权。合成数据和参考回放数据的来源见 [数据说明](data/README.md)。
