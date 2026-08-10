<script setup lang="ts">
import { onMounted, ref } from "vue";
import Modal from "@/components/Modal.vue";
import { api } from "@/services/api";
import type { GenerationField } from "@/types/api";

const props = defineProps<{ workflowId: string; title: string }>();
const emit = defineEmits<{ close: []; saved: [] }>();

const fields = ref<GenerationField[]>([]);
const apiTemplate = ref<Record<string, unknown>>({});
const removed = ref<Set<string>>(new Set());
const loading = ref(true);
const saving = ref(false);
const error = ref<string | null>(null);

const DEFAULT_CHECKED_KEYS = new Set(["seed", "width", "height"]);
const DEFAULT_CHECKED_LABELS = new Set(["正面提示词", "负面提示词"]);

function isDefaultChecked(f: GenerationField): boolean {
  if (DEFAULT_CHECKED_KEYS.has(f.key)) return true;
  if (DEFAULT_CHECKED_LABELS.has(f.label)) return true;
  return false;
}

function initRemoved(fields: GenerationField[]): Set<string> {
  const set = new Set<string>();
  for (const f of fields) {
    if (!isDefaultChecked(f)) set.add(f.key);
  }
  return set;
}

onMounted(async () => {
  removed.value = new Set();
  try {
    const existing = await api.workflows.generationConfig.get(props.workflowId);
    if (existing && existing.fields.length > 0) {
      fields.value = existing.fields;
      apiTemplate.value = existing.api_template;
      removed.value = initRemoved(existing.fields);
    } else {
      const d = await api.workflows.generationConfig.discover(props.workflowId);
      fields.value = d.fields;
      apiTemplate.value = d.api_template;
      removed.value = initRemoved(d.fields);
    }
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err);
  } finally {
    loading.value = false;
  }
});

function toggleField(key: string, checked: boolean) {
  if (checked) removed.value.delete(key);
  else removed.value.add(key);
}

async function save() {
  saving.value = true;
  error.value = null;
  try {
    const visible = fields.value.filter((f) => !removed.value.has(f.key));
    await api.workflows.generationConfig.save(props.workflowId, {
      api_template: apiTemplate.value,
      fields: visible,
    });
    emit("saved");
    emit("close");
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err);
  } finally {
    saving.value = false;
  }
}
</script>

<template>
  <Modal :title="`生成配置 · ${props.title}`" @close="emit('close')">
    <div v-if="loading" class="cc-loading">加载中…</div>

    <div v-else class="cc-form">
      <div class="cc-desc">
        选择要让「生成」页面显示的参数。取消勾选 = 生成时不显示。
      </div>

      <div v-if="fields.length === 0 && !error" class="cc-empty">
        未发现可填参数。请确认工作流已保存为 ComfyUI 格式。
      </div>

      <div
        v-for="f in fields"
        :key="f.key"
        class="cc-field-row"
      >
        <el-checkbox
          :model-value="!removed.has(f.key)"
          @update:model-value="(v: boolean) => toggleField(f.key, v)"
        />
        <el-tag size="small" type="info" class="cc-type-tag">{{ f.type }}</el-tag>
        <span class="cc-label">{{ f.label }}</span>
        <span class="cc-key">{{ f.key }}</span>
        <el-checkbox v-model="f.required" class="cc-required" size="small">
          必填
        </el-checkbox>
        <span v-if="f.options && f.options.length" class="cc-range" :title="f.options.join(', ')">
          {{ f.options.length }} 项可选
        </span>
        <span v-else-if="f.type === 'number' || f.type === 'seed'" class="cc-range">
          {{ f.min ?? "—" }} ~ {{ f.max ?? "—" }}{{ f.step ? ` 步进 ${f.step}` : "" }}
        </span>
      </div>

      <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon />
    </div>

    <template #footer>
      <el-button @click="emit('close')">取消</el-button>
      <el-button type="primary" :loading="saving" :disabled="loading" @click="save">
        {{ saving ? "保存中…" : "保存" }}
      </el-button>
    </template>
  </Modal>
</template>

<style lang="scss" scoped>
.cc-loading {
  padding: 1rem;
  color: #64748b;
}
.cc-form {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}
.cc-desc {
  font-size: 0.85rem;
  color: #64748b;
  margin-bottom: 0.5rem;
}
.cc-empty {
  color: #94a3b8;
  font-size: 0.85rem;
  padding: 0.5rem 0;
}
.cc-field-row {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}
.cc-label {
  min-width: 80px;
  font-weight: 500;
}
.cc-key {
  color: #94a3b8;
  font-size: 0.8rem;
}
.cc-type-tag {
  flex-shrink: 0;
}
.cc-range {
  color: #94a3b8;
  font-size: 0.75rem;
  white-space: nowrap;
}
</style>
