<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ArrowLeft, Delete, Edit, Plus } from "@element-plus/icons-vue";
import Modal from "@/components/Modal.vue";
import GenerationCreateModal from "@/features/generations/GenerationCreateModal.vue";
import GenerationDetailModal from "@/features/generations/GenerationDetailModal.vue";
import { api } from "@/services/api";
import { useNsfwStore } from "@/stores/nsfw";
import { storeToRefs } from "pinia";
import type { GenerationSummary, WorkspaceSummary } from "@/types/api";
import { mediaTypeOf, type MediaType } from "@/features/generations/mediaType";

const route = useRoute();
const router = useRouter();
const wsId = computed(() => String(route.params.id));

const workspace = ref<WorkspaceSummary | null>(null);
const notFound = ref(false);
const loadError = ref<string | null>(null);

const items = ref<GenerationSummary[]>([]);
const loading = ref(false);
const page = ref(1);
const pageSize = ref(60);
const total = ref(0);
const detail = ref<GenerationSummary | null>(null);
const showCreateWs = ref(false);
const showCreateGen = ref(false);
const editName = ref("");
const editError = ref<string | null>(null);
const editSubmitting = ref(false);
const showRename = ref(false);
const confirmDelete = ref(false);

const { enabled: nsfwEnabled } = storeToRefs(useNsfwStore());
let pollTimer: number | undefined;

async function loadWorkspace() {
  loadError.value = null;
  notFound.value = false;
  try {
    workspace.value = await api.workspaces.get(wsId.value);
    editName.value = workspace.value.name;
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    if (msg.includes("404") || msg.includes("not found")) {
      notFound.value = true;
    } else {
      loadError.value = msg;
    }
  }
}

async function loadGenerations(silent = false) {
  if (!silent) loading.value = true;
  try {
    const data = await api.generations.list({
      workspace_id: wsId.value,
      page: page.value,
      page_size: pageSize.value,
      exclude_nsfw: !nsfwEnabled.value,
    });
    items.value = data.items;
    total.value = data.total;
  } catch (err) {
    loadError.value = err instanceof Error ? err.message : String(err);
  } finally {
    if (!silent) loading.value = false;
  }
}

async function pollGenerations() {
  try {
    const data = await api.generations.list({
      workspace_id: wsId.value,
      page: page.value,
      page_size: pageSize.value,
      exclude_nsfw: !nsfwEnabled.value,
    });
    items.value = data.items;
    total.value = data.total;
  } catch {
    /* 静默 */
  }
}

function mediaType(g: GenerationSummary): MediaType | null {
  if (!g.outputs.length) return null;
  return mediaTypeOf(g.outputs[0]);
}

function thumbUrl(g: GenerationSummary): string | null {
  if (!g.outputs.length) return null;
  return api.generations.imageUrl(g.id, g.outputs[0]);
}

function back() {
  router.push("/workspaces");
}

function openCreateGen() {
  showCreateGen.value = true;
}

function onCreateClosed() {
  showCreateGen.value = false;
  loadGenerations();
  loadWorkspace(); // refresh count/preview
}

async function startEditName() {
  if (!workspace.value) return;
  editName.value = workspace.value.name;
  editError.value = null;
  showRename.value = true;
}

async function submitEditName() {
  if (!workspace.value) return;
  const name = editName.value.trim();
  if (!name || name === workspace.value.name) {
    editName.value = workspace.value.name;
    return;
  }
  editSubmitting.value = true;
  editError.value = null;
  try {
    const res = await api.workspaces.update(workspace.value.id, name);
    if (!res.ok) {
      const data = await res.json().catch(() => null);
      throw new Error(data?.detail ?? `重命名失败:${res.status}`);
    }
    await loadWorkspace();
  } catch (err) {
    editError.value = err instanceof Error ? err.message : String(err);
  } finally {
    editSubmitting.value = false;
  }
}

async function removeFromWorkspace(g: GenerationSummary) {
  if (!workspace.value) return;
  const wsIdVal = workspace.value.id;
  await api.generations.removeWorkspace(g.id, wsIdVal);
  // 直接从本地列表移除
  items.value = items.value.filter((it) => it.id !== g.id);
  total.value = Math.max(0, total.value - 1);
  await loadWorkspace();
}

async function doDeleteWorkspace() {
  if (!workspace.value) return;
  try {
    const res = await api.workspaces.remove(workspace.value.id);
    if (res.status !== 204) {
      const data = await res.json().catch(() => null);
      throw new Error(data?.detail ?? `删除失败:${res.status}`);
    }
    confirmDelete.value = false;
    back();
  } catch (err) {
    loadError.value = err instanceof Error ? err.message : String(err);
  }
}

onMounted(async () => {
  await loadWorkspace();
  if (!notFound.value) {
    await loadGenerations();
    pollTimer = window.setInterval(pollGenerations, 2000);
  }
});

onUnmounted(() => {
  if (pollTimer !== undefined) window.clearInterval(pollTimer);
});

watch(wsId, async () => {
  await loadWorkspace();
  if (!notFound.value) {
    page.value = 1;
    await loadGenerations();
  }
});

watch(nsfwEnabled, () => {
  page.value = 1;
  loadGenerations();
});

const visibleItems = computed(() => items.value);
</script>

<template>
  <div>
    <div class="cc-toolbar">
      <el-button :icon="ArrowLeft" link @click="back">返回工作区</el-button>
      <div class="cc-spacer" />
      <el-button type="primary" :icon="Plus" @click="openCreateGen">新建生成</el-button>
    </div>

    <el-alert
      v-if="loadError"
      :title="loadError"
      type="error"
      :closable="false"
      show-icon
    />

    <div v-if="notFound" class="cc-notfound">
      <el-empty description="工作区不存在或已被删除">
        <el-button type="primary" @click="back">返回列表</el-button>
      </el-empty>
    </div>

    <template v-else-if="workspace">
      <div class="cc-header">
        <div class="cc-header-main">
          <h2 class="cc-title">{{ workspace.name }}</h2>
          <span class="cc-meta">{{ workspace.generation_count }} 条生成</span>
        </div>
        <div class="cc-header-actions">
          <el-button :icon="Edit" link type="primary" @click="startEditName">重命名</el-button>
          <el-button :icon="Delete" link type="danger" @click="confirmDelete = true">删除工作区</el-button>
        </div>
      </div>

      <div v-if="editError" class="cc-edit-error">{{ editError }}</div>

      <div v-loading="loading" class="cc-masonry">
        <template v-if="visibleItems.length === 0 && !loading">
          <el-empty description="该工作区暂无生成,点击右上角「新建生成」开始" />
        </template>
        <article
          v-for="g in visibleItems"
          :key="g.id"
          class="cc-tile"
          @click="detail = g"
        >
          <video
            v-if="mediaType(g) === 'video'"
            :src="thumbUrl(g) ?? ''"
            muted
            autoplay
            loop
            playsinline
            class="cc-tile-media"
          />
          <img
            v-else-if="thumbUrl(g)"
            :src="thumbUrl(g) ?? ''"
            :alt="g.workflow_name"
            class="cc-tile-media"
            loading="lazy"
          />
          <div v-else class="cc-tile-empty">无输出</div>
          <el-button
            :icon="Delete"
            size="small"
            class="cc-tile-remove"
            circle
            @click.stop="removeFromWorkspace(g)"
            title="从工作区移除"
          />
        </article>
      </div>

      <div v-if="total > pageSize" class="cc-pagination">
        <el-pagination
          :current-page="page"
          :page-size="pageSize"
          :total="total"
          :page-sizes="[30, 60, 120]"
          layout="total, sizes, prev, pager, next"
          background
          @current-change="(p: number) => { page = p; loadGenerations(); }"
          @size-change="(s: number) => { pageSize = s; page = 1; loadGenerations(); }"
        />
      </div>
    </template>

    <GenerationDetailModal
      v-if="detail"
      :generation-id="detail.id"
      :title="detail.workflow_name"
      @close="detail = null"
    />
    <GenerationCreateModal
      v-if="showCreateGen && workspace"
      :preselect-workspace-id="workspace.id"
      @close="onCreateClosed"
    />

    <Modal v-if="showRename" title="重命名工作区" width="420px" @close="showRename = false">
      <el-input
        v-model="editName"
        placeholder="工作区名称"
        maxlength="255"
        show-word-limit
        @keyup.enter="submitEditName"
      />
      <el-alert
        v-if="editError"
        :title="editError"
        type="error"
        :closable="false"
        show-icon
        style="margin-top: 0.5rem"
      />
      <template #footer>
        <el-button @click="showRename = false">取消</el-button>
        <el-button type="primary" :loading="editSubmitting" @click="submitEditName">保存</el-button>
      </template>
    </Modal>

    <Modal v-if="confirmDelete" title="删除工作区" width="420px" @close="confirmDelete = false">
      <p>确定删除工作区「{{ workspace?.name }}」？</p>
      <p class="cc-delete-hint">
        该工作区当前关联 {{ workspace?.generation_count ?? 0 }} 条生成记录。删除后,
        这些记录仍会保留,仅解除与该工作区的关联。
      </p>
      <template #footer>
        <el-button @click="confirmDelete = false">取消</el-button>
        <el-button type="danger" @click="doDeleteWorkspace">删除</el-button>
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
.cc-header {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 1rem;
  margin-bottom: 1rem;
  flex-wrap: wrap;
}
.cc-header-main {
  display: flex;
  align-items: baseline;
  gap: 0.75rem;
}
.cc-title {
  margin: 0;
  font-size: 1.4rem;
  color: #0f172a;
}
.cc-meta {
  color: #64748b;
  font-size: 0.85rem;
}
.cc-header-actions {
  display: flex;
  gap: 0.25rem;
}
.cc-edit-error {
  color: var(--el-color-danger);
  font-size: 0.85rem;
  margin-bottom: 0.5rem;
}
.cc-notfound {
  margin-top: 2rem;
}

.cc-masonry {
  column-count: 4;
  column-gap: 0.75rem;
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

.cc-tile {
  break-inside: avoid;
  margin-bottom: 0.75rem;
  position: relative;
  background: #f1f5f9;
  border-radius: 8px;
  overflow: hidden;
  cursor: pointer;
  transition: transform 0.15s ease, box-shadow 0.15s ease;
}
.cc-tile:hover {
  transform: translateY(-2px);
  box-shadow: 0 6px 16px rgba(15, 23, 42, 0.08);
}
.cc-tile-media {
  width: 100%;
  height: auto;
  display: block;
  background: #e2e8f0;
}
.cc-tile-empty {
  padding: 3rem 1rem;
  text-align: center;
  color: #94a3b8;
}
.cc-tile-remove {
  position: absolute;
  top: 6px;
  right: 6px;
  opacity: 0;
  transition: opacity 0.15s;
  background: rgba(15, 23, 42, 0.7);
  color: #fff;
  border: none;
}
.cc-tile:hover .cc-tile-remove {
  opacity: 1;
}
.cc-pagination {
  display: flex;
  justify-content: flex-end;
  margin-top: 1rem;
}
.cc-delete-hint {
  margin: 0.5rem 0 0;
  color: #64748b;
  font-size: 0.85rem;
}
</style>