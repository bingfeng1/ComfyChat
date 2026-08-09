export interface ApiInfo {
  name: string;
  version: string;
}

export interface HealthStatus {
  status: "ok" | "error";
  database: "ok" | "error";
  comfyui: "ok" | "error" | "unknown";
}