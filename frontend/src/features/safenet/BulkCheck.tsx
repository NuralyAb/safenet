import { useRef, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api, LANG_RU, LEVEL_RU, TRACK_RU, type BulkResult } from "../../api/client";
import { LevelBadge, TrackBadge } from "./RiskExplain";

/** Score a whole file of posts at once — shows throughput and the riskiest items. */
export function BulkCheck() {
  const qc = useQueryClient();
  const [file, setFile] = useState<File | null>(null);
  const [persist, setPersist] = useState(true);
  const ref = useRef<HTMLInputElement>(null);
  const run = useMutation<BulkResult, Error, { demo?: number }>({
    mutationFn: ({ demo }) => api.bulkCheck(demo ? { demo, persist } : { file: file as File, persist }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["content-triage"] });
      qc.invalidateQueries({ queryKey: ["safenet-summary"] });
      qc.invalidateQueries({ queryKey: ["campaigns"] });
    },
  });
  const r = run.data;

  return (
    <div className="stack">
      <div className="input-row">
        <input ref={ref} type="file" className="input" accept=".csv,.jsonl,.txt,text/csv,text/plain,application/json"
               onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
        <button className="btn btn-primary" disabled={!file || run.isPending} onClick={() => run.mutate({})}>
          {run.isPending ? <><span className="spinner" /> Проверка…</> : "Проверить файл"}
        </button>
      </div>
      <div className="row" style={{ gap: 10, flexWrap: "wrap", alignItems: "center" }}>
        <span className="muted small">или демо-лента (синтетика, ≈6% схем):</span>
        {[1000, 5000, 20000].map((n) => (
          <button key={n} className="chip" disabled={run.isPending} onClick={() => run.mutate({ demo: n })}>
            {n.toLocaleString("ru-RU")} постов
          </button>
        ))}
        <label className="small row" style={{ gap: 6, alignItems: "center", marginLeft: "auto" }}>
          <input type="checkbox" checked={persist} onChange={(e) => setPersist(e.target.checked)} />
          помеченные — в очередь материалов
        </label>
      </div>
      <p className="muted small">
        CSV со столбцом <code className="code">text</code> (и необязательными author, source, url, views), JSONL
        с полем <code className="code">text</code> или TXT — один пост на строку. Без LLM и внешних API:
        детерминированные правила + обучаемая модель.
      </p>
      {run.error && <p className="err small">{run.error.message}</p>}

      {r && (
        <div className="stack fade-in">
          <div className="dash-kpis">
            <div className="kpi" style={{ cursor: "default" }}><div className="kpi-top"><span className="kpi-label">Проверено</span></div>
              <div className="kpi-value">{r.rows.toLocaleString("ru-RU")}</div><div className="kpi-sub">за {r.seconds} с</div></div>
            <div className="kpi" style={{ cursor: "default" }}><div className="kpi-top"><span className="kpi-label">Скорость</span></div>
              <div className="kpi-value">{r.items_per_second}/с</div><div className="kpi-sub">≈ {Math.round((r.items_per_second ?? 0) * 86400 / 1e6)} млн в сутки на процесс</div></div>
            <div className="kpi alert" style={{ cursor: "default" }}><div className="kpi-top"><span className="kpi-label">Помечено</span></div>
              <div className="kpi-value">{r.flagged}</div><div className="kpi-sub">{(100 * r.flagged / Math.max(1, r.rows)).toFixed(1)}% · в очередь: {r.persisted}</div></div>
            <div className="kpi" style={{ cursor: "default" }}><div className="kpi-top"><span className="kpi-label">По трекам</span></div>
              <div className="kpi-value" style={{ fontSize: 16 }}>{Object.entries(r.by_track).map(([t, n]) => `${TRACK_RU[t]}: ${n}`).join(" · ") || "—"}</div>
              <div className="kpi-sub">{Object.entries(r.by_level).map(([l, n]) => `${LEVEL_RU[l]}: ${n}`).join(" · ")}</div></div>
            <div className="kpi" style={{ cursor: "default" }}><div className="kpi-top"><span className="kpi-label">Языки</span></div>
              <div className="kpi-value" style={{ fontSize: 16 }}>{Object.entries(r.languages).map(([l, n]) => `${LANG_RU[l] ?? l}: ${n}`).join(" · ")}</div></div>
          </div>
          <table className="table">
            <thead><tr><th>#</th><th>Аккаунт</th><th>Текст</th><th>Трек</th><th>Риск</th><th>Признаки</th></tr></thead>
            <tbody>{r.top.map((t) => (
              <tr key={t.row}>
                <td className="muted small">{t.row}</td><td><b>{t.author || "—"}</b></td>
                <td className="small">{t.text}</td><td><TrackBadge track={t.track} /></td>
                <td><LevelBadge level={t.threat_level} score={t.score} /></td>
                <td className="muted small">{t.signals.join("; ")}</td>
              </tr>
            ))}</tbody>
          </table>
        </div>
      )}
    </div>
  );
}
