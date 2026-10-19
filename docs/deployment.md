# 配置与部署

## 主程序

```powershell
python -m pip install -e ".[dev,api]"
Copy-Item .env.example .env
```

Linux/macOS 复制配置用 `cp .env.example .env`。程序只读取工作目录下的 .env，终端环境变量优先。`--home` 指定运行根目录；安装后的 wheel 同样包含知识、Prompt、Skill 和演示数据。

## PaddleOCR 独立环境

使用与 PaddlePaddle 兼容的 Python，建议单独建立 Python 3.12 环境。先按 [PaddlePaddle 官方安装页](https://www.paddlepaddle.org.cn/install/quick) 选择适合 CPU/CUDA 的安装命令，再安装适配器依赖：

```powershell
py -3.12 -m venv .ocr-venv
.\.ocr-venv\Scripts\python.exe -m pip install -r scripts/requirements-ocr.txt
.\.ocr-venv\Scripts\python.exe -m uvicorn scripts.serve_ocr:app --host 127.0.0.1 --port 8008
```

模型首次初始化会下载 PaddleOCR 模型。`/health` 返回 engine_loaded。设置 OCR_API_KEY 时，主程序与服务环境使用相同值；适配器进程从环境变量读取该值。

## Embedding 与 Qdrant

默认 hash Embedding + Qdrant Local，直接写入 runtime/。配置语义 Embedding 后重新 ingest。默认模型 text-embedding-3-small 可替换为对应服务支持的模型。

启用 Qdrant Server：

```powershell
docker compose up -d qdrant
```

在 .env 填写 `QDRANT_URL=http://127.0.0.1:6333`，按服务配置填写 QDRANT_API_KEY。主程序本地模式与服务模式使用相同的数据契约。

Qdrant Local 同时只允许一个进程打开存储。CLI、评估和 HTTP 服务应顺序访问同一工作目录；多个工作进程使用 Qdrant Server，并由任务调度层序列化相同 run_id。

## API 与容器

```powershell
python -m uvicorn drawflow.api:create_app --factory --host 127.0.0.1 --port 8000 --workers 1
```

配置 DRAWFLOW_API_KEY 后通过 X-API-Key 请求业务接口。API 接收服务机器可访问的输入文件路径，面向可信操作端。

```powershell
docker build -t drawflow-agent .
docker run --rm -p 127.0.0.1:8000:8000 --env-file .env -v drawflow_workspace:/workspace drawflow-agent
```

容器运行目录为 /workspace；任务产物与检查点位于挂载卷。处理本机图纸时，将图纸目录挂载到容器并使用容器中的文件路径。容器内访问独立 OCR 服务需要填写可达的 OCR_ENDPOINT。

## 环境变量

| 变量 | 用途 |
|---|---|
| OPENAI_API_KEY / OPENAI_BASE_URL / VISION_MODEL | live 视觉模型连接 |
| STRUCTURED_METHOD | function_calling、json_schema 或 json_mode，由端点能力决定 |
| MODEL_TIMEOUT | 模型单次请求超时秒数 |
| EMBEDDING_BACKEND | hash 或 openai |
| EMBEDDING_MODEL / EMBEDDING_BASE_URL / EMBEDDING_API_KEY | 向量模型连接 |
| QDRANT_URL / QDRANT_API_KEY / QDRANT_COLLECTION | 向量存储连接与集合 |
| OCR_ENDPOINT / OCR_API_KEY | OCR 适配器 |
| LANGSMITH_TRACING / LANGSMITH_API_KEY / LANGSMITH_PROJECT / LANGSMITH_ENDPOINT | 追踪服务 |
| DRAWFLOW_HOME | 运行根目录，默认当前目录；CLI --home 优先 |
| DRAWFLOW_API_KEY | API 业务接口的 X-API-Key |

## 运行材料

`.env`、runtime/、outputs/、虚拟环境与构建产物均由 Git 忽略。持久化备份需覆盖 checkpoints.sqlite、memory.sqlite、Embeddings 缓存与 Qdrant 存储。已完成任务可保留其三个交付 JSON 和 run.json 作为项目档案。
