import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  api, LANG_RU, LEVEL_RU, SOURCE_RU, TRACK_RU, VIEW_RU,
  type BreakdownLine, type SafeNetRisk, type SignalQuote,
} from "../../api/client";
import { RiskGauge } from "../investigation/RiskGauge";

const TRACK_ORDER = ["lottery", "casino", "pyramid"];

export function LevelBadge({ level, score }: { level: string; score?: number }) {
  return (
    <span className={`badge threat ${level}`}>
      {score !== undefined ? `${score} · ` : ""}{LEVEL_RU[level] ?? level}
    </span>
  );
}

export function TrackBadge({ track }: { track?: string }) {
  if (!track) return <span className="badge">без трека</span>;
  return <span className={`badge sn-track sn-track-${track}`}>{TRACK_RU[track] ?? track}</span>;
}

export function QuoteChip({ q }: { q: SignalQuote }) {
  const where = [q.source && q.source !== "text" ? SOURCE_RU[q.source] ?? q.source : "", VIEW_RU[q.view] ?? ""]
    .filter(Boolean).join(" · ");
  return (
    <span className={`sn-quote${q.view && q.view !== "base" ? " obf" : ""}`} title={where || "текст поста"}>
      «{q.text}»{where && <em>{where}</em>}
    </span>
  );
}

function SignalLine({ b }: { b: BreakdownLine }) {
  const label = b.label || b.factor;
  const extra = b.detail ?? "";
  return (
    <li className="sn-signal">
      <span className="sn-plus">+{Math.round(b.contribution)}</span>
      <div>
        <div className="sn-signal-label">{label}</div>
        {extra && <div className="muted small">{extra}</div>}
        {(b.quotes ?? []).length > 0 && (
          <div className="sn-quotes">{(b.quotes ?? []).map((q, i) => <QuoteChip key={i} q={q} />)}</div>
        )}
      </div>
    </li>
  );
}

const DISPO = [
  { id: "escalated", label: "Передать специалисту" },
  { id: "watching", label: "В наблюдение" },
  { id: "dismissed", label: "Ложное срабатывание" },
];

export function DispositionButtons({ id }: { id: number }) {
  const qc = useQueryClient();
  const [done, setDone] = useState<string | null>(null);
  const set = useMutation({
    mutationFn: (d: string) => api.setContentDisposition(id, d),
    onSuccess: (_r, d) => { setDone(d); qc.invalidateQueries({ queryKey: ["content-triage"] }); },
  });
  return (
    <div className="row" style={{ gap: 6, flexWrap: "wrap" }}>
      {DISPO.map((d) => (
        <button key={d.id} className={`btn btn-sm ${done === d.id ? "btn-primary" : "btn-ghost"}`}
                disabled={set.isPending} onClick={() => set.mutate(d.id)}>{d.label}</button>
      ))}
    </div>
  );
}

/** Explainable risk: score, level, track, the signs that fired (with quotes), gates. */
export function RiskExplain({ risk, contentRiskId, compact = false }: {
  risk: SafeNetRisk; contentRiskId?: number; compact?: boolean;
}) {
  const signals = risk.breakdown.filter((b) => (b.kind ?? "signal") === "signal" && b.contribution > 0);
  const adjustments = risk.breakdown.filter((b) => b.kind === "adjustment");
  const tracks = risk.tracks ?? {};

  return (
    <div className="stack">
      <div className="report-top">
        <RiskGauge score={risk.score} level={risk.threat_level} />
        <div className="report-meta">
          <div className="row" style={{ gap: 8, flexWrap: "wrap", alignItems: "center" }}>
            <LevelBadge level={risk.threat_level} />
            <TrackBadge track={risk.track} />
            {risk.language && <span className="badge">язык: {LANG_RU[risk.language] ?? risk.language}</span>}
            {(risk.multi_track ?? []).length > 1 && (
              <span className="badge sn-multi">несколько треков: {(risk.multi_track ?? []).map((t) => TRACK_RU[t]).join(" + ")}</span>
            )}
          </div>
          <p className="small" style={{ margin: "6px 0" }}>{risk.recommendation}</p>
          {!compact && (
            <div className="sn-track-bars">
              {TRACK_ORDER.map((t) => {
                const s = tracks[t]?.score ?? 0;
                return (
                  <div key={t} className="bar-row">
                    <span className="bar-tag">{TRACK_RU[t]}</span>
                    <div className="bar-track"><div className={`bar-fill lvl-${tracks[t]?.threat_level ?? "LOW"}`} style={{ width: `${s}%` }} /></div>
                    <span className="bar-n">{s}</span>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>

      <div>
        <div className="eyebrow" style={{ marginBottom: 6 }}>
          Почему помечено · признаков: {signals.length}
        </div>
        {signals.length === 0 ? (
          <p className="muted small">Признаков возможного нарушения не найдено.</p>
        ) : (
          <ul className="sn-signals">{signals.map((b) => <SignalLine key={b.factor} b={b} />)}</ul>
        )}
      </div>

      {adjustments.length > 0 && (
        <div>
          <div className="eyebrow" style={{ marginBottom: 6 }}>Поправки против ложных срабатываний</div>
          <ul className="sn-adjs">
            {adjustments.map((b, i) => (
              <li key={i} className="sn-adj"><span className="sn-minus">{Math.round(b.contribution)}</span> {b.note}</li>
            ))}
          </ul>
        </div>
      )}

      <div className="sn-disclaimer">
        ⚖️ {risk.disclaimer || "Система показывает признаки возможного нарушения, а не вердикт. Законность проверяет специалист."}
      </div>

      {contentRiskId !== undefined && (
        <div className="row" style={{ gap: 10, alignItems: "center", flexWrap: "wrap" }}>
          <span className="eyebrow">Решение аналитика</span>
          <DispositionButtons id={contentRiskId} />
        </div>
      )}
    </div>
  );
}

export function IdentifierList({ ids }: { ids: Record<string, string[] | undefined> }) {
  const LABEL: Record<string, string> = {
    phones: "телефон", cards: "карта", promo_codes: "промокод", short_links: "короткая ссылка",
    telegram: "telegram", domains: "домен", wallets: "кошелёк", whatsapp: "whatsapp",
  };
  const entries = Object.entries(ids).filter(([, v]) => (v ?? []).length > 0);
  if (!entries.length) return null;
  return (
    <div>
      <div className="eyebrow" style={{ marginBottom: 6 }}>Идентификаторы для графа связей</div>
      <div className="row" style={{ flexWrap: "wrap", gap: 6 }}>
        {entries.flatMap(([k, vs]) => (vs ?? []).map((v) => (
          <code key={`${k}:${v}`} className="code" title={LABEL[k] ?? k}>{LABEL[k] ?? k}: {v}</code>
        )))}
      </div>
    </div>
  );
}
