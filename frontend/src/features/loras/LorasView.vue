<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
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
const nsfwFilter = ref("");

const BINDING_GUIDE_URL = "/docs/lora-ai-binding-guide.md";
const guideNotice = ref(true);

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
    if (nsfwFilter.value === "nsfw" && !it.is_nsfw) return false;
    if (nsfwFilter.value === "safe" && it.is_nsfw) return false;
    return true;
  });
});

async function toggleLoraNsfw(row: LoraSummary) {
  try {
    await api.loras.updateNsfw(row.name, !row.is_nsfw);
    row.is_nsfw = !row.is_nsfw;
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err);
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
      <el-select v-model="nsfwFilter" placeholder="NSFW 状态" clearable style="width: 130px">
        <el-option value="nsfw" label="NSFW" />
        <el-option value="safe" label="安全" />
      </el-select>
    </div>

    <el-table :data="filteredItems" v-loading="loading" stripe style="width: 100%">
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
      <el-table-column label="NSFW" width="100">
        <template #default="{ row }">
          <el-tag
            :type="row.is_nsfw ? 'danger' : 'success'"
            size="small"
            style="cursor: pointer"
            @click="toggleLoraNsfw(row)"
          >
            {{ row.is_nsfw ? "NSFW" : "安全" }}
          </el-tag>
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
</style>
