import { useState } from "react";
import type { ChangeSet, CheckResult } from "../../assistantTypes";

function DiffView({ diff }: { diff: string }) {
  const lines = diff.replace(/\n$/, "").split("\n");
  return (
    <pre className="diff">
      {lines.map((line, i) => {
        let kind = "ctx";
        if (line.startsWith("+++") || line.startsWith("---")) kind = "file";
        else if (line.startsWith("@@")) kind = "hunk";
        else if (line.startsWith("+")) kind = "add";
        else if (line.startsWith("-")) kind = "del";
        return (
          <span key={i} className={`diff__line diff__line--${kind}`}>
            {line || " "}
          </span>
        );
      })}
    </pre>
  );
}

const STATUS_LABEL: Record<ChangeSet["status"], string> = {
  pending: "Proposed",
  applied: "Applied",
  discarded: "Discarded",
  reverted: "Undone",
};

export function CheckOutput({ result }: { result: CheckResult }) {
  const tone = result.passed ? "good" : "bad";
  const verdict = result.error && result.exit_code === null && !result.timed_out
    ? `could not run: ${result.error}`
    : result.timed_out
      ? `stopped after ${Math.round(result.duration_seconds)}s`
      : result.passed
        ? `passed in ${result.duration_seconds.toFixed(1)}s`
        : `failed (exit code ${result.exit_code}) in ${result.duration_seconds.toFixed(1)}s`;
  return (
    <details className={`check check--${tone}`} open={!result.passed}>
      <summary>
        <span className="check__dot" />
        <code>{result.command}</code> {verdict}
      </summary>
      {result.output && <pre className="check__output">{result.output}</pre>}
    </details>
  );
}

/** A proposed change: per-file diffs, static check results, and apply / discard / undo. */
export function ChangeSetCard({
  changeSet,
  busy,
  onApply,
  onDiscard,
  onRevert,
  onFix,
}: {
  changeSet: ChangeSet;
  busy: boolean;
  onApply: () => Promise<void>;
  onDiscard: () => Promise<void>;
  onRevert: () => Promise<void>;
  onFix: (result: CheckResult) => void;
}) {
  const [working, setWorking] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const verification = changeSet.verification;

  const run = (action: () => Promise<void>) => {
    setWorking(true);
    setError(null);
    action()
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setWorking(false));
  };

  const disabled = busy || working;
  return (
    <div className={`change change--${changeSet.status}`}>
      <div className="change__head">
        <span className={`change__status change__status--${changeSet.status}`}>
          {STATUS_LABEL[changeSet.status]}
        </span>
        <span className="change__summary">{changeSet.summary}</span>
      </div>

      {verification && (
        <div
          className={`change__verify change__verify--${verification.passed ? (verification.warning_count ? "warn" : "good") : "bad"}`}
        >
          {verification.passed
            ? verification.checked_files
              ? `Static checks passed (${verification.checked_files} files checked${verification.warning_count ? `, ${verification.warning_count} warning(s)` : ""}).`
              : verification.skipped_reason || "Nothing to check statically."
            : `Static checks found ${verification.error_count} problem(s) this change would introduce:`}
          {verification.issues.length > 0 && (
            <ul>
              {verification.issues.map((issue, i) => (
                <li key={i}>
                  <span className={`change__sev change__sev--${issue.severity}`}>{issue.severity}</span>{" "}
                  <code>
                    {issue.path}
                    {issue.line ? `:${issue.line}` : ""}
                  </code>{" "}
                  {issue.message}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {changeSet.files.map((file) => (
        <details className="change__file" key={file.path} open={changeSet.status === "pending"}>
          <summary>
            <code>{file.path}</code>
            {file.is_new && <span className="change__new">new file</span>}
          </summary>
          <DiffView diff={file.diff} />
        </details>
      ))}

      {changeSet.check && <CheckOutput result={changeSet.check} />}

      {error && <div className="change__error">{error}</div>}

      <div className="change__actions">
        {changeSet.status === "pending" && (
          <>
            <button className="btn btn--primary" disabled={disabled} onClick={() => run(onApply)}>
              {working ? "Applying…" : "Apply change"}
            </button>
            <button className="btn" disabled={disabled} onClick={() => run(onDiscard)}>
              Discard
            </button>
          </>
        )}
        {changeSet.status === "applied" && (
          <button className="btn" disabled={disabled} onClick={() => run(onRevert)}>
            {working ? "Undoing…" : "Undo change"}
          </button>
        )}
        {changeSet.status === "applied" && changeSet.check && !changeSet.check.passed && (
          <button
            className="btn btn--primary"
            disabled={disabled}
            onClick={() => changeSet.check && onFix(changeSet.check)}
          >
            Ask ForgeAI to fix it
          </button>
        )}
      </div>
    </div>
  );
}
