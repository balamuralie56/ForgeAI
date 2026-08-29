import { useReport } from "../../useReport";
import { ReportGate } from "../ReportGate";
import type { ProjectPlan } from "../../types";

export function PlanTab({ enabled }: { enabled: boolean }) {
  const state = useReport<ProjectPlan>("project_plan", enabled);

  return (
    <div className="tab-panel">
      <ReportGate state={state} waitingLabel="The plan appears once the Planner stage completes.">
        {(plan) => (
          <div className="plan">
            <section className="plan__section">
              <h3>Goal</h3>
              <p className="plan__goal">{plan.goal.goal}</p>
              {plan.goal.description && <p className="plan__goal-desc">{plan.goal.description}</p>}
            </section>

            {plan.milestones.length > 0 && (
              <section className="plan__section">
                <h3>Milestones</h3>
                <div className="plan__milestones">
                  {plan.milestones.map((m) => {
                    const tasksByMilestone = plan.tasks.filter((t) => t.milestone_id === m.milestone_id);
                    return (
                      <div key={m.milestone_id} className="milestone">
                        <div className="milestone__title">{m.title}</div>
                        {m.description && <p className="milestone__desc">{m.description}</p>}
                        {tasksByMilestone.length > 0 && (
                          <ul className="milestone__tasks">
                            {tasksByMilestone.map((t) => (
                              <li key={t.task_id}>
                                <span>{t.name}</span>
                                <span className="milestone__hours">{t.estimated_duration_hours}h</span>
                              </li>
                            ))}
                          </ul>
                        )}
                      </div>
                    );
                  })}
                </div>
              </section>
            )}

            {plan.requirements.length > 0 && (
              <section className="plan__section">
                <h3>Requirements</h3>
                <ul className="plan__requirements">
                  {plan.requirements.map((r) => (
                    <li key={r.requirement_id}>
                      <span className={`priority-pill priority-pill--${r.priority.toLowerCase()}`}>
                        {r.priority}
                      </span>
                      <span>{r.description}</span>
                      <span className="plan__req-type">{r.is_functional ? "functional" : "non-functional"}</span>
                    </li>
                  ))}
                </ul>
              </section>
            )}

            {(plan.risks.length > 0 || plan.assumptions.length > 0) && (
              <div className="plan__grid">
                {plan.risks.length > 0 && (
                  <section className="plan__section">
                    <h3>Risks</h3>
                    <ul className="plan__list">
                      {plan.risks.map((r, i) => (
                        <li key={i}>{r}</li>
                      ))}
                    </ul>
                  </section>
                )}
                {plan.assumptions.length > 0 && (
                  <section className="plan__section">
                    <h3>Assumptions</h3>
                    <ul className="plan__list">
                      {plan.assumptions.map((a, i) => (
                        <li key={i}>{a}</li>
                      ))}
                    </ul>
                  </section>
                )}
              </div>
            )}

            {plan.clarifications.length > 0 && (
              <section className="plan__section">
                <h3>Clarifications assumed</h3>
                <ul className="plan__list">
                  {plan.clarifications.map((c) => (
                    <li key={c.question_id}>
                      <strong>{c.question}</strong> — assumed: {c.assumed_answer}
                    </li>
                  ))}
                </ul>
              </section>
            )}
          </div>
        )}
      </ReportGate>
    </div>
  );
}
