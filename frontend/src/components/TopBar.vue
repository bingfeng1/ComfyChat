<script setup lang="ts">
import { onMounted, ref } from "vue";
import { api } from "@/services/api";
import type { HealthStatus } from "@/types/api";

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

onMounted(check);
</script>

<template>
  <header class="topbar">
    <h1>ComfyChat</h1>
    <div class="health">
      <template v-if="error">
        <span class="dot error"></span>
        <span>后端不可达</span>
      </template>
      <template v-else-if="health">
        <span class="dot" :class="health.status === 'ok' ? 'ok' : 'error'"></span>
        <span>{{ health.status === "ok" ? "运行正常" : "异常" }}</span>
        <span class="sub">{{ health.comfyui }}</span>
      </template>
      <template v-else>
        <span class="dot loading"></span>
        <span>检查中…</span>
      </template>
      <button class="refresh" title="重新检查" @click="check">↻</button>
    </div>
  </header>
</template>

<style scoped>
.topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0.75rem 1.5rem;
  border-bottom: 1px solid #e2e8f0;
}
.topbar h1 {
  font-size: 1rem;
  margin: 0;
  color: #334155;
}
.health {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.85rem;
  color: #64748b;
}
.dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  display: inline-block;
}
.dot.ok { background: #22c55e; }
.dot.error { background: #ef4444; }
.dot.loading { background: #94a3b8; }
.sub { color: #94a3b8; }
.refresh {
  border: none;
  background: transparent;
  cursor: pointer;
  font-size: 1rem;
}
</style>
