<script setup lang="ts">
import { ref } from "vue";

const props = defineProps<{ filename: string }>();
const emit = defineEmits<{
  overwrite: [];
  cancel: [];
  rename: [name: string];
}>();

const show = ref(true);
const showRenameInput = ref(false);
const renameValue = ref("");

function emitCancel() {
  show.value = false;
  emit("cancel");
}

function emitOverwrite() {
  show.value = false;
  emit("overwrite");
}

function confirmRename() {
  const name = renameValue.value.trim();
  if (name) {
    show.value = false;
    emit("rename", name);
    renameValue.value = "";
    showRenameInput.value = false;
  }
}
</script>

<template>
  <el-dialog
    v-model="show"
    :title="`文件重名：${props.filename}`"
    width="520px"
    :close-on-press-escape="true"
    @close="emitCancel"
  >
    <p>已存在同名工作流。请选择如何处理：</p>

    <div v-if="showRenameInput" class="cc-rename-box">
      <el-input v-model="renameValue" placeholder="新文件名" @keyup.enter="confirmRename" />
      <el-button @click="confirmRename">确定</el-button>
      <el-button @click="showRenameInput = false">取消</el-button>
    </div>

    <template #footer>
      <template v-if="!showRenameInput">
        <el-button @click="showRenameInput = true">重命名</el-button>
        <el-button type="danger" @click="emitOverwrite">覆盖</el-button>
        <el-button @click="emitCancel">取消</el-button>
      </template>
    </template>
  </el-dialog>
</template>

<style lang="scss" scoped>
.cc-rename-box {
  display: flex;
  gap: 0.5rem;
  margin: 0.75rem 0;
  align-items: center;
}
</style>
