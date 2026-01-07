"""
LangGraph orchestrator.

Refactored from the original single-module script so that:
  * the LLM is built by a factory (`build_llm`) and can be injected — tests and
    the eval harness pass a deterministic FakeChatModel instead of Gemini;
  * the graph is built by `build_app(llm)` so any LLM can drive it;
  * `run_agent` threads a `run_id` + LangChain `callbacks` into `app.invoke`;
  * `run_agent_instrumented` wraps a run with an SSE callback handler + metrics
    and emits start/final/done events — shared by the API and the eval harness.

The node/route logic (timeout handling, malformed-JSON repair, message
trimming, END detection) is preserved from the original implementation.
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Annotated, List, TypedDict

from langchain.chat_models import init_chat_model
from langchain_core.messages import HumanMessage, trim_messages
from langchain_core.rate_limiters import InMemoryRateLimiter
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode

from config import get_settings
from observability.callbacks import SSECallbackHandler
from observability.events import event_bus
from observability.metrics import RunMetrics
from shared_store import url_time
from tools import (
    add_dependencies,
    download_file,
    encode_image_to_base64,
    get_rendered_html,
    ocr_image_tool,
    post_request,
    run_code,
    transcribe_audio,
)

settings = get_settings()
EMAIL = settings.email
SECRET = settings.secret

RECURSION_LIMIT = settings.recursion_limit
MAX_TOKENS = settings.max_tokens


# -------------------------------------------------
# STATE
# -------------------------------------------------
class AgentState(TypedDict):
    messages: Annotated[List, add_messages]


TOOLS = [
    run_code, get_rendered_html, download_file,
    post_request, add_dependencies, ocr_image_tool, transcribe_audio, encode_image_to_base64
]


# -------------------------------------------------
# LLM FACTORY
# -------------------------------------------------
def build_llm(model: str | None = None):
    """Build the tool-bound Gemini chat model. Injectable for tests/eval."""
    rate_limiter = InMemoryRateLimiter(
        requests_per_second=4 / 60,
        check_every_n_seconds=1,
        max_bucket_size=4,
    )
    llm = init_chat_model(
        model_provider="google_genai",
        model=model or settings.gemini_model,
        rate_limiter=rate_limiter,
    )
    return llm.bind_tools(TOOLS)


# -------------------------------------------------
# SYSTEM PROMPT
# -------------------------------------------------
SYSTEM_PROMPT = f"""
You are an autonomous quiz-solving agent.

Your job is to:
1. Load each quiz page from the given URL.
2. Extract instructions, parameters, and submit endpoint.
3. Solve tasks exactly.
4. Submit answers ONLY to the correct endpoint.
5. Follow new URLs until none remain, then output END.

Rules:
- For base64 generation of an image NEVER use your own code, always use the "encode_image_to_base64" tool that's provided
- Never hallucinate URLs or fields.
- Never shorten endpoints.
- Always inspect server response.
- Never stop early.
- Use tools for HTML, downloading, rendering, OCR, or running code.
- Include:
    email = {EMAIL}
    secret = {SECRET}
"""


# -------------------------------------------------
# NODES (factory closes over the injected llm)
# -------------------------------------------------
def handle_malformed_node(state: AgentState):
    """Ask the LLM to retry after an invalid tool-call (malformed JSON)."""
    print("--- DETECTED MALFORMED JSON. ASKING AGENT TO RETRY ---")
    return {
        "messages": [
            {
                "role": "user",
                "content": "SYSTEM ERROR: Your last tool call was Malformed (Invalid JSON). Please rewrite the code and try again. Ensure you escape newlines and quotes correctly inside the JSON.",
            }
        ]
    }


def make_agent_node(llm):
    def agent_node(state: AgentState):
        # --- TIME HANDLING START ---
        cur_time = time.time()
        cur_url = os.getenv("url")

        prev_time = url_time.get(cur_url)
        offset = os.getenv("offset", "0")

        if prev_time is not None:
            prev_time = float(prev_time)
            diff = cur_time - prev_time

            if diff >= 180 or (offset != "0" and (cur_time - float(offset)) > 90):
                print(f"Timeout exceeded ({diff}s) — instructing LLM to purposely submit wrong answer.")
                fail_instruction = """
                You have exceeded the time limit for this task (over 180 seconds).
                Immediately call the `post_request` tool and submit a WRONG answer for the CURRENT quiz.
                """
                fail_msg = HumanMessage(content=fail_instruction)
                result = llm.invoke(state["messages"] + [fail_msg])
                return {"messages": [result]}
        # --- TIME HANDLING END ---

        trimmed_messages = trim_messages(
            messages=state["messages"],
            max_tokens=MAX_TOKENS,
            strategy="last",
            include_system=True,
            start_on="human",
            token_counter=llm,
        )

        has_human = any(msg.type == "human" for msg in trimmed_messages)
        if not has_human:
            print("WARNING: Context was trimmed too far. Injecting state reminder.")
            current_url = os.getenv("url", "Unknown URL")
            reminder = HumanMessage(content=f"Context cleared due to length. Continue processing URL: {current_url}")
            trimmed_messages.append(reminder)

        print(f"--- INVOKING AGENT (Context: {len(trimmed_messages)} items) ---")
        result = llm.invoke(trimmed_messages)
        return {"messages": [result]}

    return agent_node


# -------------------------------------------------
# ROUTE LOGIC
# -------------------------------------------------
def route(state):
    last = state["messages"][-1]

    if "finish_reason" in getattr(last, "response_metadata", {}):
        if last.response_metadata["finish_reason"] == "MALFORMED_FUNCTION_CALL":
            return "handle_malformed"

    tool_calls = getattr(last, "tool_calls", None)
    if tool_calls:
        print("Route -> tools")
        return "tools"

    content = getattr(last, "content", None)
    if isinstance(content, str) and content.strip() == "END":
        return END

    if isinstance(content, list) and len(content) and isinstance(content[0], dict):
        if content[0].get("text", "").strip() == "END":
            return END

    print("Route -> agent")
    return "agent"


# -------------------------------------------------
# GRAPH FACTORY
# -------------------------------------------------
def build_app(llm):
    graph = StateGraph(AgentState)
    graph.add_node("agent", make_agent_node(llm))
    graph.add_node("tools", ToolNode(TOOLS))
    graph.add_node("handle_malformed", handle_malformed_node)

    graph.add_edge(START, "agent")
    graph.add_edge("tools", "agent")
    graph.add_edge("handle_malformed", "agent")

    graph.add_conditional_edges(
        "agent",
        route,
        {
            "tools": "tools",
            "agent": "agent",
            "handle_malformed": "handle_malformed",
            END: END,
        },
    )
    return graph.compile()


_default_app = None


def get_default_app():
    """Lazily build (and cache) the real Gemini-backed app."""
    global _default_app
    if _default_app is None:
        _default_app = build_app(build_llm())
    return _default_app


# -------------------------------------------------
# RUN STATE INIT
# -------------------------------------------------
def _init_run_state(url: str) -> None:
    """Reset the process-global run state for a fresh quiz chain.

    NOTE: this state is process-global (os.environ + module dicts), so only one
    run can be active at a time. The API enforces this with a single-run guard.
    """
    from shared_store import BASE64_STORE

    url_time.clear()
    BASE64_STORE.clear()
    os.environ["url"] = url
    os.environ["offset"] = "0"
    url_time[url] = time.time()


# -------------------------------------------------
# RUNNER
# -------------------------------------------------
def run_agent(url: str, run_id: str | None = None, callbacks=None, app=None):
    """Run the quiz chain to completion. Returns the final LangGraph state."""
    _init_run_state(url)
    active_app = app if app is not None else get_default_app()

    initial_messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": url},
    ]

    config: dict = {"recursion_limit": RECURSION_LIMIT}
    if callbacks:
        config["callbacks"] = callbacks

    final_state = active_app.invoke({"messages": initial_messages}, config=config)
    print("Tasks completed successfully!")
    return final_state


def _extract_final_text(final_state) -> str:
    try:
        last = final_state["messages"][-1]
        content = getattr(last, "content", "")
        if isinstance(content, list):
            return " ".join(
                part.get("text", "") for part in content if isinstance(part, dict)
            ).strip()
        return str(content).strip()
    except (KeyError, IndexError, AttributeError):
        return ""


@dataclass
class RunOutcome:
    success: bool
    result: dict | None
    metrics: RunMetrics
    error: str | None


def run_agent_instrumented(
    url: str,
    run_id: str,
    app=None,
    persist=None,
    bus=event_bus,
    model: str | None = None,
) -> RunOutcome:
    """Run a quiz chain with SSE events + metrics. Shared by API and eval.

    ``success`` here means the chain *completed without error* (reached END).
    Per-answer correctness is graded by the quiz server, not by this flag.
    """
    metrics = RunMetrics(model=model or settings.gemini_model)
    handler = SSECallbackHandler(run_id, metrics, bus=bus, persist=persist)
    handler.emit("status", name="started", url=url)
    try:
        final_state = run_agent(url, run_id=run_id, callbacks=[handler], app=app)
        text = _extract_final_text(final_state)
        result = {"final_message": text}
        success = True
        metrics.finish()
        handler.emit("final", name="completed", success=success, result=result, **metrics.snapshot())
        return RunOutcome(success=success, result=result, metrics=metrics, error=None)
    except Exception as exc:  # noqa: BLE001 — surface any failure as a run outcome
        metrics.finish()
        handler.emit("error", name="run_failed", error=str(exc))
        return RunOutcome(success=False, result=None, metrics=metrics, error=str(exc))
    finally:
        handler.emit("done")
        bus.close(run_id)
