<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import Modal from "@/components/Modal.vue";
import { api } from "@/services/api";
import type { GenerationConfigSummary, GenerationField, GenerationSummary } from "@/types/api";

const props = defineProps<{ preset?: GenerationSummary | null }>();
const emit = defineEmits<{ close: [] }>();

const configs = ref<GenerationConfigSummary[]>([]);
const workflowId = ref("");
const values = ref<Record<string, string | number>>({});
const randomFlags = ref<Record<string, boolean>>({});
const loading = ref(false);
const submitting = ref(false);
const submitError = ref<string | null>(null);

const current = computed(
  () => configs.value.find((c) => c.workflow_id === workflowId.value) ?? null
);

const fields = computed<GenerationField[]>(() => current.value?.fields ?? []);

onMounted(async () => {
  try {
    configs.value = (await api.workflows.generationConfigs()).items;
    if (configs.value.length > 0) {
      const presetId = props.preset?.workflow_id ?? configs.value[0].workflow_id;
      selectWorkflow(presetId);
    }
  } catch (err) {
    submitError.value = err instanceof Error ? err.message : String(err);
  }
});

function selectWorkflow(id: string) {
  workflowId.value = id;
  values.value = {};
  randomFlags.value = {};
  if (props.preset && props.preset.workflow_id === id) {
    const p = props.preset.parameters;
    for (const f of fields.value) {
      const v = p[f.key];
      if (typeof v === "string" || typeof v === "number") values.value[f.key] = v;
      randomFlags.value[`${f.key}_random`] = Boolean(p[`${f.key}_random`]);
    }
  } else {
    for (const f of fields.value) {
      if (typeof f.default === "string" || typeof f.default === "number") {
        values.value[f.key] = f.default;
      }
    }
  }
}

async function submit() {
  if (!workflowId.value) return;
  submitting.value = true;
  submitError.value = null;
  try {
    const parameters: Record<string, unknown> = {};
    for (const f of fields.value) {
      const isSeed = f.type === "seed";
      const isRandom = isSeed && randomFlags.value[`${f.key}_random`];
      if (isRandom) {
        parameters[`${f.key}_random`] = true;
      } else {
        parameters[f.key] = values.value[f.key];
        if (isSeed) parameters[`${f.key}_random`] = false;
      }
    }
    await api.generations.create({ workflow_id: workflowId.value, parameters });
    emit("close");
  } catch (err) {
    submitError.value = err instanceof Error ? err.message : String(err);
  } finally {
    submitting.value = false;
  }
}
</script>

<template>
  <Modal :title="props.preset ? '再生成' : '新建生成'" @close="emit('close')">
    <div class="form">
      <label class="row">
        工作流
        <select v-model="workflowId" @change="selectWorkflow(workflowId)">
          <option v-for="c in configs" :key="c.workflow_id" :value="c.workflow_id">
            {{ c.workflow_name }}
          </option>
        </select>
      </label>

      <template v-if="current">
        <div v-for="f in fields" :key="f.key" class="row">
          <label>{{ f.label }}</label>
          <template v-if="f.type === 'seed'">
            <label class="inline">
              <input
                type="checkbox"
                v-model="randomFlags[`${f.key}_random`]"
              />
              随机
            </label>
            <input
              v-if="!randomFlags[`${f.key}_random`]"
              v-model.number="values[f.key]"
              type="number"
              class="input"
              :required="f.required"
            />
          </template>
          <textarea
            v-else
            v-model="values[f.key]"
            class="input"
            :required="f.required"
            rows="3"
          />
        </div>
      </template>
      <p v-else-if="!loading" class="hint">没有可用的已配置工作流，请先在工作流页配置生成参数。</p>

      <p v-if="submitError" class="err">{{ submitError }}</p>

      <div class="actions">
        <button class="btn" @click="emit('close')">取消</button>
        <button class="btn primary" :disabled="submitting || !current" @click="submit">
          {{ submitting ? "提交中…" : "生成" }}
        </button>
      </div>
    </div>
  </Modal>
</template>

<style scoped>
.form { display: flex; flex-direction: column; gap: 0.75rem; }
.row { display: flex; flex-direction: column; gap: 0.25rem; font-size: 0.9rem; }
.inline { display: flex; align-items: center; gap: 0.25rem; }
.input { padding: 0.4rem; border: 1px solid #cbd5e1; border-radius: 6px; }
.hint { color: #64748b; font-size: 0.85rem; }
.err { color: #ef4444; }
.actions { display: flex; gap: 0.5rem; justify-content: flex-end; }
.btn { padding: 0.4rem 0.9rem; border: 1px solid #cbd5e1; border-radius: 6px; background: #fff; cursor: pointer; }
.btn.primary { background: #0ea5e9; border-color: #0ea5e9; color: #fff; }
</style>
