<script setup lang="ts">
import type { GenerationSummary } from "@/types/api";

defineProps<{ preset?: GenerationSummary | null }>();
defineEmits<{ close: [] }>();
</script>

<template>
  <div class="stub" />
</template>
