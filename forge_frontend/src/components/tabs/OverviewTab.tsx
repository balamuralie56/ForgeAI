import { RequestForm } from "../RequestForm";
import type { WorkflowStatus } from "../../types";

function formatTime(epochSeconds: number | null): string {
  if (!epochSeconds) return "—";
  return new Date(epochSeconds * 1000).toLocaleString();
}

export function OverviewTab({
  workflow,
  isRunning,
  onSubmit,
}: {
  workflow: WorkflowStatus | null;
  isRunning: boolean;
  onSubmit: (goal: string) => void;
}) {
  return (
    <div className="tab-panel">
      <RequestForm onSubmit={onSubmit} disabled={isRunning} />

      {workflow && (
        <div className="overview-card">
          <div className="overview-card__row">
            <span className="overview-card__label">Type</span>
            <span>{workflow.type}</span>
          </div>
          <div className="overview-card__row">
            <span className="overview-card__label">Started</span>
            <span>{formatTime(workflow.created_at)}</span>
          </div>
          <div className="overview-card__row">
            <span className="overview-card__label">Last update</span>
            <span>{formatTime(workflow.updated_at)}</span>
          </div>
          <div className="overview-card__row">
            <span className="overview-card__label">Workflow ID</span>
            <span className="overview-card__id">{workflow.id}</span>
          </div>
        </div>
      )}
    </div>
  );
}
