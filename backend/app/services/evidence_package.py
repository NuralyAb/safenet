"""Evidence Package Generator — «Аналитическая справка с цифровыми доказательствами».

Turns the AI output into a legally-presentable document by binding it to the
chain of custody we already keep (SHA-256 + WORM). The package itself is
tamper-evident: a manifest hash covers everything, so any later edit is provable.

Pure (no I/O) -> unit-tested. The endpoint assembles the inputs (workflow report
+ evidence rows) and calls this.
"""
from __future__ import annotations

import hashlib
import json


def package_hash(package: dict) -> str:
    """SHA-256 over the whole package except the manifest field itself."""
    body = {k: v for k, v in package.items() if k != "manifest_sha256"}
    blob = json.dumps(body, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(blob.encode()).hexdigest()


def build_package(report: dict, evidence: list[dict], *, generated_at: str,
                  generated_by: str) -> dict:
    """Assemble the analytical report. `report` = investigation result; `evidence` =
    chain-of-custody rows [{sha256, evidence_key, collected_at, source, url}]."""
    risk = report.get("risk", {}) if isinstance(report, dict) else {}
    network = report.get("network", {}) if isinstance(report, dict) else {}

    package = {
        "title": "Аналитическая справка с цифровыми доказательствами",
        "object": report.get("target", ""),
        "category": report.get("category", ""),
        "generated_at": generated_at,
        "generated_by": generated_by,
        "risk": {
            "score": risk.get("score"),
            "threat_level": risk.get("threat_level"),
            "recommendation": risk.get("recommendation"),
        },
        # Explainability: each factor traces to evidence_ids -> defensible.
        "factors": [
            {"factor": b.get("factor"), "contribution": b.get("contribution"),
             "evidence_ids": b.get("evidence_ids", []), "note": b.get("note", "")}
            for b in risk.get("breakdown", [])
        ],
        "findings": report.get("findings", []),
        "scheme_matches": report.get("scheme_matches", 0),
        "network": {
            "related_objects": network.get("related_objects", 0),
            "accounts": network.get("accounts", 0),
            "wallets": network.get("wallets", 0),
        },
        "narrative": report.get("narrative", ""),
        "evidence": [
            {"sha256": e.get("sha256"), "evidence_key": e.get("evidence_key"),
             "collected_at": e.get("collected_at"), "source": e.get("source"),
             "url": e.get("url", "")}
            for e in evidence
        ],
        "chain_of_custody": (
            "Оригиналы хранятся в WORM-хранилище (object-lock). Целостность каждого "
            "артефакта подтверждается SHA-256, зафиксированным в момент сбора. Оценка "
            "риска детерминирована и объяснима; каждый фактор привязан к доказательству."
        ),
    }
    package["manifest_sha256"] = package_hash(package)
    return package


def render_markdown(p: dict) -> str:
    """Human-readable справка for export/print."""
    lines = [
        f"# {p['title']}", "",
        f"**Объект:** {p['object']}  ", f"**Категория:** {p['category']}  ",
        f"**Сформировано:** {p['generated_at']} · {p['generated_by']}", "",
        "## Оценка риска",
        f"- **Риск:** {p['risk']['score']}/100 ({p['risk']['threat_level']})",
        f"- **Рекомендация:** {p['risk']['recommendation']}", "",
        "## Факторы (с привязкой к доказательствам)",
    ]
    for f in p["factors"]:
        ev = ", ".join(f["evidence_ids"]) or "—"
        lines.append(f"- {f['factor']}: вклад {f['contribution']} · улики: {ev}"
                     + (f" · {f['note']}" if f["note"] else ""))
    lines += ["", "## Связи", f"- Объектов в сети: {p['network']['related_objects']} "
              f"({p['network']['accounts']} аккаунтов, {p['network']['wallets']} кошельков)",
              f"- Совпадений со схемами: {p['scheme_matches']}", "",
              "## Заключение AI", p["narrative"], "",
              "## Доказательная база (chain of custody)"]
    for e in p["evidence"]:
        lines.append(f"- `{e['sha256']}` · {e['source']} · {e['collected_at']} · {e['evidence_key']}")
    lines += ["", p["chain_of_custody"], "",
              f"**Хеш-манифест справки (целостность):** `{p['manifest_sha256']}`"]
    return "\n".join(lines)
