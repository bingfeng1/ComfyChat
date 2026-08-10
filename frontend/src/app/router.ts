import { createRouter, createWebHistory, type RouteRecordRaw } from "vue-router";

const routes: RouteRecordRaw[] = [
  { path: "/", redirect: "/workflows" },
  {
    path: "/workflows",
    name: "workflows",
    component: () => import("@/features/workflows/WorkflowsView.vue"),
  },
  {
    path: "/generations",
    name: "generations",
    component: () => import("@/features/generations/GenerationsView.vue"),
  },
  {
    path: "/loras",
    name: "loras",
    component: () => import("@/features/loras/LorasView.vue"),
  },
];

export const router = createRouter({
  history: createWebHistory(),
  routes,
});
