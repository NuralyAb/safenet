import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, type WatchlistNotification } from "../../api/client";

const MAX_VISIBLE = 4;

/**
 * Global toast stack (top-right) for "new video from a monitored account" alerts.
 * Polls every 20s; each new video is ALSO auto-analysed by the sweep, so the toast
 * already carries its risk score. Click a toast → open the author's dossier.
 */
export function NotificationToasts({ onOpen }: { onOpen?: (account: string) => void }) {
  const qc = useQueryClient();
  const q = useQuery<WatchlistNotification[]>({
    queryKey: ["notifications"],
    queryFn: () => api.getNotifications(true),
    refetchInterval: 20_000,
    refetchOnWindowFocus: true,
  });
  const read = useMutation({
    mutationFn: (id: number) => api.readNotification(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["notifications"] }),
  });
  const readAll = useMutation({
    mutationFn: () => api.readAllNotifications(),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["notifications"] }),
  });

  const items = q.data ?? [];
  if (items.length === 0) return null;

  const visible = items.slice(0, MAX_VISIBLE);
  const extra = items.length - visible.length;

  const open = (n: WatchlistNotification) => {
    if (onOpen) onOpen(n.author);
    read.mutate(n.id);
  };

  return (
    <div className="toast-stack" role="region" aria-label="Уведомления мониторинга">
      {visible.map((n) => (
        <div key={n.id} className="alert-toast" role="status" aria-live="polite">
          <div className="alert-body" onClick={() => open(n)} role="button" tabIndex={0}
               onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && open(n)}
               title="Открыть досье аккаунта">
            <div className="alert-head">
              <span className="alert-dot" />
              <strong>{n.reason === "high_risk" ? "⚠ Радар: найдено мошенничество" : "Новое видео под наблюдением"}</strong>
            </div>
            <div className="alert-account">{n.author || "(аккаунт)"}</div>
            <div className="muted small">
              {n.source || "источник"}
              {n.threat_level && <> · <span className={`badge threat ${n.threat_level}`}>{n.score} · {n.threat_level}</span></>}
            </div>
            <div className="muted small">Видео уже проанализировано — откройте досье или «Материалы».</div>
          </div>
          <button className="alert-x" aria-label="Закрыть" title="Закрыть"
                  onClick={() => read.mutate(n.id)}>×</button>
        </div>
      ))}
      {(extra > 0 || items.length > 1) && (
        <button className="btn btn-ghost btn-sm toast-dismiss-all"
                disabled={readAll.isPending} onClick={() => readAll.mutate()}>
          {extra > 0 ? `Ещё ${extra} · скрыть все` : "Скрыть все"}
        </button>
      )}
    </div>
  );
}
