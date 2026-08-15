import { storeToRefs } from "pinia";

import { useNsfwStore } from "@/stores/nsfw";

export function useNsfwFilter() {
  const store = useNsfwStore();
  const { enabled } = storeToRefs(store);
  return {
    enabled,
    setEnabled: store.setEnabled,
    toggle: store.toggle,
  };
}
