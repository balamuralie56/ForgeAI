import { useEffect, useState } from "react";
import { api } from "../api";
import type { RunSummary, StorageUsage } from "../types";

const ACTIVE_STATES = new Set(["PENDING", "RUNNING", "WAITING"]);

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function formatWhen(epochSeconds: number): string {
  return new Date(epochSeconds * 1000).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function errorMessage(e: unknown): string {
  return e instanceof Error ? e.message : String(e);
}

/** Lists every recorded run so it can be reopened or deleted, with storage usage. */
export function HistorySidebar({
  selectedId,
  refreshKey,
  onSelect,
  onNew,
  onDeleted,
}: {
  selectedId: string | null;
  refreshKey: unknown;
  onSelect: (id: string) => void;
  onNew: () => void;
  onDeleted: (id: string) => void;
}) {
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [total, setTotal] = useState(0);
  const [storage, setStorage] = useState<StorageUsage | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [confirmId, setConfirmId] = useState<string | null>(null);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    let cancelled = false;
    Promise.all([api.listRuns(50, 0), api.getStorage()])
      .then(([list, usage]) => {
        if (cancelled) return;
        setRuns(list.runs);
        setTotal(list.total);
        setStorage(usage);
        setError(null);
        setLoaded(true);
      })
      .catch((e) => {
        if (cancelled) return;
        setError(errorMessage(e));
        setLoaded(true);
      });
    return () => {
      cancelled = true;
    };
  }, [refreshKey, tick]);

  const hasActive = runs.some((r) => ACTIVE_STATES.has(r.state));
  useEffect(() => {
    if (!hasActive) return;
    const interval = window.setInterval(() => setTick((t) => t + 1), 5000);
    return () => window.clearInterval(interval);
  }, [hasActive]);

  const deleteRun = (id: string) => {
    api
      .deleteRun(id)
      .then(() => {
        setConfirmId(null);
        onDeleted(id);
        setTick((t) => t + 1);
      })
      .catch((e) => {
        setConfirmId(null);
        setError(errorMessage(e));
      });
  };

  return (
    <aside className="history" aria-label="Run history">
      <div className="history__head">
        <h2 className="history__title">History</h2>
        <button type="button" className="history__new" onClick={onNew}>
          + New build
        </button>
      </div>

      {error && <div className="history__error">{error}</div>}

      <ul className="history__list">
        {loaded && runs.length === 0 && !error && (
          <li className="history__empty">No runs yet. Your builds are saved here.</li>
        )}
        {runs.map((run) => (
          <li
            key={run.workflow_id}
            className={`history__item${run.workflow_id === selectedId ? " history__item--selected" : ""}`}
          >
            {confirmId === run.workflow_id ? (
              <div className="history__confirm">
                <span>Delete this run?</span>
                <button
                  type="button"
                  className="history__btn history__btn--danger"
                  onClick={() => deleteRun(run.workflow_id)}
                >
                  Delete
                </button>
                <button type="button" className="history__btn" onClick={() => setConfirmId(null)}>
                  Cancel
                </button>
              </div>
            ) : (
              <>
                <button
                  type="button"
                  className="history__open"
                  onClick={() => onSelect(run.workflow_id)}
                  title={run.goal || run.name}
                >
                  <span className="history__goal">{run.goal || run.name}</span>
                  <span className="history__meta">
                    <span className={`history__state history__state--${run.state.toLowerCase()}`}>
                      {run.state.toLowerCase()}
                    </span>
                    <span>{Math.round(run.progress)}%</span>
                    <span>{formatWhen(run.created_at)}</span>
                  </span>
                  <span className="history__model">{run.model}</span>
                </button>
                <button
                  type="button"
                  className="history__delete"
                  aria-label="Delete run"
                  title="Delete run"
                  disabled={ACTIVE_STATES.has(run.state)}
                  onClick={() => setConfirmId(run.workflow_id)}
                >
                  ✕
                </button>
              </>
            )}
          </li>
        ))}
      </ul>

      {storage && (
        <div className="history__storage" title="Storage used by saved runs and generated files">
          {total} {total === 1 ? "run" : "runs"} · history {formatBytes(storage.history_database_bytes)} ·
          workspace {formatBytes(storage.workspace_bytes)}
        </div>
      )}
    </aside>
  );
}
