import { useSyncExternalStore } from "react";
import type { ContentTriageItem } from "../../api/client";

/**
 * Module-level store for the Hunter feed: reveals real clips one at a time
 * (every 30–50s) at the bottom of the list and accumulates them. Lives outside
 * React so the hunt keeps running — and the found videos persist — even when the
 * analyst navigates to another screen and back.
 */
type Snap = { revealed: ContentTriageItem[]; running: boolean };

const MIN_GAP = 30_000;   // 30s
const MAX_GAP = 50_000;   // 50s
const FIRST_GAP = 3_000;  // first hit lands quickly for feedback

let snap: Snap = { revealed: [], running: false };
let queue: ContentTriageItem[] = [];
let timer: ReturnType<typeof setTimeout> | null = null;
const listeners = new Set<() => void>();

function emit(next: Snap) {
  snap = next;
  listeners.forEach((l) => l());
}

function tick() {
  timer = null;
  const next = queue.shift();
  if (next) emit({ revealed: [...snap.revealed, next], running: queue.length > 0 });
  if (queue.length > 0) {
    timer = setTimeout(tick, MIN_GAP + Math.floor(Math.random() * (MAX_GAP - MIN_GAP)));
  } else {
    emit({ revealed: snap.revealed, running: false });
  }
}

/** Begin (or extend) the hunt with a candidate pool; already-shown clips are skipped. */
export function startHunt(pool: ContentTriageItem[]): void {
  const seen = new Set(snap.revealed.map((c) => c.content_id));
  queue = pool.filter((c) => !seen.has(c.content_id));
  if (queue.length === 0) return;
  emit({ revealed: snap.revealed, running: true });
  if (!timer) timer = setTimeout(tick, FIRST_GAP);
}

export function stopHunt(): void {
  if (timer) { clearTimeout(timer); timer = null; }
  queue = [];
  emit({ revealed: snap.revealed, running: false });
}

export function resetHunt(): void {
  if (timer) { clearTimeout(timer); timer = null; }
  queue = [];
  emit({ revealed: [], running: false });
}

function subscribe(cb: () => void) {
  listeners.add(cb);
  return () => { listeners.delete(cb); };
}

export function useHunterFeed(): Snap {
  return useSyncExternalStore(subscribe, () => snap, () => snap);
}
