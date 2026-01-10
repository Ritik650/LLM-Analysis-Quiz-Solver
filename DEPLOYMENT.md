# Deployment Guide

Three pieces, three hosts:

| Piece | Host | Why |
|-------|------|-----|
| FastAPI + LangGraph + Gemini + Playwright | **Hugging Face Spaces** (Docker, :7860) | 16 GB RAM runs Chromium; long solves aren't bound by a function timeout |
| React/Vite dashboard | **Vercel** | Static SPA; only serves the UI + streams SSE |
| Auth + run history (Postgres) | **Supabase** | Persistent runs/users across Space restarts |

> The backend Docker image is verified to build and boot (`/healthz` + `/auth/register` succeed in the exact HF image).

---

## Prerequisites

- A **Gemini API key** — https://aistudio.google.com/app/apikey
- Accounts on **Hugging Face**, **Vercel**, and **Supabase** (all free tier).
- A strong `JWT_SECRET`: `python -c "import secrets; print(secrets.token_urlsafe(48))"`

---

## Step 1 — Supabase (Postgres)

1. Create a new project at https://supabase.com/dashboard. Save the database password.
2. **Project Settings → Database → Connection string → URI**. Copy it. It looks like:
   ```
   postgresql://postgres.[ref]:[PASSWORD]@aws-0-[region].pooler.supabase.com:6543/postgres
   ```
3. Convert it to a SQLAlchemy URL by changing the scheme to `postgresql+psycopg2` — this becomes your `DATABASE_URL`:
   ```
   postgresql+psycopg2://postgres.[ref]:[PASSWORD]@aws-0-[region].pooler.supabase.com:6543/postgres
   ```
   - Use the **Session pooler** (port `5432`) or the connection **URI** shown for "Session mode" if you hit prepared-statement issues; the transaction pooler (`6543`) works with psycopg2 for this app.
4. **No manual SQL needed** — the app runs `Base.metadata.create_all` on startup and creates the `users`, `api_keys`, `runs`, and `steps` tables automatically on first boot.

---

## Step 2 — Backend on Hugging Face Spaces

1. Create a **new Space** → SDK **Docker** → hardware CPU basic (free). This repo already carries the HF frontmatter (`sdk: docker`, `app_port: 7860`) in the README, so it builds as-is.
2. **Space → Settings → Variables and secrets** — add these **secrets**:

   | Key | Value |
   |-----|-------|
   | `GOOGLE_API_KEY` | your Gemini key |
   | `JWT_SECRET` | your 48-char random string |
   | `DATABASE_URL` | the Supabase `postgresql+psycopg2://…` URL from Step 1 |
   | `ALLOWED_ORIGINS` | *(set after Step 3 to your Vercel URL)* |
   | `GEMINI_MODEL` | `gemini-3-pro` (optional) |
   | `EMAIL` / `SECRET` | optional — legacy quiz-submission identity |

3. Push this repo to the Space's git remote:
   ```bash
   git remote add space https://huggingface.co/spaces/<hf-username>/<space-name>
   git push space main
   ```
   (Authenticate with an HF **write** token when prompted.) The Space builds the Docker image and starts on `:7860`.
4. Your backend base URL will be: `https://<hf-username>-<space-name>.hf.space`
   Verify: open `…/healthz` → `{"status":"ok"}`.

---

## Step 3 — Frontend on Vercel

1. **Add New → Project** → import `Ritik650/LLM-Analysis-Quiz-Solver`.
2. **Root Directory:** `frontend`. Framework preset **Vite** (auto-detected; `vercel.json` handles the SPA rewrite).
3. **Environment Variables:**
   | Key | Value |
   |-----|-------|
   | `VITE_API_BASE` | your HF Space URL, e.g. `https://<hf-username>-<space-name>.hf.space` |
4. Deploy. Vercel gives you a URL like `https://llm-analysis-quiz-solver.vercel.app`.

---

## Step 4 — Wire CORS (backend ↔ frontend)

1. Back in the HF Space secrets, set:
   | Key | Value |
   |-----|-------|
   | `ALLOWED_ORIGINS` | your Vercel URL, e.g. `https://llm-analysis-quiz-solver.vercel.app` |
2. Restart the Space (Settings → **Factory reboot** or push a commit).

---

## Step 5 — Verify end to end

1. Open the Vercel URL → **Register** an account.
2. Paste a quiz URL and hit **Solve** — watch the live SSE trace (reasoning, tool calls, tokens, elapsed).
   - No real quiz handy? Run `uv run python -m eval.mock_quiz` locally and expose it, or point at a real quiz endpoint.
3. Confirm the run appears in **Run History** (proves Supabase persistence).

---

## Environment variable reference

See [.env.example](.env.example). Deployment-critical ones:

| Variable | Where | Notes |
|----------|-------|-------|
| `GOOGLE_API_KEY` | HF | Gemini key |
| `JWT_SECRET` | HF | **Must** be set; ≥32 bytes |
| `DATABASE_URL` | HF | Supabase `postgresql+psycopg2://…` |
| `ALLOWED_ORIGINS` | HF | Vercel origin (comma-separated for multiple) |
| `VITE_API_BASE` | Vercel | HF Space base URL |

---

## Troubleshooting

- **CORS errors in the browser** → `ALLOWED_ORIGINS` on HF must exactly match the Vercel origin (scheme + host, no trailing slash). Restart the Space after changing.
- **SSE trace never streams** → HF proxies streaming responses; the app already sends `X-Accel-Buffering: no`. Ensure `VITE_API_BASE` has no trailing slash and points at HTTPS.
- **DB connection errors on boot** → check the `postgresql+psycopg2://` scheme and that the password is URL-encoded if it contains special characters.
- **`409 A run is already active`** → by design: the agent keeps process-global state, so one run at a time. Wait for the current run to finish.
- **CI auto-deploy** → `.github/workflows/ci.yml` has a guarded deploy job; set repo secrets `HF_TOKEN` + `HF_SPACE` (and optionally `VERCEL_TOKEN`) to push the backend to the Space on merge to `main`. It no-ops without them.
