<script setup lang="ts">
import { ref } from "vue";
import ImportConflictDialog from "./ImportConflictDialog.vue";

const props = defineProps<{
  importing: boolean;
  conflict: { filename: string } | null;
}>();

const emit = defineEmits<{
  chosen: [file: File];
  "conflict-resolve": [action: "rename" | "overwrite" | "cancel", name?: string];
}>();

const input = ref<HTMLInputElement | null>(null);

function onInput(e: Event) {
  const el = e.target as HTMLInputElement;
  const file = el.files?.[0];
  if (file) {
    emit("chosen", file);
  }
  el.value = "";
}
</script>

<template>
  <div>
    <el-button type="primary" :loading="importing" :disabled="importing" @click="input?.click()">
      {{ importing ? "上传中…" : "导入" }}
    </el-button>
    <input
      ref="input"
      type="file"
      accept=".json,application/json"
      style="display: none"
      @change="onInput"
    />

    <ImportConflictDialog
      v-if="props.conflict"
      :filename="props.conflict.filename"
      @overwrite="emit('conflict-resolve', 'overwrite')"
      @cancel="emit('conflict-resolve', 'cancel')"
      @rename="(name) => emit('conflict-resolve', 'rename', name)"
    />
  </div>
</template>