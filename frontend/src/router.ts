import type { Component } from "vue";
import { createRouter, createWebHistory, type RouteRecordRaw } from "vue-router";
import { Collection, Folder, MagicStick, Picture } from "@element-plus/icons-vue";

declare module "vue-router" {
  interface RouteMeta {
    label?: string;
    icon?: Component;
    sidebar?: boolean;
  }
}

const routes: RouteRecordRaw[] = [
  { path: "/", redirect: "/workflows" },
  {
    path: "/workflows",
    name: "workflows",
    component: () => import("@/features/workflows/WorkflowsView.vue"),
    meta: { label: "工作流", icon: Folder, sidebar: true },
  },
  {
    path: "/generations",
    name: "generations",
    component: () => import("@/features/generations/GenerationsView.vue"),
    meta: { label: "生成", icon: Picture, sidebar: true },
  },
  {
    path: "/loras",
    name: "loras",
    component: () => import("@/features/loras/LorasView.vue"),
    meta: { label: "LoRA", icon: MagicStick, sidebar: true },
  },
  {
    path: "/workspaces",
    name: "workspaces",
    component: () => import("@/features/workspaces/WorkspacesView.vue"),
    meta: { label: "工作区", icon: Collection, sidebar: true },
  },
  {
    path: "/workspaces/:id",
    name: "workspace-detail",
    component: () => import("@/features/workspaces/WorkspaceDetailView.vue"),
    meta: { sidebar: false },
  },
];

export const router = createRouter({
  history: createWebHistory(),
  routes,
});

export interface NavItem {
  to: string;
  label: string;
  icon: Component;
  match: string;
}

export function getNavItems(): NavItem[] {
  return router.options.routes
    .filter((r) => r.meta?.sidebar !== false && r.meta?.label && r.meta?.icon)
    .map((r) => ({
      to: r.path,
      label: r.meta!.label!,
      icon: r.meta!.icon!,
      match: r.path,
    }));
}
