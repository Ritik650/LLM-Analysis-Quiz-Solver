import { useEffect, useRef } from "react";
import type { AgentEvent } from "../types";

const TOOL_ICON: Record<string, string> = {
  run_code: "🐍",
  download_file: "⬇️",
  post_request: "📤",
  get_rendered_html: "🌐",
  add_dependencies: "📦",
};

function str(v: unknown): string {
  if (v == null) return "";
  return typeof v === "string" ? v : JSON.stringify(v, null, 2);
}

function TraceItem({ ev }: { ev: AgentEvent }) {
  if (ev.type === "llm") {
    return (
      <div className="trace-item llm">
        <div className="trace-head">
          <span>💭 reasoning</span>
        </div>
        <div className="trace-body reasoning">{str(ev.data.text)}</div>
      </div>
    );
  }
  if (ev.type === "tool") {
    const name = ev.name ?? "tool";
    return (
      <div className="trace-item tool">
        <div className="trace-head">
          <span>{TOOL_ICON[name] ?? "🔧"} tool call</span>
          <span className="chip">{name}</span>
        </div>
        <div className="trace-body">
          <pre>{str(ev.data.input)}</pre>
        </div>
      </div>
    );
  }
  if (ev.type === "tool_result") {
    return (
      <div className="trace-item tool_result">
        <div className="trace-head">
          <span>✅ result</span>
          <span className="chip">{ev.name ?? "tool"}</span>
        </div>
        <div className="trace-body">
          <pre>{str(ev.data.output)}</pre>
        </div>
      </div>
    );
  }
  if (ev.type === "final") {
    const result = ev.data.result as { final_message?: string } | undefined;
    return (
      <div className="trace-item final">
        <div className="trace-head">
          <span>🏁 final answer</span>
          <span className="chip">{ev.data.success ? "success" : "failed"}</span>
        </div>
        <div className="trace-body">{result?.final_message || "Run complete."}</div>
      </div>
    );
  }
  if (ev.type === "error") {
    return (
      <div className="trace-item error">
        <div className="trace-head">
          <span>⚠️ {ev.name ?? "error"}</span>
        </div>
        <div className="trace-body">{str(ev.data.error)}</div>
      </div>
    );
  }
  return null;
}

export default function TraceView({ events }: { events: AgentEvent[] }) {
  const endRef = useRef<HTMLDivElement>(null);
  const display = events.filter((e) =>
    ["llm", "tool", "tool_result", "final", "error"].includes(e.type),
  );

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [display.length]);

  if (display.length === 0) {
    return <div className="empty">No activity yet — submit a quiz URL to begin.</div>;
  }

  return (
    <div className="trace">
      {display.map((ev) => (
        <TraceItem key={ev.seq} ev={ev} />
      ))}
      <div ref={endRef} />
    </div>
  );
}
