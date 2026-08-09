export interface ApiInfo {
  name: string;
  version: string;
}

export interface HealthStatus {
  status: "ok" | "error";
  database: "ok" | "error";
  comfyui: "ok" | "error" | "unknown";
}

export type WorkflowSource = "browse" | "import";

export interface WorkflowSummary {
  id: string;
  name: string;
  source: WorkflowSource;
  source_key: string;
  original_name: string;
  size_bytes: number;
  created_at: string;
  updated_at: string;
}

export interface WorkflowList {
  items: WorkflowSummary[];
}

export interface SyncBrowseResult {
  added: number;
  updated: number;
  skipped: number;
  error: string | null;
}

export interface SyncResult {
  synced_at: string;
  browse: SyncBrowseResult;
}

export interface ImportConflict {
  filename: string;
  existing: WorkflowSummary;
}