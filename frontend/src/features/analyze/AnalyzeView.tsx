import { useRef, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api, type AnalysisResult } from "../../api/client";
import { RiskGauge } from "../investigation/RiskGauge";

interface Props {
  onInvestigate?: (account: string) => void;
}

const CLAIM_LABELS: Record<string, string> = {
  promises_returns: "обещание прибыли",
  has_referral: "реферальная схема",
  gambling_content: "игорный контент",
};

/** Компактное число: 1234 → 1.2K, 2_500_000 → 2.5M. */
function fmt(n: number): string {
  if (!n) return "0";
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return String(n);
}

export function AnalyzeView({ onInvestigate }: Props) {
  const qc = useQueryClient();
  const [mode, setMode] = useState<"url" | "file">("url");
  const [url, setUrl] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const run = useMutation<AnalysisResult>({
    mutationFn: () => (mode === "url" ? api.analyzeUrl(url.trim()) : api.analyzeFile(file as File)),
    // analysed clip is persisted as Content -> refresh the account picker
    onSuccess: () => qc.invalidateQueries({ queryKey: ["accounts"] }),
  });

  const watch = useMutation({
    mutationFn: ({ source, account }: { source: string; account: string }) =>
      api.addWatch(source, "account", account),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["watchlist"] }),
  });

  // Put an extracted Telegram channel under monitoring (its public posts get
  // scraped + analysed on each sweep) and into the dossier.
  const [watchedTg, setWatchedTg] = useState<Set<string>>(new Set());
  const watchTg = useMutation({
    mutationFn: (channel: string) => api.addWatch("telegram", "account", channel),
    onSuccess: (_d, channel) => {
      setWatchedTg((s) => new Set(s).add(channel));
      qc.invalidateQueries({ queryKey: ["watchlist"] });
    },
  });

  const canRun = mode === "url" ? url.trim().length > 0 : file !== null;
  const r = run.data;
  const watchable = r && r.author && r.source && r.source !== "upload" && r.source !== "url";

  return (
    <div className="stack">
      <section className="card">
        <div className="card-head">
          <h2>Проверить конкретное видео</h2>
          <span className="hint">ссылка или загрузка файла</span>
        </div>
        <div className="card-pad stack">
          <div className="tabs">
            <button className={`tab${mode === "url" ? " active" : ""}`} onClick={() => setMode("url")}>По ссылке</button>
            <button className={`tab${mode === "file" ? " active" : ""}`} onClick={() => setMode("file")}>Загрузить файл</button>
          </div>

          {mode === "url" ? (
            <div className="input-row">
              <input className="input" value={url} placeholder="https://www.youtube.com/watch?v=…  или ссылка TikTok/Instagram"
                     onChange={(e) => setUrl(e.target.value)}
                     onKeyDown={(e) => e.key === "Enter" && canRun && run.mutate()} />
              <button className="btn btn-primary" disabled={!canRun || run.isPending} onClick={() => run.mutate()}>
                {run.isPending ? <><span className="spinner" /> Анализ…</> : "Анализировать"}
              </button>
            </div>
          ) : (
            <div className="input-row">
              <input ref={fileRef} type="file" accept="video/*" className="input"
                     onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
              <button className="btn btn-primary" disabled={!canRun || run.isPending} onClick={() => run.mutate()}>
                {run.isPending ? <><span className="spinner" /> Анализ…</> : "Анализировать"}
              </button>
            </div>
          )}

          {run.isPending && <p className="muted small">Прогон через ffmpeg → распознавание речи → OCR → визуальные теги → NLP → риск. Может занять до минуты.</p>}
          {run.error && <p className="err small">{(run.error as Error).message}</p>}
        </div>
      </section>

      {r && (
        <section className="card fade-in">
          <div className="card-head"><h2>Результат анализа</h2><span className="hint">SHA-256 {r.sha256.slice(0, 12)}…</span></div>
          <div className="card-pad stack">
            <div className="report-top">
              <RiskGauge score={r.risk.score} level={r.risk.threat_level} />
              <div className="report-meta">
                <div className="row">
                  <span className={`badge threat ${r.risk.threat_level}`}>{r.risk.threat_level}</span>
                  <span className="muted small">{r.risk.recommendation}</span>
                </div>
                <div className="row">
                  {Object.entries(CLAIM_LABELS).map(([k, label]) =>
                    r.claims[k] ? <span key={k} className="badge threat HIGH">{label}</span> : null
                  )}
                  {r.claims.has_license
                    ? <span className="badge threat LOW">лицензия в реестре</span>
                    : <span className="badge threat CRITICAL">не в реестре лицензий</span>}
                  {r.tags.length > 0 && r.tags.map((t) => <span key={t} className="badge">{t}</span>)}
                </div>
                <div className="row" style={{ alignItems: "center", gap: 8 }}>
                  <span className="eyebrow">Охват</span>
                  <span className="badge" title="просмотры">👁 {fmt(r.reach?.views ?? 0)}</span>
                  {(r.reach?.likes ?? 0) > 0 && <span className="badge" title="лайки">❤ {fmt(r.reach.likes)}</span>}
                  {(r.reach?.comments ?? 0) > 0 && <span className="badge" title="комментарии">💬 {fmt(r.reach.comments)}</span>}
                  {(r.reach?.shares ?? 0) > 0 && <span className="badge" title="репосты">↗ {fmt(r.reach.shares)}</span>}
                  <span className="muted small">приоритет {r.priority} (риск × охват)</span>
                </div>
              </div>
            </div>

            {r.author && (
              <div className="status">
                <div style={{ display: "grid", gap: 2 }}>
                  <strong>Автор: {r.author}</strong>
                  <span className="muted small">
                    {watchable
                      ? "Поставьте аккаунт под наблюдение — система соберёт его другие видео, и будет доступно полное расследование (связи, кошельки, схемы)."
                      : "Источник без автора (загруженный файл) — для слежки используйте ссылку на видео."}
                  </span>
                </div>
                <div className="row" style={{ marginLeft: "auto", gap: 8 }}>
                  {watchable && (
                    <button className="btn btn-primary btn-sm" disabled={watch.isPending || watch.isSuccess}
                            onClick={() => watch.mutate({ source: r.source, account: r.author })}>
                      {watch.isSuccess ? "В наблюдении" : watch.isPending ? "…" : "Следить за аккаунтом"}
                    </button>
                  )}
                  {onInvestigate && (
                    <button className="btn btn-ghost btn-sm" onClick={() => onInvestigate(r.author)}>
                      Расследовать
                    </button>
                  )}
                </div>
              </div>
            )}

            {(r.identifiers.telegram.length + r.identifiers.wallets.length + r.identifiers.domains.length) > 0 && (
              <div>
                <div className="eyebrow" style={{ marginBottom: 6 }}>Извлечённые идентификаторы</div>
                <div className="row" style={{ flexWrap: "wrap", gap: 8, alignItems: "center" }}>
                  {r.identifiers.telegram.map((v) => (
                    <span key={`tg:${v}`} style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
                      <code className="code">tg:{v}</code>
                      <button className="btn btn-ghost btn-sm"
                              title="Добавить TG-канал в мониторинг — его публичные посты будут собираться и анализироваться"
                              disabled={watchTg.isPending || watchedTg.has(v)}
                              onClick={() => watchTg.mutate(v)}>
                        {watchedTg.has(v) ? "в наблюдении" : "Мониторить"}
                      </button>
                    </span>
                  ))}
                  {r.identifiers.wallets.map((v) => <code key={`wallet:${v}`} className="code">wallet:{v}</code>)}
                  {r.identifiers.domains.map((v) => <code key={v} className="code">{v}</code>)}
                </div>
              </div>
            )}

            {r.scheme_matches.length > 0 && (
              <div>
                <div className="eyebrow" style={{ marginBottom: 6 }}>Совпадения со схемами · {r.scheme_matches.length}</div>
                <ul className="plain-list">
                  {r.scheme_matches.slice(0, 8).map((m) => (
                    <li key={m.content_id}><code className="code">{m.content_id.slice(0, 12)}…</code> · score {m.score}{m.shared.length ? ` · ${m.shared.join(", ")}` : ""}</li>
                  ))}
                </ul>
              </div>
            )}

            <div>
              <div className="eyebrow" style={{ marginBottom: 6 }}>Распознанный текст (подпись + речь + экран)</div>
              <pre className="evpkg-md">{r.text || "—"}</pre>
            </div>
          </div>
        </section>
      )}
    </div>
  );
}
