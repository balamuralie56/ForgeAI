import { useState } from "react";
import { useReport } from "../../useReport";
import { ReportGate } from "../ReportGate";
import { CodeViewer } from "../CodeViewer";
import type { TestReport } from "../../types";

export function TestsTab({ enabled }: { enabled: boolean }) {
  const state = useReport<TestReport>("test_report", enabled);
  const [selected, setSelected] = useState<string | null>(null);

  return (
    <div className="tab-panel">
      <ReportGate state={state} waitingLabel="Test results appear once the Tester stage completes.">
        {(report) => {
          const byType = new Map<string, typeof report.test_files>();
          for (const f of report.test_files) {
            const list = byType.get(f.test_type) ?? [];
            list.push(f);
            byType.set(f.test_type, list);
          }
          const activeFile = report.test_files.find((f) => f.path === selected) ?? null;

          return (
            <div className="tests">
              <div className="score-row">
                <span className={`status-chip status-chip--${report.status.toLowerCase()}`}>
                  {report.status}
                </span>
                {report.coverage_summary && (
                  <span className="tests__coverage">{report.coverage_summary}</span>
                )}
              </div>

              {report.summary && <p className="tab-panel__summary">{report.summary}</p>}

              <div className="tests__split">
                <div className="tests__list">
                  {[...byType.entries()].map(([type, files]) => (
                    <div key={type} className="tests__group">
                      <div className="tests__group-label">{type}</div>
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
                  {report.test_files.length === 0 && (
                    <div className="report-gate__empty">No test files generated.</div>
                  )}
                </div>
                <div className="tests__preview">
                  {activeFile ? (
                    <CodeViewer path={activeFile.path} content={activeFile.content} />
                  ) : (
                    <div className="report-gate__empty">Select a test file to preview it.</div>
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
