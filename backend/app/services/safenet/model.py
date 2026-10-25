"""Learned layer: «похоже на размеченные схемы» (multinomial Naive Bayes, pure Python).

Rules are precise but miss paraphrases. This small, transparent model generalises
over word stems across all normalised views (de-obfuscated, transliterated, numbers
as digits) and becomes ONE more signal — never the score itself:

  * trained on the tuning/analysed sets only (dev + test + holdout); the blind sets
    are never used for training, so metrics on them stay honest
  * explanation = the stems that pushed the decision most («вложил», «получ», «%»)
  * as a signal it adds ≤ 20 points to its track; with p ≥ CORE_P it may stand in for
    the track's missing core sign, but the score is then capped at «средний» (50) —
    a model alone can never produce «высокий».

Deterministic, ~ms per text, no dependencies, retrained in < 1 s at first use.
"""
from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from functools import lru_cache

from app.services.safenet.normalize import build_views

TRAIN_SETS = ("dev", "test", "holdout")
CLASSES = ("lottery", "casino", "pyramid", "none")
MIN_P = 0.6          # below: no signal
CORE_P = 0.85        # at/above: may replace a missing core sign (score capped at 50)
WEIGHT = 20

_WORD = re.compile(r"[a-zа-я0-9%₸$]+")
_STOP = {"и", "в", "на", "не", "что", "это", "за", "для", "как", "по", "от", "с", "у", "к", "я", "мы", "вы",
         "ты", "все", "так", "уже", "есть", "мен", "мен", "бул", "осы", "да", "же", "или", "а", "но", "из"}


def _stem(w: str) -> str:
    if w.isdigit():
        n = int(w)
        return "<num>" if n < 100 else ("<sum_k>" if n < 100_000 else "<sum_big>")
    return w[:6]


def features(text: str) -> list[str]:
    """Stems (+ bigrams) from the de-obfuscated, transliterated and number-word views."""
    v = build_views(text)
    joined = " ".join(x for x in (v.collapsed, v.translit, v.numwords, v.emoji) if x)
    words = [w for w in _WORD.findall(joined) if w not in _STOP and (len(w) > 2 or w in ("%", "₸"))]
    stems = [_stem(w) for w in words]
    out = list(dict.fromkeys(stems))                    # presence, not counts (robust to length)
    out += list(dict.fromkeys(f"{a}_{b}" for a, b in zip(stems, stems[1:])))
    return out


class NaiveBayes:
    def __init__(self, alpha: float = 0.5):
        self.alpha = alpha
        self.count: dict[str, Counter] = {c: Counter() for c in CLASSES}
        self.docs: Counter = Counter()
        self.vocab: set[str] = set()

    def fit(self, rows: list[tuple[str, str]]) -> "NaiveBayes":
        for text, label in rows:
            f = features(text)
            self.count[label].update(f)
            self.docs[label] += 1
            self.vocab.update(f)
        self.total = {c: sum(self.count[c].values()) for c in CLASSES}
        return self

    def _loglik(self, f: str, c: str) -> float:
        v = len(self.vocab) or 1
        return math.log((self.count[c][f] + self.alpha) / (self.total[c] + self.alpha * v))

    def predict(self, text: str) -> tuple[dict[str, float], dict[str, list[tuple[str, float]]]]:
        """Class probabilities (tempered for calibration) + top contributing features per class."""
        feats = [f for f in features(text) if f in self.vocab]
        if not feats:
            return {c: (1.0 if c == "none" else 0.0) for c in CLASSES}, {}
        n_docs = sum(self.docs.values())
        scores: dict[str, float] = {}
        contrib: dict[str, list[tuple[str, float]]] = defaultdict(list)
        for c in CLASSES:
            s = math.log((self.docs[c] + 1) / (n_docs + len(CLASSES)))
            for f in feats:
                ll = self._loglik(f, c)
                s += ll
                contrib[c].append((f, ll - self._loglik(f, "none")))
            scores[c] = s
        # temper by √n so long texts don't produce 0/1 certainties
        t = math.sqrt(len(feats))
        m = max(scores.values())
        exp = {c: math.exp((scores[c] - m) / t) for c in CLASSES}
        z = sum(exp.values())
        probs = {c: exp[c] / z for c in CLASSES}
        top = {c: sorted((x for x in contrib[c] if x[1] > 0), key=lambda x: -x[1])[:4] for c in CLASSES}
        return probs, top


@lru_cache(maxsize=1)
def model() -> NaiveBayes:
    from app.services.safenet.evaluation import load
    rows = []
    for name in TRAIN_SETS:
        rows += [(r["text"], r["track"] if r["label"] == 1 else "none") for r in load(name)]
    return NaiveBayes().fit(rows)


def readable(feature: str, words: dict[str, str] | None = None) -> str:
    """Show the stem as the word it came from in this text («тикеле» -> «тікелей»)."""
    words = words or {}
    parts = [words.get(p, p) for p in feature.split("_")]
    out = " ".join(parts)
    return out.replace("<sum_k>", "сумма").replace("<sum_big>", "крупная сумма").replace("<num>", "число")


def stem_words(text: str) -> dict[str, str]:
    """stem -> the first original word (as written) that produced it."""
    from app.services.safenet.normalize import fold

    out: dict[str, str] = {}
    for w in re.findall(r"[^\W\d_]+", text):
        found = _WORD.findall(fold(w))
        if found and len(found[0]) > 2:
            out.setdefault(_stem(found[0]), w)
    return out


def predict(text: str) -> tuple[str, float, list[str]]:
    """(track or "none", probability, explanation stems)."""
    probs, top = model().predict(text)
    track = max(CLASSES, key=lambda c: probs[c])
    words = stem_words(text)
    return track, probs[track], [readable(f, words) for f, _ in top.get(track, [])]
