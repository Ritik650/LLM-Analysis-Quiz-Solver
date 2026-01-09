"""
A tiny, deterministic quiz server so the agent can be evaluated offline.

Each "chain" is a sequence of arithmetic tasks. A page exposes ``EXPR=`` (the
expression to compute) and ``SUBMIT=`` (where to POST). Submitting the correct
answer returns the next page URL; the last step returns ``url: null`` so the
agent stops. URLs are built from the request's own base so the server works on
whatever port it is bound to.
"""
from __future__ import annotations

import socket
import threading
import time

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse

# chain_id -> list of (expression, expected_answer_as_string)
DEFAULT_CHAINS: dict[str, list[tuple[str, str]]] = {
    "arith": [("2+2", "4"), ("10*3", "30"), ("100-1", "99")],
    "single": [("7*6", "42")],
    "longer": [("1+1", "2"), ("2*2", "4"), ("3*3", "9"), ("4*4", "16")],
}


def build_app(chains: dict[str, list[tuple[str, str]]] = DEFAULT_CHAINS) -> FastAPI:
    app = FastAPI(title="Mock Quiz Server")

    @app.get("/healthz")
    def healthz():
        return {"status": "ok"}

    @app.get("/q/{chain}/{step}", response_class=HTMLResponse)
    def page(chain: str, step: int, request: Request):
        tasks = chains.get(chain)
        if not tasks or step < 1 or step > len(tasks):
            return HTMLResponse("<h1>Not found</h1>", status_code=404)
        expr, _ = tasks[step - 1]
        submit = f"{request.base_url}q/{chain}/{step}/submit"
        # Each directive on its own line (newline after the URL) so a greedy
        # \S+ parse can't swallow the closing HTML tags into the submit URL.
        return HTMLResponse(
            f"<html><body><h1>Task {chain}#{step}</h1>"
            f"<p>Compute the expression and submit the answer.</p>"
            f"<pre>\nEXPR={expr}\nSUBMIT={submit}\n</pre>\n</body></html>"
        )

    @app.post("/q/{chain}/{step}/submit")
    async def submit(chain: str, step: int, request: Request):
        tasks = chains.get(chain)
        if not tasks or step < 1 or step > len(tasks):
            return JSONResponse({"error": "not found"}, status_code=404)
        try:
            body = await request.json()
        except Exception:
            body = {}
        _, expected = tasks[step - 1]
        correct = str(body.get("answer")).strip() == expected
        if not correct:
            # Wrong answer → let the agent retry the same page.
            return {"correct": False, "url": f"{request.base_url}q/{chain}/{step}"}
        if step < len(tasks):
            return {"correct": True, "url": f"{request.base_url}q/{chain}/{step + 1}"}
        return {"correct": True, "url": None}  # end of chain

    return app


def _free_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def start_mock_quiz(
    chains: dict[str, list[tuple[str, str]]] = DEFAULT_CHAINS, port: int | None = None
) -> tuple[str, uvicorn.Server]:
    """Start the server in a daemon thread. Returns (base_url, server)."""
    port = port or _free_port()
    config = uvicorn.Config(
        build_app(chains), host="127.0.0.1", port=port, log_level="warning"
    )
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    return f"http://127.0.0.1:{port}", server


def stop_mock_quiz(server: uvicorn.Server) -> None:
    server.should_exit = True


if __name__ == "__main__":
    base, server = start_mock_quiz()
    print(f"Mock quiz server running at {base}")
    print("Start URLs: " + ", ".join(f"{base}/q/{c}/1" for c in DEFAULT_CHAINS))
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        stop_mock_quiz(server)
