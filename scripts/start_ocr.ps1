# 启动独立的本机 PaddleOCR HTTP 服务。
# 从项目目录执行 .\scripts\start_ocr.ps1；可用 -Port 指定其他监听端口。
# 本脚本负责进程和日志，不执行图纸的模型识别；OCR实际加载在收到请求时发生。
param([int]$Port = 8008, [string]$PythonPath)
# 任一步失败就停止脚本，避免启动条件不满足时仍写出误导性的进程记录。
$ErrorActionPreference = 'Stop'
# 按脚本自身位置定位项目，优先使用仓库内 OCR 环境。
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
# OCR依赖位于.ocr-venv，主程序的.venv不需要安装Paddle推理库。
if (-not $PythonPath) { $PythonPath = Join-Path $projectRoot '.ocr-venv\Scripts\python.exe' }
$pythonPath = (Resolve-Path -LiteralPath $PythonPath).Path
if (-not (Test-Path -LiteralPath $pythonPath)) { throw 'OCR 环境不存在，请按 docs/paddleocr_deployment.md 安装。' }
# 进程信息、标准输出和错误日志集中放在runtime，便于排查HTTP启动或模型加载失败。
$outputDirectory = Join-Path $projectRoot 'runtime\logs\ocr-service'
New-Item -ItemType Directory -Force -Path $outputDirectory | Out-Null
# 端口已有监听时拒绝重复启动，不擅自结束原有进程。
$existing = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue
if ($existing) { throw "端口 $Port 已被占用；请先检查现有服务或指定其他端口。" }
# Uvicorn按模块名找到FastAPI的app；工作目录设为项目，确保scripts包可被导入。
# 仅绑定127.0.0.1；隐藏窗口运行，PassThru返回进程对象，便于记录它的PID。
$process = Start-Process -FilePath $pythonPath -ArgumentList @('-m','uvicorn','scripts.serve_paddleocr:app','--host','127.0.0.1','--port',"$Port") -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $outputDirectory 'stdout.log') -RedirectStandardError (Join-Path $outputDirectory 'stderr.log')
# 停止脚本会核对PID、解释器和服务模块；不要只凭PID就认定进程仍属于本项目。
@{pid=$process.Id;port=$Port;python=$pythonPath;started=(Get-Date).ToString('o')} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $outputDirectory 'service.json') -Encoding utf8
# 这里表示已创建进程；HTTP是否就绪、模型是否加载，还需通过/health及实际OCR请求确认。
Write-Output "PaddleOCR 服务已启动：PID=$($process.Id)，http://127.0.0.1:$Port，日志：$outputDirectory"
