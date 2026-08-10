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

onMounted(async () => {
  removed.value = new Set();
  try {
    const existing = await api.workflows.generationConfig.get(props.workflowId);
    if (existing) {
      fields.value = existing.fields;
      apiTemplate.value = existing.api_template;
    } else {
      const d = await api.workflows.generationConfig.discover(props.workflowId);
      fields.value = d.fields;
      apiTemplate.value = d.api_template;
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
        <span class="cc-label">{{ f.label }}</span>
        <span class="cc-key">{{ f.key }}</span>
        <el-input
          v-model="f.label"
          size="small"
          class="cc-label-edit"
          placeholder="标签"
        />
        <el-checkbox v-model="f.required" class="cc-required" size="small">
          必填
        </el-checkbox>
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
.cc-label-edit {
  width: 160px;
}
</style>
