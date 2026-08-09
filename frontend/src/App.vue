<script setup lang="ts">
import { onMounted, ref } from "vue";
import { api } from "@/services/api";
import type { HealthStatus } from "@/types/api";

const health = ref<HealthStatus | null>(null);
const error = ref<string | null>(null);

onMounted(async () => {
  try {
    health.value = await api.health();
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err);
  }
});
</script>

<template>
  <main>
    <h1>ComfyChat 前端就绪</h1>
    <section>
      <h2>后端健康</h2>
      <p v-if="error">错误：{{ error }}</p>
      <pre v-else-if="health">{{ health }}</pre>
      <p v-else>正在加载…</p>
    </section>
  </main>
</template>

<style scoped>
main {
  font-family: system-ui, sans-serif;
  margin: 2rem auto;
  max-width: 640px;
  padding: 0 1rem;
}
pre {
  background: #f4f4f5;
  padding: 0.75rem;
  border-radius: 4px;
}
</style>