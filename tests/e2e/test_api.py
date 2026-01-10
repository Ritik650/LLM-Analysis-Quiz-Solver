"""End-to-end tests hitting the FastAPI app with the TestClient.

The real Gemini app is swapped for a FakeChatModel-backed graph so /solve runs
the full pipeline (auth -> run row -> background agent -> steps -> metrics ->
finalize) with no API key.
"""
from __future__ import annotations

import time

import pytest

import agent
from eval.fake_llm import FakeChatModel
from eval.mock_quiz import start_mock_quiz, stop_mock_quiz


@pytest.fixture()
def mock_quiz():
    base, server = start_mock_quiz({"arith": [("2+2", "4"), ("10*3", "30")]})
    yield base
    stop_mock_quiz(server)


@pytest.fixture()
def fake_default_app(monkeypatch):
    app = agent.build_app(FakeChatModel())
    monkeypatch.setattr(agent, "get_default_app", lambda: app)
    yield


def _wait_for_run(client, run_id, headers, timeout=30.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        resp = client.get(f"/runs/{run_id}", headers=headers)
        if resp.status_code == 200 and resp.json()["status"] in ("success", "failed"):
            return resp.json()
        time.sleep(0.25)
    raise AssertionError("run did not finish in time")


def test_solve_requires_auth(client):
    resp = client.post("/solve", json={"url": "http://x"})
    assert resp.status_code == 401


def test_healthz(client):
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_full_solve_flow(client, auth_token, mock_quiz, fake_default_app):
    headers = auth_token["headers"]

    resp = client.post("/solve", json={"url": f"{mock_quiz}/q/arith/1"}, headers=headers)
    assert resp.status_code == 202, resp.text
    run_id = resp.json()["run_id"]

    detail = _wait_for_run(client, run_id, headers)
    assert detail["status"] == "success"
    assert detail["success"] is True
    assert detail["tool_call_count"] == 6  # 2 steps x (download, run_code, post)
    assert detail["total_tokens"] > 0
    assert len(detail["steps"]) > 0

    # History is user-scoped and includes this run.
    runs = client.get("/runs", headers=headers).json()["runs"]
    assert any(r["id"] == run_id for r in runs)


def test_stream_replays_finished_run(client, auth_token, mock_quiz, fake_default_app):
    headers = auth_token["headers"]
    token = auth_token["token"]

    run_id = client.post(
        "/solve", json={"url": f"{mock_quiz}/q/arith/1"}, headers=headers
    ).json()["run_id"]
    _wait_for_run(client, run_id, headers)

    # SSE endpoint replays the persisted trace (token via query param).
    resp = client.get(f"/runs/{run_id}/stream?token={token}")
    assert resp.status_code == 200
    body = resp.text
    assert "event: tool" in body
    assert "event: done" in body


def test_legacy_secret_still_works(client, mock_quiz, fake_default_app):
    # Back-compat path: no JWT, shared SECRET in the body.
    resp = client.post(
        "/solve", json={"url": f"{mock_quiz}/q/arith/1", "secret": "legacy-shared-secret"}
    )
    assert resp.status_code == 202
    run_id = resp.json()["run_id"]

    # Legacy runs are anonymous (user_id=None), so poll the DB directly to
    # confirm completion (also releases the single-run lock for later tests).
    from persistence.db import SessionLocal
    from persistence.repository import RunRepository

    deadline = time.time() + 30
    status = None
    while time.time() < deadline:
        with SessionLocal() as s:
            run = RunRepository.get_run(s, run_id, user_id=None)
            status = run.status if run else None
        if status in ("success", "failed"):
            break
        time.sleep(0.25)
    assert status == "success"
