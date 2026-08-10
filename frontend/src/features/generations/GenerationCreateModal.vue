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
    <el-form label-position="top">
      <el-form-item label="工作流">
        <el-select v-model="workflowId" @change="selectWorkflow(workflowId)">
          <el-option
            v-for="c in configs"
            :key="c.workflow_id"
            :value="c.workflow_id"
            :label="c.workflow_name"
          />
        </el-select>
      </el-form-item>

      <template v-if="current">
        <el-form-item
          v-for="f in fields"
          :key="f.key"
          :label="f.label"
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
          <el-input
            v-else
            type="textarea"
            :rows="3"
            :model-value="values[f.key]"
            @update:model-value="(v: string) => values[f.key] = v ?? ''"
          />
        </el-form-item>
      </template>
      <el-alert
        v-else-if="configs.length === 0"
        type="info"
        title="没有可用的已配置工作流，请先在工作流页配置生成参数。"
        :closable="false"
        show-icon
      />

      <el-alert
        v-if="submitError"
        :title="submitError"
        type="error"
        :closable="false"
        show-icon
      />
    </el-form>

    <template #footer>
      <el-button @click="emit('close')">取消</el-button>
      <el-button
        type="primary"
        :loading="submitting"
        :disabled="!current"
        @click="submit"
      >
        {{ submitting ? "提交中…" : "生成" }}
      </el-button>
    </template>
  </Modal>
</template>

<style lang="scss" scoped>
.cc-seed-row {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}
</style>
