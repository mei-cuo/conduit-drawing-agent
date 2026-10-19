# 支持在已安装项目的环境中使用 python -m conduit。
# 它与 scripts/run.py 调用同一个 main；SystemExit 把返回值变成进程退出码。
from .cli import main

raise SystemExit(main())
