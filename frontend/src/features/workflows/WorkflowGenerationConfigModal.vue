<script setup lang="ts">
import { onMounted, ref } from "vue";
import Modal from "@/components/Modal.vue";
import { api } from "@/services/api";
import type { GenerationField } from "@/types/api";

const props = defineProps<{ workflowId: string; title: string }>();
const emit = defineEmits<{ close: []; saved: [] }>();

const apiTemplate = ref("{}");
const fields = ref<GenerationField[]>([]);
const saving = ref(false);
const error = ref<string | null>(null);

onMounted(async () => {
  try {
    const cfg = await api.workflows.generationConfig.get(props.workflowId);
    apiTemplate.value = JSON.stringify(cfg.api_template, null, 2);
    fields.value = cfg.fields;
  } catch {
    // 无配置时为空模板
    apiTemplate.value = "{}";
    fields.value = [];
  }
});

function addField() {
  fields.value.push({
    key: "",
    label: "",
    type: "text",
    node_id: "",
    input_name: "",
    default: "",
    required: true,
  });
}

function removeField(i: number) {
  fields.value.splice(i, 1);
}

async function save() {
  saving.value = true;
  error.value = null;
  try {
    const parsed = JSON.parse(apiTemplate.value);
    await api.workflows.generationConfig.save(props.workflowId, {
      api_template: parsed,
      fields: fields.value,
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
    <div class="form">
      <label class="row">
        API 模板 JSON
        <textarea v-model="apiTemplate" class="input code" rows="8" />
      </label>

      <h4>参数字段</h4>
      <div v-for="(f, i) in fields" :key="i" class="field-row">
        <input v-model="f.key" class="input" placeholder="key" />
        <input v-model="f.label" class="input" placeholder="label" />
        <select v-model="f.type" class="input">
          <option value="text">text</option>
          <option value="seed">seed</option>
        </select>
        <input v-model="f.node_id" class="input" placeholder="node_id" />
        <input v-model="f.input_name" class="input" placeholder="input_name" />
        <input v-model="f.default" class="input" placeholder="default" />
        <label class="inline">
          <input v-model="f.required" type="checkbox" />必填
        </label>
        <button class="link danger" @click="removeField(i)">×</button>
      </div>
      <button class="btn" @click="addField">+ 添加字段</button>

      <p v-if="error" class="err">{{ error }}</p>

      <div class="actions">
        <button class="btn" @click="emit('close')">取消</button>
        <button class="btn primary" :disabled="saving" @click="save">
          {{ saving ? "保存中…" : "保存" }}
        </button>
      </div>
    </div>
  </Modal>
</template>

<style scoped>
.form { display: flex; flex-direction: column; gap: 0.75rem; }
.row { display: flex; flex-direction: column; gap: 0.25rem; font-size: 0.9rem; }
.field-row { display: flex; gap: 0.25rem; align-items: center; flex-wrap: wrap; }
.inline { display: flex; align-items: center; gap: 0.25rem; font-size: 0.8rem; }
.input { padding: 0.35rem; border: 1px solid #cbd5e1; border-radius: 6px; font-size: 0.85rem; }
.code { font-family: monospace; font-size: 0.8rem; }
.err { color: #ef4444; }
.actions { display: flex; gap: 0.5rem; justify-content: flex-end; }
.btn { padding: 0.4rem 0.9rem; border: 1px solid #cbd5e1; border-radius: 6px; background: #fff; cursor: pointer; }
.btn.primary { background: #0ea5e9; border-color: #0ea5e9; color: #fff; }
.link.danger { border: none; background: none; color: #ef4444; cursor: pointer; }
</style>
