<script setup lang="ts">
import Modal from "@/components/Modal.vue";

const props = defineProps<{ filename: string }>();
const emit = defineEmits<{
  overwrite: [];
  cancel: [];
  "rename-click": [];
}>();
</script>

<template>
  <Modal :title="`文件重名：${props.filename}`" @close="emit('cancel')">
    <p>已存在同名工作流。请选择如何处理：</p>
    <div class="actions">
      <button class="btn" @click="emit('rename-click')">重命名</button>
      <button class="btn danger" @click="emit('overwrite')">覆盖</button>
      <button class="btn" @click="emit('cancel')">取消</button>
    </div>
  </Modal>
</template>

<style scoped>
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
