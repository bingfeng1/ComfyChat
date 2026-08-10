<script setup lang="ts">
import { ref } from "vue";
import Modal from "@/components/Modal.vue";
import GenerationCreateModal from "./GenerationCreateModal.vue";
import GenerationDetailModal from "./GenerationDetailModal.vue";
import { useGenerations } from "./useGenerations";
import { api } from "@/services/api";
import type { GenerationSummary } from "@/types/api";

const { items, loading, error, statusFilter, refresh, remove } = useGenerations();

const showCreate = ref(false);
const detail = ref<GenerationSummary | null>(null);
const regenerate = ref<GenerationSummary | null>(null);
const confirmDelete = ref<GenerationSummary | null>(null);

async function doDelete() {
  if (!confirmDelete.value) return;
  await remove(confirmDelete.value.id);
  confirmDelete.value = null;
}

const statusLabel: Record<string, string> = {
  queued: "排队中",
  running: "执行中",
  success: "成功",
  failed: "失败",
};

function statusType(status: string): "success" | "warning" | "danger" | "info" {
  if (status === "success") return "success";
  if (status === "failed") return "danger";
  if (status === "running" || status === "queued") return "warning";
  return "info";
}

function fmtTime(iso: string) {
  return new Date(iso).toLocaleString();
}

function thumbUrl(g: GenerationSummary): string | null {
  const first = g.outputs[0];
  return first ? api.generations.imageUrl(g.id, first) : null;
}

function promptText(g: GenerationSummary): string {
  const p = g.parameters["text"];
  return typeof p === "string" ? p : "";
}
</script>

<template>
  <div>
    <div class="cc-toolbar">
      <h2>生成</h2>
      <div class="cc-spacer" />
      <el-button type="primary" @click="showCreate = true">+ 新建生成</el-button>
    </div>

    <el-alert
      v-if="error"
      :title="error"
      type="error"
      :closable="false"
      show-icon
    />

    <div class="cc-filters">
      <el-select v-model="statusFilter" placeholder="全部状态" clearable style="width: 200px" @change="() => refresh()">
        <el-option value="" label="全部状态" />
        <el-option value="queued" label="排队中" />
        <el-option value="running" label="执行中" />
        <el-option value="success" label="成功" />
        <el-option value="failed" label="失败" />
      </el-select>
    </div>

    <el-table :data="items" v-loading="loading" stripe style="width: 100%">
      <el-table-column label="图" width="100">
        <template #default="{ row }">
          <el-image
            v-if="thumbUrl(row)"
            :src="thumbUrl(row)!"
            fit="cover"
            style="width: 72px; height: 72px; border-radius: 6px"
            :preview-src-list="[thumbUrl(row)!]"
            preview-teleported
          />
          <div v-else class="cc-thumb-placeholder" />
        </template>
      </el-table-column>
      <el-table-column label="提示词" min-width="240">
        <template #default="{ row }">
          <span class="cc-prompt">{{ promptText(row) || "—" }}</span>
        </template>
      </el-table-column>
      <el-table-column label="工作流" min-width="160">
        <template #default="{ row }">{{ row.workflow_name }}</template>
      </el-table-column>
      <el-table-column label="状态" width="120">
        <template #default="{ row }">
          <el-tag :type="statusType(row.status)" size="small">
            {{ statusLabel[row.status] ?? row.status }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="时间" width="180">
        <template #default="{ row }">{{ fmtTime(row.created_at) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="180" align="right">
        <template #default="{ row }">
          <el-button link type="primary" @click="detail = row">查看</el-button>
          <el-button link type="primary" @click="regenerate = row">再生成</el-button>
          <el-button link type="danger" @click="confirmDelete = row">删除</el-button>
        </template>
      </el-table-column>
      <template #empty>
        <el-empty description="暂无生成记录" />
      </template>
    </el-table>

    <GenerationCreateModal v-if="showCreate" @close="showCreate = false" />
    <GenerationCreateModal v-if="regenerate" :preset="regenerate" @close="regenerate = null" />
    <GenerationDetailModal
      v-if="detail"
      :generation-id="detail.id"
      :title="detail.workflow_name"
      @close="detail = null"
    />

    <Modal v-if="confirmDelete" title="删除生成记录" @close="confirmDelete = null">
      <p>确定删除该生成记录及其图片？</p>
      <template #footer>
        <el-button @click="confirmDelete = null">取消</el-button>
        <el-button type="danger" @click="doDelete">删除</el-button>
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
  margin-bottom: 0.75rem;
}
.cc-thumb-placeholder {
  display: inline-block;
  width: 72px;
  height: 72px;
  background: #e2e8f0;
  border-radius: 6px;
}
.cc-prompt {
  display: inline-block;
  max-width: 280px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  vertical-align: bottom;
}
</style>
