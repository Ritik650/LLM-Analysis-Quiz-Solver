"""
SSECallbackHandler — the bridge between LangChain/LangGraph and our
observability stack.

It subscribes to the agent's execution via LangChain's callback protocol and
converts each interesting moment into an :class:`AgentEvent` that is (a)
published to the live event bus for SSE and (b) handed to an optional ``persist``
callback that writes it as a ``Step`` row. It also accumulates token usage and
tool-call counts into a :class:`RunMetrics`.
"""
from __future__ import annotations

import threading
from typing import Any, Callable

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult

from .events import AgentEvent, EventBus, event_bus
from .metrics import RunMetrics

_MAX_SNIPPET = 2000


def _truncate(value: Any, limit: int = _MAX_SNIPPET) -> str:
    text = value if isinstance(value, str) else str(value)
    if len(text) > limit:
        return text[:limit] + f"... [truncated {len(text) - limit} chars]"
    return text


class SSECallbackHandler(BaseCallbackHandler):
    raise_error = False

    def __init__(
        self,
        run_id: str,
        metrics: RunMetrics,
        bus: EventBus = event_bus,
        persist: Callable[[AgentEvent], None] | None = None,
    ) -> None:
        self.run_id = run_id
        self.metrics = metrics
        self.bus = bus
        self.persist = persist
        self._seq = 0
        self._lock = threading.Lock()

    # -- core emit ------------------------------------------------------
    def emit(
        self,
        type: str,
        name: str | None = None,
        node: str | None = None,
        **data: Any,
    ) -> AgentEvent:
        with self._lock:
            self._seq += 1
            seq = self._seq
        event = AgentEvent(
            run_id=self.run_id, seq=seq, type=type, name=name, node=node, data=data
        )
        self.bus.publish(event)
        if self.persist is not None:
            try:
                self.persist(event)
            except Exception:  # never let persistence break a live run
                pass
        return event

    def _emit_metrics(self) -> None:
        self.emit("token", **self.metrics.snapshot())

    # -- LangChain callbacks -------------------------------------------
    def on_chat_model_start(self, serialized, messages, **kwargs) -> None:
        self.emit("node", node="agent", name="thinking")

    def on_llm_end(self, response: LLMResult, **kwargs) -> None:
        prompt = completion = total = 0
        text = ""
        try:
            gen = response.generations[0][0]
            message = getattr(gen, "message", None)
            usage = getattr(message, "usage_metadata", None) if message else None
            if usage:
                prompt = usage.get("input_tokens", 0) or 0
                completion = usage.get("output_tokens", 0) or 0
                total = usage.get("total_tokens", prompt + completion) or 0
            content = getattr(message, "content", "") if message else ""
            if isinstance(content, list):
                text = " ".join(
                    part.get("text", "") for part in content if isinstance(part, dict)
                )
            elif isinstance(content, str):
                text = content
        except (IndexError, AttributeError):
            pass

        if total or prompt or completion:
            self.metrics.add_llm_usage(prompt, completion, total)
        if text.strip():
            self.emit("llm", name="reasoning", node="agent", text=_truncate(text))
        self._emit_metrics()

    def on_tool_start(self, serialized, input_str, **kwargs) -> None:
        name = (serialized or {}).get("name", "tool")
        inputs = kwargs.get("inputs")
        payload = inputs if inputs is not None else input_str
        self.metrics.add_tool_call(name)
        self.emit("tool", name=name, node="tools", input=_truncate(payload))

    def on_tool_end(self, output, **kwargs) -> None:
        name = kwargs.get("name") or "tool"
        content = getattr(output, "content", output)
        self.emit("tool_result", name=name, node="tools", output=_truncate(content))

    def on_tool_error(self, error, **kwargs) -> None:
        self.emit("error", name="tool_error", node="tools", error=_truncate(str(error)))

    def on_llm_error(self, error, **kwargs) -> None:
        self.emit("error", name="llm_error", node="agent", error=_truncate(str(error)))
