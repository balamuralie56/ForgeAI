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

// ─── Plugin reports (GET /api/reports/{key}) ────────────────────────────────
// Mirrors each plugin's dataclasses in forge_plugins/*/models.py exactly.

export interface ReportResponse<T> {
  report: string;
  data: T;
}

export interface RunSummary {
  workflow_id: string;
  name: string;
  goal: string;
  workflow_type: string;
  state: string;
  progress: number;
  model: string;
  created_at: number;
  updated_at: number;
}

export interface RunListResponse {
  runs: RunSummary[];
  total: number;
  limit: number;
  offset: number;
}

export interface RunDetail extends RunSummary {
  stages: Partial<StageStatus>[];
  errors: Record<string, string>;
  artifact_kinds: string[];
}

export interface RunArtifactResponse<T> {
  workflow_id: string;
  kind: string;
  data: T;
}

export interface StorageUsage {
  history_database_bytes: number;
  run_count: number;
  artifact_bytes_by_run: Record<string, number>;
  workspace_bytes: number;
}

// planner
export interface ProjectGoal {
  goal: string;
  description: string;
}
export interface Requirement {
  requirement_id: string;
  description: string;
  is_functional: boolean;
  priority: "HIGH" | "MEDIUM" | "LOW" | string;
  dependencies: string[];
}
export interface ClarificationQuestion {
  question_id: string;
  question: string;
  context: string;
  assumed_answer: string;
}
export interface Milestone {
  milestone_id: string;
  title: string;
  description: string;
  tasks: string[];
}
export interface Task {
  task_id: string;
  name: string;
  description: string;
  milestone_id: string;
  dependencies: string[];
  estimated_duration_hours: number;
}
export interface ProjectPlan {
  goal: ProjectGoal;
  requirements: Requirement[];
  clarifications: ClarificationQuestion[];
  milestones: Milestone[];
  tasks: Task[];
  estimated_order: string[];
  risks: string[];
  assumptions: string[];
}

// architect
export interface TechnologyDecision {
  category: string;
  technology: string;
  rationale: string;
}
export interface APISpecification {
  path: string;
  method: string;
  description: string;
  request_payload_schema: string;
  response_payload_schema: string;
}
export interface ModuleSpecification {
  name: string;
  purpose: string;
  dependencies: string[];
  apis: APISpecification[];
}
export interface DatabaseSchema {
  table_name: string;
  columns: Record<string, string>;
  primary_key: string;
  foreign_keys: Record<string, string>;
  description: string;
}
export interface ArchitectureDecisionRecord {
  adr_id: string;
  title: string;
  status: string;
  context: string;
  decision: string;
  consequences: string;
  date: string;
}
export interface ArchitectureSpecification {
  project_id: string;
  directory_structure: string;
  modules: ModuleSpecification[];
  database_design: DatabaseSchema[];
  decisions: TechnologyDecision[];
  adrs: ArchitectureDecisionRecord[];
  mermaid_diagrams: Record<string, string>;
  rationale: string;
}

// developer
export interface ImplementationReport {
  project_id: string;
  files: FileEntry[];
  summary: string;
  status: string;
}

// tester
export interface GeneratedTestFile {
  path: string;
  content: string;
  test_type: string;
}
export interface TestReport {
  project_id: string;
  test_files: GeneratedTestFile[];
  coverage_summary: string;
  status: string;
  summary: string;
}

// documentation
export interface GeneratedDocFile {
  path: string;
  content: string;
  category: string;
}
export interface DocumentationReport {
  project_id: string;
  doc_files: GeneratedDocFile[];
  status: string;
  summary: string;
}

// security & reviewer share this finding shape (severity/confidence/location)
export interface Finding {
  id: string;
  rule_id: string;
  category: string;
  title: string;
  description: string;
  severity: "CRITICAL" | "HIGH" | "MEDIUM" | "LOW" | "INFO" | string;
  confidence: "HIGH" | "MEDIUM" | "LOW" | string;
  file_path: string | null;
  line_number: number | null;
  recommendation: string;
  references: string[];
  // security-only
  cwe?: string | null;
  owasp?: string | null;
  // reviewer-only
  principle?: string | null;
}
export interface SecurityReport {
  project_id: string;
  findings: Finding[];
  risk_score: number;
  security_score: number;
  status: string;
  summary: string;
  recommendations: string[];
}
export interface ReviewReport {
  project_id: string;
  findings: Finding[];
  quality_score: number;
  solid_scores: Record<string, number | null>;
  status: string;
  summary: string;
  recommendations: string[];
}

// git
export interface GitCommit {
  sha: string;
  message: string;
  files: string[];
  author: string;
  timestamp: string;
}
export interface GitTag {
  name: string;
  sha: string;
  annotation: string;
}
export interface SemverBump {
  current: string;
  recommended: string;
  bump_type: "MAJOR" | "MINOR" | "PATCH" | string;
  rationale: string;
}
export interface GitHubPR {
  url: string;
  number: number;
  title: string;
  branch: string;
  base: string;
}
export interface GitReport {
  project_id: string;
  commits: GitCommit[];
  tags: GitTag[];
  semver: SemverBump | null;
  pr: GitHubPR | null;
  changelog: string;
  ci_manifest: Record<string, unknown>;
  status: string;
  summary: string;
}

// ─── Live file tree (built client-side from file list + WS events) ─────────
export interface FileTreeNode {
  name: string;
  path: string;
  isDir: boolean;
  sizeBytes?: number;
  children?: FileTreeNode[];
}
