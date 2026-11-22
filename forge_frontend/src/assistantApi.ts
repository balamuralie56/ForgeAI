import { API_BASE, ApiError } from "./api";
import type {
  AssistantMessage,
  AssistantMode,
  AssistantStatus,
  ChangeSet,
  Conversation,
  ConversationDetail,
  ConversationSettingsInput,
  TurnEvent,
} from "./assistantTypes";

// The assistant API reads project files and runs check commands, so the
// backend only answers requests that carry this header (see assistant_routes.py).
const CLIENT_HEADERS = { "Content-Type": "application/json", "X-ForgeAI-Client": "web" };

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}/api/assistant${path}`, {
    ...init,
    headers: CLIENT_HEADERS,
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({ detail: response.statusText }));
    throw new ApiError(body.detail ?? response.statusText, response.status);
  }
  return response.json() as Promise<T>;
}

/**
 * Sends a request and calls `onEvent` for every streamed event until the
 * reply is done. Aborting `signal` closes the stream, which stops the reply
 * on the server (what was generated so far is kept).
 */
async function sendMessage(
  conversationId: string,
  content: string,
  mode: AssistantMode,
  attached: string[],
  onEvent: (event: TurnEvent) => void,
  signal: AbortSignal,
): Promise<void> {
  const response = await fetch(
    `${API_BASE}/api/assistant/conversations/${conversationId}/messages`,
    {
      method: "POST",
      headers: CLIENT_HEADERS,
      body: JSON.stringify({ content, mode, attached }),
      signal,
    },
  );
  if (!response.ok || !response.body) {
    const body = await response.json().catch(() => ({ detail: response.statusText }));
    throw new ApiError(body.detail ?? response.statusText, response.status);
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let newline = buffer.indexOf("\n");
    while (newline >= 0) {
      const line = buffer.slice(0, newline).trim();
      buffer = buffer.slice(newline + 1);
      if (line) onEvent(JSON.parse(line) as TurnEvent);
      newline = buffer.indexOf("\n");
    }
  }
  const rest = buffer.trim();
  if (rest) onEvent(JSON.parse(rest) as TurnEvent);
}

export const assistantApi = {
  status: () => request<AssistantStatus>("/status"),

  listConversations: () =>
    request<{ conversations: Conversation[]; total: number }>("/conversations?limit=200"),

  createConversation: (input: ConversationSettingsInput) =>
    request<Conversation>("/conversations", { method: "POST", body: JSON.stringify(input) }),

  getConversation: (id: string) => request<ConversationDetail>(`/conversations/${id}`),

  updateConversation: (id: string, input: Partial<ConversationSettingsInput>) =>
    request<Conversation>(`/conversations/${id}`, {
      method: "PATCH",
      body: JSON.stringify(input),
    }),

  deleteConversation: (id: string) =>
    request<{ deleted: boolean }>(`/conversations/${id}`, { method: "DELETE" }),

  listFiles: (id: string) => request<{ files: string[] }>(`/conversations/${id}/files`),

  sendMessage,

  stop: (id: string) =>
    request<{ stopped: boolean }>(`/conversations/${id}/stop`, { method: "POST" }),

  runCheck: (id: string) =>
    request<{ message: AssistantMessage }>(`/conversations/${id}/check`, { method: "POST" }),

  applyChange: (id: string) =>
    request<{ change_set: ChangeSet; check_message: AssistantMessage | null }>(
      `/changes/${id}/apply`,
      { method: "POST" },
    ),

  discardChange: (id: string) =>
    request<{ change_set: ChangeSet }>(`/changes/${id}/discard`, { method: "POST" }),

  revertChange: (id: string) =>
    request<{ change_set: ChangeSet }>(`/changes/${id}/revert`, { method: "POST" }),
};
