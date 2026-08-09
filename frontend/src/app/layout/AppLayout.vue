<script setup lang="ts">
import Sidebar from "@/components/Sidebar.vue";
import TopBar from "@/components/TopBar.vue";
</script>

<template>
  <div class="layout">
    <Sidebar />
    <div class="main-col">
      <TopBar />
      <main class="content">
        <router-view />
      </main>
    </div>
  </div>
</template>

<style scoped>
.layout {
  display: flex;
  height: 100vh;
}
.main-col {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
}
.content {
  flex: 1;
  overflow-y: auto;
  padding: 1.5rem;
}
</style>
