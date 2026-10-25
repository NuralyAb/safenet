"""Evaluate the SafeNet KZ detector and write the metrics report.

    python -m scripts.evaluate_safenet                 # test set, rules-only
    python -m scripts.evaluate_safenet --set dev       # tuning set
    python -m scripts.evaluate_safenet --errors        # print misclassified items
    python -m scripts.evaluate_safenet --write-docs    # regenerate docs/METRICS.md
    python -m scripts.evaluate_safenet --llm           # + LLM assist (synthetic data only!)
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.services.safenet.evaluation import evaluate, load
from app.services.safenet.lexicon import TRACK_LABELS

# repo docs/ when run from a checkout; inside the backend container (/app) docs/ isn't mounted
_REPO_DOCS = Path(__file__).resolve().parents[2] / "docs"
DOCS = (_REPO_DOCS if _REPO_DOCS.is_dir() else Path(__file__).resolve().parents[1]) / "METRICS.md"


def pct(x) -> str:
    return "—" if x is None else f"{100 * x:.1f}%"


def to_markdown(reports: dict[str, dict]) -> str:
    lines = ["# SafeNet KZ — метрики качества", "",
             "Сгенерировано `python -m scripts.evaluate_safenet --write-docs`. Без LLM и внешних API — "
             "воспроизводимо офлайн. Два режима: **правила** (детерминированный словарь + числа) и "
             "**правила + модель** (плюс обучаемый слой `model.py`, обученный только на dev/test/holdout).", "",
             "«Помечено» = балл ≥ 40 (уровень «средний» или «высокий») — материал уходит "
             "специалисту на ручную проверку. Система не выносит вердикт.", "",
             "## Протокол оценки (честно)", "",
             "Все выборки синтетические и размечены вручную. Каждую новую выборку прогоняли **один раз "
             "вслепую** и фиксировали результат. Слепые выборки blind и blind2 написали отдельные "
             "исполнители, не видевшие ни правил, ни других выборок.", "",
             "| Прогон | Версия | Режим | Precision | Recall | F1 | FPR | Комментарий |",
             "|---|---|---|---|---|---|---|---|",
             "| test (178), вслепую | v1 | правила | 100% | 65.3% | 79.0% | 0% | гейты слишком строгие |",
             "| holdout (120), вслепую | v2 | правила | 90.2% | 76.7% | 82.9% | 8.3% | после разбора ошибок test |",
             "| blind (150), вслепую | v3 | правила | 96.6% | 63.3% | 76.5% | 3.3% | независимый автор |",
             "| **blind2 (150), вслепую** | **v4** | правила | 94.9% | 62.2% | 75.2% | 5.0% | "
             "второй независимый автор, сложнее: числа прописью, эфиры, OCR, казахские чаты |",
             "| **blind2 (150), вслепую** | **v4** | **правила + модель** | **95.6%** | **72.2%** | **82.3%** | "
             "**5.0%** | **главная оценка**: модель +10 п.п. recall без роста ложных срабатываний |", "",
             "Что изменилось в v4 (общие механизмы, не подгонка под выборку): числа прописью RU/KZ и денежный "
             "сленг, «эмодзи-арифметика», исправлена ошибка `азино`⊂`казино` (ложный бренд), канал-прокладка "
             "и «даю ссылку» как призыв, обучаемый слой.", "",
             "Слабое место — **пирамиды на незнакомом стиле** (recall ≈ 57% на blind2): «капает каждый день», "
             "суммы без явного вложения. Следующий шаг — модель на решениях аналитиков из очереди "
             "(экран «Адаптация») и LLM-помощник с проверкой цитат (замер не выполнен — у ключа OpenAI нет квоты).", "",
             "Ниже — детальные цифры. dev/test/holdout в режиме «правила + модель» не приводятся: "
             "модель на них обучена. blind после v3 видел разработчик (ошибки разбирались), поэтому для v4 "
             "он полуслепой.", ""]
    for key, r in reports.items():
        name, mode = key if isinstance(key, tuple) else (key, "rules")
        mode_ru = "правила + модель" if mode == "model" else "только правила"
        title = {
            "blind2": "Слепая выборка №2 — главная оценка v4",
            "blind": "Слепая выборка №1 (оценка v3; для v4 — полуслепая)",
            "holdout": "Отложенная выборка №2 (слепой прогон v2 дал P 90.2% / R 76.7% / FPR 8.3%; "
                       "затем использована для разбора ошибок — цифры ниже уже НЕ слепые)",
            "test": "Тестовая выборка №1 (слепой прогон v1 дал P 100% / R 65.3% / FPR 0%; "
                    "затем использована для разбора ошибок — цифры ниже уже НЕ слепые)",
            "dev": "Выборка настройки (синтетические шаблоны, на ней подбирались признаки)",
        }[name] + f" · {mode_ru}"
        b = r["binary"]
        lines += [f"## {title}", "",
                  f"Объём: **{r['n']}** (позитивов {r['positives']}, негативов {r['negatives']}, "
                  f"из них трудных негативов {r['hard_negatives']}).", "",
                  "| Метрика | Значение |", "|---|---|",
                  f"| Precision | **{pct(b['precision'])}** |", f"| Recall | **{pct(b['recall'])}** |",
                  f"| F1 | {pct(b['f1'])} |",
                  f"| Доля ложных срабатываний (FPR) | **{pct(b['fpr'])}** |",
                  f"| FPR на трудных негативах | {pct(r['hard_negative_fpr'])} |",
                  f"| Accuracy | {pct(b['accuracy'])} |",
                  f"| Recall на уровне «высокий» | {pct(r['high_level']['recall'])} |",
                  f"| FPR на уровне «высокий» | {pct(r['high_level']['fpr'])} |", "",
                  "### По трекам", "", "| Трек | N | Precision | Recall | F1 | FPR на чистом контенте |",
                  "|---|---|---|---|---|---|"]
        for t, m in r["per_track"].items():
            lines.append(f"| {TRACK_LABELS[t]} | {m['support']} | {pct(m['precision'])} | {pct(m['recall'])} | "
                         f"{pct(m['f1'])} | {pct(m['fpr'])} |")
        lines += ["", "### Recall по языкам", "", "| Язык | N | Recall |", "|---|---|---|"]
        for k, v in r["recall_by_language"].items():
            lines.append(f"| {k} | {v['n']} | {pct(v['recall'])} |")
        lines += ["", "### Recall при обфускации", "", "| Обфускация | N | Recall |", "|---|---|---|"]
        for k, v in r["recall_by_obfuscation"].items():
            lines.append(f"| {k} | {v['n']} | {pct(v['recall'])} |")
        lines += ["", "### Матрица ошибок (строки — разметка, столбцы — прогноз)", "",
                  "| | " + " | ".join(r["confusion"]) + " |", "|---" * (len(r["confusion"]) + 1) + "|"]
        for a, row in r["confusion"].items():
            lines.append(f"| **{a}** | " + " | ".join(str(v) for v in row.values()) + " |")
        tp = r["throughput"]
        lines += ["", f"Скорость: {tp['items_per_second']} материалов/с на одно ядро "
                      f"({tp['ms_per_item']} мс на материал, правила без LLM).", ""]
        if name == "blind2" and mode == "model" and r["errors"]:
            lines += ["### Ошибки на слепой выборке (оставлены как есть, без доработки под них)", "",
                      "| id | тип | разметка → прогноз | балл | текст |", "|---|---|---|---|---|"]
            for e in r["errors"]:
                text = e["text"].replace("|", "/").replace("\n", " ")[:120]
                lines.append(f"| {e['id']} | {e['type']} | {e['track']} → {e['pred_track']} | {e['score']} | {text} |")
            lines.append("")
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", default="test", choices=["blind2", "blind", "test", "dev", "holdout", "all"])
    ap.add_argument("--errors", action="store_true")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--write-docs", action="store_true")
    ap.add_argument("--llm", action="store_true")
    ap.add_argument("--model", action="store_true", help="rules + learned layer (model.py)")
    ap.add_argument("--out", default="", help="where --write-docs writes (default: docs/METRICS.md)")
    args = ap.parse_args()

    llm = None
    if args.llm:
        from app.services.ai.factory import get_llm
        llm = get_llm()

    if args.write_docs:
        plan = [("blind2", "model"), ("blind2", "rules"), ("blind", "model"), ("blind", "rules"),
                ("holdout", "rules"), ("test", "rules"), ("dev", "rules")]
    else:
        names = ["blind2", "blind", "holdout", "test", "dev"] if args.set == "all" else [args.set]
        plan = [(n, "model" if args.model else "rules") for n in names]
    reports = {(n, m): evaluate(load(n), llm=llm, use_model=(m == "model")) for n, m in plan}
    for (n, m), r in reports.items():
        b = r["binary"]
        print(f"[{n}{'+model' if m == 'model' else ''}] n={r['n']} P={pct(b['precision'])} R={pct(b['recall'])} F1={pct(b['f1'])} "
              f"FPR={pct(b['fpr'])} hardFPR={pct(r['hard_negative_fpr'])} | "
              + " ".join(f"{t}:P{pct(m['precision'])}/R{pct(m['recall'])}" for t, m in r["per_track"].items())
              + f" | {r['throughput']['items_per_second']} items/s")
        if args.errors:
            for e in r["errors"]:
                print(f"  {e['type']:<11} {e['id']:<9} {e['track']:>7}->{e['pred_track']:<7} {e['score']:>3} "
                      f"{e['signals']} | {e['text'][:110]}")
        if args.json:
            print(json.dumps(r, ensure_ascii=False, indent=1))
    if args.write_docs:
        out = Path(args.out) if args.out else DOCS
        out.write_text(to_markdown(reports), encoding="utf-8")
        print(f"wrote {out}")


if __name__ == "__main__":
    main()
