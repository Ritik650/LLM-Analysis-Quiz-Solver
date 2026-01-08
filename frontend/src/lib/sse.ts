// SSE subscription helper.
//
// EventSource cannot set custom headers, so the JWT is passed as ?token=. The
// backend emits one named SSE event per agent event type; we register a generic
// listener for each known type and forward parsed payloads to the caller.

import { apiBase, getToken } from "./api";
import type { AgentEvent, EventType } from "../types";

const EVENT_TYPES: EventType[] = [
  "status",
  "node",
  "llm",
  "tool",
  "tool_result",
  "token",
  "final",
  "error",
  "done",
];

export function streamRun(
  runId: string,
  onEvent: (event: AgentEvent) => void,
  onDone: () => void,
): () => void {
  const token = getToken() ?? "";
  const url = `${apiBase}/runs/${runId}/stream?token=${encodeURIComponent(token)}`;
  const source = new EventSource(url);

  const handle = (raw: MessageEvent) => {
    try {
      const event = JSON.parse(raw.data) as AgentEvent;
      if (event.type === "done") {
        onDone();
        source.close();
      } else {
        onEvent(event);
      }
    } catch {
      /* ignore malformed frame */
    }
  };

  for (const type of EVENT_TYPES) {
    source.addEventListener(type, handle as EventListener);
  }

  source.onerror = () => {
    // Connection dropped or run finished; close and signal done.
    source.close();
    onDone();
  };

  return () => source.close();
}
