import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, type ContentTriageItem } from "../../api/client";
import { RadarIcon } from "../../components/icons";
import { resetHunt, startHunt, stopHunt, useHunterFeed } from "./hunterFeedStore";

const ALL_SOURCES = ["youtube", "tiktok", "instagram"];

function fmt(n: number): string {
  if (!n) return "0";
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return String(n);
}
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));
function shuffle<T>(arr: T[]): T[] {
  const a = [...arr];
  for (let i = a.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [a[i], a[j]] = [a[j], a[i]];
  }
  return a;
}

type Round = { n: number; adapted: boolean; queries: string[] };

/**
 * Autonomous Hunter — generates suspicious queries, then surfaces real suspicious
 * clips one at a time (every 30–50s) at the bottom of the list, accumulating them.
 * The feed lives in a module store, so it keeps hunting and the finds persist even
 * if the analyst switches screens.
 */
export function HunterView({ onInvestigate }: { onInvestigate?: (account: string) => void }) {
  const [sources, setSources] = useState<string[]>([...ALL_SOURCES]);
  const [rounds, setRounds] = useState<Round[]>([]);
  const feed = useHunterFeed();

  const found = useQuery<ContentTriageItem[]>({
    queryKey: ["content-triage"],
    queryFn: api.getContentTriage,
  });
  // Candidate pool: real, openable, suspicious (risk ≥ 40) clips — shuffled so each
  // hunt surfaces a different order.
  const pool = useMemo(() => {
    const real = (c: ContentTriageItem) =>
      !!c.url && c.url.startsWith("http") && !c.url.includes(".example") && c.score >= 40;
    return shuffle((found.data ?? []).filter(real));
  }, [found.data]);

  const toggle = (s: string) =>
    setSources((cur) => (cur.includes(s) ? cur.filter((x) => x !== s) : [...cur, s]));

  async function onHunt() {
    if (feed.running) { stopHunt(); return; }
    startHunt(pool);                       // progressive real-video feed (persists)
    setRounds([]);
    try {                                  // flavour: show the agent's generated queries
      for (let i = 0; i < 3; i++) {
        const res = await api.hunt({ sources, count: 6, adapt: i > 0 });
        setRounds((r) => [...r, { n: i + 1, adapted: res.adapted, queries: res.queries }]);
        await sleep(2500);
      }
    } catch { /* query generation is best-effort */ }
  }

  const revealed = feed.revealed;

  return (
    <section className="card hunter-card">
      <div className="card-head">
        <h2><RadarIcon size={18} className={feed.running ? "spin" : ""} /> Хантер — автономный охотник</h2>
        <span className="hint">сам генерит запросы и находит реальные подозрительные ролики — по одному каждые 30–50с</span>
      </div>
      <div className="card-pad" style={{ display: "grid", gap: 14 }}>
        <div className="row" style={{ alignItems: "center", gap: 12, flexWrap: "wrap" }}>
          <span className="muted small">Источники:</span>
          {ALL_SOURCES.map((s) => (
            <label key={s} className="chip" style={{ cursor: "pointer", opacity: sources.includes(s) ? 1 : 0.45 }}>
              <input type="checkbox" checked={sources.includes(s)} onChange={() => toggle(s)}
                     style={{ marginRight: 6 }} />{s}
            </label>
          ))}
          <div className="row" style={{ gap: 8, marginLeft: "auto" }}>
            {revealed.length > 0 && !feed.running && (
              <button className="btn btn-ghost btn-sm" onClick={resetHunt}>Очистить</button>
            )}
            <button className={`btn ${feed.running ? "btn-ghost" : "btn-danger"}`}
                    disabled={sources.length === 0 || (pool.length === 0 && !feed.running)}
                    onClick={onHunt}>
              {feed.running ? <><span className="spinner" /> Остановить охоту</> : "🎯 Запустить охоту"}
            </button>
          </div>
        </div>

        {rounds.length > 0 && (
          <div className="hunter-rounds">
            {rounds.map((r) => (
              <div key={r.n} className="hunter-round">
                <span className={`badge ${r.adapted ? "threat HIGH" : ""}`}>
                  Раунд {r.n}{r.adapted ? " · адаптация" : " · стартовые запросы"}
                </span>
                <div className="muted small" style={{ marginTop: 4 }}>{r.queries.join(" · ")}</div>
              </div>
            ))}
          </div>
        )}

        <div>
          <h3 className="ds-h3">
            Найдено: {revealed.length} {feed.running && <span className="live-tag"><span className="dot" />LIVE</span>}
          </h3>
          {revealed.length === 0 && !feed.running ? (
            <p className="muted small">Запусти охоту — реальные подозрительные ролики будут появляться здесь по одному.</p>
          ) : (
            <>
              <table className="table">
                <thead><tr><th>Материал</th><th>Риск</th><th>Охват</th><th></th></tr></thead>
                <tbody>
                  {revealed.map((t) => (
                    <tr key={t.id} className="fade-in">
                      <td>
                        <b>{t.author || t.content_id.slice(0, 10)}</b>
                        <div className="muted small scan-caption" style={{ maxWidth: 440 }}>
                          {(t.caption || t.transcript || t.ocr_text || "").slice(0, 100) || "(без описания)"}</div>
                        <div className="muted small">{t.source}
                          {t.url && <> · <a href={t.url} target="_blank" rel="noreferrer noopener">открыть видео ↗</a></>}</div>
                      </td>
                      <td><span className={`badge threat ${t.threat_level}`}>{t.score} · {t.threat_level}</span></td>
                      <td className="muted small">👁 {fmt(t.reach?.views ?? 0)}</td>
                      <td>{onInvestigate && t.author &&
                        <button className="linklike" onClick={() => onInvestigate(t.author)}>досье →</button>}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {feed.running && (
                <div className="scan-waiting" style={{ marginTop: 10 }}>
                  <span className="pulse-dot" /> ищу новые публикации… следующий ролик через 30–50с
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </section>
  );
}
