import { defineStore } from "pinia";

const STORAGE_KEY = "cc_nsfw_enabled";

function readInitial(): boolean {
  if (typeof localStorage === "undefined") return true;
  return localStorage.getItem(STORAGE_KEY) !== "false";
}

export const useNsfwStore = defineStore("nsfw", {
  state: () => ({
    enabled: readInitial(),
  }),
  actions: {
    setEnabled(value: boolean) {
      this.enabled = value;
      if (typeof localStorage !== "undefined") {
        localStorage.setItem(STORAGE_KEY, String(value));
      }
    },
    toggle() {
      this.setEnabled(!this.enabled);
    },
  },
});
