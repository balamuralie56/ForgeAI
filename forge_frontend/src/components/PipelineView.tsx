import { STAGE_ORDER } from "../types";
import type { WorkflowStatus } from "../types";

const STAGE_LABELS: Record<string, string> = {
  planner: "Planner",
  architect: "Architect",
  developer: "Developer",
  tester: "Tester",
  documentation: "Documentation",
  security: "Security",
  reviewer: "Reviewer",
  git: "Git",
};

const STATUS_ICON: Record<string, string> = {
  PENDING: "○",
  RUNNING: "◐",
  WAITING: "◐",
  COMPLETED: "●",
  FAILED: "✕",
  CANCELLED: "–",
};

export function PipelineView({ workflow }: { workflow: WorkflowStatus }) {
  const stageByName = new Map(workflow.stages.map((s) => [s.name, s]));
  const knownStages = new Set<string>(STAGE_ORDER);
  const orderedNames: string[] = [
    ...STAGE_ORDER.filter((n) => stageByName.has(n)),
    ...workflow.stages.map((s) => s.name).filter((n) => !knownStages.has(n)),
  ];

  return (
    <div className="pipeline">
      <div className="pipeline__header">
        <h2>{workflow.name}</h2>
        <span className={`pipeline__state pipeline__state--${workflow.state.toLowerCase()}`}>
          {workflow.state}
        </span>
      </div>

      <div className="pipeline__progress-track">
        <div
          className="pipeline__progress-fill"
          style={{ width: `${workflow.progress}%` }}
        />
      </div>
      <div className="pipeline__progress-label">{workflow.progress.toFixed(0)}%</div>

      <ol className="pipeline__stages">
        {orderedNames.map((name) => {
          const stage = stageByName.get(name);
          if (!stage) return null;
          const error = workflow.errors[name];
          return (
            <li
              key={name}
              className={`stage stage--${stage.status.toLowerCase()} ${stage.optional ? "stage--optional" : ""}`}
            >
              <span className="stage__icon">{STATUS_ICON[stage.status] ?? "○"}</span>
              <span className="stage__name">{STAGE_LABELS[name] ?? name}</span>
              {stage.optional && <span className="stage__badge">optional</span>}
              {error && <span className="stage__error" title={error}>{error}</span>}
            </li>
          );
        })}
      </ol>
    </div>
  );
}
