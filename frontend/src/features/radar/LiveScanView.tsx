import { useEffect, useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, type ContentTriageItem } from "../../api/client";
import { RadarIcon } from "../../components/icons";

const STEP_MS = 1100;            // cadence within a burst
const REVEAL_COUNT = 12;         // clips surfaced per scan run
const PAUSE_MIN = 15_000;        // gap between bursts (ms)
const PAUSE_SPAN = 5_000;        // +0..5s jitter

function fmt(n: number): string {
  if (!n) return "0";
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return String(n);
}
function findings(it: ContentTriageItem): string[] {
  return (it.breakdown ?? []).filter((f) => (f.contribution ?? 0) > 0 && f.note).map((f) => f.note as string);
}
function caption(it: ContentTriageItem): string {
  return (it.caption || it.transcript || it.ocr_text || "").slice(0, 90) || "(без текста)";
}
/** Deterministic gradient "poster" per clip so each card reads as a distinct video. */
function poster(id: string) {
  let h = 0;
  for (const ch of id) h = (h * 31 + ch.charCodeAt(0)) >>> 0;
  const a = h % 360, b = (a + 42) % 360;
  return { background: `linear-gradient(150deg, hsl(${a} 48% 30%), hsl(${b} 52% 17%))` };
}
/** Real YouTube thumbnail from the clip URL (no API key). mqdefault = 320×180,
 *  no letterbox bars (unlike hqdefault). Falls back to the gradient poster. */
function ytThumb(url?: string): string | null {
  if (!url) return null;
  const m = url.match(/(?:youtu\.be\/|v=|shorts\/|embed\/)([\w-]{11})/);
  return m ? `https://i.ytimg.com/vi/${m[1]}/mqdefault.jpg` : null;
}
function shuffle<T>(arr: T[]): T[] {
  const a = [...arr];
  for (let i = a.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [a[i], a[j]] = [a[j], a[i]];
  }
  return a;
}
/** Delay (ms) to wait BEFORE revealing each card: clips arrive in bursts of 2–3,
 *  with a 15–20s "searching" pause between bursts — like an agent discovering
 *  new posts over time rather than dumping a static list. */
function burstPlan(n: number): number[] {
  const delays: number[] = [];
  let i = 0, first = true;
  while (i < n) {
    const burst = 2 + Math.floor(Math.random() * 2); // 2 or 3
    for (let k = 0; k < burst && i < n; k++, i++) {
      if (first) { delays.push(450); first = false; }
      else if (k === 0) delays.push(PAUSE_MIN + Math.floor(Math.random() * PAUSE_SPAN));
      else delays.push(STEP_MS);
    }
  }
  return delays;
}

interface Run { clips: ContentTriageItem[]; delays: number[]; }

/**
 * Live Scan — demo theatre. An agent "scrolls" a feed: clips surface in bursts
 * (2–3 at a time, then a pause while it searches), each analysing then revealing
 * its risk verdict while a report tallies the campaign live. Real, openable clips
 * only; a fresh shuffled subset each run so no two scans look the same.
 */
export function LiveScanView({ onInvestigate }: { onInvestigate?: (account: string) => void }) {
  const list = useQuery<ContentTriageItem[]>({ queryKey: ["content-triage"], queryFn: api.getContentTriage });
  // Only clips with a real, openable URL — drop synthetic mock items (….example/…).
  const pool = useMemo(
    () => (list.data ?? []).filter((c) => !!c.url && c.url.startsWith("http") && !c.url.includes(".example")),
    [list.data],
  );

  const [run, setRun] = useState<Run | null>(null);
  const [running, setRunning] = useState(false);
  const [shown, setShown] = useState(0);
  const [elapsed, setElapsed] = useState(0);
  const [waiting, setWaiting] = useState(false);   // long inter-burst pause
  const feedRef = useRef<HTMLDivElement>(null);

  const clips = run?.clips ?? [];

  // reveal scheduler — pulls the next card after its planned delay
  useEffect(() => {
    if (!running || !run) return;
    if (shown >= run.clips.length) { setRunning(false); setWaiting(false); return; }
    const delay = run.delays[shown] ?? STEP_MS;
    setWaiting(delay > 5_000);
    const t = setTimeout(() => { setWaiting(false); setShown((n) => n + 1); }, delay);
    return () => clearTimeout(t);
  }, [running, shown, run]);

  // running clock
  useEffect(() => {
    if (!running) return;
    const t = setInterval(() => setElapsed((e) => e + 1), 1000);
    return () => clearInterval(t);
  }, [running]);

  useEffect(() => { feedRef.current?.scrollTo({ top: 1e9, behavior: "smooth" }); }, [shown, waiting]);

  const start = () => {
    const picked = shuffle(pool).slice(0, REVEAL_COUNT);
    setRun({ clips: picked, delays: burstPlan(picked.length) });
    setShown(0); setElapsed(0); setWaiting(false); setRunning(true);
  };
  const clock = `${String(Math.floor(elapsed / 60)).padStart(2, "0")}:${String(elapsed % 60).padStart(2, "0")}`;

  const revealed = clips.slice(0, shown);
  const high = revealed.filter((c) => (c.score ?? 0) >= 65);
  const med = revealed.filter((c) => (c.score ?? 0) >= 40 && (c.score ?? 0) < 65);
  const accounts = new Set(revealed.map((c) => c.author).filter(Boolean));
  const maxRisk = revealed.reduce((m, c) => Math.max(m, c.score ?? 0), 0);
  const verdict = maxRisk >= 85 ? "CRITICAL" : maxRisk >= 65 ? "HIGH" : maxRisk >= 40 ? "MEDIUM" : "LOW";
  const done = run != null && shown >= clips.length && shown > 0 && !running;
  const pct = clips.length ? Math.round((shown / clips.length) * 100) : 0;

  return (
    <section className="card">
      <div className="card-head">
        <h2><RadarIcon size={18} className={running ? "spin" : ""} /> Live-скан ленты</h2>
        {(running || done) && (
          <span className="live-tag">
            <span className="dot" />{running ? "LIVE" : "ГОТОВО"}
            <span className="live-clock">{clock}</span>
          </span>
        )}
        <span className="hint">демонстрация работы агента: ролики находятся пачками и анализируются на лету</span>
      </div>
      <div className="card-pad">
        <div className="input-row" style={{ marginBottom: 12 }}>
          <button className="btn btn-primary" onClick={start} disabled={running || pool.length === 0}>
            {running ? <><span className="spinner" /> Сканирую…</> : <><RadarIcon size={16} /> Запустить скан</>}
          </button>
          <span className="muted small">{pool.length} роликов в пуле · {pct}%</span>
          <div className="scan-bar"><div className="scan-bar-fill" style={{ width: `${pct}%` }} /></div>
        </div>

        {pool.length === 0 && <div className="empty"><p>Нет роликов для скана — запустите Радар угроз или включите демо-режим.</p></div>}

        <div className="scan-grid">
          <div className="scan-feed" ref={feedRef}>
            {revealed.map((c, i) => {
              const isScanning = running && !waiting && i === revealed.length - 1;
              const thumb = ytThumb(c.url);
              const Inner = (
                <>
                  {thumb && <img className="scan-thumb-img" src={thumb} alt="" loading="lazy"
                                 onError={(e) => { (e.currentTarget as HTMLImageElement).style.display = "none"; }} />}
                  <span className="play">
                    <svg width="8" height="9" viewBox="0 0 8 9" aria-hidden="true"><path d="M0 0l8 4.5L0 9z" fill="#fff" /></svg>
                  </span>
                  <span className="src">{(c.source || "?").slice(0, 2).toUpperCase()}</span>
                </>
              );
              return (
                <div key={c.id} className={`scan-card${isScanning ? " scanning" : ""}`}>
                  {c.url
                    ? <a className="scan-thumb" style={poster(c.content_id)} href={c.url} target="_blank" rel="noopener noreferrer" title="Открыть оригинал" onClick={(e) => e.stopPropagation()}>{Inner}</a>
                    : <div className="scan-thumb" style={poster(c.content_id)}>{Inner}</div>}
                  <div className="scan-card-body">
                    <div className="row" style={{ gap: 8 }}>
                      <b>{c.author || c.content_id.slice(0, 10)}</b>
                      <span className="muted small">{c.source}</span>
                      <span className="spacer" />
                      {isScanning ? <span className="muted small"><span className="spinner" /> анализ…</span>
                        : <span className={`badge threat ${c.threat_level}`}>{c.score} · {c.threat_level}</span>}
                    </div>
                    <div className="muted small scan-caption">{caption(c)}</div>
                    {!isScanning && findings(c).length > 0 &&
                      <div className="muted small">⚑ {findings(c).slice(0, 2).join(" · ")}</div>}
                  </div>
                </div>
              );
            })}
            {running && waiting && (
              <div className="scan-waiting"><span className="pulse-dot" /> ищу новые публикации в ленте…</div>
            )}
          </div>

          <div className="scan-report">
            <div className="ds-h3">Отчёт {done && "· готов"}</div>
            <div className="scan-stats">
              <div><b>{shown}</b><span className="muted small">просканировано</span></div>
              <div><b className="err">{high.length}</b><span className="muted small">высокий риск</span></div>
              <div><b>{med.length}</b><span className="muted small">средний</span></div>
              <div><b>{accounts.size}</b><span className="muted small">аккаунтов</span></div>
            </div>
            <div className={`campaign-banner threat ${verdict}`} style={{ marginTop: 10 }}>
              <div className="campaign-flow">
                <span><b>{shown}</b> роликов</span><span className="flow-arrow">→</span>
                <span><b>{accounts.size}</b> аккаунтов</span><span className="flow-arrow">→</span>
                <span className="campaign-verdict">приоритет · <b>{verdict}</b></span>
              </div>
            </div>
            {high.length > 0 && (
              <div style={{ marginTop: 10 }}>
                <div className="ds-h3">Найдено мошенничество</div>
                <ul className="linked-list">
                  {high.slice(0, 6).map((c) => (
                    <li key={c.id}>
                      <span className={`badge threat ${c.threat_level}`}>{c.score}</span>{" "}
                      {onInvestigate && c.author
                        ? <button className="linklike" onClick={() => onInvestigate(c.author)}>{c.author}</button>
                        : <b>{c.author || c.content_id.slice(0, 10)}</b>}
                      <span className="muted small"> · 👁 {fmt(c.reach?.views ?? 0)}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
            {done && <div className="muted small" style={{ marginTop: 8 }}>Скан завершён. Высокий риск передан в очередь материалов.</div>}
          </div>
        </div>
      </div>
    </section>
  );
}
