"""Unit tests for the SSE event bus."""
from __future__ import annotations

from observability.events import AgentEvent, EventBus


def test_publish_reaches_subscribers():
    bus = EventBus()
    q = bus.subscribe("run1")
    bus.publish(AgentEvent(run_id="run1", seq=1, type="tool", name="run_code"))
    event = q.get_nowait()
    assert event.type == "tool"
    assert event.name == "run_code"


def test_close_sends_sentinel():
    bus = EventBus()
    q = bus.subscribe("run1")
    bus.close("run1")
    assert q.get_nowait() is None


def test_unrelated_run_not_delivered():
    bus = EventBus()
    q = bus.subscribe("run1")
    bus.publish(AgentEvent(run_id="run2", seq=1, type="tool"))
    assert q.empty()


def test_event_to_sse_format():
    ev = AgentEvent(run_id="r", seq=3, type="token", data={"total_tokens": 5})
    frame = ev.to_sse()
    assert frame.startswith("event: token\n")
    assert "data: " in frame
    assert frame.endswith("\n\n")
