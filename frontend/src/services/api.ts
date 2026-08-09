import type {
  ApiInfo,
  HealthStatus,
  ImportConflict,
  SyncResult,
  WorkflowList,
  WorkflowSource,
  WorkflowSummary,
  WorkflowVersion,
  WorkflowVersionList,
} from "@/types/api";

const API_BASE = "/api";

async function get<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`);
  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
  }
  return (await response.json()) as T;
}

async function request(path: string, init?: RequestInit): Promise<Response> {
  return fetch(`${API_BASE}${path}`, init);
}

export const api = {
  root: () => get<ApiInfo>("/"),
  health: () => get<HealthStatus>("/health"),
  workflows: {
    list: (params?: { source?: WorkflowSource; q?: string }) => {
      const sp = new URLSearchParams();
      if (params?.source) sp.set("source", params.source);
      if (params?.q) sp.set("q", params.q);
      const qs = sp.toString() ? `?${sp.toString()}` : "";
      return get<WorkflowList>(`/workflows${qs}`);
    },
    get: (id: string) => get<WorkflowSummary>(`/workflows/${id}`),
    getBody: (id: string) => get<Record<string, unknown>>(`/workflows/${id}/body`),
    export: (id: string) => request(`/workflows/${id}/export`),
    remove: (id: string) => request(`/workflows/${id}`, { method: "DELETE" }),
    import: async (file: File, opts?: { overwrite?: boolean; name?: string }) => {
      const form = new FormData();
      form.append("file", file);
      const sp = new URLSearchParams();
      if (opts?.overwrite) sp.set("overwrite", "true");
      if (opts?.name) sp.set("name", opts.name);
      const qs = sp.toString() ? `?${sp.toString()}` : "";
      return request(`/workflows/import${qs}`, { method: "POST", body: form });
    },
    sync: () => request(`/workflows/sync`, { method: "POST" }),
    versions: {
      list: (id: string) => get<WorkflowVersionList>(`/workflows/${id}/versions`),
      getBody: (id: string, version: number) =>
        get<Record<string, unknown>>(`/workflows/${id}/versions/${version}`),
      remove: (id: string, version: number) =>
        request(`/workflows/${id}/versions/${version}`, { method: "DELETE" }),
    },
  },
};
