# LangSmith 安装与接入

LangSmith 用来查看程序执行的过程：每一步收到什么、返回什么，以及在哪里出错。SDK 已声明在 `pyproject.toml`，安装项目时会一并安装。查看追踪的网页入口是 [LangSmith 控制台](https://smith.langchain.com)。SDK 安装和云端账户配置需分别完成。[官方快速入门](https://docs.langchain.com/langsmith/observability-quickstart)

## 1. 检查本地安装

在 PowerShell 中运行：

```powershell
# 在克隆后的项目根目录执行
python .\scripts\check_langsmith.py
```

脚本会打印 SDK 版本、密钥是否已填写，并执行一个 `2 + 3` 的 LangChain 小例子。默认检查不调用模型，也不上传追踪。

## 2. 创建 LangSmith 密钥

登录控制台，进入 **Settings → API Keys**，创建个人使用的 Personal Access Token。把密钥填到项目根目录 `.env`，并将追踪设置改为 `true`：[账户和密钥说明](https://docs.langchain.com/langsmith/create-account-api-key)

```dotenv
LANGSMITH_TRACING=true
LANGSMITH_API_KEY=这里填写你的密钥
LANGSMITH_PROJECT=conduit-drawing-workflows
LANGSMITH_ENDPOINT=https://api.smith.langchain.com
LANGSMITH_WORKSPACE_ID=
```

端点要与账户区域对应；这里使用默认美国端点。只有密钥覆盖多个工作区时才需要填写 `LANGSMITH_WORKSPACE_ID`。LangSmith 密钥和豆包密钥各有用途：前者上传追踪，后者调用模型。这个检查例子不需要豆包 API。

## 3. 发送一条检查追踪

```powershell
python .\scripts\check_langsmith.py --send
```

脚本只发送 `a=2`、`b=3` 和计算结果，随后读取这条追踪确认已保存。输出 `cloud_trace_verified: true` 表示云端验证通过。打开控制台的 **Tracing**，找到 `conduit-drawing-workflows` 项目中的 `langsmith-install-check`；部分界面会先让你选择同名 Agent，再进入 Tracing。

连接或认证报错时，先检查密钥、端点和网络。密钥需由使用者自行配置。

## 4. 查看图纸工作流

统一入口已经读取根目录 `.env`。配置完成后可以先运行模拟样例，观察执行过程：

```powershell
python .\scripts\run.py --mock --out outputs/langsmith-demo
```

LangChain 和 LangGraph 原生支持 LangSmith 追踪。开启追踪后，这些调用的输入、输出和步骤会发送到配置的 LangSmith 服务。[官方接入说明](https://docs.langchain.com/langsmith/observability-quickstart)

终端环境变量优先于 `.env`。无需追踪时，将 `.env` 中的 `LANGSMITH_TRACING` 改回 `false`；如果终端也设置了它，需同步修改或移除。
