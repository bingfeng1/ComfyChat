import type {
  ApiInfo,
  GenerationConfigList,
  GenerationConfigPayload,
  LoraList,
  GenerationList,
  GenerationStatus,
  GenerationSummary,
  HealthStatus,
  ImportConflict,
  SyncResult,
  WorkflowList,
  WorkflowSource,
  WorkflowSummary,
  WorkflowVersion,
  WorkflowVersionList,
  WorkspaceList,
  WorkspaceSummary,
} from "@/types/api";

const API_BASE = "/api";

async function get<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`);
  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
  }
  return (await response.json()) as T;
}

async function getOrNull<T>(path: string): Promise<T | null> {
  const response = await fetch(`${API_BASE}${path}`);
  if (response.status === 404) {
    return null;
  }
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
    generationConfigs: () =>
      get<GenerationConfigList>(`/workflows/generation-configs`),
    generationConfig: {
      get: (id: string) =>
        getOrNull<
          GenerationConfigPayload & { workflow_id: string; updated_at: string }
        >(`/workflows/${id}/generation-config`),
      save: (id: string, payload: GenerationConfigPayload) =>
        request(`/workflows/${id}/generation-config`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        }),
      discover: (id: string) =>
        get<GenerationConfigPayload & { api_template: Record<string, unknown> }>(
          `/workflows/${id}/generation-config/discover`
        ),
    },
  },
  generations: {
    list: (params?: { status?: GenerationStatus; workflow_id?: string; workspace_id?: string; page?: number; page_size?: number; exclude_nsfw?: boolean }) => {
      const sp = new URLSearchParams();
      if (params?.status) sp.set("status", params.status);
      if (params?.workflow_id) sp.set("workflow_id", params.workflow_id);
      if (params?.workspace_id) sp.set("workspace_id", params.workspace_id);
      if (params?.page) sp.set("page", String(params.page));
      if (params?.page_size) sp.set("page_size", String(params.page_size));
      if (params?.exclude_nsfw) sp.set("exclude_nsfw", "true");
      const qs = sp.toString() ? `?${sp.toString()}` : "";
      return get<GenerationList>(`/generations${qs}`);
    },
    get: (id: string) => get<GenerationSummary>(`/generations/${id}`),
    create: async (payload: {
      workflow_id: string;
      parameters: Record<string, unknown>;
      workspace_ids?: string[];
    }) => {
      const res = await request(`/generations`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      return res;
    },
    cancel: (id: string) => request(`/generations/${id}/cancel`, { method: "POST" }),
    remove: (id: string) => request(`/generations/${id}`, { method: "DELETE" }),
    setWorkspaces: (id: string, workspaceIds: string[]) =>
      request(`/generations/${id}/workspaces`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ workspace_ids: workspaceIds }),
      }),
    removeWorkspace: (id: string, workspaceId: string) =>
      request(`/generations/${id}/workspaces/${encodeURIComponent(workspaceId)}`, {
        method: "DELETE",
      }),
    imageUrl: (id: string, filename: string) =>
      `${API_BASE}/generations/${id}/images/${encodeURIComponent(filename)}`,
  },
  loras: {
    list: () => get<LoraList>("/lora"),
    updateNsfw: (name: string, isNsfw: boolean) =>
      request(`/lora/${encodeURIComponent(name)}/nsfw`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ is_nsfw: isNsfw }),
      }),
    updateTrigger: (name: string, triggerWords: string | null) =>
      request(`/lora/${encodeURIComponent(name)}/trigger`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ trigger_words: triggerWords }),
      }),
  },
  workspaces: {
    list: () => get<WorkspaceList>("/workspaces"),
    get: (id: string) =>
      get<WorkspaceSummary>(`/workspaces/${encodeURIComponent(id)}`),
    create: (name: string) =>
      request("/workspaces", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name }),
      }),
    update: (id: string, name: string) =>
      request(`/workspaces/${encodeURIComponent(id)}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name }),
      }),
    remove: (id: string) =>
      request(`/workspaces/${encodeURIComponent(id)}`, { method: "DELETE" }),
    generationCount: (id: string) =>
      get<{ count: number }>(`/workspaces/${encodeURIComponent(id)}/generation-count`),
  },
};
