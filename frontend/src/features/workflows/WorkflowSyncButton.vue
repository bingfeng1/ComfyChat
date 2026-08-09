<script setup lang="ts">
const props = defineProps<{
  syncing: boolean;
}>();
const emit = defineEmits<{ sync: [] }>();
</script>

<template>
  <button class="btn" :disabled="props.syncing" @click="emit('sync')">
    {{ props.syncing ? "同步中…" : "同步" }}
  </button>
</template>

<style scoped>
.btn {
  padding: 0.4rem 0.9rem;
  border: 1px solid #cbd5e1;
  border-radius: 6px;
  background: #fff;
  cursor: pointer;
}
</style>
