import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, LANG_RU, TRACK_RU, type Methodology, type MetricsReport } from "../../api/client";

const pct = (x: number | null | undefined) => (x === null || x === undefined ? "—" : `${(100 * x).toFixed(1)}%`);
const OBF_RU: Record<string, string> = {
  none: "без обфускации", leet: "подмена символов", spaced: "разрядка букв", homoglyph: "латиница в кириллице",
  translit: "транслит", emoji: "эмодзи",
};
const KIND_RU: Record<string, string> = { post: "пост", chat: "сообщение чата", stream: "транскрипт эфира", ocr: "скриншот (OCR)" };
const LABELS = ["lottery", "casino", "pyramid", "none"];

function Kpi({ label, value, sub, warn }: { label: string; value: string; sub?: string; warn?: boolean }) {
  return (
    <div className={`kpi${warn ? " alert" : ""}`} style={{ cursor: "default" }}>
      <div className="kpi-top"><span className="kpi-label">{label}</span></div>
      <div className="kpi-value">{value}</div>
      {sub && <div className="kpi-sub">{sub}</div>}
    </div>
  );
}

function SliceTable({ title, rows }: { title: string; rows: [string, { n: number; recall?: number | null; fpr?: number | null }][] }) {
  return (
    <section className="card">
      <div className="card-head"><h2>{title}</h2></div>
      <div className="card-pad">
        <table className="table">
          <thead><tr><th>Срез</th><th>N</th><th>{rows[0]?.[1].fpr !== undefined ? "FPR" : "Recall"}</th></tr></thead>
          <tbody>{rows.map(([k, v]) => (
            <tr key={k}><td>{k}</td><td>{v.n}</td><td><b>{pct(v.recall ?? v.fpr)}</b></td></tr>
          ))}</tbody>
        </table>
      </div>
    </section>
  );
}

export function MetricsView() {
  const [dataset, setDataset] = useState("blind2");
  const [withModel, setWithModel] = useState(true);
  const m = useQuery<MetricsReport>({ queryKey: ["metrics", dataset, withModel], queryFn: () => api.getMetrics(dataset, withModel) });
  const meth = useQuery<Methodology>({ queryKey: ["methodology"], queryFn: api.getMethodology });
  const r = m.data;

  return (
    <div className="stack">
      <section className="card">
        <div className="card-head">
          <h2>Метрики на размеченных выборках</h2>
          <span className="hint">без LLM и внешних API — воспроизводимо офлайн</span>
        </div>
        <div className="card-pad stack">
          <div className="row" style={{ gap: 10, flexWrap: "wrap", alignItems: "center" }}>
            <div className="tabs">
              {(r?.available ?? [{ id: "blind2", title: "" }]).map((d) => (
                <button key={d.id} className={`tab${dataset === d.id ? " active" : ""}`} onClick={() => setDataset(d.id)}>
                  {{ blind2: "Слепая №2 (главная)", blind: "Слепая №1", holdout: "Отложенная", test: "Тест", dev: "Настройка" }[d.id] ?? d.id}
                </button>
              ))}
            </div>
            <div className="tabs">
              <button className={`tab${!withModel ? " active" : ""}`} onClick={() => setWithModel(false)}>Только правила</button>
              <button className={`tab${withModel ? " active" : ""}`} onClick={() => setWithModel(true)}>Правила + модель</button>
            </div>
          </div>
          {r?.training_set && (
            <p className="err small">Модель обучена на этой выборке — цифры в режиме «правила + модель» здесь не являются оценкой качества.
              Честная оценка — на слепых выборках.</p>
          )}
          {m.isLoading && <div className="empty"><span className="spinner" /></div>}
          {m.error && <p className="err small">{(m.error as Error).message}</p>}
          {r && (
            <>
              <p className="small">{r.title}. Объём: <b>{r.n}</b> (позитивов {r.positives}, негативов {r.negatives},
                трудных негативов {r.hard_negatives}). «Помечено» = балл ≥ {r.threshold} (уровень «средний» и выше).</p>
              <div className="dash-kpis">
                <Kpi label="Precision" value={pct(r.binary.precision)} sub="доля верных среди помеченных" />
                <Kpi label="Recall" value={pct(r.binary.recall)} sub="доля найденных схем" />
                <Kpi label="F1" value={pct(r.binary.f1)} />
                <Kpi label="Ложные срабатывания (FPR)" value={pct(r.binary.fpr)} sub={`на трудных: ${pct(r.hard_negative_fpr)}`}
                     warn={(r.binary.fpr ?? 0) > 0.05} />
                <Kpi label="Уровень «высокий»" value={pct(r.high_level.recall)} sub={`FPR: ${pct(r.high_level.fpr)}`} />
                <Kpi label="Скорость" value={`${r.throughput.items_per_second ?? "—"}/с`}
                     sub={`${r.throughput.ms_per_item} мс на материал, 1 ядро`} />
              </div>
            </>
          )}
        </div>
      </section>

      {r && (
        <>
          <section className="card">
            <div className="card-head"><h2>По трекам</h2><span className="hint">one-vs-rest; FPR — доля чистого контента, ошибочно помеченного этим треком</span></div>
            <div className="card-pad">
              <table className="table">
                <thead><tr><th>Трек</th><th>N</th><th>Precision</th><th>Recall</th><th>F1</th><th>FPR</th></tr></thead>
                <tbody>{Object.entries(r.per_track).map(([t, v]) => (
                  <tr key={t}><td><b>{TRACK_RU[t]}</b></td><td>{v.support}</td><td>{pct(v.precision)}</td>
                    <td>{pct(v.recall)}</td><td>{pct(v.f1)}</td><td>{pct(v.fpr)}</td></tr>
                ))}</tbody>
              </table>
            </div>
          </section>

          <div className="grid-3">
            <SliceTable title="Recall по языкам" rows={Object.entries(r.recall_by_language).map(([k, v]) => [LANG_RU[k] ?? k, v])} />
            <SliceTable title="Recall при обфускации" rows={Object.entries(r.recall_by_obfuscation).map(([k, v]) => [OBF_RU[k] ?? k, v])} />
            <SliceTable title="Recall по типу материала" rows={Object.entries(r.recall_by_kind).map(([k, v]) => [KIND_RU[k] ?? k, v])} />
          </div>

          <section className="card">
            <div className="card-head"><h2>Матрица ошибок</h2><span className="hint">строки — разметка, столбцы — прогноз</span></div>
            <div className="card-pad">
              <table className="table sn-confusion">
                <thead><tr><th></th>{LABELS.map((l) => <th key={l}>{TRACK_RU[l]}</th>)}</tr></thead>
                <tbody>{LABELS.map((a) => (
                  <tr key={a}><td><b>{TRACK_RU[a]}</b></td>
                    {LABELS.map((b) => <td key={b} className={a === b ? "sn-diag" : (r.confusion[a]?.[b] ? "sn-off" : "")}>{r.confusion[a]?.[b] ?? 0}</td>)}
                  </tr>
                ))}</tbody>
              </table>
            </div>
          </section>

          <section className="card">
            <div className="card-head"><h2>Ошибки ({r.errors.length})</h2><span className="hint">FN — пропуск, FP — ложное срабатывание</span></div>
            <div className="card-pad">
              {r.errors.length === 0 ? <p className="muted small">Ошибок нет.</p> : (
                <table className="table">
                  <thead><tr><th>Тип</th><th>Разметка → прогноз</th><th>Балл</th><th>Текст</th></tr></thead>
                  <tbody>{r.errors.map((e) => (
                    <tr key={e.id}>
                      <td><span className={`badge threat ${e.type === "FP" ? "HIGH" : "MEDIUM"}`}>{e.type}</span></td>
                      <td className="small">{TRACK_RU[e.track]} → {TRACK_RU[e.pred_track]}</td>
                      <td>{e.score}</td><td className="small">{e.text}</td>
                    </tr>
                  ))}</tbody>
                </table>
              )}
            </div>
          </section>
        </>
      )}

      {meth.data && (
        <section className="card">
          <div className="card-head"><h2>Методика: признаки и расчёт риска</h2>
            <span className="hint">высокий ≥ {meth.data.levels.HIGH}, средний ≥ {meth.data.levels.MEDIUM}, иначе низкий</span></div>
          <div className="card-pad stack">
            <p className="small">
              Балл трека = Σ вес признака × сила признака (1.0 — точное правило, 0.8 — LLM с проверенной цитатой,
              0.5 — слабое правило). Затем применяются гейты и смягчения против ложных срабатываний.
              Итог — максимум по трекам. Каждая поправка видна аналитику отдельной строкой. LLM никогда не ставит балл.
            </p>
            <ul className="plain-list">{meth.data.gates.map((g, i) => <li key={i} className="small">• {g}</li>)}</ul>
            {Object.entries(meth.data.weights).map(([track, w]) => (
              <div key={track}>
                <div className="eyebrow" style={{ margin: "8px 0 4px" }}>{meth.data!.tracks[track]}</div>
                <table className="table">
                  <thead><tr><th>Признак</th><th>Вес</th><th>Описание</th></tr></thead>
                  <tbody>{Object.entries(w).sort((a, b) => b[1] - a[1]).map(([sid, weight]) => {
                    const s = meth.data!.signals.find((x) => x.id === sid);
                    return (
                      <tr key={sid}>
                        <td><b>{s?.label ?? meth.data!.extra[sid] ?? sid}</b>{s?.role === "core" && <span className="badge" style={{ marginLeft: 6 }}>ключевой</span>}</td>
                        <td>{weight}</td><td className="muted small">{s?.description ?? ""}</td>
                      </tr>
                    );
                  })}</tbody>
                </table>
              </div>
            ))}
            <div className="sn-disclaimer">⚖️ {meth.data.disclaimer}</div>
          </div>
        </section>
      )}
    </div>
  );
}
