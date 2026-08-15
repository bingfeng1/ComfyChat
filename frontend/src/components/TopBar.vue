<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { storeToRefs } from "pinia";
import { Refresh } from "@element-plus/icons-vue";
import { api } from "@/services/api";
import { useNsfwStore } from "@/stores/nsfw";
import type { HealthStatus } from "@/types/api";

const nsfwStore = useNsfwStore();
const { enabled: nsfwEnabled } = storeToRefs(nsfwStore);
const setNsfwEnabled = nsfwStore.setEnabled;

const health = ref<HealthStatus | null>(null);
const error = ref<string | null>(null);

async function check() {
  try {
    health.value = await api.health();
    error.value = null;
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err);
  }
}

const tagType = computed<"success" | "danger" | "info">(() => {
  if (error.value) return "danger";
  if (!health.value) return "info";
  return health.value.status === "ok" ? "success" : "danger";
});

const tagText = computed(() => {
  if (error.value) return "后端不可达";
  if (!health.value) return "检查中…";
  return health.value.status === "ok" ? "运行正常" : "异常";
});

onMounted(check);
</script>

<template>
  <el-header class="cc-topbar">
    <h1 class="cc-title">ComfyChat</h1>
    <div class="cc-spacer" />
    <div class="cc-nsfw-toggle">
      <span class="cc-nsfw-label">NSFW</span>
      <el-switch
        :model-value="nsfwEnabled"
        @update:model-value="setNsfwEnabled"
        inline-prompt
        active-text="显示"
        inactive-text="隐藏"
        style="--el-switch-width: 56px"
      />
    </div>
    <div class="cc-health">
      <el-tag :type="tagType" size="small">{{ tagText }}</el-tag>
      <span v-if="health" class="cc-sub">{{ health.comfyui }}</span>
      <el-button
        :icon="Refresh"
        circle
        size="small"
        title="重新检查"
        @click="check"
      />
    </div>
  </el-header>
</template>

<style lang="scss" scoped>
@use "@/styles/variables" as *;

.cc-topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: $cc-topbar-height;
  padding: 0 $cc-content-padding;
  background: #fff;
  box-shadow: $cc-topbar-shadow;
}
.cc-title {
  font-size: 1rem;
  margin: 0;
  color: #334155;
}
.cc-spacer {
  flex: 1;
}
.cc-nsfw-toggle {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-right: 1rem;
}
.cc-nsfw-label {
  font-size: 0.85rem;
  color: #475569;
  font-weight: 500;
}
.cc-health {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.85rem;
  color: #64748b;
}
.cc-sub {
  color: #94a3b8;
}
</style>
