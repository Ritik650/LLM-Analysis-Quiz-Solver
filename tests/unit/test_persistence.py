"""Unit tests for the persistence repositories."""
from __future__ import annotations

import uuid

from persistence.repository import RunRepository, UserRepository


def _email():
    return f"u_{uuid.uuid4().hex[:8]}@example.com"


def test_user_create_and_authenticate(session):
    email = _email()
    user = UserRepository.create_user(session, email, "password123")
    assert user.id is not None
    assert UserRepository.authenticate(session, email, "password123") is not None
    assert UserRepository.authenticate(session, email, "wrong") is None


def test_api_key_lifecycle(session):
    user = UserRepository.create_user(session, _email(), "password123")
    record, raw = UserRepository.create_api_key(session, user, "ci")
    assert raw.startswith("qk_")
    # The raw key resolves back to the user...
    assert UserRepository.get_user_by_api_key(session, raw).id == user.id
    # ...until it is revoked.
    assert UserRepository.revoke_api_key(session, user, record.id)
    assert UserRepository.get_user_by_api_key(session, raw) is None


def test_run_create_append_finalize(session):
    run_id = str(uuid.uuid4())
    RunRepository.create_run(session, run_id, "http://quiz/1", user_id=None)
    RunRepository.append_step(session, run_id, seq=1, type="tool", name="run_code")
    RunRepository.append_step(session, run_id, seq=2, type="tool", name="post_request")
    run = RunRepository.finalize_run(
        session, run_id, status="success", success=True,
        total_tokens=1234, tool_call_count=2, est_cost_usd=0.01,
        final_result={"final_message": "END"},
    )
    assert run.status == "success"
    assert run.success is True
    assert run.total_tokens == 1234
    assert run.duration_ms is not None
    assert len(run.steps) == 2


def test_list_runs_is_user_scoped(session):
    u1 = UserRepository.create_user(session, _email(), "password123")
    u2 = UserRepository.create_user(session, _email(), "password123")
    RunRepository.create_run(session, str(uuid.uuid4()), "http://a", user_id=u1.id)
    RunRepository.create_run(session, str(uuid.uuid4()), "http://b", user_id=u2.id)
    assert len(RunRepository.list_runs(session, u1.id)) == 1
    assert len(RunRepository.list_runs(session, u2.id)) == 1
