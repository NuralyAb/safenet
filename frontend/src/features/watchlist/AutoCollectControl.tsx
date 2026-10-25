import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, type MonitoringSchedule } from "../../api/client";

/** «Запустить / Остановить автосбор» — auto-collection only runs when started by hand.

 * Every sweep spends paid AI calls (speech, vision, LLM), so it is off by default and
 * the state is visible everywhere (sidebar) — not hidden behind a settings checkbox.
 */
export function AutoCollectControl({ compact = false }: { compact?: boolean }) {
  const qc = useQueryClient();
  const q = useQuery<MonitoringSchedule>({
    queryKey: ["monitoring-schedule"], queryFn: api.getSchedule, refetchInterval: 30_000,
  });
  const done = () => {
    qc.invalidateQueries({ queryKey: ["monitoring-schedule"] });
    qc.invalidateQueries({ queryKey: ["watchlist"] });
  };
  const start = useMutation({ mutationFn: api.startAutoCollect, onSuccess: done });
  const stop = useMutation({ mutationFn: api.stopAutoCollect, onSuccess: done });

  const on = q.data?.enabled ?? false;
  const busy = start.isPending || stop.isPending || q.isLoading;
  const err = (start.error || stop.error) as Error | null;

  return (
    <div className={`autocollect${on ? " on" : ""}${compact ? " compact" : ""}`}>
      <div className="autocollect-state">
        <span className={`autocollect-dot${on ? " on" : ""}`} />
        <span>Автосбор: <b>{on ? "работает" : "остановлен"}</b></span>
      </div>
      {on ? (
        <button className="btn btn-danger btn-sm" disabled={busy} onClick={() => stop.mutate()}
                title="Остановить: задачи автосбора в очереди отменяются до платной обработки">
          {stop.isPending ? "…" : "Остановить"}
        </button>
      ) : (
        <button className="btn btn-primary btn-sm" disabled={busy} onClick={() => start.mutate()}
                title="Запустить: сразу обойти все цели мониторинга, дальше — по расписанию">
          {start.isPending ? "…" : "Запустить"}
        </button>
      )}
      {!compact && start.data && on && (
        <span className="muted small">отправлено целей: {start.data.dispatched}</span>
      )}
      {err && <span className="err small">{err.message}</span>}
    </div>
  );
}
