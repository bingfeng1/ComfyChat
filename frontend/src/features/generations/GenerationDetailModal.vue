<script setup lang="ts">
import { ref, watch } from "vue";
import Modal from "@/components/Modal.vue";
import { api } from "@/services/api";
import type { GenerationSummary } from "@/types/api";

const props = defineProps<{ generationId: string; title: string }>();
const emit = defineEmits<{ close: [] }>();

const gen = ref<GenerationSummary | null>(null);
const loadError = ref<string | null>(null);

watch(
  () => props.generationId,
  async (id) => {
    if (!id) return;
    loadError.value = null;
    try {
      gen.value = await api.generations.get(id);
    } catch (err) {
      loadError.value = err instanceof Error ? err.message : String(err);
    }
  },
  { immediate: true }
);
</script>

<template>
  <Modal :title="props.title" @close="emit('close')">
    <div v-if="gen" class="cc-detail">
      <el-image
        v-for="out in gen.outputs"
        :key="out"
        :src="api.generations.imageUrl(gen.id, out)"
        class="cc-preview"
        fit="contain"
        alt=""
      />
      <p v-if="gen.outputs.length === 0" class="cc-hint">无输出图片</p>
      <dl class="cc-meta">
        <dt>状态</dt><dd>{{ gen.status }}</dd>
        <dt>工作流</dt><dd>{{ gen.workflow_name }}</dd>
        <dt>时间</dt><dd>{{ new Date(gen.created_at).toLocaleString() }}</dd>
        <template v-if="gen.error">
          <dt>错误</dt><dd class="cc-err">{{ gen.error }}</dd>
        </template>
      </dl>
      <h4>参数</h4>
      <pre class="cc-json">{{ JSON.stringify(gen.parameters, null, 2) }}</pre>
    </div>
    <p v-else-if="loadError" class="cc-err">{{ loadError }}</p>
    <p v-else>加载中…</p>
  </Modal>
</template>

<style lang="scss" scoped>
.cc-detail {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}
:deep(.cc-preview) {
  max-width: 100%;
  max-height: 55vh;
  object-fit: contain;
  border-radius: 6px;
}
.cc-hint {
  color: #64748b;
}
.cc-meta {
  display: grid;
  grid-template-columns: 4rem 1fr;
  gap: 0.25rem 0.5rem;
  font-size: 0.85rem;
}
.cc-meta dt {
  color: #64748b;
}
.cc-err {
  color: #ef4444;
}
.cc-json {
  max-height: 30vh;
  overflow: auto;
  background: #0f172a;
  color: #a5b4fc;
  padding: 0.75rem;
  border-radius: 6px;
  font-size: 0.8rem;
}
</style>
