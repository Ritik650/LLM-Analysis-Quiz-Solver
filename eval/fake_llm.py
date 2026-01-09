"""
FakeChatModel — a deterministic, zero-cost stand-in for Gemini.

It drives the exact tool sequence a real agent would use to solve the mock
quiz — download the page, run code to compute the answer, POST it, follow the
next URL — by inspecting the conversation and the process-global ``url`` state.
This lets the eval harness, integration tests, and e2e tests exercise the *full*
graph + tools + persistence + metrics pipeline with no API key and no network
beyond localhost.

It is a plumbing/regression stand-in, not a measure of real reasoning quality —
smoke metrics are labelled as such; real-Gemini numbers require a key.
"""
from __future__ import annotations

import os
import re
import uuid
from typing import Any

from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from config import get_settings

# The reader script the model "writes": parse EXPR/SUBMIT from the page and
# compute the answer. eval() is safe here — the content is our own mock server.
_READER_SCRIPT = (
    "import re\n"
    "html = open('page.html', encoding='utf-8').read()\n"
    "expr = re.search(r'EXPR=(.+)', html).group(1).strip()\n"
    "submit = re.search(r'SUBMIT=(\\S+)', html).group(1).strip()\n"
    "print('ANSWER=' + str(eval(expr)))\n"
    "print('SUBMIT=' + submit)\n"
)


def _tool_call(name: str, args: dict) -> dict:
    return {"name": name, "args": args, "id": "call_" + uuid.uuid4().hex[:8]}


class FakeChatModel(BaseChatModel):
    """Deterministic tool-calling model. ``bind_tools`` is a no-op returning
    self so the model stays a BaseChatModel (needed by trim_messages)."""

    @property
    def _llm_type(self) -> str:
        return "fake-quiz-model"

    def bind_tools(self, tools: Any, **kwargs: Any):  # type: ignore[override]
        return self

    # Cheap token counters so trim_messages doesn't pull in a real tokenizer
    # (the BaseChatModel default requires the `transformers` package).
    def get_num_tokens(self, text: str) -> int:
        return max(len(text) // 4, 1)

    def get_num_tokens_from_messages(self, messages, tools=None) -> int:
        return sum(self.get_num_tokens(str(getattr(m, "content", ""))) for m in messages)

    def _decide(self, messages: list[BaseMessage]) -> dict:
        settings = get_settings()
        last = messages[-1]
        current_url = os.getenv("url", "")

        if last.type in ("human", "system"):
            return _tool_call("download_file", {"url": current_url, "filename": "page.html"})

        if last.type == "tool":
            name = getattr(last, "name", "") or ""
            content = last.content if isinstance(last.content, str) else str(last.content)

            if name == "download_file":
                return _tool_call("run_code", {"code": _READER_SCRIPT})

            if name == "run_code":
                # run_code's dict is serialised via repr(), so real newlines
                # become literal "\\n"; stop the capture at whitespace, quotes,
                # or a backslash so we don't swallow the rest of the repr.
                answer = re.search(r"ANSWER=([^\s\\'\"]+)", content)
                submit = re.search(r"SUBMIT=(https?://[^\s\\'\"]+)", content)
                if answer and submit:
                    return _tool_call(
                        "post_request",
                        {
                            "url": submit.group(1),
                            "payload": {
                                "answer": answer.group(1),
                                "email": settings.email or "test@example.com",
                                "url": current_url,
                            },
                        },
                    )
                return {"end": True}

            if name == "post_request":
                if "Tasks completed" in content:
                    return {"end": True}
                next_url = os.getenv("url", "")
                if next_url:
                    return _tool_call(
                        "download_file", {"url": next_url, "filename": "page.html"}
                    )
                return {"end": True}

        return {"end": True}

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        action = self._decide(messages)
        # Rough token accounting so metrics/cost have realistic-shaped numbers.
        approx_in = sum(len(str(getattr(m, "content", ""))) for m in messages) // 4
        usage = {
            "input_tokens": max(approx_in, 1),
            "output_tokens": 24,
            "total_tokens": max(approx_in, 1) + 24,
        }

        if action.get("end"):
            message = AIMessage(content="END", usage_metadata=usage)
        else:
            message = AIMessage(content="", tool_calls=[action], usage_metadata=usage)

        return ChatResult(generations=[ChatGeneration(message=message)])
