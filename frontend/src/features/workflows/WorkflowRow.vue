<script setup lang="ts">
import type { WorkflowSummary } from "@/types/api";

const props = defineProps<{
  workflow: WorkflowSummary;
}>();

const emit = defineEmits<{
  view: [];
  export: [];
  delete: [];
  history: [];
}>();

function fmtSize(bytes: number) {
  if (bytes < 1024) return `${bytes}B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)}KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)}MB`;
}

function fmtTime(iso: string) {
  const d = new Date(iso);
  return d.toLocaleString();
}

const sourceLabel: Record<string, string> = {
  browse: "ComfyUI",
  import: "导入",
};
</script>

<template>
  <tr>
    <td class="name">{{ props.workflow.name }}.json</td>
    <td>{{ sourceLabel[props.workflow.source] ?? props.workflow.source }}</td>
    <td>{{ fmtSize(props.workflow.size_bytes) }}</td>
    <td>{{ fmtTime(props.workflow.updated_at) }}</td>
    <td class="actions">
      <button
        v-if="props.workflow.source === 'browse' && props.workflow.has_history"
        class="link"
        @click="emit('history')"
      >历史</button>
      <button class="link" @click="emit('view')">看</button>
      <button class="link" @click="emit('export')">↓</button>
      <button class="link danger" @click="emit('delete')">×</button>
    </td>
  </tr>
</template>

<style scoped>
.name { font-weight: 500; }
.actions { display: flex; gap: 0.5rem; }
.link {
  border: none;
  background: none;
  color: #0ea5e9;
  cursor: pointer;
  padding: 0 0.25rem;
}
.link.danger { color: #ef4444; }
</style>
