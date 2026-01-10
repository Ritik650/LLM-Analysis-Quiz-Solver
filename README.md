---
title: LLM Analysis Quiz Solver
emoji: 🏃
colorFrom: red
colorTo: blue
sdk: docker
pinned: false
app_port: 7860
---

# Autonomous Quiz Solver Agent

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.121+-green.svg)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/React-18-61dafb.svg)](https://react.dev/)

A full-stack, observable, autonomous agent that solves multi-step data quizzes.
A **LangGraph** state machine driving **Gemini** navigates a chain of quiz pages
— scraping, downloading, writing & running code, and submitting answers — while
a **React dashboard streams every reasoning step and tool call live** over
Server-Sent Events.

> **v2 turned a backend-only prototype into a shipped product**: a live SSE
> dashboard (E1), run persistence + history (E2), token/cost/latency
> observability (E3), JWT + API-key auth (E4), a hardened code sandbox (E5), an
> evaluation harness with measured metrics (E6), and a full test suite + CI (E7).

## 📋 Table of Contents

- [Architecture](#-architecture)
- [Feature highlights](#-feature-highlights)
- [Project structure](#-project-structure)
- [Quick start](#-quick-start)
- [Configuration](#-configuration)
- [Authentication (E4)](#-authentication-e4)
- [API reference](#-api-reference)
- [Live dashboard (E1)](#-live-dashboard-e1)
- [Persistence (E2)](#-persistence-e2)
- [Observability (E3)](#-observability-e3)
- [Sandbox hardening & threat model (E5)](#-sandbox-hardening--threat-model-e5)
- [Evaluation harness & measured metrics (E6)](#-evaluation-harness--measured-metrics-e6)
- [Tests & CI (E7)](#-tests--ci-e7)
- [Deployment](#-deployment)
- [Known limitations](#-known-limitations)
- [License](#-license)

## 🏗 Architecture

```
        ┌───────────────────────────┐          Vercel
        │   React + Vite dashboard   │  ◀── live SSE trace, history, auth
        └─────────────┬─────────────┘
                      │ POST /auth/login → JWT
                      │ POST /solve → { run_id }
                      │ EventSource /runs/{id}/stream?token=JWT
                      ▼
        ┌───────────────────────────┐          Hugging Face Space (Docker, :7860)
        │        FastAPI app         │
        │  ┌──────────────────────┐  │
        │  │ auth/  JWT + API keys │  │
        │  │ persistence/  SQLA    │──┼──▶ SQLite (local) / Postgres · Supabase
        │  │ observability/  bus + │  │
        │  │   callbacks + metrics │──┼──▶ structured JSON logs · LangSmith (opt)
        │  └──────────┬───────────┘  │
        │             ▼              │
        │   agent.py  LangGraph      │
        │   ┌───────┐    ┌───────┐   │
        │   │ agent │◀──▶│ tools │   │  run_code (sandboxed), scraper,
        │   └───────┘    └───────┘   │  downloader, POST, OCR, transcribe…
        └───────────────────────────┘
```

The agent loop is unchanged in spirit — `agent` (LLM) ↔ `tools` with
malformed-call repair and timeout handling — but every node transition, LLM
call, and tool call now emits an event that is **streamed** to the browser and
**persisted** as a step.

## ✨ Feature highlights

| # | Enhancement | What it adds |
|---|-------------|--------------|
| E1 | **Live dashboard** | React/Vite SPA streaming reasoning, tool calls, progress, answers, live tokens + elapsed timer via SSE |
| E2 | **Persistence** | Every run stored (URL, step trace, tokens, cost, duration, success) with `GET /runs` + history view |
| E3 | **Observability** | Per-run token/cost/latency/tool-call metrics, structured JSON logs, optional LangSmith tracing |
| E4 | **Auth** | JWT access tokens, per-user hashed API keys, protected `/solve` + `/runs` (legacy shared-secret kept for back-compat) |
| E5 | **Sandbox hardening** | `run_code` runs under wall-clock + CPU + fd limits with an optional network guard; documented threat model |
| E6 | **Eval harness** | Deterministic mock quiz + FakeChatModel → success-rate / latency / token report (`--smoke` for CI) |
| E7 | **Tests + CI** | Unit / integration / e2e tests + GitHub Actions (lint → test → eval → build → guarded deploy) |

## 📁 Project structure

```
LLM-Analysis-TDS-Project-2/
├── agent.py                 # LangGraph orchestrator (LLM factory + instrumented runner)
├── main.py                  # FastAPI: /solve, /runs, SSE stream, auth wiring
├── config.py                # Central env-driven settings
├── shared_store.py          # Process-global run state (BASE64 + timing)
├── auth/                    # JWT issue/verify, API keys, FastAPI deps + routes
├── persistence/             # SQLAlchemy engine, models, repositories
├── observability/           # Event bus, SSE callback handler, metrics, tracing
├── tools/                   # 8 tools (run_code hardened for E5)
├── eval/                    # Mock quiz server, FakeChatModel, harness, report
├── frontend/                # React + Vite + TS dashboard (SSE live trace)
├── tests/                   # unit / integration / e2e
├── .github/workflows/ci.yml # lint → test → eval → build → deploy (guarded)
├── Dockerfile               # backend image (HF Spaces, :7860)
└── README.md
```

## 🚀 Quick start

### Backend

```bash
pip install uv
uv sync
uv run playwright install chromium      # only needed for live web scraping
cp .env.example .env                     # fill in GOOGLE_API_KEY, JWT_SECRET, …
uv run main.py                           # http://0.0.0.0:7860
```

### Frontend

```bash
cd frontend
npm install
npm run dev                              # http://localhost:5173 (proxies to :7860)
```

Register in the UI, paste a quiz URL, and watch the agent solve it live.

### Try it end-to-end with the mock quiz (no Gemini key needed)

```bash
uv run python -m eval.mock_quiz          # prints start URLs like .../q/arith/1
# submit one of those URLs from the dashboard, or:
uv run python -m eval.run_eval --smoke   # runs the agent against the mock server
```

## ⚙️ Configuration

All settings come from environment variables (see [.env.example](.env.example)):

| Variable | Default | Purpose |
|----------|---------|---------|
| `GOOGLE_API_KEY` | — | Gemini API key (real runs) |
| `GEMINI_MODEL` | `gemini-3-pro` | Model id |
| `JWT_SECRET` | *(ephemeral)* | **Set in prod.** Signs access tokens |
| `JWT_EXPIRE_MINUTES` | `1440` | Token lifetime |
| `DATABASE_URL` | `sqlite:///./data/runs.db` | SQLite locally, `postgresql+psycopg2://…` for Supabase |
| `ALLOW_LEGACY_SECRET` | `true` | Accept the deprecated shared `SECRET` on `/solve` |
| `ALLOWED_ORIGINS` | `*` | CORS origins (comma-separated) |
| `RUN_CODE_TIMEOUT` | `120` | Wall-clock limit (s) for generated code |
| `RUN_CODE_CPU_SECONDS` | `60` | CPU-time limit (POSIX) |
| `RUN_CODE_ENFORCE_MEM` | `false` | Enable `RLIMIT_AS` memory cap (off — breaks numpy/pandas) |
| `RUN_CODE_ALLOW_NETWORK` | `true` | Allow generated code network access |
| `LANGCHAIN_TRACING_V2` | `false` | Enable LangSmith tracing |

## 🔐 Authentication (E4)

Self-contained JWT + per-user API keys. Passwords are bcrypt-hashed; API keys
are shown once and stored only as SHA-256 hashes.

```bash
# Register (returns a JWT)
curl -sX POST localhost:7860/auth/register \
  -H 'Content-Type: application/json' \
  -d '{"email":"me@example.com","password":"password123"}'

# Use the token
TOKEN=... # access_token from above
curl -sX POST localhost:7860/solve \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"url":"https://quiz-server/quiz/1"}'

# Create an API key for programmatic use
curl -sX POST localhost:7860/auth/api-keys \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' -d '{"name":"ci"}'
# → use it as:  -H "X-API-Key: qk_..."
```

> The production deployment path uses **Supabase Auth** (Postgres + hosted JWT);
> this self-issued scheme is fully offline-testable and interchangeable — swap
> `auth/dependencies.py` to verify Supabase JWTs against its JWKS.

## 📡 API reference

| Method & path | Auth | Description |
|---------------|------|-------------|
| `POST /auth/register` | — | Create user, return JWT |
| `POST /auth/login` | — | Return JWT |
| `GET /auth/me` | Bearer/API key | Current user |
| `POST /auth/api-keys` · `GET` · `DELETE /{id}` | Bearer/API key | Manage API keys |
| `POST /solve` | Bearer / API key / legacy secret | Start a run → `{ run_id }` (202) |
| `GET /runs` | Bearer/API key | List your runs |
| `GET /runs/{id}` | Bearer/API key | Full run detail + step trace |
| `GET /runs/{id}/stream?token=…` | JWT/API key via query | **SSE** live/replayed trace |
| `GET /healthz` | — | Liveness |

## 📊 Live dashboard (E1)

The dashboard opens an `EventSource` to `/runs/{id}/stream`. The backend fans
each `AgentEvent` (reasoning, `tool`, `tool_result`, `token`, `final`) out to a
thread-safe queue; the stream **replays persisted steps first** (so late/refresh
connections still see the whole run) then streams live until a `done` sentinel.
It shows a colour-coded trace timeline, a live token counter, an elapsed timer,
estimated cost, and a per-user run-history panel you can click to replay.

## 💾 Persistence (E2)

SQLAlchemy models — `User`, `ApiKey`, `Run`, `Step` — run on **SQLite** with
zero setup and on **Postgres/Supabase** by setting `DATABASE_URL`. Each run
records the URL, timestamped step trace, tool calls, final result, success flag,
token/cost totals, and duration.

## 🔭 Observability (E3)

`observability/` provides an `SSECallbackHandler` (a LangChain callback) that
accumulates a `RunMetrics` object — prompt/completion tokens, estimated cost
(model-aware pricing table), wall-clock latency, and a tool-call distribution —
surfaced on `/runs/{id}` and the dashboard, and emitted as structured JSON logs.
Set `LANGCHAIN_TRACING_V2=true` + `LANGCHAIN_API_KEY` for full LangSmith traces.

## 🛡 Sandbox hardening & threat model (E5)

`run_code` executes arbitrary LLM-generated Python — treated as **untrusted**.

**Controls applied** (see [tools/run_code.py](tools/run_code.py)):

- **Wall-clock timeout** (portable) — process killed past `RUN_CODE_TIMEOUT`.
- **CPU-time limit** — `RLIMIT_CPU` (POSIX) stops busy loops.
- **File-descriptor limit** — `RLIMIT_NOFILE`.
- **Memory cap** — `RLIMIT_AS`, opt-in (`RUN_CODE_ENFORCE_MEM`) because address-space caps break numpy/pandas.
- **Network guard** — best-effort socket block when `RUN_CODE_ALLOW_NETWORK=false`.
- **Isolated working dir** (`LLMFiles/`) and output truncation.

**Residual risk (honest):** without a nested container / nsjail, filesystem and
network isolation are best-effort — generated code shares the container's
filesystem and, by default, its network. In production, run the executor in a
locked-down sidecar (nsjail, gVisor, or a per-run container) with an egress
allow-list. On Windows dev, POSIX rlimits don't apply and only the wall-clock
timeout is enforced.

## 🧪 Evaluation harness & measured metrics (E6)

`eval/` ships a deterministic **mock quiz server** and a **FakeChatModel** that
drives the real graph + real tools (`download_file` → `run_code` → `post_request`),
so runs are reproducible with no API key.

```bash
uv run python -m eval.run_eval          # full suite → eval/report.{json,md}
uv run python -m eval.run_eval --smoke  # single chain (CI)
uv run python -m eval.run_eval --real   # real Gemini (needs GOOGLE_API_KEY)
```

**Measured results** (deterministic FakeChatModel harness — real numbers from an
actual run, exercising the full agent + tool + persistence + metrics pipeline;
these gauge the *plumbing*, not Gemini's reasoning):

| Metric | Value |
|--------|-------|
| Success rate | **100% (3/3 chains)** |
| Median latency | **944 ms** |
| p95 latency | **1128 ms** |
| Avg tokens / run | **2,326** |
| Avg est. cost / run | **$0.0012** |
| Tool-call distribution | `download_file`×8, `run_code`×8, `post_request`×8 |

> **Real-Gemini metrics** require a `GOOGLE_API_KEY` and are intentionally *not*
> estimated here. Reproduce with `uv run python -m eval.run_eval --real` against
> the mock server (or real quiz URLs) and paste the emitted table.

## ✅ Tests & CI (E7)

29 tests — run `uv run pytest`:

- **unit** — auth (bcrypt/JWT/API keys), tools (mocked network/subprocess + the sandbox timeout), metrics, event bus, persistence repositories.
- **integration** — one full agent loop against the mock quiz, asserting the run is solved, persisted, and emits events.
- **e2e** — TestClient: register → login → `/solve` → poll `/runs/{id}` → assert success + SSE replay (Gemini swapped for the FakeChatModel).

[CI](.github/workflows/ci.yml) runs **lint (ruff) → test → eval smoke → build
backend image → build frontend → guarded deploy** on every push to `main`.

## 🌐 Deployment

| Piece | Host |
|-------|------|
| FastAPI + LangGraph + Gemini + Playwright | **Hugging Face Spaces** (Docker, already configured for :7860) |
| React/Vite dashboard | **Vercel** (`frontend/`, `VITE_API_BASE` → the HF Space) |
| Auth + run history | **Supabase** (Postgres via `DATABASE_URL`; Supabase Auth optional) |

HF's 16 GB RAM handles Chromium comfortably. The dashboard on Vercel only serves
the UI and streams the SSE trace — all agent work runs on HF (Vercel's 10 s
function timeout never applies to the long-running solve).

## ⚠️ Known limitations

- **One active run at a time.** The agent keeps process-global URL/timing state
  (`os.environ` + module dicts), so `/solve` returns `409` while a run is active.
  Full concurrency would require threading run state through the graph — future work.
- **Sandbox isolation is best-effort** without a nested container (see threat model).
- **Cost figures are estimates** from a model-pricing table; free-tier usage is $0.

## 📄 License

MIT — see [LICENSE](LICENSE).

**Course**: Tools in Data Science (TDS), IIT Madras.
