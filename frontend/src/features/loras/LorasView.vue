<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import { Refresh, Search } from "@element-plus/icons-vue";
import { api } from "@/services/api";
import { useNsfwFilter } from "@/composables/useNsfwFilter";
import type { LoraSummary } from "@/types/api";

const items = ref<LoraSummary[]>([]);
const loading = ref(false);
const error = ref<string | null>(null);
const search = ref("");
const familyFilter = ref("");
const boundFilter = ref("");
const deletedFilter = ref("");
const { enabled: nsfwEnabled } = useNsfwFilter();

const BINDING_GUIDE_URL = "/docs/lora-ai-binding-guide.md";
const guideNotice = ref(true);

// Inline trigger-word edit state, keyed by lora name.
const triggerEdit = reactive<Record<string, { draft: string; saving: boolean }>>({});
const editingName = ref<string | null>(null);

async function load() {
  loading.value = true;
  error.value = null;
  try {
    const data = await api.loras.list();
    items.value = data.items;
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err);
  } finally {
    loading.value = false;
  }
}

function fmtFamily(f: string | null): string {
  return f || "未知";
}

const familyOptions = computed(() => {
  const set = new Set<string>();
  for (const it of items.value) set.add(it.base_family || "未知");
  return [...set].sort();
});

const newUnboundLoras = computed(() =>
  items.value.filter((it) => !it.deleted_from_comfyui && it.models.length === 0),
);

const filteredItems = computed(() => {
  const q = search.value.trim().toLowerCase();
  return items.value.filter((it) => {
    if (q && !it.name.toLowerCase().includes(q)) return false;
    if (familyFilter.value && (it.base_family || "未知") !== familyFilter.value) return false;
    if (boundFilter.value === "bound" && it.models.length === 0) return false;
    if (boundFilter.value === "unbound" && it.models.length > 0) return false;
    if (deletedFilter.value === "deleted" && !it.deleted_from_comfyui) return false;
    if (deletedFilter.value === "active" && it.deleted_from_comfyui) return false;
    if (!nsfwEnabled.value && it.is_nsfw) return false;
    return true;
  });
});

async function toggleLoraNsfw(row: LoraSummary, targetValue?: boolean) {
  const newValue = targetValue ?? !row.is_nsfw;
  try {
    await api.loras.updateNsfw(row.name, newValue);
    row.is_nsfw = newValue;
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err);
  }
}

function startEditTrigger(row: LoraSummary) {
  editingName.value = row.name;
  triggerEdit[row.name] = { draft: row.trigger_words ?? "", saving: false };
}

function cancelEditTrigger(name: string) {
  delete triggerEdit[name];
  if (editingName.value === name) editingName.value = null;
}

async function commitEditTrigger(row: LoraSummary) {
  const state = triggerEdit[row.name];
  if (!state) return;
  const next = state.draft.trim();
  const current = (row.trigger_words ?? "").trim();
  if (next === current) {
    cancelEditTrigger(row.name);
    return;
  }
  state.saving = true;
  try {
    await api.loras.updateTrigger(row.name, next || null);
    row.trigger_words = next || null;
    cancelEditTrigger(row.name);
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err);
    state.saving = false;
  }
}

onMounted(load);
</script>

<template>
  <div>
    <div class="cc-toolbar">
      <h2>LoRA 管理</h2>
      <div class="cc-spacer" />
      <el-button :icon="Refresh" :loading="loading" @click="load">重新扫描</el-button>
    </div>

    <el-alert
      v-if="error"
      :title="`无法加载 LoRA：${error}`"
      type="error"
      :closable="false"
      show-icon
    />

    <el-alert
      v-if="newUnboundLoras.length > 0 && guideNotice"
      type="info"
      :closable="true"
      show-icon
      class="cc-guide-alert"
      @close="guideNotice = false"
    >
      <template #title>
        检测到 {{ newUnboundLoras.length }} 个 LoRA 尚未绑定主模型。
        可让 AI 帮你查询并绑定
        <a :href="BINDING_GUIDE_URL" target="_blank" rel="noopener" class="cc-guide-link">查看绑定指南</a>
      </template>
    </el-alert>

    <div class="cc-filters">
      <el-input
        v-model="search"
        placeholder="搜索名称…"
        :prefix-icon="Search"
        clearable
        style="width: 240px"
      />
      <el-select v-model="familyFilter" placeholder="全部架构族" clearable style="width: 160px">
        <el-option v-for="opt in familyOptions" :key="opt" :value="opt" :label="opt" />
      </el-select>
      <el-select v-model="boundFilter" placeholder="绑定状态" clearable style="width: 140px">
        <el-option value="bound" label="有绑定" />
        <el-option value="unbound" label="无绑定" />
      </el-select>
      <el-select v-model="deletedFilter" placeholder="全部状态" clearable style="width: 130px">
        <el-option value="active" label="正常" />
        <el-option value="deleted" label="已删除" />
      </el-select>
    </div>

    <el-table :data="filteredItems" v-loading="loading" stripe style="width: 100%">
      <el-table-column v-if="nsfwEnabled" label="NSFW" width="100">
        <template #default="{ row }">
          <el-switch
            :model-value="row.is_nsfw"
            @update:model-value="(val: boolean | string | number) => toggleLoraNsfw(row, Boolean(val))"
            inline-prompt
            active-text="是"
            inactive-text="否"
            style="--el-switch-width: 56px"
          />
        </template>
      </el-table-column>
      <el-table-column label="文件名" min-width="280">
        <template #default="{ row }">
          <span :class="['cc-name', { 'cc-deleted-name': row.deleted_from_comfyui }]">
            {{ row.name }}
          </span>
          <el-tag
            v-if="row.deleted_from_comfyui"
            size="small"
            type="info"
            class="cc-deleted-tag"
          >已删除</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="主模型" min-width="260">
        <template #default="{ row }">
          <template v-if="row.models.length">
            <el-tag v-for="m in row.models" :key="m" size="small" class="cc-model-tag">
              {{ m }}
            </el-tag>
          </template>
          <span v-else class="cc-muted">—</span>
        </template>
      </el-table-column>
      <el-table-column label="架构族" width="130">
        <template #default="{ row }">{{ fmtFamily(row.base_family) }}</template>
      </el-table-column>
      <el-table-column label="来源" min-width="220">
        <template #default="{ row }">
          <a
            v-if="row.source_url"
            :href="row.source_url"
            target="_blank"
            rel="noopener"
            class="cc-url"
          >{{ row.source_url }}</a>
          <span v-else class="cc-muted">—</span>
        </template>
      </el-table-column>
      <el-table-column label="触发词" min-width="200">
        <template #default="{ row }">
          <template v-if="editingName === row.name">
            <el-input
              v-model="triggerEdit[row.name].draft"
              size="small"
              :loading="triggerEdit[row.name]?.saving"
              placeholder="触发词,空格分隔多个"
              class="cc-trigger-input"
              @blur="commitEditTrigger(row)"
              @keyup.enter="(e: Event) => (e.target as HTMLInputElement).blur()"
              @keyup.escape="cancelEditTrigger(row.name)"
            />
          </template>
          <span
            v-else
            class="cc-trigger-cell"
            :title="row.trigger_words ? '双击编辑' : '双击添加触发词'"
            @dblclick="startEditTrigger(row)"
          >
            {{ row.trigger_words || "—" }}
          </span>
        </template>
      </el-table-column>
      <template #empty>
        <el-empty description="暂无 LoRA" />
      </template>
    </el-table>
  </div>
</template>

<style lang="scss" scoped>
.cc-toolbar {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  margin-bottom: 0.75rem;
}
.cc-filters {
  display: flex;
  gap: 0.75rem;
  margin-bottom: 0.75rem;
  align-items: center;
}
.cc-spacer {
  flex: 1;
}
.cc-name {
  font-weight: 500;
}
.cc-muted {
  color: #cbd5e1;
}
.cc-model-tag {
  margin: 2px 6px 2px 0;
}
.cc-url {
  color: #0ea5e9;
  text-decoration: none;
  word-break: break-all;
}
.cc-url:hover {
  text-decoration: underline;
}
.cc-guide-alert {
  margin-bottom: 0.75rem;
}
.cc-guide-link {
  color: #0ea5e9;
  font-weight: 500;
  text-decoration: none;
}
.cc-guide-link:hover {
  text-decoration: underline;
}
.cc-deleted-name {
  color: #94a3b8;
  text-decoration: line-through;
}
.cc-deleted-tag {
  margin-left: 6px;
}
.cc-trigger-cell {
  cursor: text;
  display: inline-block;
  padding: 2px 6px;
  border-radius: 4px;
  border: 1px dashed transparent;
  max-width: 100%;
  word-break: break-word;
}
.cc-trigger-cell:hover {
  border-color: #cbd5e1;
  background-color: rgba(14, 165, 233, 0.04);
}
.cc-muted.cc-trigger-cell:hover {
  background-color: rgba(203, 213, 225, 0.08);
}
.cc-trigger-input {
  width: 100%;
}
</style>
