"""Capability discovery: BM25 over each capability's name, description, parameters and output type.

ponytail: plain Okapi BM25 with a tiny stemmer, stdlib only. Swap in embeddings behind `search()` if the
schema-scaling experiment shows lexical recall falling off at large catalogue sizes."""

from __future__ import annotations

import math
import re
from collections import Counter
from collections.abc import Iterable

from bizops.domain.models.capability import Capability

_STOPWORDS = (
    "a an the of for to in on and or by with is are be what which who how me my our we do does did it its "
    "this that from at as all any show list get find give tell please"
)
_STOP = frozenset(_STOPWORDS.split())
_SPLIT = re.compile(r"[^a-z0-9]+")


def _stem(t: str) -> str:
    for suffix in ("ies", "ing", "es", "s"):
        if len(t) > len(suffix) + 2 and t.endswith(suffix):
            return t[: -len(suffix)] + ("y" if suffix == "ies" else "")
    return t


def tokens(text: str) -> list[str]:
    return [_stem(t) for t in _SPLIT.split(text.lower()) if t and t not in _STOP]


def _document(cap: Capability) -> list[str]:
    name = cap.name.replace(".", " ").replace("_", " ")
    parts = [name, name, cap.description, cap.output]  # the name counts twice: it is the strongest signal
    for p in cap.parameters:
        parts += [p.name.replace("_", " "), p.description]
    return tokens(" ".join(parts))


class CapabilityIndex:
    def __init__(self, capabilities: Iterable[Capability], k1: float = 1.2, b: float = 0.75) -> None:
        self.caps = list(capabilities)
        self.k1, self.b = k1, b
        self.docs = [Counter(_document(c)) for c in self.caps]
        self.lengths = [sum(d.values()) for d in self.docs]
        self.avg = sum(self.lengths) / max(len(self.lengths), 1)
        df: Counter[str] = Counter()
        for d in self.docs:
            df.update(d.keys())
        n = len(self.docs)
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}

    def search(self, query: str, limit: int = 8) -> list[tuple[Capability, float]]:
        q = tokens(query)
        scored: list[tuple[float, int]] = []
        for i, (doc, length) in enumerate(zip(self.docs, self.lengths, strict=True)):
            score = 0.0
            for t in q:
                tf = doc.get(t, 0)
                if tf:
                    score += (
                        self.idf[t]
                        * tf
                        * (self.k1 + 1)
                        / (tf + self.k1 * (1 - self.b + self.b * length / self.avg))
                    )
            if score > 0:
                scored.append((score, i))
        scored.sort(key=lambda x: (-x[0], self.caps[x[1]].name))
        return [(self.caps[i], round(s, 3)) for s, i in scored[:limit]]


__all__ = ["CapabilityIndex", "tokens"]
