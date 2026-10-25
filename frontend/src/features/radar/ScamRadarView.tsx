import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, type ContentTriageItem } from "../../api/client";
import { RadarIcon } from "../../components/icons";

const PRESETS = [
  "инвест казино без лицензии",
  "гарантированный доход 300%",
  "крипто сигналы приватный канал",
  "пирамида реферальная программа",
];
const SOURCES = ["youtube", "tiktok", "instagram"];

/** Compact number. */
function fmt(n: number): string {
  if (!n) return "0";
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return String(n);
}

/**
 * Scam Radar — proactive discovery by keyword/hashtag (not a known @handle).
 * Triggers a background discovery sweep, then shows the freshly-scored materials
 * (newest, highest-risk first). Offline-safe under AI_PROVIDER=mock.
 */
export function ScamRadarView({ onInvestigate }: { onInvestigate?: (account: string) => void }) {
  const qc = useQueryClient();
  const [query, setQuery] = useState(PRESETS[0]);
  const [source, setSource] = useState("youtube");

  const found = useQuery<ContentTriageItem[]>({
    queryKey: ["content-triage"],
    queryFn: api.getContentTriage,
  });
  const run = useMutation({
    mutationFn: () => api.discover(query.trim(), source),
    onSuccess: () => {
      // refresh results a few times while the background pipeline lands items
      [4000, 9000, 15000].forEach((t) =>
        setTimeout(() => qc.invalidateQueries({ queryKey: ["content-triage"] }), t));
    },
  });
  // «В постоянный радар» — add the keyword as a watch-target so the scheduler keeps
  // scanning it continuously (the autonomous fraud-finding agent).
  const watch = useMutation({
    mutationFn: () => api.addWatch(source, "keyword", query.trim()),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["watchlist"] }),
  });
  // «Авто-охота» — агент сам генерит пачку запросов и запускает по ним сбор.
  const hunt = useMutation({
    mutationFn: () => api.hunt({ count: 6 }),
    onSuccess: () => {
      [5000, 12000, 20000].forEach((t) =>
        setTimeout(() => qc.invalidateQueries({ queryKey: ["content-triage"] }), t));
    },
  });

  const items = (found.data ?? []).slice(0, 20);

  return (
    <section className="card">
      <div className="card-head">
        <h2><RadarIcon size={18} /> Scam Radar</h2>
        <span className="hint">проактивный поиск новых подозрительных публикаций по ключевым словам</span>
      </div>
      <div className="card-pad" style={{ display: "grid", gap: 14 }}>
        <div className="input-row">
          <input className="input" value={query} spellCheck={false}
                 onChange={(e) => setQuery(e.target.value)}
                 onKeyDown={(e) => e.key === "Enter" && query.trim() && run.mutate()}
                 placeholder="ключевое слово / хэштег" style={{ flex: 1 }} />
          <select className="input" value={source} onChange={(e) => setSource(e.target.value)}
                  style={{ width: 130 }}>
            {SOURCES.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
          <button className="btn btn-primary" disabled={run.isPending || !query.trim()}
                  onClick={() => run.mutate()}>
            {run.isPending ? <><span className="spinner" /> Поиск…</> : <><RadarIcon size={16} /> Искать</>}
          </button>
          <button className="btn btn-ghost" disabled={watch.isPending || !query.trim()}
                  onClick={() => watch.mutate()} title="Сканировать это непрерывно (агент)">
            {watch.isSuccess ? "✓ в радаре" : "В постоянный радар"}
          </button>
          <button className="btn btn-ghost" disabled={hunt.isPending}
                  onClick={() => hunt.mutate()} title="Агент сам сгенерит запросы и запустит поиск">
            {hunt.isPending ? <><span className="spinner" /> Охота…</> : "🎯 Авто-охота"}
          </button>
        </div>

        {hunt.isSuccess && (
          <span className="muted small">
            Авто-охота запущена по {hunt.data?.count} запросам: {hunt.data?.queries.slice(0, 4).join(", ")}…
            Найденное появится ниже.
          </span>
        )}

        <div className="chip-row">
          {PRESETS.map((p) => (
            <button key={p} className="chip" onClick={() => setQuery(p)} style={{ cursor: "pointer" }}>{p}</button>
          ))}
        </div>

        {run.isSuccess && (
          <span className="muted small">
            Поиск «{run.data?.query}» запущен в фоне — новые ролики скачиваются, анализируются и
            появляются ниже (обновится само через 1–2 мин).
          </span>
        )}
        {run.error && <span className="err small">{(run.error as Error).message}</span>}

        <div>
          <h3 className="ds-h3">Обнаруженные материалы (приоритет по риску)</h3>
          {items.length === 0 ? (
            <p className="muted small">Пока пусто. Запустите поиск — найденное появится здесь.</p>
          ) : (
            <table className="table">
              <thead><tr><th>Материал</th><th>Риск</th><th>Охват</th><th></th></tr></thead>
              <tbody>
                {items.map((t) => (
                  <tr key={t.id}>
                    <td>
                      <b>{t.author || t.content_id}</b>
                      <div className="muted small">{t.source}
                        {t.url && <> · <a href={t.url} target="_blank" rel="noreferrer noopener">видео</a></>}</div>
                    </td>
                    <td><span className={`badge threat ${t.threat_level}`}>{t.score} · {t.threat_level}</span></td>
                    <td className="muted small">👁 {fmt(t.reach?.views ?? 0)}</td>
                    <td>{onInvestigate && t.author &&
                      <button className="linklike" onClick={() => onInvestigate(t.author)}>досье →</button>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </section>
  );
}
