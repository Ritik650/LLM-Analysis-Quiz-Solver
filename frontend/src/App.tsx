import { useCallback, useEffect, useRef, useState } from "react";
import Login from "./components/Login";
import TraceView from "./components/TraceView";
import RunHistory from "./components/RunHistory";
import { api, getToken, setToken } from "./lib/api";
import { streamRun } from "./lib/sse";
import type { AgentEvent, RunSummary } from "./types";

type Status = "idle" | "running" | "success" | "failed";

export default function App() {
  const [email, setEmail] = useState<string | null>(null);
  const [checking, setChecking] = useState(true);

  const [url, setUrl] = useState("");
  const [events, setEvents] = useState<AgentEvent[]>([]);
  const [status, setStatus] = useState<Status>("idle");
  const [tokens, setTokens] = useState(0);
  const [cost, setCost] = useState(0);
  const [toolCount, setToolCount] = useState(0);
  const [elapsed, setElapsed] = useState(0);
  const [runs, setRuns] = useState<RunSummary[]>([]);

  const startRef = useRef(0);
  const closeRef = useRef<(() => void) | null>(null);

  // Validate an existing token on load.
  useEffect(() => {
    if (!getToken()) {
      setChecking(false);
      return;
    }
    api
      .me()
      .then((u) => setEmail(u.email))
      .catch(() => setToken(null))
      .finally(() => setChecking(false));
  }, []);

  const refreshRuns = useCallback(() => {
    api
      .listRuns()
      .then((r) => setRuns(r.runs))
      .catch(() => {});
  }, []);

  useEffect(() => {
    if (email) refreshRuns();
  }, [email, refreshRuns]);

  // Elapsed timer while a run is live.
  useEffect(() => {
    if (status !== "running") return;
    const id = setInterval(() => setElapsed(Date.now() - startRef.current), 250);
    return () => clearInterval(id);
  }, [status]);

  function applyMetrics(data: Record<string, unknown>) {
    if (typeof data.total_tokens === "number") setTokens(data.total_tokens);
    if (typeof data.est_cost_usd === "number") setCost(data.est_cost_usd);
    if (typeof data.tool_call_count === "number") setToolCount(data.tool_call_count);
  }

  const onEvent = useCallback((ev: AgentEvent) => {
    setEvents((prev) => [...prev, ev]);
    if (ev.type === "token" || ev.type === "final") applyMetrics(ev.data);
    if (ev.type === "final") setStatus(ev.data.success ? "success" : "failed");
    if (ev.type === "error" && ev.name === "run_failed") setStatus("failed");
  }, []);

  async function solve() {
    if (!url.trim()) return;
    closeRef.current?.();
    setEvents([]);
    setTokens(0);
    setCost(0);
    setToolCount(0);
    setElapsed(0);
    setStatus("running");
    startRef.current = Date.now();
    try {
      const { run_id } = await api.solve(url.trim());
      closeRef.current = streamRun(run_id, onEvent, () => {
        setStatus((s) => (s === "running" ? "success" : s));
        refreshRuns();
      });
    } catch (err) {
      setStatus("failed");
      setEvents([
        {
          run_id: "",
          seq: 0,
          type: "error",
          name: "submit_failed",
          data: { error: (err as Error).message },
          ts: 0,
        },
      ]);
    }
  }

  async function loadRun(id: string) {
    closeRef.current?.();
    setStatus("idle");
    const detail = await api.getRun(id);
    setEvents(
      detail.steps.map((s) => ({
        run_id: id,
        seq: s.seq,
        type: s.type,
        name: s.name,
        node: s.node,
        data: s.data ?? {},
        ts: 0,
      })),
    );
    setTokens(detail.total_tokens);
    setCost(detail.est_cost_usd);
    setToolCount(detail.tool_call_count);
    setElapsed(detail.duration_ms ?? 0);
    setStatus(detail.status === "running" ? "running" : (detail.status as Status));
  }

  function logout() {
    closeRef.current?.();
    setToken(null);
    setEmail(null);
    setEvents([]);
    setStatus("idle");
  }

  if (checking) return null;
  if (!email) return <Login onAuthed={setEmail} />;

  const mmss = `${String(Math.floor(elapsed / 60000)).padStart(2, "0")}:${String(
    Math.floor((elapsed % 60000) / 1000),
  ).padStart(2, "0")}`;

  return (
    <>
      <nav className="nav">
        <div className="nav-brand">
          <span className="logo">⚡</span>
          <span>Quiz Solver Agent</span>
        </div>
        <div className="nav-right">
          <span className="mono">{email}</span>
          <button className="btn-ghost" onClick={logout}>
            Logout
          </button>
        </div>
      </nav>

      <div className="layout">
        <div className="panel">
          <h2>Live Run</h2>
          <div className="solve-row">
            <input
              type="text"
              placeholder="https://quiz-server.example/quiz/1"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && solve()}
            />
            <button className="btn" onClick={solve} disabled={status === "running"}>
              {status === "running" ? "Solving…" : "Solve"}
            </button>
          </div>

          <div className="metrics">
            <div className="metric">
              <div className="label">Status</div>
              <div className="value" style={{ fontSize: 15 }}>
                <span className={`dot ${status === "idle" ? "" : status}`} />
                {status}
              </div>
            </div>
            <div className="metric">
              <div className="label">Elapsed</div>
              <div className="value">{mmss}</div>
            </div>
            <div className="metric">
              <div className="label">Tokens</div>
              <div className="value">{tokens.toLocaleString()}</div>
            </div>
            <div className="metric">
              <div className="label">Est. Cost</div>
              <div className="value">${cost.toFixed(4)}</div>
            </div>
          </div>

          <h2 style={{ marginTop: 4 }}>
            Agent Trace <span className="chip">{toolCount} tool calls</span>
          </h2>
          <TraceView events={events} />
        </div>

        <div className="panel">
          <h2>Run History</h2>
          <RunHistory runs={runs} onSelect={loadRun} />
        </div>
      </div>
    </>
  );
}
