<script setup lang="ts">
import { Delete, Plus } from "@element-plus/icons-vue";
import { computed } from "vue";
import type { LoraEntry, LoraSummary } from "@/types/api";

const props = withDefaults(
  defineProps<{
    modelValue: LoraEntry[];
    loras: LoraSummary[];
    mainModel?: string | null;
    nsfwEnabled?: boolean;
    emptyLoraName?: string;
    defaultStrength?: number;
  }>(),
  {
    mainModel: null,
    nsfwEnabled: true,
    emptyLoraName: "",
    defaultStrength: 1,
  },
);
const emit = defineEmits<{ "update:modelValue": [LoraEntry[]] }>();

const filteredOptions = computed<string[]>(() => {
  const candidates = props.loras
    .filter((l) => !l.deleted_from_comfyui)
    .map((l) => l.name);
  const nsfwFiltered = props.nsfwEnabled
    ? candidates
    : candidates.filter((name) => {
        const lora = props.loras.find((l) => l.name === name);
        return lora && !lora.is_nsfw;
      });
  if (!props.mainModel) return nsfwFiltered;
  const filtered = nsfwFiltered
    .map((name) => props.loras.find((l) => l.name === name))
    .filter((l) => l && l.models.includes(props.mainModel!))
    .map((l) => l!.name);
  return filtered.length > 0 ? filtered : nsfwFiltered;
});

function addEntry() {
  emit("update:modelValue", [
    ...props.modelValue,
    { lora_name: props.emptyLoraName, strength_model: props.defaultStrength },
  ]);
}

function removeEntry(idx: number) {
  emit("update:modelValue", props.modelValue.filter((_, i) => i !== idx));
}

function patchEntry(idx: number, patch: Partial<LoraEntry>) {
  emit(
    "update:modelValue",
    props.modelValue.map((e, i) => (i === idx ? { ...e, ...patch } : e)),
  );
}
</script>

<template>
  <div class="cc-lora-array">
    <div v-if="modelValue.length === 0" class="cc-lora-empty">
      尚未添加 LoRA,点击下方按钮添加。
    </div>
    <div v-for="(entry, i) in modelValue" :key="i" class="cc-lora-row">
      <el-select
        :model-value="entry.lora_name"
        filterable
        placeholder="选择 LoRA"
        class="cc-lora-name"
        @update:model-value="(v: string) => patchEntry(i, { lora_name: v })"
      >
        <el-option
          v-for="opt in filteredOptions"
          :key="opt"
          :value="opt"
          :label="opt"
        />
      </el-select>
      <el-input-number
        :model-value="entry.strength_model"
        :min="-100"
        :max="100"
        :step="0.01"
        :precision="2"
        controls-position="right"
        class="cc-lora-strength"
        @update:model-value="(v: number | undefined) => patchEntry(i, { strength_model: v ?? 0 })"
      />
      <el-button
        :icon="Delete"
        link
        type="danger"
        @click="removeEntry(i)"
      />
    </div>
    <el-button :icon="Plus" plain size="small" @click="addEntry">
      添加 LoRA
    </el-button>
  </div>
</template>

<style lang="scss" scoped>
.cc-lora-array {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.cc-lora-row {
  display: flex;
  align-items: center;
  gap: 8px;
}
.cc-lora-name {
  flex: 1;
  min-width: 0;
}
.cc-lora-strength {
  width: 120px;
  flex-shrink: 0;
}
.cc-lora-empty {
  color: #94a3b8;
  font-size: 0.85rem;
  padding: 4px 0;
}
</style>
