import type { AssistantMessage, ChangeSet, CheckResult, IncludedCode } from "../../assistantTypes";
import { ChangeSetCard, CheckOutput } from "./ChangeSetCard";
import { RichText } from "./RichText";

/** The prose a model wrote before its first edit block (its plan). */
function planText(content: string): string {
  const before = content.split(/^\s*<{5,9}\s*SEARCH\s*$/m)[0];
  // Code in an edit reply is what the change card's diff already shows.
  const lines: string[] = [];
  let inCode = false;
  for (const line of before.split("\n")) {
    if (/^\s*(```|~~~)/.test(line)) {
      inCode = !inCode;
      continue;
    }
    if (!inCode && !/^#{1,6}\s+\S+\s+\((whole file|lines \d+-\d+ of \d+[^)]*)\)\s*$/.test(line.trim())) {
      lines.push(line);
    }
  }
  while (lines.length && !lines[lines.length - 1].trim()) lines.pop();
  const pathLine = /^[\s*#`>-]*(?:(?:file(?:name)?|path)\s*:\s*)?[\w./\\-]+\.[A-Za-z0-9]{1,8}[`*:\s]*$/i;
  if (lines.length && pathLine.test(lines[lines.length - 1])) lines.pop();
  return lines.join("\n").trim();
}

export function ContextLine({ included }: { included: IncludedCode[] }) {
  if (!included.length) return null;
  const shown = included.slice(0, 6).map((c) =>
    c.full ? c.path : `${c.path}:${c.start_line}-${c.end_line}`,
  );
  const more = included.length - shown.length;
  return (
    <div className="msg__context" title={included.map((c) => `${c.path} ${c.start_line}-${c.end_line}`).join("\n")}>
      Read {shown.join(", ")}
      {more > 0 ? ` and ${more} more` : ""}
    </div>
  );
}

function footer(message: AssistantMessage): string {
  const parts: string[] = [];
  if (message.metadata.seconds !== undefined) parts.push(`${message.metadata.seconds.toFixed(1)} s`);
  const tokens = message.metadata.usage?.completion_tokens;
  if (tokens) parts.push(`${tokens} tokens`);
  const attempts = message.metadata.attempts?.length ?? 0;
  if (attempts > 1) parts.push(`${attempts} attempts`);
  if (message.metadata.cancelled) parts.push("stopped");
  return parts.join(" · ");
}

/** One stored message: a user request, an assistant reply (with its change), or a check run. */
export function MessageItem({
  message,
  changeSet,
  busy,
  onApply,
  onDiscard,
  onRevert,
  onFix,
}: {
  message: AssistantMessage;
  changeSet?: ChangeSet;
  busy: boolean;
  onApply: (id: string) => Promise<void>;
  onDiscard: (id: string) => Promise<void>;
  onRevert: (id: string) => Promise<void>;
  onFix: (result: CheckResult) => void;
}) {
  if (message.role === "user") {
    return (
      <div className="msg msg--user">
        {message.metadata.auto_fix_round && (
          <div className="msg__badge">Auto-fix round {message.metadata.auto_fix_round}</div>
        )}
        <RichText text={message.content} />
        {message.metadata.attached && message.metadata.attached.length > 0 && (
          <div className="msg__context">Attached {message.metadata.attached.join(", ")}</div>
        )}
      </div>
    );
  }

  if (message.role === "check") {
    const result = message.metadata.check;
    return (
      <div className="msg msg--check">
        {result ? <CheckOutput result={result} /> : message.content}
        {result && !result.passed && (
          <button className="btn btn--ghost msg__fix" disabled={busy} onClick={() => onFix(result)}>
            Ask ForgeAI to fix it
          </button>
        )}
      </div>
    );
  }

  const isEdit = message.mode === "edit";
  const plan = isEdit ? planText(message.content) : message.content;
  const attempts = message.metadata.attempts ?? [];
  const lastProblems = attempts.length ? attempts[attempts.length - 1].problems : undefined;
  return (
    <div className="msg msg--assistant">
      <ContextLine included={message.metadata.context ?? []} />
      {plan ? <RichText text={plan} /> : !changeSet && !message.metadata.error && <p className="msg__muted">(No reply.)</p>}
      {changeSet && (
        <ChangeSetCard
          changeSet={changeSet}
          busy={busy}
          onApply={() => onApply(changeSet.id)}
          onDiscard={() => onDiscard(changeSet.id)}
          onRevert={() => onRevert(changeSet.id)}
          onFix={onFix}
        />
      )}
      {message.metadata.edit_failed && (
        <div className="msg__warn">
          The model's edits did not match the files after {attempts.length} tries, so nothing was
          proposed.
          {lastProblems && (
            <ul>
              {lastProblems.map((p, i) => (
                <li key={i}>
                  {p.path && <code>{p.path}</code>} {p.message}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
      {message.metadata.error && <div className="msg__warn">{message.metadata.error}</div>}
      {isEdit && message.content && (changeSet || message.metadata.edit_failed) && (
        <details className="msg__raw">
          <summary>Model's raw reply</summary>
          <pre>{message.content}</pre>
        </details>
      )}
      {footer(message) && <div className="msg__footer">{footer(message)}</div>}
    </div>
  );
}
