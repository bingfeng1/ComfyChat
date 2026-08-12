import { ref } from "vue";

const STORAGE_KEY = "cc_nsfw_enabled";

export function useNsfwFilter() {
  const enabled = ref(localStorage.getItem(STORAGE_KEY) !== "false");

  function setEnabled(value: boolean) {
    enabled.value = value;
    localStorage.setItem(STORAGE_KEY, String(value));
  }

  function toggle() {
    setEnabled(!enabled.value);
  }

  return {
    enabled,
    setEnabled,
    toggle,
  };
}
