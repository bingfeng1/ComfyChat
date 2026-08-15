import { onMounted, onUnmounted, ref, watch } from "vue";
import { api } from "@/services/api";
import { useNsfwFilter } from "@/composables/useNsfwFilter";
import type { GenerationStatus, GenerationSummary, WorkflowSummary } from "@/types/api";

export function useGenerations() {
  const items = ref<GenerationSummary[]>([]);
  const loading = ref(false);
  const error = ref<string | null>(null);
  const statusFilter = ref<GenerationStatus | "">("");
  const workflowFilter = ref<string>("");
  const workspaceFilter = ref<string>("");
  const page = ref(1);
  const pageSize = ref(15);
  const total = ref(0);
  const workflows = ref<WorkflowSummary[]>([]);
  const { enabled: nsfwEnabled } = useNsfwFilter();
  let timer: number | undefined;

  async function loadWorkflows() {
    try {
      const data = await api.workflows.list();
      workflows.value = data.items;
    } catch {
      /* 工作流列表获取失败不影响主流程 */
    }
  }

  async function refresh(silent = false) {
    if (!silent) loading.value = true;
    error.value = null;
    try {
      const data = await api.generations.list({
        status: statusFilter.value || undefined,
        workflow_id: workflowFilter.value || undefined,
        workspace_id: workspaceFilter.value || undefined,
        page: page.value,
        page_size: pageSize.value,
        exclude_nsfw: !nsfwEnabled.value,
      });
      items.value = data.items;
      total.value = data.total;
    } catch (err) {
      error.value = err instanceof Error ? err.message : String(err);
    } finally {
      if (!silent) loading.value = false;
    }
  }

  async function poll() {
    try {
      const data = await api.generations.list({
        status: statusFilter.value || undefined,
        workflow_id: workflowFilter.value || undefined,
        workspace_id: workspaceFilter.value || undefined,
        page: page.value,
        page_size: pageSize.value,
        exclude_nsfw: !nsfwEnabled.value,
      });
      items.value = data.items;
      total.value = data.total;
    } catch {
      /* 静默轮询失败不打扰用户 */
    }
  }

  async function create(payload: {
    workflow_id: string;
    parameters: Record<string, unknown>;
    workspace_ids?: string[];
  }) {
    const res = await api.generations.create(payload);
    if (res.status !== 201) {
      const data = await res.json().catch(() => null);
      throw new Error(data?.detail ?? `创建失败：${res.status}`);
    }
    page.value = 1;
    await refresh();
    return (await res.json()) as GenerationSummary;
  }

  async function remove(id: string) {
    const res = await api.generations.remove(id);
    if (res.status !== 204) throw new Error(`删除失败：${res.status}`);
    await refresh();
  }

  async function setWorkspaces(id: string, workspaceIds: string[]) {
    const res = await api.generations.setWorkspaces(id, workspaceIds);
    if (!res.ok) {
      const data = await res.json().catch(() => null);
      throw new Error(data?.detail ?? `更新工作区失败:${res.status}`);
    }
    await refresh(true);
  }

  async function removeWorkspace(id: string, workspaceId: string) {
    const res = await api.generations.removeWorkspace(id, workspaceId);
    if (res.status !== 204) throw new Error(`解除失败：${res.status}`);
    await refresh(true);
  }

  function setPage(n: number) {
    page.value = n;
    refresh();
  }

  function setPageSize(n: number) {
    pageSize.value = n;
    page.value = 1;
    refresh();
  }

  watch(statusFilter, () => {
    page.value = 1;
    refresh();
  });

  watch(workflowFilter, () => {
    page.value = 1;
    refresh();
  });

  watch(workspaceFilter, () => {
    page.value = 1;
    refresh();
  });

  watch(nsfwEnabled, () => {
    page.value = 1;
    refresh();
  });

  onMounted(() => {
    loadWorkflows();
    refresh();
    timer = window.setInterval(poll, 2000);
  });
  onUnmounted(() => {
    if (timer) window.clearInterval(timer);
  });

  return {
    items,
    loading,
    error,
    statusFilter,
    workflowFilter,
    workspaceFilter,
    workflows,
    page,
    pageSize,
    total,
    refresh,
    create,
    remove,
    setWorkspaces,
    removeWorkspace,
    setPage,
    setPageSize,
  };
}
