# PaddleOCR 下载与本机部署

## 部署方式

在仓库根目录创建独立 Python 3.12 OCR 环境 `.ocr-venv`。主程序使用 `.venv`，通过 HTTP 调用 OCR 服务。下列版本和耗时为历史 CPU 环境记录，完整流程需在自己的环境验证。

本次安装选择 CPU 版本。官方下载指南列出兼容的 Python 版本及 CPU/GPU 安装命令；项目使用其 CPU 安装渠道。[PaddlePaddle Windows 安装指南](https://www.paddlepaddle.org.cn/documentation/docs/install/pip/windows-pip_en.html)。

| 组件 | 本次安装版本 |
|---|---|
| Python | 3.12 |
| PaddlePaddle | 3.3.0，CPU |
| PaddleOCR | 3.7.0 |
| PaddleX | 3.7.2 |
| FastAPI | 0.143.0 |
| Uvicorn | 0.54.0 |

完整版本列表在 `requirements/requirements-ocr.lock.txt`。`requirements/requirements-ocr-service.txt` 是适配器依赖范围；迁移时优先参考本次锁定版本和官方兼容说明。

已下载的官方模型：

- `PP-OCRv5_server_det`：文本检测。
- `PP-OCRv5_server_rec`：文本识别。

本机缓存目录为 用户主目录下的 `.paddlex/official_models`。选择 PP-OCRv5 服务端模型作为固定基线，避免库升级后默认模型变化。关闭文档旋转/去畸变模块，保持 OCR 坐标与输入图纸的对应；默认检测长边上限 2000 像素，CPU 8 线程，关闭 MKLDNN 作为本机运行基线。

## 新电脑复现安装

```powershell
# 在克隆后的项目根目录执行
py -3.12 -m venv .\.ocr-venv
& .\.ocr-venv\Scripts\python.exe -m pip install --upgrade pip
& .\.ocr-venv\Scripts\python.exe -m pip install paddlepaddle==3.3.0 -i https://www.paddlepaddle.org.cn/packages/stable/cpu/
& .\.ocr-venv\Scripts\python.exe -m pip install -r requirements/requirements-ocr-service.txt
& .\.ocr-venv\Scripts\python.exe -c 'import paddle; paddle.utils.run_check()'
```

本次自检输出 `PaddlePaddle is installed successfully!`，随后完成实际样例推理。第一次初始化会下载模型，首次保存可视化还会下载字体，首次总耗时不能代表稳定推理速度。

## 启动与停止服务

```powershell
& .\scripts\start_ocr.ps1
Invoke-RestMethod http://127.0.0.1:8008/health
```

启动脚本以隐藏窗口运行 Uvicorn，只监听本机 `127.0.0.1:8008`，保存 PID 和日志到 `runtime/logs/ocr-service/`。`/health` 中 `engine_loaded=false` 表示 HTTP 服务已经启动、尚未初始化模型；成功识别后应为 true。

前台运行也可以：

```powershell
& .\.ocr-venv\Scripts\python.exe -m uvicorn scripts.serve_paddleocr:app --host 127.0.0.1 --port 8008
```

停止后台服务：

```powershell
& .\scripts\stop_ocr.ps1
```

不安装系统开机启动项。重新开机后按需启动；端口已有监听时脚本拒绝重复启动，请先核对服务身份。日志中缺少 ccache 的警告不代表推理失败，本次 CPU 自检和样例识别已通过。

## HTTP 契约

这是本项目编写的小型适配器，**不是 PaddleX 官方 serving API 的直接复制**。客户端 POST 到 `/ocr`：

```json
{"image_base64": "PNG/JPG 内容的纯 Base64，不带 data URL 前缀"}
```

返回：

```json
{
  "width": 1987,
  "height": 1406,
  "lines": [
    {"id": "t0001", "text": "17", "bbox": [0.91, 0.06, 0.93, 0.08], "confidence": 0.99}
  ]
}
```

上面只示意结构，不是完整实际响应。bbox 是输入整页的归一化坐标；ID 页内唯一。服务内部用 PaddleOCR 3.x `predict`，将 `Result.json` 中 `rec_texts`、`rec_scores`、`rec_boxes` 映射成工作流契约。

## 真实样例结果

运行实际推理与 HTTP 验证：

```powershell
& .\.ocr-venv\Scripts\python.exe .\scripts\run_ocr_sample.py
python .\scripts\probe_ocr_service.py
```

已完成的本地推理识别出 **117 行文字**，底部 34#～45# 对应的 12 个桩号均出现在 OCR 文本中：K9+043、K9+163、K9+285、K9+315、K9+395、K9+475、K9+525、K9+635、K9+745、K9+775、K9+850、K9+966。

这个计数仅表示文字读出；不代表桩号已正确关联到所有井，也不代表井/设备全部识别准确。

| 本次文件 | 内容 |
|---|---|
| `outputs/paddleocr_reference/raw.json` | PaddleOCR 原始实际结果 |
| `outputs/paddleocr_reference/ocr.json` | 可供 sidecar 模式读取的规范化结果 |
| `outputs/paddleocr_reference/*_ocr_res_img.png` | 实际检测框和文字的可视化 |
| `runtime/logs/ocr-service/sample_response.json` | 实际 HTTP 请求返回结果 |
| `runtime/logs/ocr-service/verification.json` | HTTP 健康状态、实际耗时、12 个参考桩号匹配记录 |

首次完整流程约 193.5 秒，包含模型和可视化字体下载；首次 HTTP 请求含模型载入用时 44.29 秒，117 行文字及 12 个桩号均返回，健康状态变为 `engine_loaded=true`。实际记录在 verification 文件中。主流程可用 `--ocr sidecar` 复用实际结果，防止每次重做 OCR。

## 接入工作流

`.env` 已预填本地 OCR 地址：

```dotenv
OCR_ENDPOINT=http://127.0.0.1:8008/ocr
```

```powershell
python -m conduit --input data/examples/reference_drawing.png --ocr paddle-http --export-agent-request --out outputs/agent-handoff
```

这个命令无需豆包密钥：完成真实预处理和 OCR，导出子智能体任务材料。子智能体文件桥接详见 `agent_bridge.md`。

如果以后切换 GPU，先按官方安装说明核对显卡驱动、Paddle 与 CUDA 版本，再调整服务初始化参数；当前已部署和验证的是 CPU 版本。
