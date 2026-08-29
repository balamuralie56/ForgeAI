import { useReport } from "../../useReport";
import { ReportGate } from "../ReportGate";
import type { GitReport } from "../../types";

export function GitTab({ enabled }: { enabled: boolean }) {
  const state = useReport<GitReport>("git_report", enabled);

  return (
    <div className="tab-panel">
      <ReportGate state={state} waitingLabel="Git activity appears once the Git stage completes.">
        {(report) => (
          <div className="git">
            <div className="score-row">
              <span className={`status-chip status-chip--${report.status.toLowerCase()}`}>
                {report.status}
              </span>
              {report.semver && (
                <span className="git__semver">
                  {report.semver.current} → <strong>{report.semver.recommended}</strong>
                  <span className={`bump-pill bump-pill--${report.semver.bump_type.toLowerCase()}`}>
                    {report.semver.bump_type}
                  </span>
                </span>
              )}
            </div>

            {report.semver?.rationale && (
              <p className="tab-panel__summary">{report.semver.rationale}</p>
            )}

            {report.pr && (
              <section className="tab-panel__section">
                <h3>Pull request</h3>
                <a className="pr-card" href={report.pr.url} target="_blank" rel="noreferrer">
                  <span className="pr-card__number">#{report.pr.number}</span>
                  <span className="pr-card__title">{report.pr.title}</span>
                  <span className="pr-card__branch">
                    {report.pr.branch} → {report.pr.base}
                  </span>
                </a>
              </section>
            )}

            {report.commits.length > 0 && (
              <section className="tab-panel__section">
                <h3>Commits ({report.commits.length})</h3>
                <div className="commit-list">
                  {report.commits.map((c) => (
                    <div key={c.sha} className="commit">
                      <span className="commit__sha">{c.sha.slice(0, 7)}</span>
                      <span className="commit__message">{c.message}</span>
                      <span className="commit__author">{c.author}</span>
                    </div>
                  ))}
                </div>
              </section>
            )}

            {report.tags.length > 0 && (
              <section className="tab-panel__section">
                <h3>Tags</h3>
                <div className="tag-list">
                  {report.tags.map((t) => (
                    <span key={t.name} className="tag-pill">
                      {t.name}
                    </span>
                  ))}
                </div>
              </section>
            )}

            {report.changelog && (
              <section className="tab-panel__section">
                <h3>Changelog</h3>
                <pre className="git__changelog">{report.changelog}</pre>
              </section>
            )}
          </div>
        )}
      </ReportGate>
    </div>
  );
}
