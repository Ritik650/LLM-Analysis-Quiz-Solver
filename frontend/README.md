# Quiz Solver — Live Dashboard

React + Vite + TypeScript single-page app that submits quiz URLs to the agent
backend and streams the run **live** over Server-Sent Events: reasoning steps,
each tool call and its result, quiz-chain progress, final answers, token counter,
and an elapsed timer — plus a per-user run-history view.

## Develop

```bash
npm install
npm run dev          # http://localhost:5173  (proxies API to :7860)
```

Run the backend (`uv run main.py`) on port 7860 in parallel. Register an
account in the UI, paste a quiz URL, and watch the trace.

## Build

```bash
npm run build        # type-check + bundle to dist/
```

## Configuration

| Var             | Purpose                                             |
| --------------- | --------------------------------------------------- |
| `VITE_API_BASE` | Backend base URL in production (the HF Space). Empty in dev (Vite proxy). |

## Deploy

- **Vercel** (recommended): import the repo, set root to `frontend/`, set
  `VITE_API_BASE`, deploy. `vercel.json` handles the SPA rewrite.
- **Docker/nginx**: `docker build --build-arg VITE_API_BASE=https://your-space.hf.space -t quiz-dashboard . && docker run -p 8080:80 quiz-dashboard`.

Because SSE auth can't use headers, the JWT is passed to the stream endpoint as
a `?token=` query parameter (see `src/lib/sse.ts`).
