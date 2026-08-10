<script setup lang="ts">
import { Refresh } from "@element-plus/icons-vue";

const props = defineProps<{
  syncing: boolean;
}>();
const emit = defineEmits<{ sync: [] }>();
</script>

<template>
  <el-button
    :loading="props.syncing"
    type="primary"
    :icon="Refresh"
    @click="emit('sync')"
  >
    {{ props.syncing ? "同步中…" : "同步" }}
  </el-button>
</template>