<script setup lang="ts">
import { onMounted, reactive, ref } from "vue";
import { Plus } from "@element-plus/icons-vue";
import Modal from "@/components/Modal.vue";
import { api } from "@/services/api";
import type { WorkspaceSummary } from "@/types/api";

interface Draft {
  name: string;
  error: string | null;
  submitting: boolean;
}

const items = ref<WorkspaceSummary[]>([]);
const loading = ref(false);
const error = ref<string | null>(null);

const showCreate = ref(false);
const createDraft = reactive<Draft>({ name: "", error: null, submitting: false });

const editingId = ref<string | null>(null);
const editDraft = reactive<Draft>({ name: "", error: null, submitting: false });

const confirmDelete = ref<WorkspaceSummary | null>(null);
const deleteCount = ref(0);
const deleteLoading = ref(false);

async function load() {
  loading.value = true;
  error.value = null;
  try {
    const data = await api.workspaces.list();
    items.value = data.items;
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err);
  } finally {
    loading.value = false;
  }
}

function fmtTime(iso: string) {
  return new Date(iso).toLocaleString();
}

function openCreate() {
  createDraft.name = "";
  createDraft.error = null;
  createDraft.submitting = false;
  showCreate.value = true;
}

async function submitCreate() {
  const name = createDraft.name.trim();
  if (!name) {
    createDraft.error = "名称不能为空";
    return;
  }
  createDraft.submitting = true;
  createDraft.error = null;
  try {
    const res = await api.workspaces.create(name);
    if (res.status !== 201) {
      const data = await res.json().catch(() => null);
      throw new Error(data?.detail ?? `创建失败:${res.status}`);
    }
    showCreate.value = false;
    await load();
  } catch (err) {
    createDraft.error = err instanceof Error ? err.message : String(err);
  } finally {
    createDraft.submitting = false;
  }
}

function startEdit(row: WorkspaceSummary) {
  editingId.value = row.id;
  editDraft.name = row.name;
  editDraft.error = null;
  editDraft.submitting = false;
}

function cancelEdit() {
  editingId.value = null;
}

async function submitEdit(row: WorkspaceSummary) {
  const name = editDraft.name.trim();
  if (!name) {
    editDraft.error = "名称不能为空";
    return;
  }
  if (name === row.name) {
    cancelEdit();
    return;
  }
  editDraft.submitting = true;
  editDraft.error = null;
  try {
    const res = await api.workspaces.update(row.id, name);
    if (!res.ok) {
      const data = await res.json().catch(() => null);
      throw new Error(data?.detail ?? `重命名失败:${res.status}`);
    }
    cancelEdit();
    await load();
  } catch (err) {
    editDraft.error = err instanceof Error ? err.message : String(err);
  } finally {
    editDraft.submitting = false;
  }
}

async function askDelete(row: WorkspaceSummary) {
  confirmDelete.value = row;
  deleteCount.value = 0;
  deleteLoading.value = true;
  try {
    const data = await api.workspaces.generationCount(row.id);
    deleteCount.value = data.count;
  } catch {
    deleteCount.value = 0;
  } finally {
    deleteLoading.value = false;
  }
}

async function confirmDoDelete() {
  if (!confirmDelete.value) return;
  const target = confirmDelete.value;
  try {
    const res = await api.workspaces.remove(target.id);
    if (res.status !== 204) {
      const data = await res.json().catch(() => null);
      throw new Error(data?.detail ?? `删除失败:${res.status}`);
    }
    confirmDelete.value = null;
    await load();
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err);
  }
}

onMounted(load);
</script>

<template>
  <div>
    <div class="cc-toolbar">
      <h2>工作区</h2>
      <div class="cc-spacer" />
      <el-button type="primary" :icon="Plus" @click="openCreate">新建工作区</el-button>
    </div>

    <el-alert
      v-if="error"
      :title="error"
      type="error"
      :closable="false"
      show-icon
    />

    <el-table :data="items" v-loading="loading" stripe style="width: 100%">
      <el-table-column label="名称" min-width="220">
        <template #default="{ row }">
          <template v-if="editingId === row.id">
            <div class="cc-edit-row">
              <el-input
                v-model="editDraft.name"
                size="small"
                placeholder="工作区名称"
                @keyup.enter="submitEdit(row)"
                @keyup.esc="cancelEdit"
              />
              <el-button
                size="small"
                type="primary"
                :loading="editDraft.submitting"
                @click="submitEdit(row)"
              >保存</el-button>
              <el-button size="small" @click="cancelEdit">取消</el-button>
            </div>
            <div v-if="editDraft.error" class="cc-edit-error">{{ editDraft.error }}</div>
          </template>
          <span v-else>{{ row.name }}</span>
        </template>
      </el-table-column>
      <el-table-column label="创建时间" width="200">
        <template #default="{ row }">{{ fmtTime(row.created_at) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="200" align="right">
        <template #default="{ row }">
          <el-button v-if="editingId !== row.id" link type="primary" @click="startEdit(row)">重命名</el-button>
          <el-button link type="danger" @click="askDelete(row)">删除</el-button>
        </template>
      </el-table-column>
      <template #empty>
        <el-empty description="暂无工作区,点击右上角新建" />
      </template>
    </el-table>

    <Modal v-if="showCreate" title="新建工作区" width="420px" @close="showCreate = false">
      <el-form label-width="0">
        <el-form-item>
          <el-input
            v-model="createDraft.name"
            placeholder="工作区名称"
            maxlength="255"
            show-word-limit
            @keyup.enter="submitCreate"
          />
        </el-form-item>
        <el-alert
          v-if="createDraft.error"
          :title="createDraft.error"
          type="error"
          :closable="false"
          show-icon
        />
      </el-form>
      <template #footer>
        <el-button @click="showCreate = false">取消</el-button>
        <el-button type="primary" :loading="createDraft.submitting" @click="submitCreate">创建</el-button>
      </template>
    </Modal>

    <Modal
      v-if="confirmDelete"
      title="删除工作区"
      width="420px"
      @close="confirmDelete = null"
    >
      <template v-if="deleteLoading">正在检查关联的生成数量…</template>
      <template v-else>
        <p>确定删除工作区「{{ confirmDelete.name }}」？</p>
        <p v-if="deleteCount > 0" class="cc-delete-hint">
          该工作区当前关联 {{ deleteCount }} 条生成记录。删除后,这些记录仍会保留,
          仅解除与该工作区的关联。
        </p>
        <p v-else class="cc-delete-hint">该工作区暂无关联的生成记录。</p>
      </template>
      <template #footer>
        <el-button @click="confirmDelete = null">取消</el-button>
        <el-button type="danger" :disabled="deleteLoading" @click="confirmDoDelete">删除</el-button>
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
.cc-edit-row {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}
.cc-edit-error {
  margin-top: 0.25rem;
  color: var(--el-color-danger);
  font-size: 0.8rem;
}
.cc-delete-hint {
  margin: 0.5rem 0 0;
  color: #64748b;
  font-size: 0.85rem;
}
</style>
