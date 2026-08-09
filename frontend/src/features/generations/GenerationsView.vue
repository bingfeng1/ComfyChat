<script setup lang="ts">
import { ref } from "vue";
import Modal from "@/components/Modal.vue";
import GenerationCreateModal from "./GenerationCreateModal.vue";
import GenerationDetailModal from "./GenerationDetailModal.vue";
import GenerationRow from "./GenerationRow.vue";
import { useGenerations } from "./useGenerations";
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
</script>

<template>
  <div class="page">
    <div class="toolbar">
      <h2>生成</h2>
      <div class="spacer" />
      <button class="btn" @click="showCreate = true">+ 新建生成</button>
    </div>

    <div v-if="error" class="err">{{ error }}</div>

    <div class="filters">
      <select v-model="statusFilter" class="status" @change="refresh">
        <option value="">全部状态</option>
        <option value="queued">排队中</option>
        <option value="running">执行中</option>
        <option value="success">成功</option>
        <option value="failed">失败</option>
      </select>
    </div>

    <table v-if="loading && items.length === 0" class="table">
      <tbody><tr><td>加载中…</td></tr></tbody>
    </table>
    <table v-else class="table">
      <thead>
        <tr><th>图</th><th>提示词</th><th>工作流</th><th>状态</th><th>时间</th><th>操作</th></tr>
      </thead>
      <tbody>
        <GenerationRow
          v-for="g in items"
          :key="g.id"
          :generation="g"
          @view="detail = g"
          @regenerate="regenerate = g"
          @delete="confirmDelete = g"
        />
      </tbody>
    </table>

    <GenerationCreateModal
      v-if="showCreate"
      @close="showCreate = false"
    />
    <GenerationCreateModal
      v-if="regenerate"
      :preset="regenerate"
      @close="regenerate = null"
    />
    <GenerationDetailModal
      v-if="detail"
      :generation-id="detail.id"
      :title="detail.workflow_name"
      @close="detail = null"
    />

    <Modal v-if="confirmDelete" title="删除生成记录" @close="confirmDelete = null">
      <p>确定删除该生成记录及其图片？</p>
      <div class="actions">
        <button class="btn" @click="confirmDelete = null">取消</button>
        <button class="btn danger" @click="doDelete">删除</button>
      </div>
    </Modal>
  </div>
</template>

<style scoped>
.page { max-width: 1100px; }
.toolbar { display: flex; align-items: center; gap: 0.75rem; margin-bottom: 0.75rem; }
.spacer { flex: 1; }
.err { color: #ef4444; margin: 0.5rem 0; }
.filters { margin-bottom: 0.75rem; }
.status { padding: 0.4rem; border: 1px solid #cbd5e1; border-radius: 6px; }
.table { width: 100%; border-collapse: collapse; }
.table th, .table td { text-align: left; padding: 0.5rem 0.75rem; border-bottom: 1px solid #e2e8f0; }
.table th { background: #f8fafc; color: #475569; }
.actions { display: flex; gap: 0.5rem; justify-content: flex-end; }
.btn { padding: 0.4rem 0.9rem; border: 1px solid #cbd5e1; border-radius: 6px; background: #fff; cursor: pointer; }
.btn.danger { background: #ef4444; border-color: #ef4444; color: #fff; }
</style>
