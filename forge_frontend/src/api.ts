import type {
  CreateWorkflowResponse,
  Diagnostics,
  FileContentResponse,
  FileListResponse,
  ReportResponse,
  RunArtifactResponse,
  RunDetail,
  RunListResponse,
  StorageUsage,
  WorkflowStatus,
} from "./types";

export const API_BASE = "http://127.0.0.1:8420";
export const WS_URL = "ws://127.0.0.1:8420/ws/events";

class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({ detail: response.statusText }));
    throw new ApiError(body.detail ?? response.statusText, response.status);
  }
  return response.json() as Promise<T>;
}

export const api = {
  getDiagnostics: () => request<Diagnostics>("/api/diagnostics"),

  createWorkflow: (goal: string, name?: string) =>
    request<CreateWorkflowResponse>("/api/workflows", {
      method: "POST",
      body: JSON.stringify({ goal, name }),
    }),

  getWorkflow: (id: string) => request<WorkflowStatus>(`/api/workflows/${id}`),

  listFiles: (id: string) => request<FileListResponse>(`/api/workflows/${id}/files`),

  getFile: (id: string, path: string) =>
    request<FileContentResponse>(
      `/api/workflows/${id}/files/${encodeURIComponent(path)}`,
    ),

  getReport: <T>(key: string) => request<ReportResponse<T>>(`/api/reports/${key}`),

  listRuns: (limit = 50, offset = 0) =>
    request<RunListResponse>(`/api/history/runs?limit=${limit}&offset=${offset}`),

  getRun: (id: string) => request<RunDetail>(`/api/history/runs/${id}`),

  getRunArtifact: <T>(id: string, kind: string) =>
    request<RunArtifactResponse<T>>(`/api/history/runs/${id}/artifacts/${kind}`),

  deleteRun: (id: string) =>
    request<{ workflow_id: string; deleted: boolean }>(`/api/history/runs/${id}`, {
      method: "DELETE",
    }),

  getStorage: () => request<StorageUsage>("/api/history/storage"),
};

export { ApiError };
