<script setup lang="ts">
import { ref } from "vue";
import Modal from "@/components/Modal.vue";
import WorkflowImportButton from "./WorkflowImportButton.vue";
import WorkflowSyncButton from "./WorkflowSyncButton.vue";
import WorkflowDetailModal from "./WorkflowDetailModal.vue";
import WorkflowRow from "./WorkflowRow.vue";
import { useWorkflows } from "./useWorkflows";
import type { WorkflowSummary } from "@/types/api";

const {
  items,
  loading,
  error,
  sourceFilter,
  search,
  importing,
  syncing,
  syncMsg,
  conflict,
  onFileChosen,
  doSearch,
  doSync,
  removeWorkflow,
  clearConflict,
} = useWorkflows();

const detail = ref<WorkflowSummary | null>(null);
const confirmDelete = ref<WorkflowSummary | null>(null);

const pendingFile = ref<File | null>(null);

async function handleChosen(file: File) {
  pendingFile.value = file;
  const r = await onFileChosen(file);
  if (r && r.ok) {
    pendingFile.value = null;
    clearConflict();
  }
}

async function resolveConflict(action: "rename" | "overwrite" | "cancel", name?: string) {
  if (action === "cancel") {
    pendingFile.value = null;
    clearConflict();
    return;
  }
  const file = pendingFile.value;
  if (!file) {
    clearConflict();
    alert("文件已失效，请重新选择。");
    return;
  }
  if (action === "rename") {
    if (!name) return;
    const r = await onFileChosen(file, { name });
    if (r?.ok) {
      pendingFile.value = null;
      clearConflict();
    }
  } else {
    const r = await onFileChosen(file, { overwrite: true });
    if (r?.ok) {
      pendingFile.value = null;
      clearConflict();
    }
  }
}

async function onExport(id: string) {
  const res = await (await import("@/services/api")).api.workflows.export(id);
  const blob = await res.blob();
  const cd = res.headers.get("Content-Disposition") ?? "";
  const m = cd.match(/filename="?([^";]+)"?/);
  const filename = m ? m[1] : "workflow.json";
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}
</script>

<template>
  <div class="page">
    <div class="toolbar">
      <h2>工作流</h2>
      <div class="spacer" />
      <WorkflowImportButton
        :importing="importing"
        :conflict="conflict"
        @chosen="handleChosen"
        @conflict-resolve="resolveConflict"
      />
      <WorkflowSyncButton :syncing="syncing" @sync="doSync" />
    </div>

    <div v-if="syncMsg" class="sync-msg">{{ syncMsg }}</div>
    <div v-if="error" class="err">{{ error }}</div>

    <div class="filters">
      <input v-model="search" placeholder="搜索名称…" class="search" @input="doSearch" />
      <select v-model="sourceFilter" class="source" @change="doSearch">
        <option value="">全部来源</option>
        <option value="browse">ComfyUI</option>
        <option value="import">导入</option>
      </select>
    </div>

    <table v-if="loading" class="table"><tbody><tr><td>加载中…</td></tr></tbody></table>
    <table v-else class="table">
      <thead>
        <tr><th>名称</th><th>来源</th><th>大小</th><th>更新于</th><th>操作</th></tr>
      </thead>
      <tbody>
        <WorkflowRow
          v-for="wf in items"
          :key="wf.id"
          :workflow="wf"
          @view="detail = wf"
          @export="onExport(wf.id)"
          @delete="confirmDelete = wf"
        />
      </tbody>
    </table>

    <WorkflowDetailModal
      v-if="detail"
      :workflow-id="detail.id"
      :title="detail.name"
      @close="detail = null"
    />

    <Modal v-if="confirmDelete" title="删除工作流" @close="confirmDelete = null">
      <p>确定删除「{{ confirmDelete.name }}」？</p>
      <div class="actions">
        <button class="btn" @click="confirmDelete = null">取消</button>
        <button class="btn danger" @click="removeWorkflow(confirmDelete.id); confirmDelete = null">删除</button>
      </div>
    </Modal>
  </div>
</template>

<style scoped>
.page { max-width: 1100px; }
.toolbar {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  margin-bottom: 0.75rem;
}
.spacer { flex: 1; }
.sync-msg {
  padding: 0.5rem 0.75rem;
  background: #ecfdf5;
  border: 1px solid #a7f3d0;
  border-radius: 6px;
  margin-bottom: 0.75rem;
  color: #065f46;
}
.err { color: #ef4444; margin: 0.5rem 0; }
.filters {
  display: flex;
  gap: 0.75rem;
  margin-bottom: 0.75rem;
}
.search { flex: 1; padding: 0.4rem; border: 1px solid #cbd5e1; border-radius: 6px; }
.source { padding: 0.4rem; border: 1px solid #cbd5e1; border-radius: 6px; }
.table { width: 100%; border-collapse: collapse; }
.table th, .table td {
  text-align: left;
  padding: 0.5rem 0.75rem;
  border-bottom: 1px solid #e2e8f0;
}
.table th { background: #f8fafc; color: #475569; }
.actions { display: flex; gap: 0.5rem; justify-content: flex-end; }
.btn {
  padding: 0.4rem 0.9rem;
  border: 1px solid #cbd5e1;
  border-radius: 6px;
  background: #fff;
  cursor: pointer;
}
.btn.danger { background: #ef4444; border-color: #ef4444; color: #fff; }
</style>
