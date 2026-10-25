import type { ThreatLevel } from "../../api/client";

const LEVEL_VAR: Record<ThreatLevel, string> = {
  LOW: "var(--low)",
  MEDIUM: "var(--medium)",
  HIGH: "var(--critical)",
  CRITICAL: "var(--critical)",
};

/** Circular SVG ring showing a 0–100 risk score, coloured by threat level. */
export function RiskGauge({ score, level }: { score: number; level: ThreatLevel }) {
  const r = 56;
  const c = 2 * Math.PI * r;
  const pct = Math.max(0, Math.min(100, score)) / 100;
  const color = LEVEL_VAR[level];

  return (
    <div className="gauge" role="img" aria-label={`Risk score ${score} of 100, ${level}`}>
      <svg width="132" height="132" viewBox="0 0 132 132">
        <circle cx="66" cy="66" r={r} fill="none" stroke="var(--border)" strokeWidth="10" />
        <circle
          cx="66"
          cy="66"
          r={r}
          fill="none"
          stroke={color}
          strokeWidth="10"
          strokeLinecap="round"
          strokeDasharray={c}
          strokeDashoffset={c * (1 - pct)}
          transform="rotate(-90 66 66)"
          style={{ transition: "stroke-dashoffset .8s cubic-bezier(.4,0,.2,1)", filter: `drop-shadow(0 0 6px ${color})` }}
        />
      </svg>
      <div className="num">
        <b style={{ color }}>{Math.round(score)}</b>
        <span>/ 100 risk</span>
      </div>
    </div>
  );
}
