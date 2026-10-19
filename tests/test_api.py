from fastapi.testclient import TestClient

from drawflow.api import create_app


def test_api_job_and_results(tmp_path, monkeypatch):
    monkeypatch.setenv("DRAWFLOW_API_KEY", "test-key")
    client = TestClient(create_app(tmp_path))
    assert client.get("/health").status_code == 200
    assert client.post("/runs", json={"run_id": "api-run"}).status_code == 401
    headers = {"X-API-Key": "test-key"}
    result = client.post("/runs", json={"run_id": "api-run"}, headers=headers)
    assert result.status_code == 200 and result.json()["status"] == "completed"
    assert len(client.get("/runs/api-run/results", headers=headers).json()) == 3
    assert client.post("/runs", json={"run_id": "api-run"}, headers=headers).status_code == 400
    pending = client.post(
        "/runs",
        json={"run_id": "api-review", "review_policy": "always"},
        headers=headers,
    )
    assert pending.json()["status"] == "awaiting_review"
    assert client.get("/runs/api-review/results", headers=headers).status_code == 409
