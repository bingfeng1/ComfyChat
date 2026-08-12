<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from "vue";
import { CircleClose, Loading } from "@element-plus/icons-vue";
import Modal from "@/components/Modal.vue";
import { useNsfwFilter } from "@/composables/useNsfwFilter";
import { api } from "@/services/api";
import type { GenerationConfigSummary, GenerationField, GenerationStatus, GenerationSummary } from "@/types/api";
import type { LoraSummary } from "@/types/api";

const props = defineProps<{
  preset?: GenerationSummary | null;
  preselectWorkflowId?: string;
  showGoto?: boolean;
}>();
const emit = defineEmits<{ close: []; generated: []; goto: [] }>();

const loading = ref(true);
const fetchError = ref<string | null>(null);
const configs = ref<GenerationConfigSummary[]>([]);
const loras = ref<LoraSummary[]>([]);
const { enabled: nsfwEnabled } = useNsfwFilter();
const workflowId = ref("");
const values = ref<Record<string, string | number>>({});
const randomFlags = ref<Record<string, boolean>>({});
const autoAddTrigger = ref(true);
const submitting = ref(false);
const submitError = ref<string | null>(null);
const activeGenId = ref<string | null>(null);
const activeStatus = ref<GenerationStatus | null>(null);
const activeError = ref<string | null>(null);
const mainImageUrl = ref<string | null>(null);
const history = ref<Array<{ id: string; imageUrl: string }>>([]);
let pollTimer: number | undefined;
const step = ref(1);

const currentConfig = computed(
  () => configs.value.find((c) => c.workflow_id === workflowId.value) ?? null,
);

const fields = computed<GenerationField[]>(() => currentConfig.value?.fields ?? []);

const needsFieldsStep = computed(() => fields.value.length > 0);

const RATIO_PRESETS = [
  { label: "1:1", w: 1, h: 1 },
  { label: "4:3", w: 4, h: 3 },
  { label: "3:4", w: 3, h: 4 },
  { label: "3:2", w: 3, h: 2 },
  { label: "2:3", w: 2, h: 3 },
  { label: "16:9", w: 16, h: 9 },
  { label: "9:16", w: 9, h: 16 },
  { label: "21:9", w: 21, h: 9 },
];

const RES_PRESETS = [
  { label: "512 × 512", w: 512, h: 512 },
  { label: "768 × 768", w: 768, h: 768 },
  { label: "896 × 896", w: 896, h: 896 },
  { label: "1024 × 1024", w: 1024, h: 1024 },
  { label: "768 × 1024", w: 768, h: 1024 },
  { label: "1024 × 768", w: 1024, h: 768 },
  { label: "1152 × 896", w: 1152, h: 896 },
  { label: "1344 × 768", w: 1344, h: 768 },
];

const widthField = computed(() => fields.value.find((f) => f.key === "width" && f.type === "number") ?? null);
const heightField = computed(() => fields.value.find((f) => f.key === "height" && f.type === "number") ?? null);
const hasSizeFields = computed(() => widthField.value !== null && heightField.value !== null);
const lockRatio = ref(false);
const ratioLabel = ref("");
const lockedRatio = ref<{ w: number; h: number } | null>(null);

function gcdOf(a: number, b: number): number {
  return b === 0 ? a : gcdOf(b, a % b);
}

function ratioOf(w: number, h: number): { w: number; h: number } {
  const gw = Math.max(1, Math.round(w));
  const gh = Math.max(1, Math.round(h));
  const g = gcdOf(gw, gh) || 1;
  return { w: Math.round(gw / g), h: Math.round(gh / g) };
}

function applyRatioPreset(label: string) {
  const p = RATIO_PRESETS.find((r) => r.label === label);
  if (!p || !hasSizeFields.value) return;
  ratioLabel.value = label;
  lockRatio.value = true;
  lockedRatio.value = { w: p.w, h: p.h };
  const w = Number(values.value["width"]) || 1024;
  values.value["height"] = Math.round((w * p.h) / p.w);
  values.value["width"] = w;
}

function applyResPreset(label: string) {
  const p = RES_PRESETS.find((r) => r.label === label);
  if (!p || !hasSizeFields.value) return;
  values.value["width"] = p.w;
  values.value["height"] = p.h;
  const g = gcdOf(p.w, p.h);
  ratioLabel.value = `${p.w / g}:${p.h / g}`;
  lockRatio.value = false;
  lockedRatio.value = null;
}

function onToggleLockRatio(checked: boolean) {
  lockRatio.value = checked;
  if (checked) {
    // 勾选锁定: 用当前宽高作为锁定比例
    lockedRatio.value = ratioOf(
      Number(values.value["width"]) || 0,
      Number(values.value["height"]) || 0,
    );
    if (lockedRatio.value.w === 0 || lockedRatio.value.h === 0) lockedRatio.value = null;
  }
}

function onSizeChange(changed: "width" | "height") {
  if (!lockRatio.value || !hasSizeFields.value || !lockedRatio.value) return;
  const { w: rw, h: rh } = lockedRatio.value;
  if (changed === "width") {
    const w = Number(values.value["width"]) || 0;
    values.value["height"] = Math.round((w * rh) / rw) || values.value["height"];
  } else {
    const h = Number(values.value["height"]) || 0;
    values.value["width"] = Math.round((h * rw) / rh) || values.value["width"];
  }
}

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
    try {
      loras.value = (await api.loras.list()).items;
    } catch {
      /* LoRA 列表不可用时不阻塞生成流程 */
    }
    configs.value = (await api.workflows.generationConfigs()).items;
    if (configs.value.length > 0) {
      if (
        props.preselectWorkflowId &&
        configs.value.some((c) => c.workflow_id === props.preselectWorkflowId)
      ) {
        selectWorkflow(props.preselectWorkflowId);
        step.value = needsFieldsStep.value ? 2 : totalSteps.value;
      } else {
        const presetId = props.preset?.workflow_id ?? configs.value[0].workflow_id;
        selectWorkflow(presetId);
      }
    }
  } catch (err) {
    fetchError.value = err instanceof Error ? err.message : String(err);
  } finally {
    loading.value = false;
  }
});

onUnmounted(() => {
  stopPolling();
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
    autoAddTrigger.value = p["auto_add_trigger"] !== false;
  } else {
    autoAddTrigger.value = true;
    for (const f of fields.value) {
      // 非 seed 字段填工作流默认值;seed 默认勾选随机,不填工作流的固定种子
      if (f.type !== "seed" && (typeof f.default === "string" || typeof f.default === "number")) {
        values.value[f.key] = f.default;
      }
      randomFlags.value[`${f.key}_random`] = f.type === "seed";
    }
  }
}

function isLoraField(f: GenerationField): boolean {
  return f.key === "lora_name";
}

function loraOptions(f: GenerationField): string[] {
  if (!isLoraField(f)) return f.options ?? [];
  // 候选源: DB 里活跃的 LoRA(`deleted_from_comfyui=false`)。
  // 不要用 f.options —— 那是工作流配置保存时的快照,之后新装的 LoRA 不在里面。
  // DB sync 会保持 loras.value 与 ComfyUI 实际安装列表一致,这里不需要二次过滤。
  const candidates = loras.value
    .filter((l) => !l.deleted_from_comfyui)
    .map((l) => l.name);
  // NSFW 过滤
  const nsfwFiltered = nsfwEnabled.value ? candidates : candidates.filter((name) => {
    const lora = loras.value.find((l) => l.name === name);
    return lora && !lora.is_nsfw;
  });
  const mainModel = currentConfig.value?.main_model;
  if (!mainModel) return nsfwFiltered;
  const filtered = nsfwFiltered
    .map((name) => loras.value.find((l) => l.name === name))
    .filter((l) => l && l.models.includes(mainModel))
    .map((l) => l!.name);
  return filtered.length > 0 ? filtered : nsfwFiltered;
}

function onWorkflowChange(id: string | number) {
  selectWorkflow(String(id));
  step.value = 1;
}

// 兜底: 字段就绪后,确保每个 seed 字段的随机标志有显式布尔值(新建生成默认勾选随机)
watch(
  fields,
  () => {
    if (!props.preset) {
      for (const f of fields.value) {
        if (f.type === "seed" && randomFlags.value[`${f.key}_random`] === undefined) {
          randomFlags.value[`${f.key}_random`] = true;
        }
      }
    }
  },
  { immediate: true },
);

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
    parameters["auto_add_trigger"] = autoAddTrigger.value;
    const res = await api.generations.create({ workflow_id: workflowId.value, parameters });
    if (res.status !== 201) {
      const data = await res.json().catch(() => null);
      throw new Error(data?.detail ?? `创建失败:${res.status}`);
    }
    const gen = (await res.json()) as GenerationSummary;
    activeGenId.value = gen.id;
    activeStatus.value = gen.status;
    activeError.value = null;
    mainImageUrl.value = null;
    emit("generated");  // 通知父级刷新列表;不 emit close,弹窗保持打开
    startPolling();
  } catch (err) {
    submitError.value = err instanceof Error ? err.message : String(err);
  } finally {
    submitting.value = false;
  }
}

function startPolling() {
  stopPolling();
  pollTimer = window.setInterval(pollOnce, 2000);
  pollOnce();
}

function stopPolling() {
  if (pollTimer !== undefined) {
    window.clearInterval(pollTimer);
    pollTimer = undefined;
  }
}

async function pollOnce() {
  if (!activeGenId.value) return;
  try {
    const gen = await api.generations.get(activeGenId.value);
    activeStatus.value = gen.status;
    activeError.value = gen.error;
    if (gen.status === "success" && gen.outputs.length > 0) {
      const filename = gen.outputs[0];
      mainImageUrl.value = api.generations.imageUrl(gen.id, filename);
      // 入栈历史(去重 + 最新在左)
      if (!history.value.some((h) => h.id === gen.id)) {
        history.value = [{ id: gen.id, imageUrl: mainImageUrl.value }, ...history.value];
      }
      stopPolling();
    } else if (gen.status === "failed") {
      stopPolling();
    }
  } catch {
    /* 单次失败静默忽略 */
  }
}

const aborting = ref(false);
const abortError = ref<string | null>(null);

async function abort() {
  if (!activeGenId.value || aborting.value) return;
  aborting.value = true;
  abortError.value = null;
  const genId = activeGenId.value;
  try {
    const res = await api.generations.cancel(genId);
    if (!res.ok) {
      const data = await res.json().catch(() => null);
      throw new Error(data?.detail ?? `中止失败:${res.status}`);
    }
    // 后端已删除该记录,直接停止轮询并复位弹窗状态
    stopPolling();
    activeGenId.value = null;
    activeStatus.value = null;
    activeError.value = null;
    mainImageUrl.value = null;
    history.value = [];
    emit("generated");
  } catch (err) {
    abortError.value = err instanceof Error ? err.message : String(err);
  } finally {
    aborting.value = false;
  }
}

function showThumbnail(url: string) {
  mainImageUrl.value = url;
}

function paramDisplay(f: GenerationField): string {
  const isSeed = f.type === "seed";
  const isRandom = isSeed && randomFlags.value[`${f.key}_random`];
  if (isRandom) return "随机";
  const v = values.value[f.key];
  if (v === undefined || v === null || v === "") return "—";
  return String(v);
}

const autoTriggerPreview = computed(() => {
  if (!autoAddTrigger.value) return "";
  const loraName = values.value["lora_name"];
  if (typeof loraName !== "string" || !loraName) return "";
  const lora = loras.value.find((l) => l.name === loraName);
  const strength = Number(values.value["strength_model"] ?? 1);
  if (!lora || !lora.trigger_words || strength <= 0) return "";
  const text = typeof values.value["text"] === "string" ? values.value["text"] : "";
  if (text.toLowerCase().includes(lora.trigger_words.toLowerCase())) return "";
  return lora.trigger_words;
});
</script>

<template>
  <Modal
    :title="props.preset ? '再生成' : '新建生成'"
    :width="step === totalSteps ? '1200px' : '620px'"
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

    <div v-else class="cc-modal-body" :class="{ 'is-final-step': step === totalSteps }">
      <div
        class="cc-modal-left"
        :class="{ 'is-full-width': step !== totalSteps }"
      >
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
        <el-form label-width="90px" label-position="left" class="cc-params-form">
        <el-form-item v-if="hasSizeFields" label="尺寸">
          <div class="cc-size-control">
            <div class="cc-size-row">
              <el-select
                v-model="ratioLabel"
                placeholder="常用比例"
                clearable
                style="width: 120px"
                @update:model-value="(v: string | number | undefined) => v && applyRatioPreset(String(v))"
              >
                <el-option
                  v-for="r in RATIO_PRESETS"
                  :key="r.label"
                  :value="r.label"
                  :label="r.label"
                />
              </el-select>
              <el-select
                placeholder="分辨率预设"
                clearable
                style="width: 150px"
                @update:model-value="(v: string | number | undefined) => v && applyResPreset(String(v))"
              >
                <el-option
                  v-for="r in RES_PRESETS"
                  :key="r.label"
                  :value="r.label"
                  :label="r.label"
                />
              </el-select>
              <el-checkbox
                :model-value="lockRatio"
                @update:model-value="(v: boolean) => onToggleLockRatio(v)"
              >锁定比例</el-checkbox>
            </div>
            <div class="cc-size-row">
              <el-input-number
                :model-value="Number(values['width']) || 0"
                @update:model-value="(v: number | undefined) => { values['width'] = (v ?? 0); onSizeChange('width'); }"
                :min="widthField?.min"
                :max="widthField?.max"
                :step="widthField?.step ?? 16"
                controls-position="right"
                style="width: 140px"
              />
              <span class="cc-size-times">×</span>
              <el-input-number
                :model-value="Number(values['height']) || 0"
                @update:model-value="(v: number | undefined) => { values['height'] = (v ?? 0); onSizeChange('height'); }"
                :min="heightField?.min"
                :max="heightField?.max"
                :step="heightField?.step ?? 16"
                controls-position="right"
                style="width: 140px"
              />
            </div>
          </div>
        </el-form-item>

        <el-form-item
          v-for="f in fields.filter((x) => !(x.key === 'width' || x.key === 'height'))"
          :key="f.key"
          :label="f.label"
          :required="f.required"
        >
          <template v-if="f.type === 'seed'">
            <div class="cc-seed-row">
              <el-checkbox
                :model-value="!!randomFlags[`${f.key}_random`]"
                @update:model-value="(v: boolean) => randomFlags[`${f.key}_random`] = v"
              >随机</el-checkbox>
              <el-input-number
                v-if="!randomFlags[`${f.key}_random`]"
                :model-value="values[f.key] as number | undefined"
                @update:model-value="(v: number | undefined) => values[f.key] = (v ?? 0)"
                :min="f.min"
                :max="f.max"
                :step="f.step"
                controls-position="right"
              />
            </div>
          </template>
          <el-input-number
            v-else-if="f.type === 'number'"
            :model-value="values[f.key] as number | undefined"
            @update:model-value="(v: number | undefined) => values[f.key] = (v ?? 0)"
            :min="f.min"
            :max="f.max"
            :step="f.step"
            controls-position="right"
            style="width: 100%"
          />
          <el-select
            v-else-if="f.type === 'select'"
            :model-value="values[f.key]"
            @update:model-value="(v: string | number) => values[f.key] = v"
            style="width: 100%"
          >
            <el-option
              v-for="opt in loraOptions(f)"
              :key="opt"
              :value="opt"
              :label="opt"
            />
          </el-select>
          <el-input
            v-else
            type="textarea"
            :rows="8"
            :model-value="values[f.key]"
            @update:model-value="(v: string) => values[f.key] = v ?? ''"
          />
          <div v-if="isLoraField(f)" class="cc-lora-toggle">
            <el-checkbox
              :model-value="autoAddTrigger"
              @update:model-value="(v: boolean) => autoAddTrigger = v"
            >自动添加 LoRA 触发词</el-checkbox>
          </div>
        </el-form-item>
        </el-form>
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
        <el-alert
          v-if="autoTriggerPreview"
          type="info"
          :closable="false"
          show-icon
          class="cc-trigger-hint"
        >
          <template #title>
            将自动在正面提示词中添加 LoRA 触发词:{{ autoTriggerPreview }}
          </template>
        </el-alert>
        <p v-if="fields.length === 0" class="cc-hint">此工作流无参数,直接生成。</p>
      </div>

      <el-alert
          v-if="submitError"
          :title="submitError"
          type="error"
          :closable="false"
          show-icon
        />
        <el-alert
          v-if="abortError"
          :title="abortError"
          type="error"
          :closable="false"
          show-icon
        />
      </div>

      <template v-if="step === totalSteps">
        <div class="cc-modal-divider"></div>

        <div class="cc-modal-right">
        <div class="cc-image-panel">
          <div class="cc-image-main">
            <el-icon v-if="activeGenId && (activeStatus === 'queued' || activeStatus === 'running')" class="is-loading cc-image-loading">
              <Loading />
            </el-icon>
            <img v-else-if="mainImageUrl" :src="mainImageUrl" alt="生成结果" class="cc-image-main-img" />
            <div v-else-if="activeGenId && activeStatus === 'failed'" class="cc-image-error">
              <p>{{ activeError || '生成失败' }}</p>
            </div>
            <div v-else class="cc-image-empty">
              <span class="cc-image-empty-icon">🖼</span>
              <p>点击「生成」开始</p>
            </div>
          </div>
          <div v-if="activeGenId" class="cc-image-status">
            <span v-if="activeStatus === 'queued'">排期中…</span>
            <span v-else-if="activeStatus === 'running'">生成中…</span>
            <span v-else-if="activeStatus === 'success'">完成</span>
            <span v-else-if="activeStatus === 'failed'">失败</span>
          </div>
          <div v-if="history.length > 0" class="cc-image-history">
            <div
              v-for="(item, idx) in history"
              :key="item.id"
              class="cc-image-thumb"
              :class="{ 'is-active': mainImageUrl === item.imageUrl }"
              @click="showThumbnail(item.imageUrl)"
            >
              <img :src="item.imageUrl" :alt="`结果 ${idx + 1}`" />
            </div>
          </div>
        </div>
      </div>
      </template>
    </div>

    <template #footer>
      <template v-if="loading || fetchError || configs.length === 0">
        <el-button type="primary" @click="emit('close')">关闭</el-button>
      </template>
      <template v-else>
        <el-button :disabled="step === 1" @click="back">上一步</el-button>
        <el-button @click="emit('close')">取消</el-button>
        <el-button v-if="showGoto" @click="emit('goto')">跳转至生成界面</el-button>
        <el-button
          v-if="step < totalSteps"
          type="primary"
          :disabled="!canProceed"
          @click="next"
        >下一步</el-button>
        <template v-else>
          <el-button
            v-if="activeGenId && (activeStatus === 'queued' || activeStatus === 'running')"
            type="danger"
            plain
            :loading="aborting"
            @click="abort"
          >
            <el-icon style="margin-right: 4px"><CircleClose /></el-icon>
            中止
          </el-button>
          <el-button
            v-else
            type="primary"
            :loading="submitting"
            @click="submit"
          >生成</el-button>
        </template>
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
.cc-params-form {
  width: 100%;
}
.cc-size-control {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  width: 100%;
}
.cc-size-row {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}
.cc-size-times {
  color: #94a3b8;
  font-size: 0.9rem;
  flex-shrink: 0;
}
:deep(.cc-params-form .el-form-item__content) {
  width: 100%;
}
:deep(.cc-params-form .el-select) {
  width: 100%;
}
.cc-lora-toggle {
  margin-bottom: 0.25rem;
  display: flex;
  gap: 1rem;
  align-items: center;
}
.cc-trigger-hint {
  margin-top: 0.25rem;
}
.cc-modal-body {
  display: flex;
  gap: 24px;
}
.cc-modal-body.is-final-step {
  min-height: 400px;
}
.cc-modal-left {
  width: 480px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}
.cc-modal-left.is-full-width {
  width: 100%;
}
.cc-modal-divider {
  width: 1px;
  background: #e2e8f0;
  flex-shrink: 0;
}
.cc-modal-right {
  flex: 1;
  min-width: 400px;
  display: flex;
  flex-direction: column;
}
.cc-image-panel {
  display: flex;
  flex-direction: column;
  gap: 12px;
  height: 100%;
}
.cc-image-main {
  flex: 1;
  background: #f8fafc;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  min-height: 360px;
}
.cc-image-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  color: #94a3b8;
}
.cc-image-empty-icon {
  font-size: 3rem;
  opacity: 0.6;
}
.cc-image-empty p {
  margin: 0;
  font-size: 0.9rem;
}
.cc-image-loading {
  font-size: 3rem;
  color: #0ea5e9;
}
.cc-image-main-img {
  max-width: 100%;
  max-height: 100%;
  object-fit: contain;
}
.cc-image-error {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  color: #ef4444;
  padding: 1rem;
  text-align: center;
}
.cc-image-status {
  font-size: 0.85rem;
  color: #475569;
  flex-shrink: 0;
}
.cc-image-history {
  display: flex;
  gap: 8px;
  overflow-x: auto;
  flex-shrink: 0;
  padding: 4px 0;
}
.cc-image-thumb {
  width: 80px;
  height: 80px;
  border-radius: 6px;
  overflow: hidden;
  cursor: pointer;
  flex-shrink: 0;
  border: 2px solid transparent;
  transition: transform 0.15s;
}
.cc-image-thumb:hover {
  transform: scale(1.05);
}
.cc-image-thumb.is-active {
  border-color: var(--el-color-primary);
  box-shadow: 0 0 0 2px rgba(14, 165, 233, 0.2);
}
.cc-image-thumb img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}
</style>
