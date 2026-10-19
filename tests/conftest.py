import pytest

from drawflow.config import ASSETS, Settings
from drawflow.contracts import Evidence, Extraction
from drawflow.storage import read_json


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setenv("LANGSMITH_TRACING", "false")
    monkeypatch.setenv("EMBEDDING_BACKEND", "hash")
    monkeypatch.delenv("QDRANT_URL", raising=False)


@pytest.fixture
def settings(tmp_path):
    return Settings(tmp_path)


@pytest.fixture
def batch():
    return Extraction.model_validate(read_json(ASSETS / "demo/batch.json"))


@pytest.fixture
def ocr():
    return [Evidence.model_validate(e) for e in read_json(ASSETS / "demo/ocr.json")["evidence"]]
