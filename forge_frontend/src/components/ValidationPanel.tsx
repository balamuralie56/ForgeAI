import { useReport } from "../useReport";
import type { CodeValidation, ImplementationReport } from "../types";

function summary(validation: CodeValidation): { tone: string; text: string } {
  const { error_count: errors, warning_count: warnings } = validation;
  const plural = (n: number, word: string) => `${n} ${word}${n === 1 ? "" : "s"}`;
  if (errors > 0) {
    return {
      tone: "bad",
      text: `Validation failed: ${plural(errors, "error")}, ${plural(warnings, "warning")}`,
    };
  }
  if (warnings > 0) {
    return { tone: "warn", text: `Validation passed with ${plural(warnings, "warning")}` };
  }
  return { tone: "good", text: "Validation passed" };
}

/** Shows whether the Developer's generated code passed static validation, issue by issue. */
export function ValidationPanel({
  enabled,
  onOpenFile,
}: {
  enabled: boolean;
  onOpenFile: (path: string) => void;
}) {
  const state = useReport<ImplementationReport>("implementation_report", enabled);
  if (state.status !== "ready") return null;

  const validation = state.data.validation;
  if (!validation) {
    return (
      <div className="validation validation--none">
        This run was generated before code validation existed, so its code was not checked.
      </div>
    );
  }

  const { tone, text } = summary(validation);
  return (
    <div className={`validation validation--${tone}`}>
      <div className="validation__head">
        <span className="validation__title">{text}</span>
        <span className="validation__meta">
          {validation.checked_files} files checked · static checks only, nothing was executed
        </span>
      </div>
      {validation.issues.length > 0 && (
        <details className="validation__details" open={validation.error_count > 0}>
          <summary>Show {validation.issues.length} issues</summary>
          <ul className="validation__list">
            {validation.issues.map((issue, i) => (
              <li key={i} className="validation__issue">
                <span className={`validation__sev validation__sev--${issue.severity}`}>
                  {issue.severity}
                </span>
                <span className="validation__check">{issue.check}</span>
                <button
                  type="button"
                  className="validation__loc"
                  onClick={() => onOpenFile(issue.path)}
                  title="Open this file"
                >
                  {issue.line ? `${issue.path}:${issue.line}` : issue.path}
                </button>
                <span className="validation__msg">{issue.message}</span>
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}
