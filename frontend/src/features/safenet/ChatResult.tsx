import { LANG_RU, type ChatAnalysis } from "../../api/client";
import { IdentifierList, LevelBadge, RiskExplain } from "./RiskExplain";
import { printReport } from "./printReport";

const PLATFORM: Record<string, string> = { telegram: "Telegram", whatsapp: "WhatsApp", text: "текст" };

/** Group analysis: risk of the whole chat, candidate roles, risky messages, templates. */
export function ChatResult({ r }: { r: ChatAnalysis }) {
  const langs = Object.entries(r.languages).map(([k, n]) => `${LANG_RU[k] ?? k}: ${n}`).join(", ");
  return (
    <div className="stack fade-in">
      <section className="card">
        <div className="card-head">
          <h2>{r.group}</h2>
          <span className="hint">
            {PLATFORM[r.platform] ?? r.platform} · {r.messages} сообщений · {r.authors} участников ·
            помечено сообщений: {r.flagged_messages}{langs ? ` · ${langs}` : ""}
            <button className="btn btn-ghost btn-sm" style={{ marginLeft: 10 }}
                    onClick={() => printReport(r.risk, {
                      title: r.group, source: r.platform, sha256: r.sha256, identifiers: r.identifiers,
                      text: [`Организатор (кандидат): ${r.organizer || "—"}`, `Кураторы (кандидаты): ${r.curators.join(", ") || "—"}`, "",
                             ...r.top_messages.filter((m) => m.score > 0).map((m) => `[${m.author}] (${m.score}) ${m.text}`)].join("\n"),
                    })}>
              Справка (печать / PDF)
            </button>
          </span>
        </div>
        <div className="card-pad stack">
          <RiskExplain risk={r.risk} contentRiskId={r.content_risk_id} />
          <IdentifierList ids={r.identifiers} />
        </div>
      </section>

      <div className="dash-cols">
        <section className="card">
          <div className="card-head"><h2>Структура группы</h2><span className="hint">роли — кандидаты для проверки</span></div>
          <div className="card-pad">
            <table className="table">
              <thead><tr><th>Участник</th><th>Роль</th><th>Сообщ.</th><th>Рисковых</th><th>Денежных признаков</th></tr></thead>
              <tbody>
                {r.members.slice(0, 15).map((m) => (
                  <tr key={m.author}>
                    <td><b>{m.author}</b></td>
                    <td>{m.role === "участник" ? <span className="muted small">участник</span>
                      : <span className="badge threat HIGH">{m.role}</span>}</td>
                    <td>{m.messages}</td><td>{m.risky_messages}</td><td>{m.money_signals}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        <section className="card">
          <div className="card-head"><h2>Шаблонные сообщения</h2><span className="hint">похожие тексты от разных людей</span></div>
          <div className="card-pad stack">
            {r.templates.length === 0 ? <p className="muted small">Шаблонов не найдено.</p> : r.templates.map((t, i) => (
              <div key={i} className="sn-template">
                <b>{t.size} сообщений</b> от {t.authors.length} участников: {t.authors.slice(0, 6).join(", ")}
                <div className="muted small">«{t.example}»</div>
              </div>
            ))}
          </div>
        </section>
      </div>

      <section className="card">
        <div className="card-head"><h2>Самые рискованные сообщения</h2><span className="hint">по убыванию балла</span></div>
        <div className="card-pad">
          <table className="table">
            <thead><tr><th>Автор</th><th>Сообщение</th><th>Риск</th><th>Признаки</th></tr></thead>
            <tbody>
              {r.top_messages.filter((m) => m.score > 0).map((m) => (
                <tr key={m.index}>
                  <td><b>{m.author}</b>{m.ts && <div className="muted small">{m.ts.replace("T", " ").slice(0, 16)}</div>}</td>
                  <td className="small">{m.text}</td>
                  <td><LevelBadge level={m.level} score={m.score} /></td>
                  <td className="muted small">{m.signals.join("; ")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
