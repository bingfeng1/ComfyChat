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
  <Modal
    :title="`历史工作流：${props.title}`"
    width="880px"
    @close="emit('close')"
  >
    <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon />

    <div v-if="viewBody || viewError" class="cc-viewer">
      <el-button link type="primary" @click="viewBody = null; viewError = null">← 返回列表</el-button>
      <pre v-if="viewBody" class="cc-json">{{ JSON.stringify(viewBody, null, 2) }}</pre>
      <p v-else-if="viewError" class="cc-err">{{ viewError }}</p>
    </div>

    <el-table v-else :data="versions" stripe style="width: 100%">
      <el-table-column label="版本" width="80">
        <template #default="{ row }">v{{ row.version }}</template>
      </el-table-column>
      <el-table-column label="名称" min-width="220" prop="name" />
      <el-table-column label="大小" width="100">
        <template #default="{ row }">{{ fmtSize(row.size_bytes) }}</template>
      </el-table-column>
      <el-table-column label="归档于" width="200">
        <template #default="{ row }">{{ fmtTime(row.captured_at) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="160" align="right">
        <template #default="{ row }">
          <el-button link type="primary" @click="viewVersion(row)">查看</el-button>
          <el-button link type="danger" @click="deleteVersion(row)">删除</el-button>
        </template>
      </el-table-column>
      <template #empty>
        <span class="cc-empty">暂无历史版本</span>
      </template>
    </el-table>
  </Modal>
</template>

<style lang="scss" scoped>
.cc-err {
  color: #ef4444;
}
.cc-viewer {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}
.cc-json {
  max-height: 60vh;
  overflow: auto;
  background: #0f172a;
  color: #a5b4fc;
  padding: 1rem;
  border-radius: 6px;
  font-size: 0.8rem;
  white-space: pre-wrap;
  word-break: break-word;
}
.cc-empty {
  color: #64748b;
  font-size: 0.9rem;
}
</style>
