<script setup lang="ts">
defineProps<{
  title: string;
}>();
const emit = defineEmits<{ close: [] }>();
</script>

<template>
  <div class="overlay" @click.self="emit('close')">
    <div class="modal">
      <div class="head">
        <h3>{{ title }}</h3>
        <button class="x" @click="emit('close')">✕</button>
      </div>
      <div class="body">
        <slot />
      </div>
    </div>
  </div>
</template>

<style scoped>
.overlay {
  position: fixed;
  inset: 0;
  background: rgba(15, 23, 42, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 50;
}
.modal {
  background: #fff;
  border-radius: 8px;
  width: min(680px, 92vw);
  max-height: 85vh;
  display: flex;
  flex-direction: column;
}
.head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0.75rem 1rem;
  border-bottom: 1px solid #e2e8f0;
}
.head h3 { margin: 0; }
.x {
  border: none;
  background: transparent;
  font-size: 1rem;
  cursor: pointer;
}
.body {
  padding: 1rem;
  overflow-y: auto;
}
</style>
