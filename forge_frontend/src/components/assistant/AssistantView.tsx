import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { assistantApi } from "../../assistantApi";
import type {
  AssistantMessage,
  AssistantMode,
  AssistantStatus,
  ChangeSet,
  CheckResult,
  Conversation,
  ConversationDetail,
  ConversationSettingsInput,
  IncludedCode,
  TurnEvent,
} from "../../assistantTypes";
import { ErrorBoundary } from "../ErrorBoundary";
import { Composer } from "./Composer";
import { ConversationForm } from "./ConversationForm";
import { ContextLine, MessageItem } from "./MessageItem";
import "./assistant.css";

interface Draft {
  mode: AssistantMode;
  segments: { text: string; reason?: string }[];
  status: string | null;
  context: IncludedCode[];
}

function errorMessage(e: unknown): string {
  return e instanceof Error ? e.message : String(e);
}

function formatWhen(epochSeconds: number): string {
  return new Date(epochSeconds * 1000).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function folderName(path: string): string {
  const parts = path.split(/[\\/]/).filter(Boolean);
  return parts[parts.length - 1] ?? path;
}

function upsert<T extends { id: string }>(items: T[], item: T): T[] {
  const index = items.findIndex((i) => i.id === item.id);
  if (index < 0) return [...items, item];
  const copy = items.slice();
  copy[index] = item;
  return copy;
}

function fixRequest(result: CheckResult): string {
  const output = (result.output || result.error).slice(-3000).trim();
  return (
    `The check command \`${result.command}\` failed. Fix the code so it passes. Here is its output:\n` +
    "```\n" +
    output +
    "\n```"
  );
}

/** The local coding assistant: conversations about a project, with checked, reversible edits. */
export function AssistantView() {
  const [status, setStatus] = useState<AssistantStatus | null>(null);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [listError, setListError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<ConversationDetail | null>(null);
  const [creating, setCreating] = useState(false);
  const [editingSettings, setEditingSettings] = useState(false);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [turnErrors, setTurnErrors] = useState<string[]>([]);
  const [files, setFiles] = useState<string[] | null>(null);
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null);
  const [checking, setChecking] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const threadRef = useRef<HTMLDivElement | null>(null);
  const selectedRef = useRef<string | null>(null);

  const refreshList = useCallback(() => {
    assistantApi
      .listConversations()
      .then((r) => {
        setConversations(r.conversations);
        setListError(null);
      })
      .catch((e) => setListError(errorMessage(e)));
    assistantApi
      .status()
      .then(setStatus)
      .catch(() => setStatus(null));
  }, []);

  const loadConversation = useCallback((id: string) => {
    assistantApi
      .getConversation(id)
      .then((d) => {
        if (selectedRef.current === id) setDetail(d);
      })
      .catch((e) => {
        if (selectedRef.current === id) setTurnErrors([errorMessage(e)]);
      });
  }, []);

  useEffect(() => {
    refreshList();
    return () => abortRef.current?.abort();
  }, [refreshList]);

  useEffect(() => {
    const thread = threadRef.current;
    if (thread) thread.scrollTop = thread.scrollHeight;
  }, [detail?.messages.length, draft]);

  const select = (id: string | null) => {
    abortRef.current?.abort();
    selectedRef.current = id;
    setSelectedId(id);
    setDetail(null);
    setDraft(null);
    setTurnErrors([]);
    setFiles(null);
    setEditingSettings(false);
    setCreating(id === null);
    if (id) loadConversation(id);
  };

  const recentFolders = useMemo(
    () => Array.from(new Set(conversations.map((c) => c.project_root))),
    [conversations],
  );

  const createConversation = async (input: ConversationSettingsInput) => {
    const conversation = await assistantApi.createConversation(input);
    refreshList();
    select(conversation.id);
  };

  const saveSettings = async (input: ConversationSettingsInput) => {
    if (!selectedId) return;
    await assistantApi.updateConversation(selectedId, input);
    setEditingSettings(false);
    setFiles(null);
    loadConversation(selectedId);
    refreshList();
  };

  const deleteConversation = (id: string) => {
    assistantApi
      .deleteConversation(id)
      .then(() => {
        setConfirmDelete(null);
        if (id === selectedRef.current) select(null);
        refreshList();
      })
      .catch((e) => setListError(errorMessage(e)));
  };

  const handleEvent = (id: string, event: TurnEvent) => {
    if (selectedRef.current !== id) return;
    switch (event.type) {
      case "message":
        setDetail((d) => (d ? { ...d, messages: upsert(d.messages, event.message) } : d));
        if (event.message.role === "assistant") {
          setDraft((dr) => (dr ? { ...dr, segments: [{ text: "" }], status: null, context: [] } : dr));
        }
        break;
      case "context":
        setDraft((dr) =>
          dr
            ? {
                ...dr,
                context: event.included,
                status: `Thinking (prompt ≈ ${event.prompt_tokens.toLocaleString()} tokens)…`,
              }
            : dr,
        );
        break;
      case "token":
        setDraft((dr) => {
          if (!dr) return dr;
          const segments = dr.segments.slice();
          const last = segments[segments.length - 1];
          segments[segments.length - 1] = { ...last, text: last.text + event.text };
          return { ...dr, segments, status: null };
        });
        break;
      case "attempt":
        setDraft((dr) =>
          dr
            ? {
                ...dr,
                segments: [...dr.segments, { text: "", reason: event.reason }],
                status: `Retrying (attempt ${event.number})…`,
              }
            : dr,
        );
        break;
      case "status":
        setDraft((dr) => (dr ? { ...dr, status: event.text } : dr));
        break;
      case "change_set":
        setDetail((d) => (d ? { ...d, change_sets: upsert(d.change_sets, event.change_set) } : d));
        break;
      case "error":
        setTurnErrors((errors) => [...errors, event.detail]);
        break;
      case "done":
        break;
    }
  };

  const send = (text: string, mode: AssistantMode, attached: string[]) => {
    const id = selectedRef.current;
    if (!id || abortRef.current) return;
    const controller = new AbortController();
    abortRef.current = controller;
    setTurnErrors([]);
    setDraft({ mode, segments: [{ text: "" }], status: "Reading the project…", context: [] });
    assistantApi
      .sendMessage(id, text, mode, attached, (event) => handleEvent(id, event), controller.signal)
      .catch((e) => {
        if (!controller.signal.aborted && selectedRef.current === id) {
          setTurnErrors((errors) => [...errors, errorMessage(e)]);
        }
      })
      .finally(() => {
        if (abortRef.current === controller) abortRef.current = null;
        if (selectedRef.current === id) {
          setDraft(null);
          loadConversation(id);
        }
        refreshList();
      });
  };

  const stop = () => {
    const id = selectedRef.current;
    abortRef.current?.abort();
    if (id) assistantApi.stop(id).catch(() => undefined);
  };

  const applyChange = async (changeSetId: string) => {
    const result = await assistantApi.applyChange(changeSetId);
    setDetail((d) => {
      if (!d) return d;
      const messages = result.check_message ? upsert(d.messages, result.check_message) : d.messages;
      return { ...d, messages, change_sets: upsert(d.change_sets, result.change_set) };
    });
  };
  const discardChange = async (changeSetId: string) => {
    const result = await assistantApi.discardChange(changeSetId);
    setDetail((d) => (d ? { ...d, change_sets: upsert(d.change_sets, result.change_set) } : d));
  };
  const revertChange = async (changeSetId: string) => {
    const result = await assistantApi.revertChange(changeSetId);
    setDetail((d) => (d ? { ...d, change_sets: upsert(d.change_sets, result.change_set) } : d));
  };

  const runCheck = () => {
    if (!selectedId) return;
    setChecking(true);
    assistantApi
      .runCheck(selectedId)
      .then((r) => setDetail((d) => (d ? { ...d, messages: upsert(d.messages, r.message) } : d)))
      .catch((e) => setTurnErrors([errorMessage(e)]))
      .finally(() => setChecking(false));
  };

  const loadFiles = () => {
    if (!selectedId || files) return;
    assistantApi
      .listFiles(selectedId)
      .then((r) => setFiles(r.files))
      .catch((e) => setTurnErrors([errorMessage(e)]));
  };

  const busy = draft !== null || Boolean(detail?.busy);
  const changeSetsByMessage = useMemo(() => {
    const map = new Map<string, ChangeSet>();
    for (const cs of detail?.change_sets ?? []) map.set(cs.message_id, cs);
    return map;
  }, [detail?.change_sets]);
  const conversation = detail?.conversation;
  const showNewForm = creating || (!selectedId && conversations.length === 0);

  return (
    <div className="assistant">
      <aside className="history">
        <div className="history__head">
          <h2 className="history__title">Conversations</h2>
          <button className="history__new" onClick={() => select(null)}>
            + New
          </button>
        </div>
        {listError && <div className="history__error">{listError}</div>}
        <ul className="history__list">
          {conversations.length === 0 && !listError && (
            <li className="history__empty">No conversations yet.</li>
          )}
          {conversations.map((c) => (
            <li
              key={c.id}
              className={`history__item${c.id === selectedId ? " history__item--selected" : ""}`}
            >
              {confirmDelete === c.id ? (
                <div className="history__confirm">
                  <span>Delete this conversation? Project files are not touched.</span>
                  <button className="history__btn history__btn--danger" onClick={() => deleteConversation(c.id)}>
                    Delete
                  </button>
                  <button className="history__btn" onClick={() => setConfirmDelete(null)}>
                    Keep
                  </button>
                </div>
              ) : (
                <>
                  <button className="history__open" onClick={() => select(c.id)}>
                    <span className="history__goal">{c.title || "New conversation"}</span>
                    <span className="history__meta">
                      <span>{folderName(c.project_root)}</span>
                      <span>{formatWhen(c.updated_at)}</span>
                    </span>
                  </button>
                  <button
                    className="history__delete"
                    title="Delete conversation"
                    disabled={status?.active_conversations.includes(c.id)}
                    onClick={() => setConfirmDelete(c.id)}
                  >
                    ✕
                  </button>
                </>
              )}
            </li>
          ))}
        </ul>
        {status && (
          <div className="history__storage">
            {status.storage.conversation_count} conversations ·{" "}
            {(status.storage.database_bytes / 1024).toFixed(0)} KB stored locally
          </div>
        )}
      </aside>

      <main className="assistant__main">
        {showNewForm && (
          <section className="assistant__intro">
            <h1>Local coding assistant</h1>
            <p>
              Ask questions about a project, or describe a change. ForgeAI finds the relevant code,
              asks your local model ({status?.model ?? "…"}), and checks every edit before showing
              it to you as a diff. Edits that don't match the files, or that would break imports or
              names, go back to the model automatically. Nothing is written until you apply it, and
              every applied change can be undone.
            </p>
            <ConversationForm
              initial={{ project_root: recentFolders[0] ?? "", check_command: "", auto_fix: false }}
              recentFolders={recentFolders}
              maxFixRounds={status?.max_fix_rounds ?? 3}
              submitLabel="Start conversation"
              onSubmit={createConversation}
              onCancel={conversations.length ? () => setCreating(false) : undefined}
            />
          </section>
        )}

        {!showNewForm && !selectedId && (
          <div className="assistant__empty">Choose a conversation, or start a new one.</div>
        )}

        {!showNewForm && selectedId && !detail && turnErrors.length === 0 && (
          <div className="assistant__empty">Loading…</div>
        )}

        {!showNewForm && conversation && detail && (
          <>
            <header className="assistant__head">
              <div className="assistant__title">
                <h1>{conversation.title || "New conversation"}</h1>
                <div className="assistant__meta">
                  <code title={conversation.project_root}>{conversation.project_root}</code>
                  {conversation.check_command && (
                    <span className="assistant__chip" title="Check command">
                      check: <code>{conversation.check_command}</code>
                    </span>
                  )}
                  {conversation.auto_fix && <span className="assistant__chip assistant__chip--on">auto-fix</span>}
                  {status && <span className="assistant__chip">{status.model}</span>}
                </div>
              </div>
              <div className="assistant__actions">
                {conversation.check_command && (
                  <button className="btn" disabled={busy || checking} onClick={runCheck}>
                    {checking ? "Running…" : "Run check"}
                  </button>
                )}
                <button className="btn" disabled={busy} onClick={() => setEditingSettings((e) => !e)}>
                  Settings
                </button>
              </div>
            </header>

            {editingSettings && (
              <ConversationForm
                initial={conversation}
                recentFolders={recentFolders}
                maxFixRounds={status?.max_fix_rounds ?? 3}
                submitLabel="Save"
                onSubmit={saveSettings}
                onCancel={() => setEditingSettings(false)}
              />
            )}

            <div className="assistant__thread" ref={threadRef}>
              {detail.messages.length === 0 && !draft && (
                <div className="assistant__tips">
                  <p>Try:</p>
                  <ul>
                    <li>
                      <b>Ask</b>: “Where is the configuration loaded?” or “What does @service.py do?”
                    </li>
                    <li>
                      <b>Change</b>: “Add a <code>--verbose</code> flag to @cli.py” or “Fix the failing test”
                    </li>
                  </ul>
                  <p className="msg__muted">
                    Small local models do best with one focused request at a time, and when you name
                    the file with @.
                  </p>
                </div>
              )}

              <ErrorBoundary key={conversation.id}>
                {detail.messages.map((m: AssistantMessage) => (
                  <MessageItem
                    key={m.id}
                    message={m}
                    changeSet={changeSetsByMessage.get(m.id)}
                    busy={busy}
                    onApply={applyChange}
                    onDiscard={discardChange}
                    onRevert={revertChange}
                    onFix={(result) => send(fixRequest(result), "edit", [])}
                  />
                ))}
              </ErrorBoundary>

              {draft && (
                <div className="msg msg--assistant msg--draft">
                  <ContextLine included={draft.context} />
                  {draft.segments.map((segment, i) => (
                    <div key={i}>
                      {segment.reason && <div className="msg__retry">Retrying: {segment.reason}</div>}
                      {segment.text &&
                        (draft.mode === "edit" ? (
                          <pre className="msg__stream">{segment.text}</pre>
                        ) : (
                          <p className="rich__text msg__live">{segment.text}</p>
                        ))}
                    </div>
                  ))}
                  {draft.status && <div className="msg__status">{draft.status}</div>}
                </div>
              )}

              {turnErrors.map((e, i) => (
                <div key={i} className="msg__warn">
                  {e}
                </div>
              ))}
            </div>

            <Composer
              busy={busy}
              files={files}
              onLoadFiles={loadFiles}
              onSend={send}
              onStop={stop}
            />
          </>
        )}
      </main>
    </div>
  );
}
