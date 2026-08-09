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
const renameValue = ref("");
const showRename = ref(false);

function onInput(e: Event) {
  const el = e.target as HTMLInputElement;
  const file = el.files?.[0];
  if (file) {
    emit("chosen", file);
  }
  el.value = "";
}

function resolve(action: "overwrite" | "cancel") {
  showRename.value = false;
  emit("conflict-resolve", action);
}

function confirmRename() {
  const name = renameValue.value.trim();
  if (name) {
    emit("conflict-resolve", "rename", name);
    showRename.value = false;
  }
}
</script>

<template>
  <div>
    <button class="btn primary" :disabled="importing" @click="input?.click()">
      {{ importing ? "上传中…" : "导入" }}
    </button>
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
      @overwrite="resolve('overwrite')"
      @cancel="resolve('cancel')"
      @rename-click="showRename = true"
    />

    <div v-if="showRename" class="rename-box">
      <input v-model="renameValue" placeholder="新文件名" />
      <button class="btn" @click="confirmRename">确定</button>
      <button class="btn" @click="showRename = false">取消</button>
    </div>
  </div>
</template>

<style scoped>
.btn {
  padding: 0.4rem 0.9rem;
  border: 1px solid #cbd5e1;
  border-radius: 6px;
  background: #fff;
  cursor: pointer;
}
.btn.primary {
  background: #0ea5e9;
  border-color: #0ea5e9;
  color: #fff;
}
.rename-box {
  margin-top: 0.5rem;
  display: flex;
  gap: 0.5rem;
}
.rename-box input {
  flex: 1;
  padding: 0.4rem;
  border: 1px solid #cbd5e1;
  border-radius: 6px;
}
</style>
