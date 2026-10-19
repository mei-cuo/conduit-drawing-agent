# 根据启动脚本的service.json停止本项目OCR进程；不扫描或结束其他Python程序。
$ErrorActionPreference = 'Stop'
# 用脚本位置定位项目；即使终端切换目录，也读取同一份进程记录。
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$metadataPath = Join-Path $projectRoot 'runtime\logs\ocr-service\service.json'
if (-not (Test-Path -LiteralPath $metadataPath)) { throw '没有服务记录。' }
# PID可能被系统回收后分配给其他程序，因此还要读取实际进程信息核对身份。
$metadata = Get-Content -LiteralPath $metadataPath -Raw | ConvertFrom-Json
$serviceProcess = Get-CimInstance Win32_Process -Filter "ProcessId=$($metadata.pid)"
if (-not $serviceProcess) { Write-Output '服务已经停止。'; exit 0 }
# 必须同时匹配记录中的解释器和本项目的Uvicorn模块，任一不符就拒绝停止。
if ($serviceProcess.ExecutablePath -ne $metadata.python -or $serviceProcess.CommandLine -notlike '*scripts.serve_paddleocr:app*') { throw '进程身份不匹配，停止操作已取消。' }
# 只结束已核对的服务进程；保留日志和记录供后续排查，重复停止会提示已停止。
Stop-Process -Id $metadata.pid
Write-Output 'PaddleOCR 服务已停止。'
