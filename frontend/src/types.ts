// Shared types mirroring the backend event + run schemas.

export type EventType =
  | "status"
  | "node"
  | "llm"
  | "tool"
  | "tool_result"
  | "token"
  | "final"
  | "error"
  | "done";

export interface AgentEvent {
  run_id: string;
  seq: number;
  type: EventType;
  name?: string | null;
  node?: string | null;
  data: Record<string, unknown>;
  ts: number;
}

export interface RunSummary {
  id: string;
  url: string;
  status: "running" | "success" | "failed";
  success: boolean | null;
  started_at: string | null;
  finished_at: string | null;
  duration_ms: number | null;
  total_tokens: number;
  est_cost_usd: number;
  tool_call_count: number;
}

export interface RunStep {
  seq: number;
  type: EventType;
  node: string | null;
  name: string | null;
  data: Record<string, unknown>;
  ts: string | null;
}

export interface RunDetail extends RunSummary {
  prompt_tokens: number;
  completion_tokens: number;
  final_result: Record<string, unknown> | null;
  error: string | null;
  steps: RunStep[];
}
