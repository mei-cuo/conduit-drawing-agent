# 上传到 GitHub

本目录已初始化本地 Git 仓库，分支为 `main`，尚未创建提交或关联远程仓库。也可使用准备好的干净压缩包，在解压目录执行 `git init -b main`。

## 检查和提交

从仓库根目录执行：

```powershell
git status --short
git add .
git diff --cached --stat
git diff --cached --name-only
git commit -m "Initial commit: drawing recognition workflow"
```

`.gitignore` 排除 `.env`、虚拟环境、缓存、运行输出、检查点、历史归档和本机规划记录。`.env.example`、参考图纸及派生 OCR/观察数据会提交。公开发布前确认这些材料的再分发授权，并选择项目许可证；当前没有添加 LICENSE。

如果 Git 要求配置作者，在本项目执行 `git config user.name "你的署名"` 和 `git config user.email "你的邮箱"`，然后重新提交。

## 关联远程仓库

在 [GitHub 新建仓库](https://github.com/new)，例如命名 `conduit-drawing-agent`，创建空仓库，不自动生成 README 或其他文件。将下面地址替换为自己的仓库：

```powershell
git remote add origin https://github.com/YOUR_NAME/conduit-drawing-agent.git
git push -u origin main
```

完成认证后推送；仓库中的 `.github/workflows/tests.yml` 会执行离线自动验证。请以 GitHub 上实际运行结果为准，本机检查不代表云端矩阵已通过。

## 后续更新

```powershell
git add .
git diff --cached --stat
git commit -m "Describe this change"
git push
```

本机运行环境的完整依赖快照放在 `requirements/`，日常安装以 `pyproject.toml` 为准。项目按源码仓库方式运行，克隆后使用 `pip install -e ".[dev]"`；当前不承诺独立 wheel 包内包含图纸和知识库。
