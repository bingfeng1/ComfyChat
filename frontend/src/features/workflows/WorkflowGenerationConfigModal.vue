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
    if (cfg === null) {
      apiTemplate.value = "{}";
      fields.value = [];
    } else {
      apiTemplate.value = JSON.stringify(cfg.api_template, null, 2);
      fields.value = cfg.fields;
    }
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err);
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
    <div class="cc-form">
      <el-form-item label="API 模板 JSON">
        <el-input
          v-model="apiTemplate"
          type="textarea"
          :rows="8"
          class="cc-code"
        />
      </el-form-item>

      <h4 class="cc-section-title">参数字段</h4>
      <div v-for="(f, i) in fields" :key="i" class="cc-field-row">
        <el-input v-model="f.key" placeholder="key" size="small" />
        <el-input v-model="f.label" placeholder="label" size="small" />
        <el-select v-model="f.type" size="small" style="width: 110px">
          <el-option value="text" label="text" />
          <el-option value="seed" label="seed" />
        </el-select>
        <el-input v-model="f.node_id" placeholder="node_id" size="small" />
        <el-input v-model="f.input_name" placeholder="input_name" size="small" />
        <el-input v-model="f.default" placeholder="default" size="small" />
        <el-checkbox v-model="f.required">必填</el-checkbox>
        <el-button link type="danger" @click="removeField(i)">×</el-button>
      </div>
      <el-button @click="addField">+ 添加字段</el-button>

      <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon />
    </div>

    <template #footer>
      <el-button @click="emit('close')">取消</el-button>
      <el-button type="primary" :loading="saving" @click="save">
        {{ saving ? "保存中…" : "保存" }}
      </el-button>
    </template>
  </Modal>
</template>

<style lang="scss" scoped>
.cc-form {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}
.cc-section-title {
  margin: 0.25rem 0 0;
  font-size: 0.9rem;
}
.cc-field-row {
  display: flex;
  gap: 0.4rem;
  align-items: center;
  flex-wrap: wrap;
}
.cc-code :deep(textarea) {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 0.8rem;
}
:deep(.cc-field-row .el-input) {
  width: 130px;
}
</style>
