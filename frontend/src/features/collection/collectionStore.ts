import { useEffect } from "react";
import { useSyncExternalStore } from "react";
import { useQueryClient } from "@tanstack/react-query";

// Tracks a background collection job (collect → process → fingerprint → score),
// which runs in Celery AFTER the HTTP call returns. The request is instant, so
// without this the UI would look idle while ~1–2 min of real work happens.
// Module-level + localStorage so the indicator survives tab switches and refresh.
type Collection = { label: string; startedAt: number } | null;

const KEY = "afm.collection";
const DURATION_MS = 60_000; // hard cap; we end EARLIER as soon as produced data appears

function load(): Collection {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return null;
    const c = JSON.parse(raw) as Collection;
    if (!c || Date.now() - c.startedAt > DURATION_MS) return null; // expired across a refresh
    return c;
  } catch {
    return null;
  }
}

let active: Collection = load();
let timer: ReturnType<typeof setTimeout> | null = null;
const listeners = new Set<() => void>();
const emit = () => listeners.forEach((l) => l());

export function beginCollection(label: string): void {
  active = { label, startedAt: Date.now() };
  localStorage.setItem(KEY, JSON.stringify(active));
  if (timer) clearTimeout(timer);
  timer = setTimeout(endCollection, DURATION_MS);
  emit();
}

export function endCollection(): void {
  active = null;
  localStorage.removeItem(KEY);
  if (timer) { clearTimeout(timer); timer = null; }
  emit();
}

function subscribe(cb: () => void): () => void {
  listeners.add(cb);
  return () => listeners.delete(cb);
}

export function useCollection(): Collection {
  return useSyncExternalStore(subscribe, () => active);
}

// While a collection is in flight, periodically refetch the data it produces so
// new accounts/materials appear without the analyst hitting refresh.
export function useCollectionAutoRefresh(): void {
  const collection = useCollection();
  const qc = useQueryClient();
  useEffect(() => {
    if (!collection) return;
    // re-arm the auto-expiry after a refresh (the setTimeout above is lost on reload)
    const remaining = Math.max(0, DURATION_MS - (Date.now() - collection.startedAt));
    const stop = setTimeout(endCollection, remaining);
    const len = (k: string) => ((qc.getQueryData([k]) as unknown[]) ?? []).length;
    const base = { accounts: len("accounts"), materials: len("content-triage") };
    const poll = setInterval(async () => {
      await Promise.all([
        qc.invalidateQueries({ queryKey: ["accounts"] }),
        qc.invalidateQueries({ queryKey: ["content-triage"] }),
        qc.invalidateQueries({ queryKey: ["watchlist"] }),
      ]);
      // Finish as soon as the collection's output shows up (don't wait out the cap).
      if (len("accounts") > base.accounts || len("content-triage") > base.materials) {
        endCollection();
      }
    }, 3000);
    return () => { clearTimeout(stop); clearInterval(poll); };
  }, [collection, qc]);
}
