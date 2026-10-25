import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, type MonitoringSchedule, type WatchTarget } from "../../api/client";
import { TrashIcon } from "../../components/icons";
import { AutoCollectControl } from "./AutoCollectControl";

const SOURCES = ["youtube", "telegram", "tiktok", "instagram"];

// Per-target cadence presets. `null` = use the global default.
const FREQ: { label: string; seconds: number | null }[] = [
  { label: "по умолчанию", seconds: null },
  { label: "каждые 10 мин", seconds: 600 },
  { label: "каждые 30 мин", seconds: 1800 },
  { label: "раз в час", seconds: 3600 },
  { label: "раз в 6 часов", seconds: 21600 },
  { label: "2 раза в день", seconds: 43200 },
  { label: "раз в день", seconds: 86400 },
  { label: "раз в 2 дня", seconds: 172800 },
];

function freqShort(s: number): string {
  if (s % 86400 === 0) { const d = s / 86400; return d === 1 ? "раз в день" : `раз в ${d} дн`; }
  if (s % 3600 === 0) { const h = s / 3600; return h === 1 ? "раз в час" : `раз в ${h} ч`; }
  return `каждые ${Math.round(s / 60)} мин`;
}

/** Frequency <select> for one target; emits seconds or null (= default). */
function FreqSelect({ value, disabled, onChange }: {
  value: number | null; disabled?: boolean; onChange: (s: number | null) => void;
}) {
  const known = FREQ.some((f) => f.seconds === value);
  return (
    <select className="input" style={{ minWidth: 150 }} disabled={disabled}
            value={value == null ? "" : String(value)}
            onChange={(e) => onChange(e.target.value === "" ? null : Number(e.target.value))}>
      {FREQ.map((f) => <option key={f.label} value={f.seconds == null ? "" : f.seconds}>{f.label}</option>)}
      {!known && value != null && <option value={value}>{freqShort(value)}</option>}
    </select>
  );
}

/** Master on/off + DEFAULT interval (applied to targets that don't set their own). */
function ScheduleCard() {
  const qc = useQueryClient();
  const q = useQuery<MonitoringSchedule>({
    queryKey: ["monitoring-schedule"], queryFn: api.getSchedule, refetchInterval: 30_000,
  });
  const save = useMutation({
    mutationFn: (body: { enabled?: boolean; interval_seconds?: number }) => api.setSchedule(body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["monitoring-schedule"] }),
  });

  const [minutes, setMinutes] = useState(10);
  useEffect(() => { if (q.data) setMinutes(Math.max(1, Math.round(q.data.interval_seconds / 60))); },
    [q.data?.interval_seconds]);

  const s = q.data;
  const fmtTs = (epoch: number) => (epoch ? new Date(epoch * 1000).toLocaleTimeString() : "—");

  return (
    <section className="card">
      <div className="card-head">
        <h2>Автосбор</h2>
        <span className="hint">главный выключатель + интервал по умолчанию</span>
      </div>
      <div className="card-pad">
        {!s ? <div className="empty"><span className="spinner" /></div> : (
          <div className="row" style={{ gap: 18, alignItems: "center", flexWrap: "wrap" }}>
            <AutoCollectControl />
            <label className="row" style={{ gap: 8 }}>
              <span className="muted small">по умолчанию каждые</span>
              <input className="input" type="number" min={1} max={1440} value={minutes}
                     disabled={save.isPending} style={{ width: 80, padding: "6px 8px" }}
                     onChange={(e) => setMinutes(Math.max(1, Math.min(1440, Number(e.target.value) || 1)))} />
              <span className="muted small">мин</span>
              <button className="btn btn-ghost btn-sm" disabled={save.isPending}
                      onClick={() => save.mutate({ interval_seconds: minutes * 60 })}>
                {save.isPending ? <><span className="spinner" /> …</> : "Сохранить"}
              </button>
            </label>
            <div className="muted small" style={{ marginLeft: "auto", textAlign: "right" }}>
              последний обход: {fmtTs(s.last_sweep)}
            </div>
          </div>
        )}
        {save.error && <p className="err small" style={{ marginTop: 8 }}>{(save.error as Error).message}</p>}
        <p className="muted small" style={{ marginTop: 10 }}>
          Автосбор запускается только кнопкой «Запустить»: все цели обходятся сразу, а дальше —
          по расписанию, пока не нажмёте «Остановить». После остановки уже поставленные в очередь
          задачи автосбора отменяются до скачивания и платной AI-обработки. Каждый обход тратит
          AI-запросы (речь, кадры, LLM). Интервал по умолчанию применяется к целям без своего.
        </p>
      </div>
    </section>
  );
}

export function WatchlistView() {
  const qc = useQueryClient();
  const list = useQuery<WatchTarget[]>({ queryKey: ["watchlist"], queryFn: api.getWatchlist });

  const [source, setSource] = useState("youtube");
  const [kind, setKind] = useState<"account" | "keyword">("account");
  const [value, setValue] = useState("");
  const [addInterval, setAddInterval] = useState<number | null>(86400);   // default new = раз в день
  const [addLimit, setAddLimit] = useState<number | "">("");

  const invalidate = () => qc.invalidateQueries({ queryKey: ["watchlist"] });
  const add = useMutation({
    mutationFn: () => api.addWatch(source, kind, value.trim(), {
      interval_seconds: addInterval, video_limit: addLimit === "" ? null : Number(addLimit),
    }),
    onSuccess: () => { setValue(""); invalidate(); },
  });
  const patch = useMutation({
    mutationFn: ({ id, body }: { id: number; body: Parameters<typeof api.patchWatch>[1] }) =>
      api.patchWatch(id, body),
    onSuccess: invalidate,
  });
  const remove = useMutation({ mutationFn: (id: number) => api.removeWatch(id), onSuccess: invalidate });

  const items = list.data ?? [];
  const fmt = (iso: string | null) => (!iso ? "—" : iso === "—" ? "при первом тике" : new Date(iso).toLocaleString());

  return (
    <div className="stack">
      <ScheduleCard />

      <section className="card">
        <div className="card-head">
          <h2>Добавить объект мониторинга</h2>
          <span className="hint">у каждого аккаунта — своя частота и лимит</span>
        </div>
        <div className="card-pad">
          <div className="watch-form">
            <select className="input" value={source} onChange={(e) => setSource(e.target.value)}>
              {SOURCES.map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
            <select className="input" value={kind} onChange={(e) => setKind(e.target.value as "account" | "keyword")}>
              <option value="account">аккаунт</option>
              <option value="keyword">ключевое слово</option>
            </select>
            <input className="input" value={value} placeholder={kind === "account" ? "@account" : "напр. инвест казино"}
                   onChange={(e) => setValue(e.target.value)}
                   onKeyDown={(e) => e.key === "Enter" && value.trim() && add.mutate()} />
            <button className="btn btn-primary" disabled={!value.trim() || add.isPending} onClick={() => add.mutate()}>
              {add.isPending ? <><span className="spinner" /> Добавление…</> : "Добавить"}
            </button>
          </div>
          <div className="row" style={{ gap: 14, marginTop: 10 }}>
            <label className="row small muted" style={{ gap: 6 }}>
              частота
              <FreqSelect value={addInterval} onChange={setAddInterval} />
            </label>
            <label className="row small muted" style={{ gap: 6 }}>
              лимит видео
              <input className="input" type="number" min={1} max={200} placeholder="по умолч."
                     value={addLimit} style={{ width: 96, padding: "6px 8px" }}
                     onChange={(e) => setAddLimit(e.target.value === "" ? "" : Math.max(1, Math.min(200, Number(e.target.value))))} />
            </label>
          </div>
          {add.error && <p className="err small">{(add.error as Error).message}</p>}
          <p className="muted small" style={{ marginTop: 10 }}>
            Пример: один Instagram — «раз в день», другой — «2 раза в день». Планировщик
            обходит каждую цель по её собственной частоте.
          </p>
        </div>
      </section>

      <section className="card">
        <div className="card-head">
          <h2>Под наблюдением</h2>
          <span className="hint">{items.filter((t) => t.active).length} активных · частота на каждую цель</span>
        </div>
        <div className="card-pad">
          {list.isLoading ? (
            <div className="empty"><span className="spinner" /></div>
          ) : items.length === 0 ? (
            <div className="empty"><h3>Список пуст</h3><p>Добавьте аккаунт или ключевое слово выше.</p></div>
          ) : (
            <table className="table">
              <thead>
                <tr><th>Источник</th><th>Значение</th><th>Частота</th><th>Лимит</th>
                  <th>След. запуск</th><th>Статус</th><th /></tr>
              </thead>
              <tbody>
                {items.map((t) => (
                  <tr key={t.id} className={t.active ? "" : "row-off"}>
                    <td>{t.source}<div className="muted small">{t.kind === "account" ? "аккаунт" : "кл. слово"}</div></td>
                    <td><code className="code">{t.value}</code></td>
                    <td>
                      <FreqSelect value={t.interval_seconds} disabled={!t.active || patch.isPending}
                        onChange={(s) => patch.mutate({ id: t.id,
                          body: s == null ? { clear_interval: true } : { interval_seconds: s } })} />
                    </td>
                    <td>
                      <input className="input" type="number" min={1} max={200} placeholder="по умолч."
                             disabled={!t.active || patch.isPending} style={{ width: 90, padding: "5px 8px" }}
                             defaultValue={t.video_limit ?? ""}
                             onBlur={(e) => {
                               const v = e.target.value;
                               if (v === "" && t.video_limit != null) patch.mutate({ id: t.id, body: { clear_limit: true } });
                               else if (v !== "" && Number(v) !== t.video_limit)
                                 patch.mutate({ id: t.id, body: { video_limit: Math.max(1, Math.min(200, Number(v))) } });
                             }} />
                    </td>
                    <td className="muted small">{t.active ? fmt(t.next_run_at) : "—"}</td>
                    <td>{t.active
                      ? <span className="badge threat LOW">активен</span>
                      : <button className="btn btn-ghost btn-sm" onClick={() => patch.mutate({ id: t.id, body: { active: true } })}>включить</button>}</td>
                    <td>
                      {t.active && (
                        <button className="btn btn-ghost btn-sm" title="Снять с наблюдения"
                                onClick={() => remove.mutate(t.id)}>
                          <TrashIcon size={15} />
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </section>
    </div>
  );
}
