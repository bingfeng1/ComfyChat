<script setup lang="ts">
import { computed } from "vue";
import { useRoute } from "vue-router";
import { Folder, MagicStick, Picture } from "@element-plus/icons-vue";

const route = useRoute();

interface NavItem {
  to: string;
  label: string;
  icon: typeof Folder;
  match: string;
}

const items: NavItem[] = [
  { to: "/workflows", label: "工作流", icon: Folder, match: "/workflows" },
  { to: "/generations", label: "生成", icon: Picture, match: "/generations" },
  { to: "/loras", label: "LoRA", icon: MagicStick, match: "/loras" },
];

const active = computed(() => {
  for (const item of items) {
    if (route.path.startsWith(item.match)) return item.to;
  }
  return "";
});
</script>

<template>
  <aside class="cc-sidebar">
    <div class="cc-brand">ComfyChat</div>
    <el-menu :default-active="active" router class="cc-menu">
      <el-menu-item v-for="item in items" :key="item.to" :index="item.to">
        <el-icon><component :is="item.icon" /></el-icon>
        <template #title>{{ item.label }}</template>
      </el-menu-item>
    </el-menu>
  </aside>
</template>

<style lang="scss" scoped>
@use "@/styles/variables" as *;

.cc-sidebar {
  width: $cc-sidebar-width;
  background: $cc-sidebar-bg;
  color: $cc-sidebar-text;
  display: flex;
  flex-direction: column;
  padding: 1rem 0;
}
.cc-brand {
  font-size: 1.1rem;
  font-weight: 700;
  padding: 0 1.25rem 1rem;
  color: #fff;
}
.cc-menu {
  background: transparent;
  border-right: none;
}
:deep(.el-menu-item) {
  color: $cc-sidebar-text;
}
:deep(.el-menu-item.is-active) {
  background: $cc-sidebar-active-bg;
  border-left: 3px solid $cc-sidebar-active-border;
}
:deep(.el-menu-item:hover) {
  background: rgba(255, 255, 255, 0.06);
}
</style>
