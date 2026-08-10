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
  has_history: boolean;
}

export interface WorkflowList {
  items: WorkflowSummary[];
}

export interface SyncBrowseResult {
  added: number;
  updated: number;
  skipped: number;
  error: string | null;
  updates?: string[];
}

export interface SyncResult {
  synced_at: string;
  browse: SyncBrowseResult;
}

export interface ImportConflict {
  filename: string;
  existing: WorkflowSummary;
}

export interface WorkflowVersion {
  id: string;
  workflow_id: string;
  version: number;
  name: string;
  size_bytes: number;
  captured_at: string;
}

export interface WorkflowVersionList {
  items: WorkflowVersion[];
}

export type GenerationStatus = "queued" | "running" | "success" | "failed";

export interface GenerationSummary {
  id: string;
  workflow_id: string;
  workflow_name: string;
  parameters: Record<string, unknown>;
  status: GenerationStatus;
  prompt_id: string;
  error: string | null;
  outputs: string[];
  created_at: string;
  updated_at: string;
}

export interface GenerationList {
  items: GenerationSummary[];
  total: number;
  page: number;
  page_size: number;
}

export interface GenerationField {
  key: string;
  label: string;
  type: "text" | "seed" | "number" | "select";
  node_id: string;
  input_name: string;
  default: string | number | boolean | null;
  required: boolean;
  min?: number;
  max?: number;
  step?: number;
  options?: string[];
}

export interface GenerationConfigSummary {
  workflow_id: string;
  workflow_name: string;
  fields: GenerationField[];
}

export interface GenerationConfigList {
  items: GenerationConfigSummary[];
}

export interface GenerationConfigPayload {
  api_template: Record<string, unknown>;
  fields: GenerationField[];
}