"""Project utility scripts; OCR dependencies live in the separate OCR environment."""
# 运行和维护脚本所在目录。业务代码位于 src/conduit，不在这里重复实现。
# 此文件也使 uvicorn 可以按 scripts.serve_paddleocr:app 找到本机 OCR 服务。
