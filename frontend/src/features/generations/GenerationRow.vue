<script setup lang="ts">
import { computed } from "vue";
import { api } from "@/services/api";
import type { GenerationSummary } from "@/types/api";

const props = defineProps<{ generation: GenerationSummary }>();
const emit = defineEmits<{ view: []; regenerate: []; delete: [] }>();

const statusLabel: Record<string, string> = {
  queued: "排队中",
  running: "执行中",
  success: "成功",
  failed: "失败",
};

const promptText = computed(() => {
  const p = props.generation.parameters["positive_prompt"];
  return typeof p === "string" ? p : "";
});

const thumb = computed(() => {
  const first = props.generation.outputs[0];
  return first ? api.generations.imageUrl(props.generation.id, first) : null;
});

function fmtTime(iso: string) {
  return new Date(iso).toLocaleString();
}
</script>

<template>
  <tr>
    <td>
      <img v-if="thumb" :src="thumb" class="thumb" alt="" />
      <div v-else class="thumb placeholder" />
    </td>
    <td class="prompt">{{ promptText || "—" }}</td>
    <td>{{ props.generation.workflow_name }}</td>
    <td>
      <span class="badge" :class="props.generation.status">
        {{ statusLabel[props.generation.status] ?? props.generation.status }}
      </span>
    </td>
    <td>{{ fmtTime(props.generation.created_at) }}</td>
    <td class="actions">
      <button class="link" @click="emit('view')">查看</button>
      <button class="link" @click="emit('regenerate')">再生成</button>
      <button class="link danger" @click="emit('delete')">×</button>
    </td>
  </tr>
</template>

<style scoped>
.thumb { width: 40px; height: 40px; object-fit: cover; border-radius: 4px; }
.placeholder { width: 40px; height: 40px; background: #e2e8f0; border-radius: 4px; }
.prompt { max-width: 280px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.badge { padding: 1px 6px; border-radius: 8px; font-size: 0.8rem; }
.badge.success { background: #e8f5e9; color: #2e7d32; }
.badge.running, .badge.queued { background: #fff3e0; color: #e65100; }
.badge.failed { background: #ffebee; color: #c62828; }
.actions { display: flex; gap: 0.5rem; }
.link { border: none; background: none; color: #0ea5e9; cursor: pointer; padding: 0 0.25rem; }
.link.danger { color: #ef4444; }
</style>
