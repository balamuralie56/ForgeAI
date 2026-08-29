import { useReport } from "../../useReport";
import { ReportGate } from "../ReportGate";
import { ScoreGauge } from "../ScoreGauge";
import { FindingsTable } from "../FindingsTable";
import type { ReviewReport } from "../../types";

export function ReviewTab({ enabled }: { enabled: boolean }) {
  const state = useReport<ReviewReport>("review_report", enabled);

  return (
    <div className="tab-panel">
      <ReportGate state={state} waitingLabel="The code review appears once the Reviewer stage completes.">
        {(report) => (
          <div className="review">
            <div className="score-row">
              <ScoreGauge label="Quality score" value={report.quality_score} goodDirection="up" />
              <span className={`status-chip status-chip--${report.status.toLowerCase()}`}>
                {report.status}
              </span>
            </div>

            {report.summary && <p className="tab-panel__summary">{report.summary}</p>}

            <section className="tab-panel__section">
              <h3>SOLID principles</h3>
              <div className="solid-grid">
                {Object.entries(report.solid_scores).map(([principle, score]) =>
                  score === null ? (
                    <div key={principle} className="solid-grid__unscored">
                      <span className="solid-grid__label">{principle}</span>
                      <span>not evaluated</span>
                    </div>
                  ) : (
                    <ScoreGauge key={principle} label={principle} value={score} goodDirection="up" />
                  ),
                )}
              </div>
            </section>

            {report.recommendations.length > 0 && (
              <section className="tab-panel__section">
                <h3>Recommendations</h3>
                <ul className="plan__list">
                  {report.recommendations.map((r, i) => (
                    <li key={i}>{r}</li>
                  ))}
                </ul>
              </section>
            )}

            <section className="tab-panel__section">
              <h3>Findings ({report.findings.length})</h3>
              <FindingsTable findings={report.findings} />
            </section>
          </div>
        )}
      </ReportGate>
    </div>
  );
}
