import { useMemo, useState } from "react";
import type { KeyboardEvent } from "react";
import type { AssistantMode } from "../../assistantTypes";

const PLACEHOLDER: Record<AssistantMode, string> = {
  ask: "Ask about this project. Point at a file with @name, e.g. “how does @store.py save tasks?”",
  edit: "Describe the change, e.g. “add a --verbose flag to @cli.py”. ForgeAI proposes a diff for you to apply.",
};

/** Message box with Ask / Change mode, file attachments, and send / stop. */
export function Composer({
  busy,
  files,
  onLoadFiles,
  onSend,
  onStop,
}: {
  busy: boolean;
  files: string[] | null;
  onLoadFiles: () => void;
  onSend: (text: string, mode: AssistantMode, attached: string[]) => void;
  onStop: () => void;
}) {
  const [text, setText] = useState("");
  const [mode, setMode] = useState<AssistantMode>("ask");
  const [attached, setAttached] = useState<string[]>([]);
  const [picking, setPicking] = useState(false);
  const [filter, setFilter] = useState("");

  const matches = useMemo(() => {
    if (!files) return [];
    const needle = filter.trim().toLowerCase();
    return files
      .filter((f) => !attached.includes(f) && (!needle || f.toLowerCase().includes(needle)))
      .slice(0, 40);
  }, [files, filter, attached]);

  const send = () => {
    const trimmed = text.trim();
    if (!trimmed || busy) return;
    onSend(trimmed, mode, attached);
    setText("");
    setAttached([]);
    setPicking(false);
  };

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      send();
    }
  };

  return (
    <div className="composer">
      {attached.length > 0 && (
        <div className="composer__chips">
          {attached.map((path) => (
            <span className="composer__chip" key={path}>
              {path}
              <button
                aria-label={`Remove ${path}`}
                onClick={() => setAttached((a) => a.filter((p) => p !== path))}
              >
                ✕
              </button>
            </span>
          ))}
        </div>
      )}

      {picking && (
        <div className="composer__picker">
          <input
            autoFocus
            placeholder={files ? "Filter files…" : "Loading files…"}
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
          />
          <ul>
            {matches.map((path) => (
              <li key={path}>
                <button
                  onClick={() => {
                    setAttached((a) => [...a, path]);
                    setFilter("");
                  }}
                >
                  {path}
                </button>
              </li>
            ))}
            {files && matches.length === 0 && <li className="composer__none">No matching files.</li>}
          </ul>
        </div>
      )}

      <textarea
        className="composer__input"
        rows={3}
        value={text}
        placeholder={PLACEHOLDER[mode]}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={onKeyDown}
      />

      <div className="composer__bar">
        <div className="segmented" role="radiogroup" aria-label="Mode">
          <button
            role="radio"
            aria-checked={mode === "ask"}
            className={mode === "ask" ? "segmented__on" : ""}
            onClick={() => setMode("ask")}
            title="Answer questions about the code. Never changes files."
          >
            Ask
          </button>
          <button
            role="radio"
            aria-checked={mode === "edit"}
            className={mode === "edit" ? "segmented__on" : ""}
            onClick={() => setMode("edit")}
            title="Propose code changes as a diff you can apply and undo."
          >
            Change
          </button>
        </div>
        <button
          className="btn btn--ghost"
          onClick={() => {
            if (!picking) onLoadFiles();
            setPicking((p) => !p);
          }}
        >
          {picking ? "Close files" : "Attach files"}
        </button>
        <span className="composer__hint">Enter to send · Shift+Enter for a new line</span>
        {busy ? (
          <button className="btn btn--danger" onClick={onStop}>
            Stop
          </button>
        ) : (
          <button className="btn btn--primary" disabled={!text.trim()} onClick={send}>
            Send
          </button>
        )}
      </div>
    </div>
  );
}
