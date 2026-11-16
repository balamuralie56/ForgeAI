import { useContext, useEffect, useState } from "react";
import { api, ApiError } from "./api";
import { RunContext } from "./runContext";

export type ReportState<T> =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "ready"; data: T }
  | { status: "unavailable" }
  | { status: "error"; message: string };

/**
 * Fetches a plugin report once `enabled` flips true (typically once that stage
 * completes) and refetches whenever `refreshKey` or the selected run changes.
 * When a run is selected the report comes from that run's own stored copy
 * (GET /api/history/runs/{id}/artifacts/{key}), so opening an older run never
 * shows a newer run's data; with no run selected it falls back to the latest
 * report (GET /api/reports/{key}). A 404 means "not computed yet", not an error.
 */
export function useReport<T>(
  key: string,
  enabled: boolean,
  refreshKey: unknown = null,
): ReportState<T> {
  const runId = useContext(RunContext);
  const [state, setState] = useState<ReportState<T>>({ status: "idle" });

  useEffect(() => {
    if (!enabled) return;
    let cancelled = false;
    setState({ status: "loading" });
    const request = runId
      ? api.getRunArtifact<T>(runId, key)
      : api.getReport<T>(key);
    request
      .then((res) => !cancelled && setState({ status: "ready", data: res.data }))
      .catch((e) => {
        if (cancelled) return;
        if (e instanceof ApiError && e.status === 404) {
          setState({ status: "unavailable" });
        } else {
          setState({
            status: "error",
            message: e instanceof Error ? e.message : String(e),
          });
        }
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, enabled, refreshKey, runId]);

  return state;
}
