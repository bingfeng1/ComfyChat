<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import Modal from "@/components/Modal.vue";
import { api } from "@/services/api";
import type { GenerationConfigSummary, GenerationField, GenerationSummary } from "@/types/api";

const props = defineProps<{ preset?: GenerationSummary | null }>();
const emit = defineEmits<{ close: [] }>();

const loading = ref(true);
const fetchError = ref<string | null>(null);
const configs = ref<GenerationConfigSummary[]>([]);
const workflowId = ref("");
const values = ref<Record<string, string | number>>({});
const randomFlags = ref<Record<string, boolean>>({});
const submitting = ref(false);
const submitError = ref<string | null>(null);
const step = ref(1);

const currentConfig = computed(
  () => configs.value.find((c) => c.workflow_id === workflowId.value) ?? null,
);

const fields = computed<GenerationField[]>(() => currentConfig.value?.fields ?? []);

const needsFieldsStep = computed(() => fields.value.length > 0);

const totalSteps = computed(() => (needsFieldsStep.value ? 3 : 2));

const stepTitle = computed(() => {
  if (step.value === 1) return "选择工作流";
  if (step.value === 2 && needsFieldsStep.value) return "填写参数";
  return "确认并生成";
});

const canProceed = computed(() => {
  if (step.value === 1) return workflowId.value !== "";
  if (step.value === 2 && needsFieldsStep.value) {
    for (const f of fields.value) {
      if (!f.required) continue;
      const isSeed = f.type === "seed";
      const isRandom = isSeed && randomFlags.value[`${f.key}_random`];
      if (isRandom) continue;
      const v = values.value[f.key];
      if (v === undefined || v === null) return false;
      if (typeof v === "string" && v.trim() === "") return false;
    }
    return true;
  }
  return true;
});

const workflowHint = computed(() => {
  if (configs.value.length === 0) return "";
  if (!currentConfig.value) return "请从下拉列表选择一个工作流";
  if (fields.value.length === 0) return "此工作流未配置参数,选完即可生成";
  return `此工作流包含 ${fields.value.length} 个参数,下一步填写`;
});

onMounted(async () => {
  try {
    configs.value = (await api.workflows.generationConfigs()).items;
    if (configs.value.length > 0) {
      const presetId = props.preset?.workflow_id ?? configs.value[0].workflow_id;
      selectWorkflow(presetId);
    }
  } catch (err) {
    fetchError.value = err instanceof Error ? err.message : String(err);
  } finally {
    loading.value = false;
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

function onWorkflowChange(id: string | number) {
  selectWorkflow(String(id));
  step.value = 1;
}

function next() {
  if (!canProceed.value) return;
  if (step.value < totalSteps.value) step.value++;
}

function back() {
  if (step.value > 1) step.value--;
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

function paramDisplay(f: GenerationField): string {
  const isSeed = f.type === "seed";
  const isRandom = isSeed && randomFlags.value[`${f.key}_random`];
  if (isRandom) return "随机";
  const v = values.value[f.key];
  if (v === undefined || v === null || v === "") return "—";
  return String(v);
}
</script>

<template>
  <Modal
    :title="props.preset ? '再生成' : '新建生成'"
    width="640px"
    @close="emit('close')"
  >
    <div v-if="loading" class="cc-loading">
      <span>加载工作流列表…</span>
    </div>

    <el-alert
      v-else-if="fetchError"
      :title="`无法加载已配置工作流：${fetchError}`"
      type="error"
      :closable="false"
      show-icon
    />

    <div v-else-if="configs.length === 0" class="cc-empty-state">
      <div class="cc-empty-icon">📋</div>
      <h4>暂无配置生成参数的工作流</h4>
      <p class="cc-empty-text">
        请先在「工作流」页选择流程 → 点击「配置」按钮,设置 API 模板和参数字段后再来生成。
      </p>
    </div>

    <div v-else>
      <div class="cc-step-header">
        第 {{ step }} 步 / 共 {{ totalSteps }} 步 — {{ stepTitle }}
      </div>

      <div v-if="step === 1" class="cc-step-body">
        <el-form-item label="工作流">
          <el-select
            :model-value="workflowId"
            style="width: 100%"
            @update:model-value="onWorkflowChange"
          >
            <el-option
              v-for="c in configs"
              :key="c.workflow_id"
              :value="c.workflow_id"
              :label="c.workflow_name"
            />
          </el-select>
        </el-form-item>
        <p class="cc-hint">{{ workflowHint }}</p>
      </div>

      <div v-else-if="step === 2 && needsFieldsStep" class="cc-step-body">
        <el-form-item
          v-for="f in fields"
          :key="f.key"
          :label="f.label"
          :required="f.required"
        >
          <template v-if="f.type === 'seed'">
            <div class="cc-seed-row">
              <el-checkbox v-model="randomFlags[`${f.key}_random`]">随机</el-checkbox>
              <el-input-number
                v-if="!randomFlags[`${f.key}_random`]"
                :model-value="values[f.key] as number | undefined"
                @update:model-value="(v: number | undefined) => values[f.key] = (v ?? 0)"
                controls-position="right"
              />
            </div>
          </template>
          <el-input-number
            v-else-if="f.type === 'number'"
            :model-value="values[f.key] as number | undefined"
            @update:model-value="(v: number | undefined) => values[f.key] = (v ?? 0)"
            controls-position="right"
            style="width: 100%"
          />
          <el-input
            v-else
            type="textarea"
            :rows="3"
            :model-value="values[f.key]"
            @update:model-value="(v: string) => values[f.key] = v ?? ''"
          />
        </el-form-item>
      </div>

      <div v-else class="cc-step-body">
        <el-descriptions :column="1" border>
          <el-descriptions-item label="工作流">
            {{ currentConfig?.workflow_name ?? workflowId }}
          </el-descriptions-item>
          <el-descriptions-item
            v-for="f in fields"
            :key="f.key"
            :label="f.label"
          >
            {{ paramDisplay(f) }}
          </el-descriptions-item>
        </el-descriptions>
        <p v-if="fields.length === 0" class="cc-hint">此工作流无参数,直接生成。</p>
      </div>

      <el-alert
        v-if="submitError"
        :title="submitError"
        type="error"
        :closable="false"
        show-icon
      />
    </div>

    <template #footer>
      <template v-if="loading || fetchError || configs.length === 0">
        <el-button type="primary" @click="emit('close')">关闭</el-button>
      </template>
      <template v-else>
        <el-button :disabled="step === 1" @click="back">上一步</el-button>
        <el-button @click="emit('close')">取消</el-button>
        <el-button
          v-if="step < totalSteps"
          type="primary"
          :disabled="!canProceed"
          @click="next"
        >下一步</el-button>
        <el-button
          v-else
          type="primary"
          :loading="submitting"
          @click="submit"
        >生成</el-button>
      </template>
    </template>
  </Modal>
</template>

<style lang="scss" scoped>
.cc-loading {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 2rem;
  color: #64748b;
}
.cc-empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  padding: 1.5rem 1rem;
}
.cc-empty-icon {
  font-size: 2rem;
  margin-bottom: 0.5rem;
  opacity: 0.7;
}
.cc-empty-state h4 {
  margin: 0 0 0.5rem;
  font-size: 1rem;
  color: #475569;
}
.cc-empty-text {
  color: #64748b;
  font-size: 0.85rem;
  max-width: 360px;
  margin: 0;
}
.cc-step-header {
  font-size: 0.85rem;
  color: #475569;
  margin-bottom: 1rem;
  padding-bottom: 0.5rem;
  border-bottom: 1px solid #e2e8f0;
}
.cc-step-body {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}
.cc-hint {
  margin: 0;
  font-size: 0.8rem;
  color: #64748b;
}
.cc-seed-row {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}
</style>
