# 发布到 GitHub

本目录是一个独立项目，发布到新仓库或在既有仓库建立明确的新版本。先确定目标仓库，再执行：

```powershell
git init -b main
git add .
git diff --cached --stat
git commit -m "Build DrawFlow drawing agent"
git remote add origin https://github.com/YOUR_NAME/drawflow-agent.git
git push -u origin main
```

提交前检查 .env 与运行产物均被忽略。examples 中的图纸为本项目构造的合成演示资产，领域规范来自项目提供的提示词。根据发布方式补充作者信息和项目许可证。

仓库简介可用：

> Evidence-grounded drawing agent with LangGraph orchestration, hybrid RAG, Qdrant, project memory and human review.

建议 Topics：langchain、langgraph、langsmith、rag、qdrant、ocr、document-ai、human-in-the-loop、agent。
