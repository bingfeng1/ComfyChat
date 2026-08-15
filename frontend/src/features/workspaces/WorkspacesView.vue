<script setup lang="ts">
import { onMounted, reactive, ref } from "vue";
import { useRouter } from "vue-router";
import { Delete, Edit, Plus } from "@element-plus/icons-vue";
import Modal from "@/components/Modal.vue";
import { api } from "@/services/api";
import type { WorkspaceSummary } from "@/types/api";

interface Draft {
  name: string;
  error: string | null;
  submitting: boolean;
}

const router = useRouter();
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

function fmtRelative(iso: string): string {
  const target = new Date(iso).getTime();
  const now = Date.now();
  const diff = Math.floor((now - target) / 1000);
  if (diff < 60) return "刚刚";
  if (diff < 3600) return `${Math.floor(diff / 60)} 分钟前`;
  if (diff < 86400) return `${Math.floor(diff / 3600)} 小时前`;
  if (diff < 86400 * 30) return `${Math.floor(diff / 86400)} 天前`;
  return new Date(iso).toLocaleDateString();
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

function startEdit(row: WorkspaceSummary, event: Event) {
  event.stopPropagation();
  editingId.value = row.id;
  editDraft.name = row.name;
  editDraft.error = null;
  editDraft.submitting = false;
}

function cancelEdit() {
  editingId.value = null;
}

async function submitEdit(row: WorkspaceSummary, event?: Event) {
  event?.stopPropagation();
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

function openCard(row: WorkspaceSummary) {
  if (editingId.value === row.id) return;
  router.push(`/workspaces/${row.id}`);
}

async function askDelete(row: WorkspaceSummary, event: Event) {
  event.stopPropagation();
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

function thumbUrl(generationId: string, filename: string): string {
  return api.generations.imageUrl(generationId, filename);
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

    <div v-loading="loading" class="cc-masonry">
      <template v-if="items.length === 0 && !loading">
        <el-empty description="暂无工作区,点击右上角新建" />
      </template>
      <article
        v-for="row in items"
        :key="row.id"
        class="cc-card"
        :class="{ 'cc-card-editing': editingId === row.id }"
        @click="openCard(row)"
      >
        <div class="cc-card-preview">
          <template v-if="row.preview.length === 0">
            <div class="cc-card-empty">暂无生成</div>
          </template>
          <template v-else>
            <div
              v-for="p in row.preview"
              :key="`${p.generation_id}-${p.filename}`"
              class="cc-card-thumb"
            >
              <video
                v-if="p.media_type === 'video'"
                :src="thumbUrl(p.generation_id, p.filename)"
                muted
                autoplay
                loop
                playsinline
                class="cc-card-thumb-media"
              />
              <img
                v-else
                :src="thumbUrl(p.generation_id, p.filename)"
                :alt="row.name"
                class="cc-card-thumb-media"
                loading="lazy"
              />
            </div>
          </template>
        </div>

        <div class="cc-card-body">
          <div v-if="editingId === row.id" class="cc-card-edit" @click.stop>
            <el-input
              v-model="editDraft.name"
              size="small"
              placeholder="工作区名称"
              maxlength="255"
              @keyup.enter="submitEdit(row)"
              @keyup.esc="cancelEdit"
            />
            <div class="cc-card-edit-actions">
              <el-button size="small" type="primary" :loading="editDraft.submitting" @click="submitEdit(row)">保存</el-button>
              <el-button size="small" @click="cancelEdit">取消</el-button>
            </div>
            <div v-if="editDraft.error" class="cc-card-edit-error">{{ editDraft.error }}</div>
          </div>
          <div v-else class="cc-card-title">
            <span class="cc-card-name">{{ row.name }}</span>
            <div class="cc-card-actions" @click.stop>
              <el-button
                link
                type="primary"
                :icon="Edit"
                size="small"
                @click="startEdit(row, $event)"
              />
              <el-button
                link
                type="danger"
                :icon="Delete"
                size="small"
                @click="askDelete(row, $event)"
              />
            </div>
          </div>
          <div class="cc-card-meta">
            {{ row.generation_count }} 条生成 · 更新于 {{ fmtRelative(row.updated_at) }}
          </div>
        </div>
      </article>
    </div>

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
  margin-bottom: 1rem;
}
.cc-spacer {
  flex: 1;
}

/* 瀑布流容器:CSS 多列布局 */
.cc-masonry {
  column-count: 4;
  column-gap: 1rem;
}
@media (max-width: 1280px) {
  .cc-masonry { column-count: 3; }
}
@media (max-width: 960px) {
  .cc-masonry { column-count: 2; }
}
@media (max-width: 600px) {
  .cc-masonry { column-count: 1; }
}

/* 卡片:break-inside: avoid 避免在列内被拆开 */
.cc-card {
  break-inside: avoid;
  margin-bottom: 1rem;
  display: block;
  background: #fff;
  border-radius: 10px;
  overflow: hidden;
  box-shadow: 0 1px 3px rgba(15, 23, 42, 0.06), 0 1px 2px rgba(15, 23, 42, 0.04);
  cursor: pointer;
  transition: transform 0.15s ease, box-shadow 0.15s ease;
  position: relative;
}
.cc-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 8px 20px rgba(15, 23, 42, 0.08), 0 4px 8px rgba(15, 23, 42, 0.04);
}
.cc-card-editing {
  cursor: default;
}

.cc-card-preview {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 2px;
  background: #f1f5f9;
  min-height: 120px;
  position: relative;
}
.cc-card-preview:has(.cc-card-thumb:nth-child(1):last-child) {
  grid-template-columns: 1fr;
}
.cc-card-thumb {
  aspect-ratio: 1 / 1;
  overflow: hidden;
  position: relative;
  background: #e2e8f0;
}
.cc-card-thumb-media {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}
.cc-card-empty {
  grid-column: 1 / -1;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #94a3b8;
  font-size: 0.85rem;
  padding: 2rem 0;
}

.cc-card-body {
  padding: 0.75rem 0.85rem 0.85rem;
}
.cc-card-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
}
.cc-card-name {
  font-weight: 600;
  color: #0f172a;
  font-size: 0.95rem;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1;
  min-width: 0;
}
.cc-card-actions {
  display: flex;
  align-items: center;
  gap: 0;
  opacity: 0;
  transition: opacity 0.15s;
}
.cc-card:hover .cc-card-actions {
  opacity: 1;
}
.cc-card-meta {
  margin-top: 0.4rem;
  font-size: 0.78rem;
  color: #64748b;
}
.cc-card-edit {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}
.cc-card-edit-actions {
  display: flex;
  gap: 0.5rem;
}
.cc-card-edit-error {
  color: var(--el-color-danger);
  font-size: 0.78rem;
}
.cc-delete-hint {
  margin: 0.5rem 0 0;
  color: #64748b;
  font-size: 0.85rem;
}
</style>