import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, LANG_RU, LEVEL_RU, TRACK_RU, type ContentTriageItem } from "../../api/client";
import { QuoteChip, TrackBadge } from "../safenet/RiskExplain";

const DISPO_LABEL: Record<string, string> = {
  pending: "ожидает", escalated: "передано специалисту", dismissed: "ложное срабатывание", watching: "наблюдение",
};
const ACTIONS = [
  { id: "escalated", label: "Специалисту" },
  { id: "watching", label: "Наблюдать" },
  { id: "dismissed", label: "Ложное" },
];
const TRACK_FILTERS = ["", "lottery", "casino", "pyramid"];
const LEVEL_FILTERS = ["", "HIGH", "MEDIUM", "LOW"];

/** Признаки нарушения = сигналы с ненулевым вкладом, по убыванию. */
function signals(item: ContentTriageItem) {
  return (item.breakdown ?? []).filter((f) => (f.kind ?? "signal") === "signal" && (f.contribution ?? 0) > 0);
}

/** Компактное число: 1234 → 1.2K, 2_500_000 → 2.5M. */
function fmt(n: number): string {
  if (!n) return "0";
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return String(n);
}

export function MaterialsView({ onInvestigate }: { onInvestigate?: (account: string) => void }) {
  const qc = useQueryClient();
  const [track, setTrack] = useState("");
  const [level, setLevel] = useState("");
  const [onlyPending, setOnlyPending] = useState(false);
  const [open, setOpen] = useState<number | null>(null);
  const list = useQuery<ContentTriageItem[]>({
    queryKey: ["content-triage"],
    queryFn: api.getContentTriage,
  });
  const set = useMutation({
    mutationFn: ({ id, d }: { id: number; d: string }) => api.setContentDisposition(id, d),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["content-triage"] }),
  });

  const all = list.data ?? [];
  const items = all.filter((t) => (!track || t.track === track)
    && (!level || t.threat_level === level || (level === "HIGH" && t.threat_level === "CRITICAL"))
    && (!onlyPending || t.disposition === "pending"));
  const pending = all.filter((t) => t.disposition === "pending" && t.threat_level !== "LOW").length;

  return (
    <section className="card">
      <div className="card-head">
        <h2>Материалы на проверку</h2>
        <span className="hint">приоритет = риск × охват · {pending} рисковых ожидают решения</span>
      </div>
      <div className="card-pad stack">
        <div className="row" style={{ gap: 8, flexWrap: "wrap", alignItems: "center" }}>
          <div className="tabs">
            {TRACK_FILTERS.map((t) => (
              <button key={t || "all"} className={`tab${track === t ? " active" : ""}`} onClick={() => setTrack(t)}>
                {t ? TRACK_RU[t] : "Все треки"} <span className="muted small">{all.filter((x) => !t || x.track === t).length}</span>
              </button>
            ))}
          </div>
          <div className="tabs">
            {LEVEL_FILTERS.map((l) => (
              <button key={l || "all"} className={`tab${level === l ? " active" : ""}`} onClick={() => setLevel(l)}>
                {l ? LEVEL_RU[l] : "Любой риск"}
              </button>
            ))}
          </div>
          <label className="small row" style={{ gap: 6, alignItems: "center" }}>
            <input type="checkbox" checked={onlyPending} onChange={(e) => setOnlyPending(e.target.checked)} /> только без решения
          </label>
        </div>

        {list.isLoading ? (
          <div className="empty"><span className="spinner" /></div>
        ) : items.length === 0 ? (
          <div className="empty">
            <h3>Материалов нет</h3>
            <p>Проверьте пост, скриншот или группу на вкладке «Проверка» или загрузите демо-данные на «Обзоре».</p>
          </div>
        ) : (
          <table className="table">
            <thead>
              <tr><th>Материал</th><th>Трек</th><th>Риск</th><th>Охват</th><th>Признаки нарушения</th><th>Решение</th></tr>
            </thead>
            <tbody>
              {items.map((t) => {
                const sig = signals(t);
                const isOpen = open === t.id;
                return (
                  <tr key={t.id} className={t.disposition === "dismissed" ? "row-off" : ""}>
                    <td>
                      <b>{t.author || t.content_id.slice(0, 12)}</b>
                      <div className="muted small">
                        {t.source}{t.lang ? ` · ${LANG_RU[t.lang] ?? t.lang}` : ""}
                        {t.url && !t.url.startsWith("https://safenet.demo/") && (
                          <> · <a href={t.url} target="_blank" rel="noreferrer noopener">открыть</a></>
                        )}
                        {onInvestigate && t.author && !t.author.startsWith("group:") && (
                          <> · <button className="linklike" onClick={() => onInvestigate(t.author)}>→ досье</button></>
                        )}
                      </div>
                      {(t.caption || t.transcript || t.ocr_text) && (
                        <details className="transcript">
                          <summary className="muted small">текст материала</summary>
                          {t.caption && <div className="t-block"><span className="t-label">Текст</span><p>{t.caption}</p></div>}
                          {t.transcript && <div className="t-block"><span className="t-label">Речь</span><p>{t.transcript}</p></div>}
                          {t.ocr_text && <div className="t-block"><span className="t-label">На изображении</span><p>{t.ocr_text}</p></div>}
                        </details>
                      )}
                    </td>
                    <td><TrackBadge track={t.track} /></td>
                    <td><span className={`badge threat ${t.threat_level}`}>{t.score} · {LEVEL_RU[t.threat_level] ?? t.threat_level}</span></td>
                    <td className="muted small" title={`приоритет: ${t.priority}`}>👁 {fmt(t.reach?.views ?? 0)}</td>
                    <td className="small">
                      {sig.length ? (
                        <>
                          <ul style={{ margin: 0, paddingLeft: 16 }}>
                            {sig.slice(0, isOpen ? 20 : 3).map((f) => (
                              <li key={f.factor}>
                                {f.label ?? f.factor} <span className="muted">+{Math.round(f.contribution)}</span>
                                {isOpen && (f.quotes ?? []).length > 0 && (
                                  <div className="sn-quotes">{(f.quotes ?? []).map((q, i) => <QuoteChip key={i} q={q} />)}</div>
                                )}
                              </li>
                            ))}
                          </ul>
                          <button className="linklike small" onClick={() => setOpen(isOpen ? null : t.id)}>
                            {isOpen ? "свернуть" : "почему помечено →"}
                          </button>
                          {isOpen && (t.breakdown ?? []).filter((b) => b.kind === "adjustment").map((b, i) => (
                            <div key={i} className="muted small">{Math.round(b.contribution)} · {b.note}</div>
                          ))}
                        </>
                      ) : (
                        <span className="muted">{t.recommendation}</span>
                      )}
                    </td>
                    <td>
                      <div className="small" style={{ marginBottom: 4 }}>
                        {DISPO_LABEL[t.disposition] ?? t.disposition}
                        {t.disposition_by && <span className="muted"> ({t.disposition_by})</span>}
                      </div>
                      <div className="row" style={{ gap: 4, flexWrap: "wrap" }}>
                        {ACTIONS.map((a) => (
                          <button key={a.id} className="btn btn-ghost btn-sm" disabled={set.isPending || t.disposition === a.id}
                                  onClick={() => set.mutate({ id: t.id, d: a.id })}>
                            {a.label}
                          </button>
                        ))}
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>
    </section>
  );
}
