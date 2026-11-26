export type AssistantMode = "ask" | "edit";

export interface Conversation {
  id: string;
  title: string;
  project_root: string;
  check_command: string;
  auto_fix: boolean;
  created_at: number;
  updated_at: number;
}

export interface IncludedCode {
  path: string;
  start_line: number;
  end_line: number;
  total_lines: number;
  full: boolean;
}

export interface CheckResult {
  command: string;
  resolved_command: string[];
  exit_code: number | null;
  passed: boolean;
  output: string;
  duration_seconds: number;
  timed_out: boolean;
  error: string;
}

export interface EditAttempt {
  reply: string;
  problems?: { path: string; message: string }[];
  verification?: Verification;
}

export interface MessageMetadata {
  attached?: string[];
  context?: IncludedCode[];
  prompt_tokens?: number;
  usage?: { prompt_tokens?: number; completion_tokens?: number; total_tokens?: number };
  seconds?: number;
  cancelled?: boolean;
  error?: string;
  attempts?: EditAttempt[];
  change_set_id?: string;
  edit_failed?: boolean;
  check?: CheckResult;
  auto_fix_round?: number;
}

export interface AssistantMessage {
  id: string;
  conversation_id: string;
  role: "user" | "assistant" | "check";
  mode: AssistantMode;
  content: string;
  metadata: MessageMetadata;
  created_at: number;
}

export interface VerificationIssue {
  severity: "error" | "warning";
  check: string;
  path: string;
  message: string;
  line: number | null;
}

export interface Verification {
  passed: boolean;
  checked_files: number;
  error_count: number;
  warning_count: number;
  issues: VerificationIssue[];
  skipped_reason: string;
}

export interface ChangeSetFile {
  path: string;
  is_new: boolean;
  diff: string;
}

export interface ChangeSet {
  id: string;
  conversation_id: string;
  message_id: string;
  status: "pending" | "applied" | "discarded" | "reverted";
  summary: string;
  files: ChangeSetFile[];
  verification: Verification | null;
  check: CheckResult | null;
  created_at: number;
  updated_at: number;
}

export interface ConversationDetail {
  conversation: Conversation;
  messages: AssistantMessage[];
  change_sets: ChangeSet[];
  busy: boolean;
}

export interface AssistantStatus {
  model: string;
  context_tokens: number;
  max_edit_attempts: number;
  max_fix_rounds: number;
  check_timeout: number;
  active_conversations: string[];
  build_running: boolean;
  storage: { database_bytes: number; conversation_count: number; message_count: number };
}

export type TurnEvent =
  | { type: "message"; message: AssistantMessage }
  | { type: "context"; included: IncludedCode[]; prompt_tokens: number; referenced: string[] }
  | { type: "token"; text: string }
  | { type: "attempt"; number: number; reason: string }
  | { type: "status"; text: string }
  | { type: "change_set"; change_set: ChangeSet }
  | { type: "error"; detail: string }
  | { type: "done" };

export interface ConversationSettingsInput {
  project_root: string;
  check_command: string;
  auto_fix: boolean;
  title?: string;
}
