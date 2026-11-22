import { useState } from "react";
import type { FormEvent } from "react";
import type { ConversationSettingsInput } from "../../assistantTypes";

/** Project folder, check command and auto-fix settings, for a new or existing conversation. */
export function ConversationForm({
  initial,
  recentFolders,
  maxFixRounds,
  submitLabel,
  onSubmit,
  onCancel,
}: {
  initial: ConversationSettingsInput;
  recentFolders: string[];
  maxFixRounds: number;
  submitLabel: string;
  onSubmit: (input: ConversationSettingsInput) => Promise<void>;
  onCancel?: () => void;
}) {
  const [projectRoot, setProjectRoot] = useState(initial.project_root);
  const [checkCommand, setCheckCommand] = useState(initial.check_command);
  const [autoFix, setAutoFix] = useState(initial.auto_fix);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = (e: FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setError(null);
    onSubmit({ project_root: projectRoot.trim(), check_command: checkCommand.trim(), auto_fix: autoFix })
      .catch((err) => setError(err instanceof Error ? err.message : String(err)))
      .finally(() => setSaving(false));
  };

  return (
    <form className="conv-form" onSubmit={submit}>
      <label className="conv-form__field">
        <span>Project folder</span>
        <input
          list="forge-recent-folders"
          required
          value={projectRoot}
          placeholder="B:\Projects\my-app"
          onChange={(e) => setProjectRoot(e.target.value)}
        />
        <datalist id="forge-recent-folders">
          {recentFolders.map((folder) => (
            <option key={folder} value={folder} />
          ))}
        </datalist>
        <small>The full path of the project ForgeAI should read and change.</small>
      </label>

      <label className="conv-form__field">
        <span>Check command (optional)</span>
        <input
          value={checkCommand}
          placeholder="python -m pytest -q"
          onChange={(e) => setCheckCommand(e.target.value)}
        />
        <small>
          Runs in the project folder after a change is applied, usually your tests. It runs without a
          shell, so <code>&&</code> and pipes don't work. A leading <code>python</code> uses the
          project's own <code>.venv</code> if it has one. ForgeAI never runs code the model writes.
        </small>
      </label>

      <label className="conv-form__check">
        <input type="checkbox" checked={autoFix} onChange={(e) => setAutoFix(e.target.checked)} />
        <span>
          Auto-fix: apply changes without asking
          {checkCommand.trim()
            ? `, run the check, and fix failures automatically (up to ${maxFixRounds} rounds)`
            : ""}
          . Every change can still be undone.
        </span>
      </label>

      {error && <div className="change__error">{error}</div>}

      <div className="conv-form__actions">
        {onCancel && (
          <button type="button" className="btn" onClick={onCancel}>
            Cancel
          </button>
        )}
        <button type="submit" className="btn btn--primary" disabled={saving || !projectRoot.trim()}>
          {saving ? "Saving…" : submitLabel}
        </button>
      </div>
    </form>
  );
}
