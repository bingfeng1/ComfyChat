# UI Polish with Element Plus + SCSS

**Date:** 2026-08-10
**Status:** Design — awaiting review
**Scope:** Frontend visual refresh only. No backend, data-flow, or behaviour changes.

## Goal

Replace the bespoke CSS-driven shell of ComfyChat with Element Plus components and SCSS tooling so that the app feels consistent, modern, and ready to grow. Keep the light-only theme the user requested. Preserve every existing component prop/emit contract that other modules depend on.

## Non-Goals

- Dark mode toggle. CSS variables are introduced for tooling, but no second theme ships.
- Mobile responsive layout. The desktop shell is what we improve.
- Routing, Pinia store, API client, or WebSocket behaviour changes.
- Backend tests, Alembic, schemas — out of scope.
- Ejecting from `frontend/vite.config.ts` `127.0.0.1` host binding.

## Tech Stack Changes

Add to `frontend/package.json`:

| Package | Purpose | Where used |
|---|---|---|
| `element-plus` (^2.11) | UI primitives | every `.vue` file with UI |
| `@element-plus/icons-vue` (^2.3) | icon set replacing emoji | sidebar, table actions, modal |
| `unplugin-vue-components` (^0.27) | on-demand component import | `vite.config.ts` |
| `unplugin-auto-import` (^0.18) | on-demand API auto-import | `vite.config.ts` |
| `sass` (^1.77) | SCSS preprocessor | `<style lang="scss">` blocks |

Install command (project-local npm mirror is already configured in `frontend/.npmrc`, so no env tweaks needed):
```
npm --prefix frontend install --save-dev element-plus @element-plus/icons-vue unplugin-vue-components unplugin-auto-import sass
```

## Vite + SCSS Configuration

### `frontend/vite.config.ts`

Add the two plugins using the official `ElementPlusResolver()` pattern (`/websites/element-plus` quickstart). Plugin order matters: `autoImport` then `components`. Aliases and `127.0.0.1` host bind are preserved.

```ts
import AutoImport from 'unplugin-auto-import/vite'
import Components from 'unplugin-vue-components/vite'
import { ElementPlusResolver } from 'unplugin-vue-components/resolvers'

plugins: [
  vue(),
  AutoImport({ resolvers: [ElementPlusResolver()] }),
  Components({ resolvers: [ElementPlusResolver({ styleExtension: 'scss' })] }),
]
```

`styleExtension: 'scss'` tells the resolver to also load the SCSS variants of the styles it injects (so future SCSS variable overrides land). Default value is `css`; switch to `scss` only because our project uses SCSS.

### `frontend/src/main.ts`

The on-demand resolver auto-registers every component into the app template at build time. We still need `app.use(ElementPlus)` once so that the locale is picked up (the resolver does not install the plugin). Add:

```ts
import zhCn from 'element-plus/dist/locale/zh-cn.mjs'
app.use(ElementPlus, { locale: zhCn })
```

After this, default Element Plus labels (e.g. pagination, empty state) render in Chinese, matching the rest of the UI.

## SCSS Folder

Create `frontend/src/styles/`:

```
src/styles/
  _variables.scss   # design tokens (see Tokens below)
  _element-overrides.scss  # theme tweaks loaded after ep styles
  index.scss        # @forward both, plus a global reset
```

Imported once from `src/main.ts`. Component `<style lang="scss">` blocks reference the variables via `@use '@/styles/variables' as *;`.

## Design Tokens (`_variables.scss`)

Single source of truth for any custom value that needs to differ from Element Plus defaults. Element Plus covers nearly everything; this file is for app-specific quirks.

```scss
$cc-sidebar-bg: #0f172a;
$cc-sidebar-text: #e2e8f0;
$cc-sidebar-active-bg: rgba(14, 165, 233, 0.18);
$cc-sidebar-active-border: #0ea5e9;

$cc-topbar-shadow: 0 1px 2px rgba(15, 23, 42, 0.06);
$cc-content-bg: #f8fafc;

$cc-status-running: #f59e0b;
$cc-status-success: #22c55e;
$cc-status-failed: #ef4444;
$cc-status-queued: #6366f1;
```

Element Plus primary color (`#409eff`) is replaced with `--el-color-primary` override (`#0ea5e9`) via CSS variables in `_element-overrides.scss` so the brand accent matches the existing visual identity.

## Component Mapping

The table below is authoritative. Every component in the left column must end up using the right-column Element Plus primitive. Component APIs (props + emits) are preserved exactly, so consumers do not change.

| Existing file / element | Becomes | Notes |
|---|---|---|
| `AppLayout.vue` outer `div.layout` | `el-container` (vertical=outer, horizontal=inner) + `el-aside` + `el-main` | use `<el-aside width="220">`, `<el-main>` only inside the inner container |
| `Sidebar.vue` `<aside>` + `<nav>` | `el-menu` with `:default-active` driven by current route | Items become `el-menu-item` with `#title` slot for icon + label |
| `Sidebar.vue` emoji icons (`📁 🖼`) | `@element-plus/icons-vue` (`Folder`, `Picture`) | icons set via `<el-icon>` |
| `TopBar.vue` raw `<header>` | `<el-header>` inside the inner `el-container` | height set to `56px` |
| `TopBar.vue` raw `<div class="health">` + colored dots | `<el-tag>` (`success` / `danger` / `info`) with a small text label | `type` mapped from health status |
| `TopBar.vue` raw refresh `<button>` | `<el-button :icon="Refresh" circle size="small">` | click handler preserved |
| `Modal.vue` custom `<div class="overlay">` | thin wrapper that renders `el-dialog` underneath and exposes the original `title` prop + `close` emit | the wrapper manages `v-model` internally and emits `close` on every dialog close path. Existing `<Modal @close="…">` and `<Modal title="…">` call sites do not change |
| `Modal.vue` `✕` close button | `el-dialog` provides this natively | remove the manual `<button class="x">` |
| `WorkflowsView.vue` `<table class="table">` | `el-table :data="items"` with `el-table-column` per column | Loading state uses `v-loading="loading"` directive on the table; empty state uses `<el-empty>` inside the table body via slot |
| `WorkflowsView.vue` raw `<input class="search">` | `el-input v-model="search" :prefix-icon="Search" placeholder="搜索名称…">` | `@input` replaced with `v-model` (Element Plus emits input) |
| `WorkflowsView.vue` raw `<select>` | `el-select` with `el-option` | same options list |
| `WorkflowsView.vue` toolbar buttons | `el-button type="primary"` / `el-button` / `el-button type="danger"` | icons via `:icon` prop |
| `WorkflowsView.vue` confirm delete `<Modal>` usage | unchanged (Modal wrapper keeps API) |  |
| `WorkflowsView.vue` error banner | `el-alert type="error" :closable="false"` | preserves "error" string |
| `WorkflowsView.vue` sync success banner | `el-alert type="success" :closable="false"` |  |
| `WorkflowRow.vue` | inline slot content inside `el-table-column` of `WorkflowsView.vue` | the row component is removed and its markup inlined. Header text and emit names flow through `(view, export, delete, history, config)` are kept by binding `@row-click` or per-column `<el-button>` clicks to existing handlers |
| `GenerationsView.vue` | same mapping as WorkflowsView | replaces `<table>` with `el-table`, `<select>` with `el-select`, raw buttons with `el-button` |
| `GenerationRow.vue` | inlined into `GenerationsView.vue` as `el-table-column` slots | badge `<span class="badge X">` replaced with `<el-tag :type="statusType(g.status)">` where `statusType` maps `success→success`, `running/queued→warning`, `failed→danger` |
| All other modals (`WorkflowDetailModal`, `WorkflowHistoryModal`, `WorkflowGenerationConfigModal`, `ImportConflictDialog`, `GenerationDetailModal`, `GenerationCreateModal`, `confirmDelete` instances) | use `Modal` wrapper → which now renders `el-dialog` underneath | prop names unchanged |
| `GenerationCreateModal.vue` form fields | `el-form` + `el-form-item` + `el-input` / `el-input-number` | preserves the existing v-model bindings to `useGenerations` |

### `:deep()` for any leftover overrides

Where Element Plus covers most styling but a small layout tweak is needed (e.g. top bar header padding), components use `<style lang="scss" scoped>` with `@use '@/styles/variables' as *;` and `:deep(.el-button)` selectors.

## Iconography

`@element-plus/icons-vue` provides SVG paths used through `<el-icon>`. Existing emoji (`📁 🖼 ✕ ↻`) become:

| Emoji | Element Plus icon |
|---|---|
| 📁 | `Folder` |
| 🖼 | `Picture` |
| ✕ | default `el-dialog` close |
| ↻ | `Refresh` |

Table action buttons (`view, export, delete, history, config, regenerate`) get dedicated icons: `View`, `Download`, `Delete`, `Document`, `Setting`, `Refresh`.

## File-level Change List

1. `frontend/package.json` — add deps
2. `frontend/vite.config.ts` — two new plugins
3. `frontend/src/main.ts` — Element Plus locale registration
4. `frontend/src/styles/{_variables,_element-overrides,index}.scss` — NEW
5. `frontend/src/app/layout/AppLayout.vue` — el-container skeleton
6. `frontend/src/components/Sidebar.vue` — el-menu
7. `frontend/src/components/TopBar.vue` — el-tag + el-button
8. `frontend/src/components/Modal.vue` — el-dialog wrapper
9. `frontend/src/features/workflows/WorkflowsView.vue` — el-table + el-form controls
10. `frontend/src/features/workflows/WorkflowRow.vue` — DELETE; content inlined in WorkflowsView
11. `frontend/src/features/generations/GenerationsView.vue` — el-table + el-form controls
12. `frontend/src/features/generations/GenerationRow.vue` — DELETE; content inlined in GenerationsView
13. `frontend/src/features/workflows/WorkflowDetailModal.vue` — use updated Modal (no template logic change)
14. `frontend/src/features/workflows/WorkflowHistoryModal.vue` — same
15. `frontend/src/features/workflows/WorkflowGenerationConfigModal.vue` — same
16. `frontend/src/features/workflows/ImportConflictDialog.vue` — same + use el-button for footer
17. `frontend/src/features/generations/GenerationDetailModal.vue` — same
18. `frontend/src/features/generations/GenerationCreateModal.vue` — el-form layout

## Risks

1. **Bundle size.** Element Plus is large. The two auto-import plugins limit the hit to what we actually use. Confirm via `npm run build` output stays under 1MB gz.
2. **`el-table` row click.** Action today is per-cell `<el-button>` inside `<el-table-column #default>`. No `:row-click` is bound, so clicking empty cells does nothing. If whole-row click is desired later, add `:row-click` once. Today: per-cell buttons only.
3. **`Modal` API preservation.** `el-dialog` is `v-model` two-way. The wrapper hides that behind a one-way `title` prop + `close` emit. Implementation: `const show = ref(true)` inside the wrapper, mounted when the consumer renders `<Modal>`; close handlers update `show = false` and emit `close`. Consumers only render `<Modal>` while they want it open, so `v-if`-driven mounting already drives the lifecycle; no external `modelValue` prop is exposed.
4. **CSS removal.** Inline colour hexes (`#0ea5e9`, `#ef4444`, etc.) are removed only where the Element Plus theme now provides the equivalent. Where a row hover or table-stripe colour is bespoke, move the value into `_variables.scss`.
5. **`@vue/generic` for `el-table-column`.** When the row type cannot be inferred (TypeScript narrow), add the `@vue-generic {WorkflowSummary}` comment above the column, per Element Plus docs.
6. **SCSS + `<style scoped>`.** Vite picks up `<style lang="scss">` automatically once `sass` is installed — no extra config beyond the plugin order.

## Verification

Commands (cwd = repo root):

1. `npm --prefix frontend run typecheck` — must pass; `vue-tsc --noEmit`
2. `npm --prefix frontend run build` — full Vite build, must succeed
3. `backend\.venv\Scripts\python -m pytest backend/tests -v` — backend untouched, must still pass 91 tests (1 known Windows fail is acceptable)
4. Manual smoke (browser at `http://localhost:5173` after `scripts\start-dev.ps1`):
   - Workflows page loads; sync button works; import dropzone responds; delete confirmation appears as a dialog
   - Generations page loads; status pills render with correct colour; create dialog form fields and buttons render correctly
   - Modal close-on-overlay-click, ESC, and ✕ all work
   - Sidebar nav highlights the active route
   - TopBar health tag updates after refresh

## Open Questions

None at design time. Decisions deferred to implementation:
- Exact toast style for action feedback: lean on `ElMessage` from `element-plus` once wiring is verified
- Persisting column widths via `el-table-column` `width` prop — start without and add if user wants
