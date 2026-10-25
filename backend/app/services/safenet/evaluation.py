"""Evaluation on labelled data: precision / recall / F1 / false-positive rate.

Positive prediction = the item is flagged for manual review (score ≥ FLAG_THRESHOLD,
i.e. level MEDIUM or HIGH). Track prediction = the top-scoring track of a flagged
item. Reported:
  * binary («нужно ли показывать специалисту»): precision, recall, F1, FPR, accuracy
  * per track (one-vs-rest): precision, recall, F1, FPR (= share of clean content
    wrongly flagged as that track)
  * FPR on HARD negatives (free giveaways, bank deposits, anti-fraud news…)
  * recall by language (ru / kk / mixed / translit) and by obfuscation type
  * the 4×4 confusion matrix and the list of errors for analysis
  * throughput (items/second, single process, rules-only)
"""
from __future__ import annotations

import json
import time
from collections import Counter, defaultdict
from pathlib import Path

from app.services.safenet import analyze_segments
from app.services.safenet.lexicon import TRACKS
from app.services.safenet.scoring import FLAG_THRESHOLD, HIGH

DATA_DIR = Path(__file__).resolve().parent / "data"
LABELS = TRACKS + ("none",)


def load(name: str) -> list[dict]:
    path = DATA_DIR / f"{name}.jsonl"
    with path.open(encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def _ratio(a: int, b: int) -> float | None:
    return round(a / b, 4) if b else None


def _f1(p: float | None, r: float | None) -> float | None:
    if not p or not r:
        return 0.0 if (p is not None and r is not None) else None
    return round(2 * p * r / (p + r), 4)


def predict(sample: dict, *, llm=None) -> dict:
    kind = sample.get("kind", "post")
    source = {"ocr": "ocr", "stream": "stream", "chat": "chat"}.get(kind, "text")
    a, _ = analyze_segments([(source, sample["text"])], llm=llm)
    return {"score": a.score, "level": a.threat_level.value, "track": a.track or "none",
            "signals": [b["factor"] for b in a.breakdown if b.get("kind") == "signal"]}


def evaluate(samples: list[dict], *, threshold: int = FLAG_THRESHOLD, llm=None) -> dict:
    t0 = time.perf_counter()
    rows = []
    for s in samples:
        p = predict(s, llm=llm)
        flagged = p["score"] >= threshold
        rows.append({**s, "pred_score": p["score"], "pred_level": p["level"],
                     "pred_track": p["track"] if flagged else "none", "flagged": flagged,
                     "pred_signals": p["signals"]})
    elapsed = time.perf_counter() - t0

    pos = [r for r in rows if r["label"] == 1]
    neg = [r for r in rows if r["label"] == 0]
    tp = sum(r["flagged"] for r in pos)
    fp = sum(r["flagged"] for r in neg)
    fn = len(pos) - tp
    tn = len(neg) - fp
    precision, recall = _ratio(tp, tp + fp), _ratio(tp, tp + fn)
    binary = {
        "tp": tp, "fp": fp, "fn": fn, "tn": tn,
        "precision": precision, "recall": recall, "f1": _f1(precision, recall),
        "fpr": _ratio(fp, fp + tn), "accuracy": _ratio(tp + tn, len(rows)),
    }

    per_track = {}
    for t in TRACKS:
        tp_t = sum(1 for r in rows if r["track"] == t and r["pred_track"] == t)
        pred_t = sum(1 for r in rows if r["pred_track"] == t)
        true_t = sum(1 for r in rows if r["track"] == t)
        fp_clean = sum(1 for r in neg if r["pred_track"] == t)
        p_t, r_t = _ratio(tp_t, pred_t), _ratio(tp_t, true_t)
        per_track[t] = {"support": true_t, "tp": tp_t, "predicted": pred_t,
                        "precision": p_t, "recall": r_t, "f1": _f1(p_t, r_t),
                        "fpr": _ratio(fp_clean, len(neg)), "false_positives_on_clean": fp_clean}

    confusion = {a: {b: 0 for b in LABELS} for a in LABELS}
    for r in rows:
        confusion[r["track"]][r["pred_track"]] += 1

    hard = [r for r in neg if r.get("hard_negative")]
    by_lang: dict[str, list] = defaultdict(list)
    by_obf: dict[str, list] = defaultdict(list)
    by_kind: dict[str, list] = defaultdict(list)
    for r in pos:
        by_lang[r.get("lang", "ru")].append(r["flagged"])
        by_obf[r.get("obfuscation", "none") or "none"].append(r["flagged"])
        by_kind[r.get("kind", "post")].append(r["flagged"])
    fp_by_lang: dict[str, list] = defaultdict(list)
    for r in neg:
        fp_by_lang[r.get("lang", "ru")].append(r["flagged"])

    def recall_map(d):
        return {k: {"n": len(v), "recall": _ratio(sum(v), len(v))} for k, v in sorted(d.items())}

    levels = Counter((r["label"], r["pred_level"]) for r in rows)
    errors = [
        {"id": r["id"], "type": "FN" if r["label"] == 1 else ("FP" if r["flagged"] else "WRONG_TRACK"),
         "track": r["track"], "pred_track": r["pred_track"], "score": r["pred_score"],
         "level": r["pred_level"], "text": r["text"][:220], "signals": r["pred_signals"],
         "category": r.get("category", "")}
        for r in rows
        if (r["label"] == 1 and not r["flagged"]) or (r["label"] == 0 and r["flagged"])
        or (r["label"] == 1 and r["flagged"] and r["pred_track"] != r["track"])
    ]
    high_only = sum(1 for r in pos if r["pred_score"] >= HIGH), sum(1 for r in neg if r["pred_score"] >= HIGH)
    return {
        "n": len(rows), "positives": len(pos), "negatives": len(neg), "hard_negatives": len(hard),
        "threshold": threshold,
        "binary": binary,
        "per_track": per_track,
        "hard_negative_fpr": _ratio(sum(r["flagged"] for r in hard), len(hard)),
        "high_level": {"recall": _ratio(high_only[0], len(pos)), "fpr": _ratio(high_only[1], len(neg))},
        "recall_by_language": recall_map(by_lang),
        "fpr_by_language": {k: {"n": len(v), "fpr": _ratio(sum(v), len(v))} for k, v in sorted(fp_by_lang.items())},
        "recall_by_obfuscation": recall_map(by_obf),
        "recall_by_kind": recall_map(by_kind),
        "level_distribution": {f"{'pos' if k[0] else 'neg'}:{k[1]}": v for k, v in sorted(levels.items())},
        "confusion": confusion,
        "errors": errors,
        "throughput": {"items": len(rows), "seconds": round(elapsed, 3),
                       "items_per_second": round(len(rows) / elapsed, 1) if elapsed else None,
                       "ms_per_item": round(1000 * elapsed / len(rows), 2) if rows else None},
    }


_CACHE: dict[str, dict] = {}


def cached_report(name: str = "test") -> dict:
    """Rules-only report for a bundled dataset (cached per process — data is static)."""
    if name not in _CACHE:
        _CACHE[name] = evaluate(load(name))
    return _CACHE[name]
