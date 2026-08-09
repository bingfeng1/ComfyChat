import { onMounted, onUnmounted, ref } from "vue";
import { api } from "@/services/api";
import type { GenerationStatus, GenerationSummary } from "@/types/api";

export function useGenerations() {
  const items = ref<GenerationSummary[]>([]);
  const loading = ref(false);
  const error = ref<string | null>(null);
  const statusFilter = ref<GenerationStatus | "">("");
  let timer: number | undefined;

  async function refresh() {
    loading.value = true;
    error.value = null;
    try {
      const data = await api.generations.list({
        status: statusFilter.value || undefined,
      });
      items.value = data.items;
    } catch (err) {
      error.value = err instanceof Error ? err.message : String(err);
    } finally {
      loading.value = false;
    }
  }

  async function create(payload: {
    workflow_id: string;
    parameters: Record<string, unknown>;
  }) {
    const res = await api.generations.create(payload);
    if (res.status !== 201) {
      const data = await res.json().catch(() => null);
      throw new Error(data?.detail ?? `创建失败：${res.status}`);
    }
    await refresh();
    return (await res.json()) as GenerationSummary;
  }

  async function remove(id: string) {
    const res = await api.generations.remove(id);
    if (res.status !== 204) throw new Error(`删除失败：${res.status}`);
    await refresh();
  }

  onMounted(() => {
    refresh();
    timer = window.setInterval(refresh, 2000);
  });
  onUnmounted(() => {
    if (timer) window.clearInterval(timer);
  });

  return { items, loading, error, statusFilter, refresh, create, remove };
}
