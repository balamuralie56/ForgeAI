import { useState } from "react";
import { useReport } from "../../useReport";
import { ReportGate } from "../ReportGate";
import { CodeViewer } from "../CodeViewer";
import type { DocumentationReport } from "../../types";

export function DocumentationTab({ enabled }: { enabled: boolean }) {
  const state = useReport<DocumentationReport>("documentation_report", enabled);
  const [selected, setSelected] = useState<string | null>(null);

  return (
    <div className="tab-panel">
      <ReportGate state={state} waitingLabel="Docs appear once the Documentation stage completes.">
        {(report) => {
          const byCategory = new Map<string, typeof report.doc_files>();
          for (const f of report.doc_files) {
            const list = byCategory.get(f.category) ?? [];
            list.push(f);
            byCategory.set(f.category, list);
          }
          const activeFile = report.doc_files.find((f) => f.path === selected) ?? null;

          return (
            <div className="tests">
              <div className="score-row">
                <span className={`status-chip status-chip--${report.status.toLowerCase()}`}>
                  {report.status}
                </span>
              </div>

              {report.summary && <p className="tab-panel__summary">{report.summary}</p>}

              <div className="tests__split">
                <div className="tests__list">
                  {[...byCategory.entries()].map(([category, files]) => (
                    <div key={category} className="tests__group">
                      <div className="tests__group-label">{category}</div>
                      {files.map((f) => (
                        <button
                          key={f.path}
                          type="button"
                          className={`tests__file ${selected === f.path ? "tests__file--active" : ""}`}
                          onClick={() => setSelected(f.path)}
                        >
                          {f.path}
                        </button>
                      ))}
                    </div>
                  ))}
                  {report.doc_files.length === 0 && (
                    <div className="report-gate__empty">No documentation files generated.</div>
                  )}
                </div>
                <div className="tests__preview">
                  {activeFile ? (
                    <CodeViewer path={activeFile.path} content={activeFile.content} />
                  ) : (
                    <div className="report-gate__empty">Select a document to preview it.</div>
                  )}
                </div>
              </div>
            </div>
          );
        }}
      </ReportGate>
    </div>
  );
}
