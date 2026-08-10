<script setup lang="ts">
import { ref } from "vue";
import { Search } from "@element-plus/icons-vue";
import Modal from "@/components/Modal.vue";
import WorkflowImportButton from "./WorkflowImportButton.vue";
import WorkflowSyncButton from "./WorkflowSyncButton.vue";
import WorkflowDetailModal from "./WorkflowDetailModal.vue";
import WorkflowHistoryModal from "./WorkflowHistoryModal.vue";
import WorkflowGenerationConfigModal from "./WorkflowGenerationConfigModal.vue";
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
const historyOf = ref<WorkflowSummary | null>(null);
const configOf = ref<WorkflowSummary | null>(null);
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

async function resolveConflict(
  action: "rename" | "overwrite" | "cancel",
  name?: string,
) {
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

function fmtSize(bytes: number) {
  if (bytes < 1024) return `${bytes}B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)}KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)}MB`;
}

function fmtTime(iso: string) {
  return new Date(iso).toLocaleString();
}

const sourceLabel: Record<string, string> = {
  browse: "ComfyUI",
  import: "导入",
};
</script>

<template>
  <div>
    <div class="cc-toolbar">
      <h2>工作流</h2>
      <div class="cc-spacer" />
      <WorkflowImportButton
        :importing="importing"
        :conflict="conflict"
        @chosen="handleChosen"
        @conflict-resolve="resolveConflict"
      />
      <WorkflowSyncButton :syncing="syncing" @sync="doSync" />
    </div>

    <el-alert
      v-if="syncMsg"
      :title="syncMsg"
      type="success"
      :closable="false"
      show-icon
    />
    <el-alert
      v-if="error"
      :title="error"
      type="error"
      :closable="false"
      show-icon
    />

    <div class="cc-filters">
      <el-input
        v-model="search"
        placeholder="搜索名称…"
        :prefix-icon="Search"
        clearable
        @input="doSearch"
      />
      <el-select v-model="sourceFilter" placeholder="全部来源" clearable @change="doSearch">
        <el-option value="" label="全部来源" />
        <el-option value="browse" label="ComfyUI" />
        <el-option value="import" label="导入" />
      </el-select>
    </div>

    <el-table :data="items" v-loading="loading" stripe style="width: 100%">
      <el-table-column label="名称" min-width="240">
        <template #default="{ row }">
          <span class="cc-name">{{ row.name }}.json</span>
        </template>
      </el-table-column>
      <el-table-column label="来源" width="120">
        <template #default="{ row }">
          {{ sourceLabel[row.source] ?? row.source }}
        </template>
      </el-table-column>
      <el-table-column label="大小" width="120">
        <template #default="{ row }">{{ fmtSize(row.size_bytes) }}</template>
      </el-table-column>
      <el-table-column label="更新于" width="200">
        <template #default="{ row }">{{ fmtTime(row.updated_at) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="220" align="right">
        <template #default="{ row }">
          <el-button
            v-if="row.source === 'browse' && row.has_history"
            link
            @click="historyOf = row"
          >历史</el-button>
          <el-button
            v-if="row.source === 'browse'"
            link
            type="primary"
            @click="configOf = row"
          >配置</el-button>
          <el-button link type="primary" @click="detail = row">查看</el-button>
          <el-button link type="primary" @click="onExport(row.id)">下载</el-button>
          <el-button link type="danger" @click="confirmDelete = row">删除</el-button>
        </template>
      </el-table-column>
      <template #empty>
        <el-empty description="暂无工作流" />
      </template>
    </el-table>

    <WorkflowDetailModal
      v-if="detail"
      :workflow-id="detail.id"
      :title="detail.name"
      @close="detail = null"
    />
    <WorkflowHistoryModal
      v-if="historyOf"
      :workflow-id="historyOf.id"
      :title="historyOf.name"
      @close="historyOf = null"
    />
    <WorkflowGenerationConfigModal
      v-if="configOf"
      :workflow-id="configOf.id"
      :title="configOf.name"
      @close="configOf = null"
      @saved="doSearch"
    />

    <Modal v-if="confirmDelete" title="删除工作流" @close="confirmDelete = null">
      <p>确定删除「{{ confirmDelete.name }}」？</p>
      <template #footer>
        <el-button @click="confirmDelete = null">取消</el-button>
        <el-button type="danger" @click="removeWorkflow(confirmDelete.id); confirmDelete = null">删除</el-button>
      </template>
    </Modal>
  </div>
</template>

<style lang="scss" scoped>
.cc-toolbar {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  margin-bottom: 0.75rem;
}
.cc-spacer {
  flex: 1;
}
.cc-filters {
  display: flex;
  gap: 0.75rem;
  margin-bottom: 0.75rem;
  align-items: center;
}
.cc-name {
  font-weight: 500;
}
:deep(.cc-toolbar .el-button + .el-button) {
  margin-left: 0;
}
</style>