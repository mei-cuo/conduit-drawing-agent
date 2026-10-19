"""Local operator API. Run with one worker or use Qdrant server for shared storage."""

from __future__ import annotations

import os
import secrets
from threading import Lock

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel

from .config import Settings, identifier
from .contracts import Review
from .runner import Runner
from .storage import read_json

lock = Lock()


class RunRequest(BaseModel):
    mode: str = "demo"
    project: str = "demo"
    run_id: str | None = None
    image: str | None = None
    ocr_json: str | None = None
    task: str = "识别通信管井、桩号与连接关系"
    review_policy: str = "issues"


def create_app(home=None):
    settings = Settings.load(home)
    app = FastAPI(title="DrawFlow Agent", version="0.1.0")

    def auth(x_api_key: str = Header(default="")):
        expected = os.getenv("DRAWFLOW_API_KEY", "")
        if expected and not secrets.compare_digest(x_api_key, expected):
            raise HTTPException(401, "API key 不匹配")

    @app.get("/health")
    def health():
        return {"status": "ok", "version": "0.1.0"}

    @app.post("/runs", dependencies=[Depends(auth)])
    def run(request: RunRequest):
        try:
            with lock:
                return Runner(settings).execute(**request.model_dump())
        except (ValueError, FileNotFoundError) as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.get("/runs/{run_id}", dependencies=[Depends(auth)])
    def status(run_id: str):
        try:
            return read_json(settings.home / "outputs" / identifier(run_id) / "run.json")
        except (ValueError, FileNotFoundError) as exc:
            raise HTTPException(404, str(exc)) from exc

    @app.post("/runs/{run_id}/review", dependencies=[Depends(auth)])
    def review(run_id: str, decision: Review):
        try:
            with lock:
                return Runner(settings).execute(run_id=run_id, resume=decision.model_dump())
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.get("/runs/{run_id}/results", dependencies=[Depends(auth)])
    def results(run_id: str):
        try:
            base = settings.home / "outputs" / identifier(run_id)
            if read_json(base / "run.json")["status"] != "completed":
                raise HTTPException(409, "当前运行尚未完成")
            return read_json(base / "results.json")
        except (ValueError, FileNotFoundError) as exc:
            raise HTTPException(404, str(exc)) from exc

    return app
