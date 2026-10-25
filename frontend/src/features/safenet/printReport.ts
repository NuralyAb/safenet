import { LANG_RU, LEVEL_RU, SOURCE_RU, TRACK_RU, VIEW_RU, type SafeNetRisk } from "../../api/client";

/** Areas of law a specialist would check for each track — reference only, not a legal qualification. */
const LAW: Record<string, string[]> = {
  lottery: ["Закон РК «О лотереях и лотерейной деятельности»", "Закон РК «О рекламе»"],
  casino: ["Закон РК «Об игорном бизнесе»", "Закон РК «О рекламе»",
           "Уголовный кодекс РК — нормы о незаконном игорном бизнесе"],
  pyramid: ["Уголовный кодекс РК, ст. 217 «Создание и руководство финансовой (инвестиционной) пирамидой»",
            "Закон РК «О рекламе»"],
};

const esc = (s: string) => s.replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c] as string));

export interface ReportMeta {
  title: string;          // account / group / file
  source?: string;
  sha256?: string;
  text?: string;
  identifiers?: Record<string, string[] | undefined>;
}

/** Open a printable «Аналитическая справка» (browser print → PDF). */
export function printReport(risk: SafeNetRisk, meta: ReportMeta) {
  const signals = risk.breakdown.filter((b) => (b.kind ?? "signal") === "signal" && b.contribution > 0);
  const adj = risk.breakdown.filter((b) => b.kind === "adjustment");
  const ids = Object.entries(meta.identifiers ?? {}).filter(([, v]) => (v ?? []).length);
  const law = LAW[risk.track ?? ""] ?? [];
  const now = new Date().toLocaleString("ru-RU");
  const rows = signals.map((b) => `
    <tr><td>+${Math.round(b.contribution)}</td><td><b>${esc(b.label ?? b.factor)}</b>${b.detail ? `<div class="m">${esc(b.detail)}</div>` : ""}
      ${(b.quotes ?? []).map((q) => `<div class="q">«${esc(q.text)}»<span>${esc([SOURCE_RU[q.source] ?? q.source, VIEW_RU[q.view] ?? ""].filter(Boolean).join(" · "))}</span></div>`).join("")}
      ${b.without !== undefined ? `<div class="m">без этого признака: ${b.without} (${LEVEL_RU[b.level_without ?? "LOW"]})</div>` : ""}</td></tr>`).join("");
  const html = `<!doctype html><html lang="ru"><head><meta charset="utf-8"><title>Справка SafeNet KZ — ${esc(meta.title)}</title>
<style>
 body{font:14px/1.5 "Segoe UI",Arial,sans-serif;color:#111;max-width:820px;margin:28px auto;padding:0 18px}
 h1{font-size:20px;margin:0 0 4px} h2{font-size:15px;margin:22px 0 8px;border-bottom:1px solid #ccc;padding-bottom:4px}
 .meta{color:#555;font-size:12px} .lvl{display:inline-block;padding:3px 10px;border-radius:6px;font-weight:700;color:#fff;background:${risk.threat_level === "HIGH" ? "#c62828" : risk.threat_level === "MEDIUM" ? "#b7791f" : "#2e7d32"}}
 table{width:100%;border-collapse:collapse} td{border-bottom:1px solid #eee;padding:6px 4px;vertical-align:top} td:first-child{width:48px;font-weight:700;color:#c62828}
 .q{background:#fff7e0;border:1px solid #f0d58a;border-radius:4px;padding:2px 6px;margin:3px 0;display:inline-block} .q span{display:block;font-size:11px;color:#777}
 .m{color:#555;font-size:12px} .box{border:1px solid #999;border-radius:6px;padding:10px;margin-top:8px}
 .disc{background:#eef3ff;border:1px solid #c5d4ff;border-radius:6px;padding:10px;font-size:13px}
 pre{white-space:pre-wrap;background:#f6f6f6;padding:10px;border-radius:6px;font:12px/1.45 Consolas,monospace}
 @media print{button{display:none}}
</style></head><body>
<button onclick="window.print()" style="float:right">Печать / PDF</button>
<h1>Аналитическая справка SafeNet KZ</h1>
<div class="meta">Сформировано: ${esc(now)} · объект: <b>${esc(meta.title)}</b>${meta.source ? ` · источник: ${esc(meta.source)}` : ""}${meta.sha256 ? `<br>SHA-256 материала (цепочка хранения): <code>${esc(meta.sha256)}</code>` : ""}</div>
<h2>Итог</h2>
<p><span class="lvl">${risk.score}/100 · ${esc(LEVEL_RU[risk.threat_level] ?? risk.threat_level)}</span>
 &nbsp; трек: <b>${esc(TRACK_RU[risk.track ?? ""] ?? "—")}</b>${risk.language ? ` · язык: ${esc(LANG_RU[risk.language] ?? risk.language)}` : ""}</p>
<p>${esc(risk.recommendation)}</p>
<h2>Признаки возможного нарушения (${signals.length})</h2>
<table>${rows || "<tr><td></td><td>Признаков не найдено.</td></tr>"}</table>
${adj.length ? `<h2>Поправки против ложных срабатываний</h2><ul>${adj.map((b) => `<li>${Math.round(b.contribution)} — ${esc(b.note ?? "")}</li>`).join("")}</ul>` : ""}
${ids.length ? `<h2>Идентификаторы</h2><ul>${ids.map(([k, v]) => `<li>${esc(k)}: ${esc((v ?? []).join(", "))}</li>`).join("")}</ul>` : ""}
${law.length ? `<h2>Нормы для проверки специалистом (справочно)</h2><ul>${law.map((l) => `<li>${esc(l)}</li>`).join("")}</ul><div class="m">Перечень не является юридической квалификацией; применимость и актуальную редакцию определяет специалист.</div>` : ""}
${meta.text ? `<h2>Текст материала</h2><pre>${esc(meta.text.slice(0, 6000))}</pre>` : ""}
<h2>Решение специалиста</h2>
<div class="box">☐ Передать в профильное ведомство &nbsp; ☐ Наблюдение &nbsp; ☐ Ложное срабатывание<br><br>Комментарий: ____________________________________________<br><br>ФИО, подпись, дата: ______________________________</div>
<p class="disc">⚖️ ${esc(risk.disclaimer || "Система показывает признаки возможного нарушения, а не вердикт.")}</p>
</body></html>`;
  const w = window.open("", "_blank");
  if (!w) return;
  w.document.open();
  w.document.write(html);
  w.document.close();
}
