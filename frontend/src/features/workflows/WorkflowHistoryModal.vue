<script setup lang="ts">
import { ref, watch } from "vue";
import Modal from "@/components/Modal.vue";
import { api } from "@/services/api";
import type { WorkflowVersion } from "@/types/api";

const props = defineProps<{
  workflowId: string;
  title: string;
}>();

const emit = defineEmits<{ close: [] }>();

const versions = ref<WorkflowVersion[]>([]);
const error = ref<string | null>(null);
const viewBody = ref<Record<string, unknown> | null>(null);
const viewError = ref<string | null>(null);

async function load() {
  error.value = null;
  try {
    const data = await api.workflows.versions.list(props.workflowId);
    versions.value = data.items;
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err);
  }
}

async function viewVersion(v: WorkflowVersion) {
  viewBody.value = null;
  viewError.value = null;
  try {
    viewBody.value = await api.workflows.versions.getBody(props.workflowId, v.version);
  } catch (err) {
    viewError.value = err instanceof Error ? err.message : String(err);
  }
}

async function deleteVersion(v: WorkflowVersion) {
  if (!confirm(`确定删除版本 ${v.version}（${v.name}）？`)) return;
  const res = await api.workflows.versions.remove(props.workflowId, v.version);
  if (res.ok || res.status === 204) {
    await load();
  }
}

function fmtSize(bytes: number) {
  if (bytes < 1024) return `${bytes}B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)}KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)}MB`;
}

function fmtTime(iso: string) {
  return new Date(iso).toLocaleString();
}

watch(() => props.workflowId, load, { immediate: true });
</script>

<template>
  <Modal :title="`历史工作流：${props.title}`" @close="emit('close')">
    <div v-if="error" class="err">{{ error }}</div>

    <div v-if="viewBody || viewError" class="viewer">
      <button class="link" @click="viewBody = null; viewError = null">← 返回列表</button>
      <pre v-if="viewBody" class="json">{{ JSON.stringify(viewBody, null, 2) }}</pre>
      <p v-else-if="viewError" class="err">{{ viewError }}</p>
    </div>

    <table v-else class="table">
      <thead>
        <tr><th>版本</th><th>名称</th><th>大小</th><th>归档于</th><th>操作</th></tr>
      </thead>
      <tbody>
        <tr v-for="v in versions" :key="v.version">
          <td>v{{ v.version }}</td>
          <td>{{ v.name }}</td>
          <td>{{ fmtSize(v.size_bytes) }}</td>
          <td>{{ fmtTime(v.captured_at) }}</td>
          <td class="actions">
            <button class="link" @click="viewVersion(v)">查看</button>
            <button class="link danger" @click="deleteVersion(v)">删除</button>
          </td>
        </tr>
        <tr v-if="versions.length === 0"><td colspan="5">暂无历史版本</td></tr>
      </tbody>
    </table>
  </Modal>
</template>

<style scoped>
.err { color: #ef4444; }
.viewer { display: flex; flex-direction: column; gap: 0.5rem; }
.json {
  max-height: 50vh;
  overflow: auto;
  background: #0f172a;
  color: #a5b4fc;
  padding: 1rem;
  border-radius: 6px;
  font-size: 0.8rem;
}
.table { width: 100%; border-collapse: collapse; }
.table th, .table td { text-align: left; padding: 0.4rem 0.6rem; border-bottom: 1px solid #e2e8f0; }
.table th { background: #f8fafc; color: #475569; }
.actions { display: flex; gap: 0.5rem; }
.link { border: none; background: none; color: #0ea5e9; cursor: pointer; padding: 0 0.25rem; }
.link.danger { color: #ef4444; }
</style>
