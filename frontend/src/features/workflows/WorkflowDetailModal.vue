<script setup lang="ts">
import { ref, watch } from "vue";
import Modal from "@/components/Modal.vue";

const props = defineProps<{
  workflowId: string;
  title: string;
}>();

const emit = defineEmits<{ close: [] }>();

const json = ref<unknown>(null);
const loadError = ref<string | null>(null);

watch(
  () => props.workflowId,
  async (id) => {
    if (!id) return;
    loadError.value = null;
    try {
      json.value = await (await import("@/services/api")).api.workflows.getBody(id);
    } catch (err) {
      loadError.value = err instanceof Error ? err.message : String(err);
    }
  },
  { immediate: true }
);
</script>

<template>
  <Modal :title="props.title" @close="emit('close')">
    <pre v-if="json" class="json">{{ JSON.stringify(json, null, 2) }}</pre>
    <p v-else-if="loadError" class="err">加载失败：{{ loadError }}</p>
    <p v-else>加载中…</p>
  </Modal>
</template>

<style scoped>
.json {
  max-height: 60vh;
  overflow: auto;
  background: #0f172a;
  color: #a5b4fc;
  padding: 1rem;
  border-radius: 6px;
  font-size: 0.8rem;
}
.err { color: #ef4444; }
</style>
