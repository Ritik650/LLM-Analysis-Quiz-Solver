import type { RunSummary } from "../types";

function fmtDuration(ms: number | null): string {
  if (!ms) return "—";
  return ms >= 1000 ? `${(ms / 1000).toFixed(1)}s` : `${ms}ms`;
}

export default function RunHistory({
  runs,
  onSelect,
}: {
  runs: RunSummary[];
  onSelect: (id: string) => void;
}) {
  if (runs.length === 0) {
    return <div className="empty">No runs yet.</div>;
  }
  return (
    <div className="run-list">
      {runs.map((r) => (
        <div key={r.id} className="run-row" onClick={() => onSelect(r.id)}>
          <div style={{ display: "flex", justifyContent: "space-between", gap: 8 }}>
            <span className="url">{r.url}</span>
            <span className={`badge ${r.status}`}>{r.status}</span>
          </div>
          <div className="stats">
            <span>⏱ {fmtDuration(r.duration_ms)}</span>
            <span className="mono">{r.total_tokens.toLocaleString()} tok</span>
            <span>{r.tool_call_count} tools</span>
          </div>
        </div>
      ))}
    </div>
  );
}
