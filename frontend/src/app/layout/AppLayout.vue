<script setup lang="ts">
import Sidebar from "@/components/Sidebar.vue";
import TopBar from "@/components/TopBar.vue";
</script>

<template>
  <el-container class="cc-shell">
    <Sidebar />
    <el-container direction="vertical" class="cc-main">
      <TopBar />
      <el-main class="cc-content">
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>

<style lang="scss" scoped>
@use "@/styles/variables" as *;

.cc-shell {
  height: 100vh;
}
.cc-main {
  min-width: 0;
  background: $cc-content-bg;
}
.cc-content {
  padding: $cc-content-padding;
}
</style>
