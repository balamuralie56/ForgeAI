import { useEffect, useState } from "react";
import { api, ApiError } from "./api";

export type ReportState<T> =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "ready"; data: T }
  | { status: "unavailable" }
  | { status: "error"; message: string };

/**
 * Fetches a plugin report (GET /api/reports/{key}) once `enabled` flips true
 * (typically once that stage completes) and refetches whenever `refreshKey`
 * changes - a 404 means "not computed yet", not a real error.
 */
export function useReport<T>(
  key: string,
  enabled: boolean,
  refreshKey: unknown = null,
): ReportState<T> {
  const [state, setState] = useState<ReportState<T>>({ status: "idle" });

  useEffect(() => {
    if (!enabled) return;
    let cancelled = false;
    setState({ status: "loading" });
    api
      .getReport<T>(key)
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
  }, [key, enabled, refreshKey]);

  return state;
}
