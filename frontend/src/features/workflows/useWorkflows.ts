import { onMounted, ref } from "vue";
import { api } from "@/services/api";
import type { WorkflowSummary, WorkflowSource } from "@/types/api";

export function useWorkflows() {
  const items = ref<WorkflowSummary[]>([]);
  const loading = ref(false);
  const error = ref<string | null>(null);
  const sourceFilter = ref<WorkflowSource | "">("");
  const search = ref("");
  const importing = ref(false);
  const syncing = ref(false);
  const syncMsg = ref<string | null>(null);
  const conflict = ref<{ filename: string } | null>(null);

  async function refresh() {
    loading.value = true;
    error.value = null;
    try {
      const data = await api.workflows.list({
        source: sourceFilter.value || undefined,
        q: search.value || undefined,
      });
      items.value = data.items;
    } catch (err) {
      error.value = err instanceof Error ? err.message : String(err);
    } finally {
      loading.value = false;
    }
  }

  async function doSearch() {
    await refresh();
  }

  async function doSync() {
    syncing.value = true;
    syncMsg.value = null;
    try {
      const res = await api.workflows.sync();
      const data = await res.json();
      const b = data.browse;
      syncMsg.value = b.error
        ? `同步失败：${b.error}`
        : `已同步 ${b.added} / 更新 ${b.updated} / 跳过 ${b.skipped}`;
      await refresh();
    } catch (err) {
      syncMsg.value = err instanceof Error ? err.message : String(err);
    } finally {
      syncing.value = false;
    }
  }

  async function onFileChosen(file: File, opts?: { overwrite?: boolean; name?: string }) {
    importing.value = true;
    error.value = null;
    try {
      const res = await api.workflows.import(file, opts);
      if (res.status === 201 || res.status === 200) {
        await refresh();
        return { ok: true as const };
      }
      if (res.status === 409) {
        const data = (await res.json()) as { filename: string };
        conflict.value = { filename: data.filename };
        return { ok: false as const, status: 409 };
      }
      const data = await res.json();
      error.value = data.detail ?? `导入失败：${res.status}`;
      return { ok: false as const, status: res.status };
    } catch (err) {
      error.value = err instanceof Error ? err.message : String(err);
      return { ok: false as const, status: 0 };
    } finally {
      importing.value = false;
    }
  }

  async function removeWorkflow(id: string) {
    const res = await api.workflows.remove(id);
    if (res.ok || res.status === 204) {
      await refresh();
    }
  }

  function clearConflict() {
    conflict.value = null;
  }

  onMounted(refresh);

  return {
    items,
    loading,
    error,
    sourceFilter,
    search,
    importing,
    syncing,
    syncMsg,
    conflict,
    refresh,
    doSearch,
    doSync,
    onFileChosen,
    removeWorkflow,
    clearConflict,
  };
}
