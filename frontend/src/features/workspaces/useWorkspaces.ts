import { onMounted, ref } from "vue";
import { api } from "@/services/api";
import type { WorkspaceSummary } from "@/types/api";

const items = ref<WorkspaceSummary[]>([]);
const loaded = ref(false);
const loading = ref(false);

async function refresh() {
  loading.value = true;
  try {
    const data = await api.workspaces.list();
    items.value = data.items;
    loaded.value = true;
  } finally {
    loading.value = false;
  }
}

export function useWorkspaces() {
  onMounted(() => {
    if (!loaded.value) refresh();
  });

  function nameOf(id: string): string {
    return items.value.find((w) => w.id === id)?.name ?? "已删除";
  }

  async function create(name: string): Promise<WorkspaceSummary> {
    const res = await api.workspaces.create(name);
    if (res.status !== 201) {
      const data = await res.json().catch(() => null);
      throw new Error(data?.detail ?? `创建失败:${res.status}`);
    }
    const ws = (await res.json()) as WorkspaceSummary;
    await refresh();
    return ws;
  }

  return {
    items,
    loading,
    refresh,
    nameOf,
    create,
  };
}
