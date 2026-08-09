import { createRouter, createWebHistory, type RouteRecordRaw } from "vue-router";

const routes: RouteRecordRaw[] = [
  {
    path: "/",
    name: "home",
    component: () => import("@/App.vue"),
  },
];

export const router = createRouter({
  history: createWebHistory(),
  routes,
});