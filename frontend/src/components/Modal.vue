<script setup lang="ts">
import { ref } from "vue";

const props = defineProps<{ title: string }>();
const emit = defineEmits<{ close: [] }>();

const show = ref(true);

function requestClose() {
  show.value = false;
  emit("close");
}
</script>

<template>
  <el-dialog
    v-model="show"
    :title="props.title"
    width="680px"
    :close-on-click-modal="true"
    :close-on-press-escape="true"
    @close="requestClose"
  >
    <slot />
    <template v-if="$slots.footer" #footer>
      <slot name="footer" />
    </template>
  </el-dialog>
</template>

<style lang="scss" scoped>
@use "@/styles/variables" as *;
</style>
