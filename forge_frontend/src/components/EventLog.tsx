import { useEffect, useRef } from "react";
import type { ForgeEvent } from "../types";

function summarize(event: ForgeEvent): string {
  const { event_type, data } = event;
  if (event_type === "workflow.stage_started") return `▸ starting ${data.stage_name}`;
  if (event_type === "workflow.stage_completed") return `✓ ${data.stage_name} completed`;
  if (event_type === "workflow.retry")
    return `↻ ${data.stage_name} retrying (attempt ${data.failed_attempt} failed)`;
  if (event_type.endsWith(".finding.detected"))
    return `⚑ [${data.severity}] ${data.title ?? data.rule_id} — ${data.file_path ?? ""}:${data.line_number ?? ""}`;
  if (event_type.endsWith(".completed")) return `✓ ${event_type}`;
  if (event_type.endsWith(".failed")) return `✕ ${event_type}: ${data.error ?? ""}`;
  return event_type;
}

function severityClass(event: ForgeEvent): string {
  if (event.event_type.endsWith(".failed") || event.event_type === "workflow.retry")
    return "log-line--warn";
  if (event.event_type.endsWith(".completed") || event.event_type === "workflow.completed")
    return "log-line--ok";
  return "";
}

export function EventLog({ events }: { events: ForgeEvent[] }) {
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [events.length]);

  return (
    <div className="event-log">
      <div className="event-log__header">Activity</div>
      <div className="event-log__body" ref={scrollRef}>
        {events.length === 0 && <div className="event-log__empty">No activity yet.</div>}
        {events.map((event, i) => (
          <div key={i} className={`log-line ${severityClass(event)}`}>
            <span className="log-line__time">
              {new Date(event.timestamp).toLocaleTimeString()}
            </span>
            <span className="log-line__text">{summarize(event)}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
