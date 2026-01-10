"""
Shared test configuration.

Environment is set BEFORE any app module is imported so `config.get_settings`
(and the SQLAlchemy engine built from it) pick up the test database and a
deterministic JWT secret. Tests never touch Gemini or the network beyond a
localhost mock server.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

_db_file = Path(tempfile.gettempdir()) / "quiz_agent_test.db"
if _db_file.exists():
    _db_file.unlink()

os.environ["JWT_SECRET"] = "test-secret-key-do-not-use-in-prod"
os.environ["JWT_EXPIRE_MINUTES"] = "60"
os.environ["EMAIL"] = "test@example.com"
os.environ["SECRET"] = "legacy-shared-secret"
os.environ["ALLOW_LEGACY_SECRET"] = "true"
os.environ["DATABASE_URL"] = f"sqlite:///{_db_file.as_posix()}"
os.environ["RUN_CODE_TIMEOUT"] = "60"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from persistence.db import SessionLocal, init_db  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _init_database():
    init_db()
    yield


@pytest.fixture()
def session():
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()


@pytest.fixture()
def client():
    from main import app

    with TestClient(app) as c:
        yield c


@pytest.fixture()
def auth_token(client):
    """Register a fresh user and return a bearer token + headers."""
    import uuid

    email = f"user_{uuid.uuid4().hex[:8]}@example.com"
    resp = client.post("/auth/register", json={"email": email, "password": "password123"})
    assert resp.status_code == 201, resp.text
    token = resp.json()["access_token"]
    return {"email": email, "token": token, "headers": {"Authorization": f"Bearer {token}"}}
