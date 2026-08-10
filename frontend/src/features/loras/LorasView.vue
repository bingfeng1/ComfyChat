<script setup lang="ts">
import { onMounted, ref } from "vue";
import { Refresh } from "@element-plus/icons-vue";
import { api } from "@/services/api";
import type { LoraSummary } from "@/types/api";

const items = ref<LoraSummary[]>([]);
const loading = ref(false);
const error = ref<string | null>(null);

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

    <el-table :data="items" v-loading="loading" stripe style="width: 100%">
      <el-table-column label="文件名" min-width="280">
        <template #default="{ row }">
          <span class="cc-name">{{ row.name }}</span>
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
</style>
