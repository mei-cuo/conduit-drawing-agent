"""Project paths, independent of the shell's current directory."""
# 集中定义项目目录，避免各模块自行拼路径后指向不同位置。
# __file__ 指向本文件；parents[2] 从 src/conduit/paths.py 回到项目根目录。
# 这些默认路径不受当前终端目录影响；CLI 显式传入的相对路径则按终端目录解析。
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
EXAMPLES_DIR = PROJECT_ROOT / "data" / "examples"
KNOWLEDGE_DIR = PROJECT_ROOT / "data" / "knowledge"
OUTPUT_DIR = PROJECT_ROOT / "outputs"
CHECKPOINT_DIR = PROJECT_ROOT / "runtime" / "checkpoints"
