import type { Finding } from "../types";

export function FindingsTable({ findings }: { findings: Finding[] }) {
  if (findings.length === 0) {
    return <div className="findings__empty">No findings — clean pass.</div>;
  }

  return (
    <div className="findings">
      {findings.map((f) => (
        <div key={f.id} className="finding">
          <div className="finding__head">
            <span className={`severity-pill severity-pill--${f.severity.toLowerCase()}`}>{f.severity}</span>
            <span className="finding__title">{f.title}</span>
            <span className="finding__rule">{f.rule_id}</span>
          </div>
          <p className="finding__desc">{f.description}</p>
          <div className="finding__meta">
            {f.file_path && (
              <span className="finding__location">
                {f.file_path}
                {f.line_number ? `:${f.line_number}` : ""}
              </span>
            )}
            {f.cwe && <span className="finding__tag">{f.cwe}</span>}
            {f.owasp && <span className="finding__tag">{f.owasp}</span>}
            {f.principle && <span className="finding__tag">{f.principle}</span>}
            <span className="finding__confidence">{f.confidence.toLowerCase()} confidence</span>
          </div>
          {f.recommendation && <p className="finding__recommendation">→ {f.recommendation}</p>}
        </div>
      ))}
    </div>
  );
}
