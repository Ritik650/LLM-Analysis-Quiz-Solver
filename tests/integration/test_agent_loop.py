"""Integration test: one full agent loop against the mock quiz server,
driven by the deterministic FakeChatModel."""
from __future__ import annotations

import uuid

import pytest

from agent import build_app, run_agent_instrumented
from eval.fake_llm import FakeChatModel
from eval.mock_quiz import start_mock_quiz, stop_mock_quiz
from observability.events import event_bus


@pytest.fixture()
def mock_quiz():
    base, server = start_mock_quiz({"arith": [("2+2", "4"), ("10*3", "30")]})
    yield base
    stop_mock_quiz(server)


def test_full_loop_solves_chain_and_emits_events(mock_quiz):
    app = build_app(FakeChatModel())
    run_id = str(uuid.uuid4())
    q = event_bus.subscribe(run_id)

    outcome = run_agent_instrumented(
        f"{mock_quiz}/q/arith/1", run_id, app=app, model="fake-quiz-model"
    )

    assert outcome.success is True
    m = outcome.metrics
    # A 2-step chain: download + run_code + post_request per step.
    assert m.tool_calls_by_name.get("download_file", 0) == 2
    assert m.tool_calls_by_name.get("run_code", 0) == 2
    assert m.tool_calls_by_name.get("post_request", 0) == 2
    assert m.total_tokens > 0

    # Drain the event stream and assert we saw tool + final + done events.
    types = []
    while True:
        item = q.get_nowait() if not q.empty() else None
        if item is None:
            break
        types.append(item.type)
    assert "tool" in types
    assert "final" in types
    assert "done" in types
