import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, type Dossier, type DossierIdentifier, type IdentifierKind } from "../../api/client";
import { SearchIcon, WalletIcon, NetworkIcon } from "../../components/icons";

/** Compact number: 1234 → 1.2K, 2_500_000 → 2.5M. */
function fmt(n: number): string {
  if (!n) return "0";
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return String(n);
}

const FACTOR_LABEL: Record<string, string> = {
  financial_promises: "Финансовые обещания",
  referral_structure: "Реферальная структура",
  known_scheme_repetition: "Повтор известной схемы",
  suspicious_links: "Подозрительные связи",
  gambling_content: "Азартный контент",
  infra_anonymity: "Анонимная инфраструктура",
};

/** Open a print-ready analytical report (browser → Save as PDF). Self-contained HTML. */
function printDossier(d: Dossier) {
  const esc = (s: string) => String(s ?? "").replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]!));
  const ids = d.identifiers.map((i) => `<li>${esc(i.kind)}: <b>${esc(i.value)}</b> ×${i.count}</li>`).join("");
  const who = d.whois.map((w) => `<li><b>${esc(w.domain)}</b> — регистратор: ${esc(w.registrar || "—")}, создан: ${esc((w.registered || "—").slice(0, 10))}${w.age_days != null ? ` (${w.age_days} дн.)` : ""}</li>`).join("");
  const pat = d.pattern.map((p) => `<li>${esc(p.label || p.factor)} — ${p.videos} материалов</li>`).join("");
  const lnk = d.linked_accounts.map((l) => `<li>${esc(l.author)} — общие: ${esc(l.shared.join(", "))}</li>`).join("");
  const vids = d.videos.map((v) => `<tr><td>${esc(v.content_id)}</td><td>${v.score ?? "—"} ${esc(v.threat_level || "")}</td><td>${esc(v.source)}</td></tr>`).join("");
  const c = d.campaign;
  const html = `<!doctype html><html lang="ru"><head><meta charset="utf-8"><title>Справка — ${esc(d.account)}</title>
  <style>body{font:13px/1.5 system-ui,sans-serif;color:#111;max-width:820px;margin:24px auto;padding:0 16px}
  h1{font-size:20px;margin:0 0 4px}h2{font-size:14px;margin:18px 0 6px;border-bottom:1px solid #ccc;padding-bottom:3px}
  .muted{color:#666}.v{font-weight:700}table{border-collapse:collapse;width:100%}td,th{border:1px solid #ddd;padding:4px 8px;text-align:left;font-size:12px}
  .banner{border:1px solid #999;border-left:4px solid #c00;padding:8px 12px;border-radius:6px;margin:8px 0}
  ul{margin:4px 0;padding-left:20px}</style></head><body>
  <h1>Аналитическая справка — ${esc(d.account)}</h1>
  <div class="muted">SafeNet KZ · источник: ${esc(d.source || "—")} · сформировано: ${new Date().toLocaleString("ru-RU")}</div>
  <div class="banner"><b>Кампания:</b> ${c.posts} публикаций → ${c.accounts} аккаунт(ов) → ${c.wallets + c.telegram + c.domains + c.phones} идентификаторов → ${c.is_network ? "1 сеть" : "1 объект"} · <span class="v">${esc(c.threat_level)}</span>${c.is_network ? ` · организатор: ${esc(c.ringleader)}` : ""}</div>
  <h2>Риск</h2><div>Общий балл: <span class="v">${d.overall ? `${d.overall.score} · ${esc(d.overall.threat_level)}` : "—"}</span> · видео: ${d.totals.videos} · охват: ${d.totals.total_views}</div>
  <h2>Идентификаторы</h2><ul>${ids || "<li>—</li>"}</ul>
  ${who ? `<h2>Домены (WHOIS)</h2><ul>${who}</ul>` : ""}
  <h2>Паттерн нарушений</h2><ul>${pat || "<li>—</li>"}</ul>
  ${lnk ? `<h2>Связанные аккаунты</h2><ul>${lnk}</ul>` : ""}
  <h2>Видео (${d.videos.length})</h2><table><thead><tr><th>ID</th><th>Риск</th><th>Источник</th></tr></thead><tbody>${vids || ""}</tbody></table>
  <p class="muted" style="margin-top:24px">Документ сформирован автоматически. Риск-оценка детерминирована; каждый фактор прослеживается к доказательству. Система показывает признаки возможного нарушения, а не вердикт; деанонимизация и процессуальные действия — в полномочиях профильных ведомств.</p>
  </body></html>`;
  const w = window.open("", "_blank");
  if (!w) return;
  w.document.write(html);
  w.document.close();
  w.focus();
  setTimeout(() => w.print(), 300);
}

const KIND_LABEL: Record<IdentifierKind, string> = {
  telegram: "Telegram-каналы",
  wallet: "Криптокошельки",
  phone: "Телефоны",
  domain: "Домены / сайты",
};
const KIND_ORDER: IdentifierKind[] = ["telegram", "wallet", "phone", "domain"];

/** A single identifier chip — Telegram/domain become links; wallet/phone are copyable. */
function IdentifierChip({ id }: { id: DossierIdentifier }) {
  const href =
    id.kind === "telegram" ? `https://t.me/${id.value.replace(/^@/, "")}`
    : id.kind === "domain" ? `https://${id.value}`
    : undefined;
  const body = (
    <>
      <span className="mono">{id.value}</span>
      {id.count > 1 && <span className="muted small"> ×{id.count}</span>}
    </>
  );
  return (
    <li className="ident-chip" title={`в ${id.count} видео`}>
      {href ? <a href={href} target="_blank" rel="noreferrer noopener">{body}</a> : body}
    </li>
  );
}

export function TargetDossierView({
  initialTarget, onInvestigate,
}: { initialTarget?: string; onInvestigate?: (account: string) => void }) {
  const accounts = useQuery<string[]>({ queryKey: ["accounts"], queryFn: api.getAccounts });
  const list = accounts.data ?? [];
  const [account, setAccount] = useState(initialTarget ?? "");

  useEffect(() => { if (initialTarget) setAccount(initialTarget); }, [initialTarget]);
  useEffect(() => { if (!account && list.length) setAccount(list[0]); }, [list, account]);

  const dossier = useQuery<Dossier>({
    queryKey: ["dossier", account],
    queryFn: () => api.getDossier(account),
    enabled: !!account,
  });
  const d = dossier.data;

  return (
    <section className="card">
      <div className="card-head">
        <h2>Досье таргета</h2>
        <span className="hint">полный портрет аккаунта: видео, риск, каналы, связи</span>
      </div>
      <div className="card-pad" style={{ display: "grid", gap: 16 }}>
        {/* target picker */}
        <div className="input-row">
          <select className="input" value={account} onChange={(e) => setAccount(e.target.value)}>
            {!list.length && <option value="">База пуста</option>}
            {list.map((a) => <option key={a} value={a}>{a}</option>)}
          </select>
          {onInvestigate && account && (
            <button className="btn btn-ghost" onClick={() => onInvestigate(account)} title="Открыть расследование">
              <SearchIcon size={16} /> Расследовать
            </button>
          )}
          {dossier.data && (
            <button className="btn btn-ghost" onClick={() => printDossier(dossier.data!)}
                    title="Печатная аналитическая справка (PDF)">
              Справка (PDF)
            </button>
          )}
        </div>

        {dossier.isLoading && <div className="empty"><span className="spinner" /></div>}
        {dossier.error && <span className="err small">{(dossier.error as Error).message}</span>}
        {!account && !dossier.isLoading && (
          <div className="empty"><h3>Аккаунтов пока нет</h3>
            <p>Соберите данные через «Мониторинг» или «Анализ видео» — затем здесь появится досье.</p></div>
        )}

        {d && (
          <>
            {/* summary header */}
            <div className="dossier-summary">
              <div className="ds-id">
                <div className="ds-account">{d.account}</div>
                <div className="muted small">{d.source || "источник неизвестен"}</div>
              </div>
              {d.overall && (
                <span className={`badge threat ${d.overall.threat_level}`}>
                  Общий риск: {d.overall.score} · {d.overall.threat_level}
                </span>
              )}
              <div className="ds-stats">
                <div><b>{d.totals.videos}</b><span className="muted small">видео</span></div>
                <div><b>{d.totals.avg_score ?? "—"}</b><span className="muted small">средний риск</span></div>
                <div><b>{d.totals.max_score ?? "—"}</b><span className="muted small">макс. риск</span></div>
                <div><b>{fmt(d.totals.total_views)}</b><span className="muted small">просмотров</span></div>
              </div>
            </div>

            {/* campaign rollup — «от видео к сети» */}
            {d.campaign && (
              <div className={`campaign-banner threat ${d.campaign.threat_level}`}>
                <div className="campaign-flow">
                  <span><b>{d.campaign.posts}</b> публикаций</span>
                  <span className="flow-arrow">→</span>
                  <span><b>{d.campaign.accounts}</b> {d.campaign.accounts > 1 ? "аккаунтов" : "аккаунт"}</span>
                  <span className="flow-arrow">→</span>
                  <span><b>{d.campaign.wallets + d.campaign.telegram + d.campaign.domains + d.campaign.phones}</b> идентификаторов</span>
                  <span className="flow-arrow">→</span>
                  <span className="campaign-verdict">
                    {d.campaign.is_network ? "1 сеть" : "1 объект"} · <b>{d.campaign.threat_level}</b>
                  </span>
                </div>
                {d.campaign.is_network && (
                  <div className="muted small">
                    Вероятный организатор: <button className="linklike" onClick={() => setAccount(d.campaign.ringleader)}>{d.campaign.ringleader}</button>
                    {d.campaign.shared_identifiers.length > 0 && <> · общие: {d.campaign.shared_identifiers.slice(0, 3).join(", ")}</>}
                  </div>
                )}
              </div>
            )}

            {/* recurring pattern */}
            {d.pattern.length > 0 && (
              <div>
                <h3 className="ds-h3">Общий паттерн</h3>
                <div className="chip-row">
                  {d.pattern.map((p) => (
                    <span key={p.factor} className="chip" title={`средний вклад ${p.avg_contribution} балла`}>
                      {p.label || (FACTOR_LABEL[p.factor] ?? p.factor)}
                      <span className="muted small"> · {p.videos} видео</span>
                    </span>
                  ))}
                </div>
              </div>
            )}

            {/* aggregated identifiers (TG channels / wallets / phones / domains) */}
            <div>
              <h3 className="ds-h3">Каналы и идентификаторы</h3>
              {d.identifiers.length === 0 ? (
                <p className="muted small">В роликах не найдено явных идентификаторов (кошельков, каналов, телефонов).</p>
              ) : (
                <div className="ident-grid">
                  {KIND_ORDER.map((kind) => {
                    const items = d.identifiers.filter((i) => i.kind === kind);
                    if (!items.length) return null;
                    return (
                      <div key={kind} className="ident-group">
                        <div className="ident-head">
                          {kind === "wallet" ? <WalletIcon size={15} /> : kind === "telegram" ? <NetworkIcon size={15} /> : null}
                          {KIND_LABEL[kind]} <span className="muted small">({items.length})</span>
                        </div>
                        <ul className="ident-list">{items.map((i) => <IdentifierChip key={i.value} id={i} />)}</ul>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>

            {/* WHOIS / RDAP enrichment for advertised domains */}
            {d.whois.length > 0 && (
              <div>
                <h3 className="ds-h3">Домены (WHOIS / RDAP)</h3>
                <div className="ident-grid">
                  {d.whois.map((w) => {
                    const fresh = w.age_days != null && w.age_days < 730;   // <2 года — частый признак скам-инфраструктуры
                    return (
                      <div key={w.domain} className="ident-group">
                        <div className="ident-head">
                          <span className="mono">{w.domain}</span>
                          {fresh && <span className="badge threat HIGH" title="недавно зарегистрирован">свежий домен</span>}
                        </div>
                        <ul className="ident-list">
                          {w.registrar && <li className="muted small">регистратор: {w.registrar}</li>}
                          {w.registered && <li className="muted small">создан: {w.registered.slice(0, 10)}
                            {w.age_days != null && <> ({w.age_days} дн. назад)</>}</li>}
                          {w.expires && <li className="muted small">истекает: {w.expires.slice(0, 10)}</li>}
                          {w.nameservers.length > 0 && <li className="muted small">NS: {w.nameservers.join(", ")}</li>}
                        </ul>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}

            {/* linked accounts (shared hard identifiers) */}
            {d.linked_accounts.length > 0 && (
              <div>
                <h3 className="ds-h3">Связанные аккаунты <span className="muted small">(общие идентификаторы = одна схема)</span></h3>
                <ul className="linked-list">
                  {d.linked_accounts.map((l) => (
                    <li key={l.author}>
                      <button className="linklike" onClick={() => setAccount(l.author)} title="Открыть досье">{l.author}</button>
                      <span className="muted small"> — общие: {l.shared.join(", ")}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {/* videos */}
            <div>
              <h3 className="ds-h3">Видео ({d.videos.length})</h3>
              {d.videos.length === 0 ? (
                <p className="muted small">Нет собранных роликов.</p>
              ) : (
                <table className="table">
                  <thead>
                    <tr><th>Материал</th><th>Риск</th><th>Охват</th><th>Найденные идентификаторы</th></tr>
                  </thead>
                  <tbody>
                    {d.videos.map((v) => {
                      const ids = [
                        ...v.identifiers.telegram.map((x) => `tg ${x}`),
                        ...v.identifiers.wallets.map((x) => `wallet ${x.slice(0, 14)}…`),
                        ...v.identifiers.phones.map((x) => `тел ${x}`),
                        ...v.identifiers.domains.map((x) => `сайт ${x}`),
                      ];
                      return (
                        <tr key={v.content_id}>
                          <td>
                            <b>{v.content_id}</b>
                            <div className="muted small">
                              {v.source}
                              {v.url && <> · <a href={v.url} target="_blank" rel="noreferrer noopener">видео</a></>}
                            </div>
                            {(v.transcript || v.ocr_text) && (
                              <details className="transcript">
                                <summary className="muted small">транскрипт / текст на экране</summary>
                                {v.transcript && <div className="t-block"><span className="t-label">Речь</span><p>{v.transcript}</p></div>}
                                {v.ocr_text && <div className="t-block"><span className="t-label">Текст на экране</span><p>{v.ocr_text}</p></div>}
                              </details>
                            )}
                          </td>
                          <td>
                            {v.score != null
                              ? <span className={`badge threat ${v.threat_level}`}>{v.score} · {v.threat_level}</span>
                              : <span className="muted small">не оценено</span>}
                          </td>
                          <td className="muted small">👁 {fmt(v.reach?.views ?? 0)}</td>
                          <td className="muted small">{ids.length ? ids.join(" · ") : "—"}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              )}
            </div>
          </>
        )}
      </div>
    </section>
  );
}
