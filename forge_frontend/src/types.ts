export interface StageStatus {
  name: string;
  status: "PENDING" | "RUNNING" | "WAITING" | "FAILED" | "CANCELLED" | "COMPLETED";
  started_at: number | null;
  completed_at: number | null;
  error: string | null;
  optional: boolean;
  critical: boolean;
}

export interface WorkflowStatus {
  id: string;
  name: string;
  type: string;
  state: string;
  progress: number;
  stages: StageStatus[];
  errors: Record<string, string>;
  created_at: number | null;
  updated_at: number | null;
}

export interface CreateWorkflowResponse {
  workflow_id: string;
  status: string;
}

export interface FileEntry {
  path: string;
  size_bytes: number;
}

export interface FileListResponse {
  workflow_id: string;
  files: FileEntry[];
}

export interface FileContentResponse {
  path: string;
  content: string;
}

export interface Diagnostics {
  version: string;
  python_version: string;
  ollama_status: string;
  registered_services: string[];
  enabled_plugins: string[];
  default_model: string;
}

export interface ForgeEvent {
  event_type: string;
  data: Record<string, unknown>;
  timestamp: string;
}

export const STAGE_ORDER = [
  "planner",
  "architect",
  "developer",
  "tester",
  "documentation",
  "security",
  "reviewer",
  "git",
] as const;
