import type { ReactNode } from "react";
import type { ReportState } from "../useReport";

/** Renders the right empty/loading/error state for a report, or the content once ready. */
export function ReportGate<T>({
  state,
  waitingLabel,
  children,
}: {
  state: ReportState<T>;
  waitingLabel: string;
  children: (data: T) => ReactNode;
}) {
  if (state.status === "idle" || state.status === "unavailable") {
    return <div className="report-gate__empty">{waitingLabel}</div>;
  }
  if (state.status === "loading") {
    return <div className="report-gate__empty">Loading…</div>;
  }
  if (state.status === "error") {
    return <div className="report-gate__error">{state.message}</div>;
  }
  return <>{children(state.data)}</>;
}
