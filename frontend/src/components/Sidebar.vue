<script setup lang="ts">
import { useRoute } from "vue-router";

const route = useRoute();

const items = [{ to: "/workflows", label: "工作流", icon: "📁" }];

function isActive(to: string) {
  return route.path.startsWith(to);
}
</script>

<template>
  <aside class="sidebar">
    <div class="brand">ComfyChat</div>
    <nav>
      <router-link
        v-for="item in items"
        :key="item.to"
        :to="item.to"
        class="nav-item"
        :class="{ active: isActive(item.to) }"
      >
        <span>{{ item.icon }}</span>
        <span>{{ item.label }}</span>
      </router-link>
    </nav>
  </aside>
</template>

<style scoped>
.sidebar {
  width: 220px;
  background: #1e293b;
  color: #e2e8f0;
  display: flex;
  flex-direction: column;
  padding: 1rem;
  gap: 1rem;
}
.brand {
  font-size: 1.1rem;
  font-weight: 700;
}
.nav-item {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.5rem 0.75rem;
  border-radius: 6px;
  color: inherit;
  text-decoration: none;
}
.nav-item:hover {
  background: #334155;
}
.nav-item.active {
  background: #0ea5e9;
  color: #fff;
}
</style>
