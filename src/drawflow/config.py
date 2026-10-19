from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ASSETS = Path(__file__).parent / "assets"


def identifier(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}", value):
        raise ValueError("ID 使用 1–80 位字母、数字、下划线或连字符")
    return value


@dataclass(frozen=True)
class Settings:
    home: Path
    embedding_backend: str = "hash"
    collection: str = "drawflow_knowledge"
    qdrant_url: str = ""

    @classmethod
    def load(cls, home: str | Path | None = None):
        root = Path(home or os.getenv("DRAWFLOW_HOME", ".")).resolve()
        load_dotenv(root / ".env", override=False)
        os.environ.setdefault("LANGSMITH_TRACING", "false")
        return cls(
            root,
            os.getenv("EMBEDDING_BACKEND", "hash"),
            os.getenv("QDRANT_COLLECTION", "drawflow_knowledge"),
            os.getenv("QDRANT_URL", ""),
        )

    @property
    def runtime(self):
        path = self.home / "runtime"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def checkpoints(self):
        return self.runtime / "checkpoints.sqlite"
