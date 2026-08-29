import { useReport } from "../../useReport";
import { ReportGate } from "../ReportGate";
import { ScoreGauge } from "../ScoreGauge";
import { FindingsTable } from "../FindingsTable";
import type { SecurityReport } from "../../types";

export function SecurityTab({ enabled }: { enabled: boolean }) {
  const state = useReport<SecurityReport>("security_report", enabled);

  return (
    <div className="tab-panel">
      <ReportGate state={state} waitingLabel="The security review appears once the Security stage completes.">
        {(report) => (
          <div className="security">
            <div className="score-row">
              <ScoreGauge label="Security score" value={report.security_score} goodDirection="up" />
              <ScoreGauge label="Risk score" value={report.risk_score} goodDirection="down" />
              <span className={`status-chip status-chip--${report.status.toLowerCase()}`}>
                {report.status}
              </span>
            </div>

            {report.summary && <p className="tab-panel__summary">{report.summary}</p>}

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
