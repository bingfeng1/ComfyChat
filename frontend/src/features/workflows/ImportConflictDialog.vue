<script setup lang="ts">
import { ref } from "vue";
import Modal from "@/components/Modal.vue";

const props = defineProps<{ filename: string }>();
const emit = defineEmits<{
  overwrite: [];
  cancel: [];
  rename: [name: string];
}>();

const showRenameInput = ref(false);
const renameValue = ref("");

function confirmRename() {
  const name = renameValue.value.trim();
  if (name) {
    emit("rename", name);
    renameValue.value = "";
    showRenameInput.value = false;
  }
}
</script>

<template>
  <Modal :title="`文件重名：${props.filename}`" @close="emit('cancel')">
    <p>已存在同名工作流。请选择如何处理：</p>

    <div v-if="showRenameInput" class="rename-box">
      <input v-model="renameValue" placeholder="新文件名" @keyup.enter="confirmRename" />
      <button class="btn" @click="confirmRename">确定</button>
      <button class="btn" @click="showRenameInput = false">取消</button>
    </div>

    <div class="actions">
      <button class="btn" @click="showRenameInput = true">重命名</button>
      <button class="btn danger" @click="emit('overwrite')">覆盖</button>
      <button class="btn" @click="emit('cancel')">取消</button>
    </div>
  </Modal>
</template>

<style scoped>
.rename-box {
  display: flex;
  gap: 0.5rem;
  margin: 0.75rem 0;
}
.rename-box input {
  flex: 1;
  padding: 0.4rem;
  border: 1px solid #cbd5e1;
  border-radius: 6px;
}
.actions {
  display: flex;
  gap: 0.75rem;
  justify-content: flex-end;
}
.btn {
  padding: 0.4rem 0.9rem;
  border: 1px solid #cbd5e1;
  border-radius: 6px;
  background: #fff;
  cursor: pointer;
}
.btn.danger {
  background: #ef4444;
  border-color: #ef4444;
  color: #fff;
}
</style>
