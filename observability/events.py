"""
In-process pub/sub event bus for live SSE streaming.

The agent runs in a worker thread (FastAPI threadpool) while the SSE endpoint
consumes events on the async event loop, so the transport between them must be
thread-safe. Each subscriber gets its own ``queue.Queue``; ``publish`` fans an
event out to every subscriber, and ``close`` pushes a ``None`` sentinel so the
SSE generator knows the run is done and can end the response.
"""
from __future__ import annotations

import json
import queue
import threading
import time
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class AgentEvent:
    """One thing that happened during a run, streamed to clients and persisted."""

    run_id: str
    seq: int
    type: str  # status | node | llm | tool | token | final | error | done
    name: str | None = None
    node: str | None = None
    data: dict[str, Any] = field(default_factory=dict)
    ts: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_sse(self) -> str:
        """Render as a Server-Sent Event frame."""
        payload = json.dumps(self.to_dict(), default=str)
        return f"event: {self.type}\ndata: {payload}\n\n"


class EventBus:
    def __init__(self) -> None:
        self._subscribers: dict[str, list[queue.Queue]] = {}
        self._lock = threading.Lock()

    def subscribe(self, run_id: str) -> queue.Queue:
        q: queue.Queue = queue.Queue()
        with self._lock:
            self._subscribers.setdefault(run_id, []).append(q)
        return q

    def unsubscribe(self, run_id: str, q: queue.Queue) -> None:
        with self._lock:
            subs = self._subscribers.get(run_id)
            if subs and q in subs:
                subs.remove(q)
                if not subs:
                    self._subscribers.pop(run_id, None)

    def publish(self, event: AgentEvent) -> None:
        with self._lock:
            subs = list(self._subscribers.get(event.run_id, []))
        for q in subs:
            q.put(event)

    def close(self, run_id: str) -> None:
        """Signal end-of-stream to all subscribers of a run."""
        with self._lock:
            subs = list(self._subscribers.get(run_id, []))
        for q in subs:
            q.put(None)  # sentinel


# Process-wide singleton used by the callback handler and the SSE endpoint.
event_bus = EventBus()
