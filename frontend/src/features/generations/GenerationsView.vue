<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { CircleClose, Plus } from "@element-plus/icons-vue";
import Modal from "@/components/Modal.vue";
import GenerationCreateModal from "./GenerationCreateModal.vue";
import GenerationDetailModal from "./GenerationDetailModal.vue";
import { useGenerations } from "./useGenerations";
import { useWorkspaces } from "@/features/workspaces/useWorkspaces";
import { api } from "@/services/api";
import type { GenerationSummary } from "@/types/api";
import { mediaTypeOf, type MediaType } from "./mediaType";

const {
  items,
  loading,
  error,
  statusFilter,
  workflowFilter,
  workspaceFilter,
  workflows,
  page,
  pageSize,
  total,
  refresh,
  remove,
  setWorkspaces,
  removeWorkspace,
  setPage,
  setPageSize,
} = useGenerations();

const { items: workspaces, nameOf, refresh: refreshWorkspaces } = useWorkspaces();

const showCreate = ref(false);
const detail = ref<GenerationSummary | null>(null);
const regenerate = ref<GenerationSummary | null>(null);
const confirmDelete = ref<GenerationSummary | null>(null);
const expandedPrompts = ref<Set<string>>(new Set());

type MediaFilter = "" | "image" | "video";
const mediaFilter = ref<MediaFilter>("");

const workspaceEditFor = ref<GenerationSummary | null>(null);
const workspaceEditDraft = ref<string[]>([]);
const workspaceEditSaving = ref(false);

const showCreateWs = ref(false);
const createWsName = ref("");
const createWsError = ref<string | null>(null);
const createWsSubmitting = ref(false);

const showCreateWsForGen = ref<GenerationSummary | null>(null);

async function doDelete() {
  if (!confirmDelete.value) return;
  await remove(confirmDelete.value.id);
  confirmDelete.value = null;
}

function togglePrompt(id: string) {
  const next = new Set(expandedPrompts.value);
  if (next.has(id)) {
    next.delete(id);
  } else {
    next.add(id);
  }
  expandedPrompts.value = next;
}

function onCreateClosed() {
  showCreate.value = false;
  page.value = 1;
  refresh();
}

function onRegenerateClosed() {
  regenerate.value = null;
  page.value = 1;
  refresh();
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

interface MediaItem {
  url: string;
  mediaType: MediaType;
  genId: string;
}

function thumbInfo(g: GenerationSummary): MediaItem | null {
  const first = g.outputs[0];
  if (!first) return null;
  return {
    url: api.generations.imageUrl(g.id, first),
    mediaType: mediaTypeOf(first),
    genId: g.id,
  };
}

function allMediaItems(): MediaItem[] {
  return items.value
    .map((g) => thumbInfo(g))
    .filter((m): m is MediaItem => m !== null);
}

function imagePreviewList(): string[] {
  return allMediaItems()
    .filter((m) => m.mediaType === "image")
    .map((m) => m.url);
}

function promptText(g: GenerationSummary): string {
  const params = g.parameters;
  for (const key of ["text", "prompt", "positive_prompt"]) {
    const v = params[key];
    if (typeof v === "string" && v.length > 0) return v;
  }
  for (const v of Object.values(params)) {
    if (typeof v === "string" && v.length > 0) return v;
  }
  return "";
}

function mediaTypeOfGen(g: GenerationSummary): MediaType | null {
  if (!g.outputs.length) return null;
  return mediaTypeOf(g.outputs[0]);
}

async function detachWorkspace(g: GenerationSummary, wsId: string) {
  await removeWorkspace(g.id, wsId);
}

function openWorkspaceEdit(g: GenerationSummary) {
  workspaceEditFor.value = g;
  workspaceEditDraft.value = [...g.workspace_ids];
  workspaceEditSaving.value = false;
}

function cancelWorkspaceEdit() {
  workspaceEditFor.value = null;
}

async function submitWorkspaceEdit() {
  if (!workspaceEditFor.value) return;
  workspaceEditSaving.value = true;
  try {
    await setWorkspaces(
      workspaceEditFor.value.id,
      workspaceEditDraft.value,
    );
    workspaceEditFor.value = null;
  } finally {
    workspaceEditSaving.value = false;
  }
}

function openCreateWorkspace() {
  showCreateWs.value = true;
  createWsName.value = "";
  createWsError.value = null;
  createWsSubmitting.value = false;
}

async function submitCreateWorkspace() {
  const name = createWsName.value.trim();
  if (!name) {
    createWsError.value = "名称不能为空";
    return;
  }
  createWsSubmitting.value = true;
  createWsError.value = null;
  try {
    await api.workspaces.create(name);
    await refreshWorkspaces();
    showCreateWs.value = false;
  } catch (err) {
    createWsError.value = err instanceof Error ? err.message : String(err);
  } finally {
    createWsSubmitting.value = false;
  }
}

async function assignWorkspaceFromChip(g: GenerationSummary, wsId: string) {
  const next = Array.from(new Set([...g.workspace_ids, wsId]));
  await setWorkspaces(g.id, next);
}

const addableWorkspaces = computed(() => {
  const gen = showCreateWsForGen.value;
  if (!gen) return workspaces.value;
  return workspaces.value.filter((w) => !gen.workspace_ids.includes(w.id));
});

function pickWorkspaceForGen(wsId: string) {
  const gen = showCreateWsForGen.value;
  if (!gen) return;
  assignWorkspaceFromChip(gen, wsId).then(() => {
    if (showCreateWsForGen.value?.id === gen.id) showCreateWsForGen.value = null;
  });
}

watch(workspaceFilter, () => {
  // 工作区选择改变时刷新可选列表(若工作区列表尚未加载)
  refreshWorkspaces();
});

// 客户端媒体类型过滤:基于 outputs[0] 扩展名。当前页面内即时切换,
// total 仍为服务端分页总数(过滤不影响服务端 query)。
const filteredItems = computed(() => {
  if (!mediaFilter.value) return items.value;
  return items.value.filter((g) => mediaTypeOfGen(g) === mediaFilter.value);
});
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
      <el-space wrap>
        <el-select v-model="workflowFilter" placeholder="全部工作流" clearable style="width: 180px">
          <el-option value="" label="全部工作流" />
          <el-option
            v-for="w in workflows"
            :key="w.id"
            :value="w.id"
            :label="w.name"
          />
        </el-select>
        <el-select v-model="workspaceFilter" placeholder="全部工作区" clearable style="width: 180px">
          <el-option value="" label="全部工作区" />
          <el-option
            v-for="w in workspaces"
            :key="w.id"
            :value="w.id"
            :label="w.name"
          />
        </el-select>
        <el-select v-model="mediaFilter" placeholder="全部类型" clearable style="width: 140px">
          <el-option value="" label="全部类型" />
          <el-option value="image" label="图片" />
          <el-option value="video" label="视频" />
        </el-select>
        <el-select v-model="statusFilter" placeholder="全部状态" clearable style="width: 140px">
          <el-option value="" label="全部状态" />
          <el-option value="queued" label="排队中" />
          <el-option value="running" label="执行中" />
          <el-option value="success" label="成功" />
          <el-option value="failed" label="失败" />
        </el-select>
      </el-space>
    </div>

    <el-table :data="filteredItems" v-loading="loading" stripe style="width: 100%">
      <el-table-column label="图" width="100">
        <template #default="{ row }">
          <template v-if="thumbInfo(row)">
            <video
              v-if="thumbInfo(row)!.mediaType === 'video'"
              :src="thumbInfo(row)!.url"
              muted
              autoplay
              loop
              playsinline
              class="cc-thumb cc-thumb-video"
              @click.stop="detail = row"
            />
            <el-image
              v-else
              :src="thumbInfo(row)!.url"
              fit="cover"
              class="cc-thumb"
              :preview-src-list="imagePreviewList()"
              preview-teleported
              show-progress
            />
          </template>
          <div v-else class="cc-thumb-placeholder" />
        </template>
      </el-table-column>
      <el-table-column label="提示词" min-width="240" :show-overflow-tooltip="false">
        <template #default="{ row }">
          <div :class="['cc-prompt', { 'is-expanded': expandedPrompts.has(row.id) }]">
            {{ promptText(row) || "—" }}
          </div>
          <el-button
            v-if="promptText(row).length > 60 || promptText(row).includes('\n')"
            link
            type="primary"
            size="small"
            class="cc-prompt-toggle"
            @click="togglePrompt(row.id)"
          >
            {{ expandedPrompts.has(row.id) ? "收起" : "展开全文" }}
          </el-button>
        </template>
      </el-table-column>
      <el-table-column label="工作流" min-width="140">
        <template #default="{ row }">{{ row.workflow_name }}</template>
      </el-table-column>
      <el-table-column label="类型" width="80">
        <template #default="{ row }">
          <el-tag v-if="mediaTypeOfGen(row)" size="small" type="info">
            {{ mediaTypeOfGen(row) === "video" ? "视频" : "图片" }}
          </el-tag>
          <span v-else>—</span>
        </template>
      </el-table-column>
      <el-table-column label="工作区" min-width="200">
        <template #default="{ row }">
          <div class="cc-ws-cell">
            <el-tag
              v-for="wsId in row.workspace_ids"
              :key="wsId"
              size="small"
              closable
              @close="detachWorkspace(row, wsId)"
            >
              {{ nameOf(wsId) }}
            </el-tag>
            <el-popover
              v-model:visible="showCreateWsForGen === row"
              placement="bottom-start"
              :width="240"
              trigger="click"
            >
              <template #reference>
                <el-button
                  link
                  type="primary"
                  size="small"
                  @click="showCreateWsForGen = row"
                >
                  <el-icon><Plus /></el-icon>
                  工作区
                </el-button>
              </template>
              <div v-if="addableWorkspaces.length === 0" class="cc-pop-empty">
                没有可加入的工作区,
                <el-button link type="primary" size="small" @click="openCreateWorkspace">新建一个</el-button>
              </div>
              <el-menu v-else class="cc-pop-menu">
                <el-menu-item
                  v-for="ws in addableWorkspaces"
                  :key="ws.id"
                  @click="pickWorkspaceForGen(ws.id)"
                >
                  {{ ws.name }}
                </el-menu-item>
              </el-menu>
            </el-popover>
          </div>
        </template>
      </el-table-column>
      <el-table-column label="状态" width="100">
        <template #default="{ row }">
          <el-tag :type="statusType(row.status)" size="small">
            {{ statusLabel[row.status] ?? row.status }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="时间" width="170">
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

    <div class="cc-pagination">
      <el-pagination
        :current-page="page"
        :page-size="pageSize"
        :total="total"
        :page-sizes="[10, 15, 20, 50]"
        layout="total, sizes, prev, pager, next"
        background
        @current-change="setPage"
        @size-change="setPageSize"
      />
    </div>

    <GenerationCreateModal v-if="showCreate" @close="onCreateClosed" />
    <GenerationCreateModal v-if="regenerate" :preset="regenerate" @close="onRegenerateClosed" />
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

    <Modal v-if="showCreateWs" title="新建工作区" width="420px" @close="showCreateWs = false">
      <el-input
        v-model="createWsName"
        placeholder="工作区名称"
        maxlength="255"
        show-word-limit
        @keyup.enter="submitCreateWorkspace"
      />
      <el-alert
        v-if="createWsError"
        :title="createWsError"
        type="error"
        :closable="false"
        show-icon
        style="margin-top: 0.5rem"
      />
      <template #footer>
        <el-button @click="showCreateWs = false">取消</el-button>
        <el-button type="primary" :loading="createWsSubmitting" @click="submitCreateWorkspace">
          创建
        </el-button>
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
.cc-thumb {
  width: 72px;
  height: 72px;
  border-radius: 6px;
  display: block;
  cursor: pointer;
}
.cc-thumb-video {
  background: #000;
  cursor: pointer;
}
.cc-prompt {
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
  white-space: pre-wrap;
  word-break: break-word;
  max-width: 100%;
  line-height: 1.5;
}
.cc-prompt.is-expanded {
  display: block;
  overflow: visible;
  -webkit-line-clamp: unset;
}
.cc-prompt-toggle {
  padding: 0;
  margin-top: 2px;
}
.cc-pagination {
  display: flex;
  justify-content: flex-end;
  margin-top: 1rem;
}
.cc-ws-cell {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  align-items: center;
}
.cc-pop-menu {
  border-right: none;
}
.cc-pop-empty {
  padding: 0.5rem;
  color: #64748b;
  font-size: 0.85rem;
}
</style>
