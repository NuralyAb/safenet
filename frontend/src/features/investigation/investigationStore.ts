import { useSyncExternalStore } from "react";

// Active investigation id, persisted so it survives BOTH tab switches (views
// unmount on navigation) AND a full page refresh (localStorage). React-query
// re-subscribes on return and refetches the current status/report.
const KEY = "afm.investigation";

let workflowId: string | null = localStorage.getItem(KEY);
const listeners = new Set<() => void>();
const emit = () => listeners.forEach((l) => l());

export function setInvestigationId(id: string | null): void {
  workflowId = id;
  if (id) localStorage.setItem(KEY, id);
  else localStorage.removeItem(KEY);
  emit();
}

function subscribe(cb: () => void): () => void {
  listeners.add(cb);
  return () => listeners.delete(cb);
}

export function useInvestigationId(): string | null {
  return useSyncExternalStore(subscribe, () => workflowId);
}
