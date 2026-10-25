import { useQuery } from "@tanstack/react-query";
import { api, TRACK_RU, type Campaign } from "../../api/client";
import { LevelBadge, TrackBadge } from "./RiskExplain";

function fmt(n: number): string {
  if (!n) return "0";
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return String(n);
}

const level = (s: number) => (s >= 65 ? "HIGH" : s >= 40 ? "MEDIUM" : "LOW");

/** Networks of accounts tied by one Kaspi number / card / promo code / template text. */
export function CampaignsView({ onOpenDossier }: { onOpenDossier?: (account: string) => void }) {
  const q = useQuery<Campaign[]>({ queryKey: ["campaigns"], queryFn: api.getCampaigns });
  const list = q.data ?? [];

  return (
    <div className="stack">
      {q.isLoading && <div className="empty"><span className="spinner" /></div>}
      {q.error && <p className="err small">{(q.error as Error).message}</p>}
      {!q.isLoading && list.length === 0 && (
        <div className="card"><div className="card-pad empty">
          <h3>Сетей пока не найдено</h3>
          <p>Кампания появляется, когда два и более аккаунта используют один Kaspi-номер, карту, промокод,
            короткую ссылку, Telegram или один и тот же шаблон текста. Загрузите демо на «Обзоре».</p>
        </div></div>
      )}
      {list.map((c, i) => (
        <section key={c.id} className="card fade-in">
          <div className="card-head">
            <h2>
              #{i + 1} · Сеть из {c.accounts.length} аккаунтов{c.track ? ` · ${TRACK_RU[c.track]}` : ""}
            </h2>
            <span className="hint">приоритет {c.priority} (риск × охват)</span>
          </div>
          <div className="card-pad stack">
            <div className="row" style={{ gap: 8, flexWrap: "wrap", alignItems: "center" }}>
              <LevelBadge level={level(c.max_score)} score={c.max_score} />
              <TrackBadge track={c.track} />
              <span className="badge">материалов: {c.materials} · помечено {c.flagged}</span>
              <span className="badge">охват 👁 {fmt(c.total_views)}</span>
              <span className="badge">{c.platforms.join(" · ")}</span>
              {c.first_seen && <span className="muted small">
                {new Date(c.first_seen).toLocaleDateString()} – {c.last_seen ? new Date(c.last_seen).toLocaleDateString() : ""}
              </span>}
            </div>

            <div>
              <div className="eyebrow" style={{ marginBottom: 6 }}>Почему это одна сеть</div>
              <ul className="sn-signals">
                {c.shared.map((s, k) => (
                  <li key={k} className="sn-signal" style={{ gridTemplateColumns: "130px 1fr" }}>
                    <span className="badge">{s.kind}</span>
                    <div>
                      <code className="code">{s.value}</code>
                      <div className="muted small">общий у: {s.accounts.join(", ")}</div>
                    </div>
                  </li>
                ))}
              </ul>
            </div>

            <div>
              <div className="eyebrow" style={{ marginBottom: 6 }}>Аккаунты и группы</div>
              <div className="chip-row">
                {c.accounts.map((a) => (
                  <button key={a.account} className="chip" disabled={!onOpenDossier || a.account.startsWith("group:")}
                          onClick={() => onOpenDossier?.(a.account)} title="Открыть досье">
                    {a.account} <span className="muted small">· {a.source} · {a.materials} мат. · макс {a.max_score}</span>
                  </button>
                ))}
              </div>
            </div>

            <div>
              <div className="eyebrow" style={{ marginBottom: 6 }}>Самые рискованные материалы</div>
              <table className="table">
                <tbody>{c.top_materials.map((m) => (
                  <tr key={m.content_risk_id}>
                    <td style={{ width: 160 }}><b>{m.author}</b></td>
                    <td className="small">{m.text}</td>
                    <td style={{ width: 110 }}><LevelBadge level={m.threat_level} score={m.score} /></td>
                  </tr>
                ))}</tbody>
              </table>
            </div>
          </div>
        </section>
      ))}
    </div>
  );
}
