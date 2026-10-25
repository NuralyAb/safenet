import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, TRACK_RU, type MonitorEvent, type MonitorStatus, type SafeNetRisk } from "../../api/client";
import { HighlightedText, LevelBadge, RiskExplain, TrackBadge } from "./RiskExplain";

const TRACKS = ["lottery", "casino", "pyramid"] as const;
const PLATFORM_RU: Record<string, string> = {
  telegram: "Telegram", instagram: "Instagram", tiktok: "TikTok", youtube: "YouTube",
};

function ago(ts: number | null | undefined, now: number): string {
  if (!ts) return "—";
  const s = Math.max(0, Math.round(now / 1000 - ts));
  if (s < 60) return `${s} с назад`;
  if (s < 3600) return `${Math.round(s / 60)} мин назад`;
  return `${Math.round(s / 3600)} ч назад`;
}

function views(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return String(n);
}

const asRisk = (e: MonitorEvent): SafeNetRisk => ({
  score: e.score, threat_level: e.threat_level, breakdown: e.breakdown, recommendation: "", track: e.track,
});

/** «Мониторинг схем» — the system finds the three schemes by itself, while the analyst keeps it on. */
export function MonitorView({ onOpenDossier }: { onOpenDossier?: (account: string) => void }) {
  const qc = useQueryClient();
  const status = useQuery<MonitorStatus>({
    queryKey: ["monitor-status"], queryFn: api.getMonitorStatus,
    refetchInterval: (q) => (q.state.data?.enabled ? 2000 : 15_000),
  });
  const on = status.data?.enabled ?? false;

  // live feed: keep what we have, ask only for newer events
  const [track, setTrack] = useState("");
  const [all, setAll] = useState(false);
  const [events, setEvents] = useState<MonitorEvent[]>([]);
  const [fresh, setFresh] = useState<Set<number>>(new Set());
  const [open, setOpen] = useState<number | null>(null);
  // the feed is the latest run only: a new start begins empty, «Остановить» keeps what was found
  const since = status.data?.started_at ?? 0;
  const feedKey = `${track}|${all}|${since}`;
  const lastId = useRef<Record<string, number>>({});
  useEffect(() => { lastId.current[feedKey] = 0; setEvents([]); }, [feedKey]);
  const feed = useQuery<MonitorEvent[]>({
    queryKey: ["monitor-feed", feedKey],
    queryFn: () => api.getMonitorFeed(lastId.current[feedKey] ?? 0, !all, track, since),
    refetchInterval: on ? 2000 : false,
  });
  useEffect(() => {
    const got = feed.data ?? [];
    if (!got.length) return;
    lastId.current[feedKey] = Math.max(lastId.current[feedKey] ?? 0, ...got.map((e) => e.id));
    setEvents((prev) => {
      const seen = new Set(prev.map((e) => e.id));
      const add = got.filter((e) => !seen.has(e.id));
      if (prev.length) setFresh(new Set(add.map((e) => e.id)));
      return [...add, ...prev].slice(0, 80);
    });
  }, [feed.data]);

  const done = () => qc.invalidateQueries({ queryKey: ["monitor-status"] });
  const start = useMutation({ mutationFn: api.startMonitor, onSuccess: done });
  const stop = useMutation({ mutationFn: api.stopMonitor, onSuccess: done });
  const [channel, setChannel] = useState("");
  const add = useMutation({
    mutationFn: () => api.addMonitorSource(channel), onSuccess: () => { setChannel(""); done(); },
  });
  const toggle = useMutation({
    mutationFn: (v: { id: number; active: boolean }) => api.toggleMonitorSource(v.id, v.active), onSuccess: done,
  });

  const [now, setNow] = useState(Date.now());
  useEffect(() => { const t = setInterval(() => setNow(Date.now()), 1000); return () => clearInterval(t); }, []);

  const st = status.data;
  const high = st ? TRACKS.reduce((s, t) => s + st.by_track[t].high, 0) : 0;
  const maxBar = Math.max(1, ...(st?.timeline ?? []).map((b) => b.lottery + b.casino + b.pyramid));
  const err = (start.error || stop.error) as Error | null;

  return (
    <div className="stack">
      <section className={`card mon-control${on ? " on" : ""}`}>
        <div className="card-pad mon-control-row">
          <div className="mon-state">
            <span className={`mon-pulse${on ? " on" : ""}`} />
            <div>
              <div className="mon-state-title">{on ? "Мониторинг работает" : "Мониторинг остановлен"}</div>
              <div className="muted small">
                {on
                  ? <>с {st?.started_at ? new Date(st.started_at * 1000).toLocaleTimeString() : "—"} · источников: {st?.active_sources ?? 0} · каждый новый пост проверяется сразу</>
                  : <>Запускается и останавливается только кнопкой. Источники опрашиваются по расписанию, находки идут в ленту и в очередь «Материалы».</>}
              </div>
            </div>
          </div>
          {on ? (
            <button className="btn btn-danger" disabled={stop.isPending} onClick={() => stop.mutate()}>
              {stop.isPending ? "…" : "Остановить мониторинг"}
            </button>
          ) : (
            <button className="btn btn-primary" disabled={start.isPending} onClick={() => start.mutate()}>
              {start.isPending ? "…" : "Запустить мониторинг"}
            </button>
          )}
        </div>
        {err && <p className="err small card-pad">{err.message}</p>}
      </section>

      <div className="dash-kpis">
        <div className="kpi"><div className="kpi-top"><span className="kpi-label">Проверено постов</span></div>
          <div className="kpi-value">{(st?.scanned ?? 0).toLocaleString("ru-RU")}</div>
          <div className="muted small">с момента запуска</div></div>
        <div className="kpi alert"><div className="kpi-top"><span className="kpi-label">Найдено признаков</span></div>
          <div className="kpi-value">{st?.flagged ?? 0}</div>
          <div className="muted small">риск ≥ 40 → в очередь</div></div>
        <div className="kpi"><div className="kpi-top"><span className="kpi-label">Высокий риск</span></div>
          <div className="kpi-value">{high}</div>
          <div className="muted small">приоритетная проверка</div></div>
        <div className="kpi"><div className="kpi-top"><span className="kpi-label">Доля находок</span></div>
          <div className="kpi-value">{st && st.scanned ? Math.round((100 * st.flagged) / st.scanned) : 0}%</div>
          <div className="muted small">остальное — обычные посты</div></div>
      </div>

      <div className="sn-track-tiles mon-tracks">
        {TRACKS.map((t) => (
          <button key={t} className={`sn-tile sn-track-${t}${track === t ? " selected" : ""}`}
                  onClick={() => setTrack(track === t ? "" : t)} title="Показать в ленте только этот трек">
            <div className="sn-tile-title">{TRACK_RU[t]}</div>
            <div className="sn-tile-nums">
              <b>{st?.by_track[t].high ?? 0}</b> высокий · <b>{st?.by_track[t].medium ?? 0}</b> средний
            </div>
            <div className="mon-spark">
              {(st?.timeline ?? []).map((b) => (
                <span key={b.minute} style={{ height: `${Math.max(4, (100 * b[t]) / maxBar)}%` }}
                      className={b[t] ? "" : "zero"} />
              ))}
            </div>
          </button>
        ))}
      </div>

      <div className="mon-cols">
        <section className="card">
          <div className="card-head">
            <h2>Лента находок{track ? ` · ${TRACK_RU[track]}` : ""}</h2>
            <label className="muted small mon-toggle">
              <input type="checkbox" checked={all} onChange={(e) => setAll(e.target.checked)} /> показывать и чистые посты
            </label>
          </div>
          <div className="card-pad">
            {events.length === 0 && (
              <div className="empty">
                <h3>{on ? "Ждём новые посты…" : "Лента пуста"}</h3>
                <p>{on ? "Первые результаты появятся через несколько секунд." : "Нажмите «Запустить мониторинг» — система сама обойдёт источники."}</p>
              </div>
            )}
            <ul className="mon-feed">
              {events.map((e) => (
                <li key={e.id} className={`mon-item${e.flagged ? "" : " clean"}${fresh.has(e.id) ? " fresh" : ""}`}>
                  <div className="mon-item-head">
                    <span className={`mon-platform p-${e.platform}`}>{PLATFORM_RU[e.platform] ?? e.platform}</span>
                    <button className="linklike mon-author" onClick={() => onOpenDossier?.(e.author)}>{e.title || e.author}</button>
                    <span className="muted small">{ago(e.ts, now)} · 👁 {views(e.views)}</span>
                    <span className="mon-spacer" />
                    {e.flagged ? <><TrackBadge track={e.track} /><LevelBadge level={e.threat_level} score={e.score} /></>
                      : <span className="badge threat LOW">{e.score} · чисто</span>}
                  </div>
                  <div className="mon-text">
                    {e.flagged ? <HighlightedText text={e.text} risk={asRisk(e)} /> : e.text}
                  </div>
                  {e.flagged && (
                    <div className="mon-signals">
                      {e.signals.slice(0, 3).map((s, i) => (
                        <span key={i} className="mon-sig" title={s.label}>
                          <b>+{Math.round(s.contribution)}</b> {s.label}{s.quote ? <> · «{s.quote}»</> : null}
                        </span>
                      ))}
                      <button className="linklike small" onClick={() => setOpen(open === e.id ? null : e.id)}>
                        {open === e.id ? "свернуть" : "разбор →"}
                      </button>
                    </div>
                  )}
                  {open === e.id && <div className="mon-explain"><RiskExplain risk={asRisk(e)} compact /></div>}
                </li>
              ))}
            </ul>
          </div>
        </section>

        <div className="stack">
          <section className="card">
            <div className="card-head"><h2>Источники</h2><span className="hint">опрос по расписанию</span></div>
            <div className="card-pad">
              <table className="table mon-sources">
                <thead><tr><th>Источник</th><th>Проверено</th><th>Находок</th><th>Опрос</th><th /></tr></thead>
                <tbody>
                  {(st?.sources ?? []).map((s) => (
                    <tr key={s.id} className={s.active ? "" : "off"}>
                      <td>
                        <div className="mon-src-name">{s.title || s.handle}</div>
                        <div className="muted small">{PLATFORM_RU[s.platform] ?? s.platform} · @{s.handle}</div>
                        {s.last_error && <div className="err small">{s.last_error}</div>}
                      </td>
                      <td>{s.scanned}</td>
                      <td>{s.flagged ? <b className="mon-hits">{s.flagged}</b> : 0}</td>
                      <td className="muted small">{ago(s.last_polled_ts, now)}</td>
                      <td>
                        <input type="checkbox" checked={s.active} title={s.active ? "Не опрашивать" : "Опрашивать"}
                               onChange={(ev) => toggle.mutate({ id: s.id, active: ev.target.checked })} />
                      </td>
                    </tr>
                  ))}
                  {!st?.sources.length && (
                    <tr><td colSpan={5} className="muted small">Источники появятся после первого запуска.</td></tr>
                  )}
                </tbody>
              </table>
              <div className="row mon-add">
                <input className="input" value={channel} placeholder="@канал или t.me/канал"
                       onChange={(e) => setChannel(e.target.value)}
                       onKeyDown={(e) => e.key === "Enter" && channel.trim() && add.mutate()} />
                <button className="btn" disabled={!channel.trim() || add.isPending} onClick={() => add.mutate()}>
                  Добавить Telegram-канал
                </button>
              </div>
              {add.error && <p className="err small">{(add.error as Error).message}</p>}
              <p className="muted small" style={{ marginTop: 8 }}>
                Публичные Telegram-каналы читаются без авторизации. WhatsApp не мониторится — у него нет публичной
                ленты; экспорт группы проверяется во вкладке «Проверка контента → Группа / чат».
              </p>
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}
