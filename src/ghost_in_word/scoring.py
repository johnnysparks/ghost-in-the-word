from __future__ import annotations

import math
import re
from collections import Counter
from typing import Iterable

from .alignment import AlignmentUnit

_TOKEN = re.compile(r"[\w’'-]+", re.UNICODE)


def tokenize(text: str) -> list[str]:
    """Return lowercase word tokens without changing the display text."""

    return [token.casefold() for token in _TOKEN.findall(text)]


def wording_distance(left: str, right: str) -> float:
    """Multiset Dice distance in [0, 1].

    This is intentionally a lexical baseline. It captures token overlap and
    makes no claim about meaning, grammar, or translation quality.
    """

    left_counts = Counter(tokenize(left))
    right_counts = Counter(tokenize(right))
    left_size = sum(left_counts.values())
    right_size = sum(right_counts.values())
    if not left_size and not right_size:
        return 0.0
    if not left_size or not right_size:
        return 1.0
    overlap = sum((left_counts & right_counts).values())
    return round(1.0 - (2.0 * overlap / (left_size + right_size)), 6)


def _character_ngrams(text: str, n: int = 3) -> Counter[str]:
    normalized = " ".join(tokenize(text))
    padded = f"  {normalized}  "
    return Counter(padded[index : index + n] for index in range(max(0, len(padded) - n + 1)))


def lexical_distance(left: str, right: str) -> float:
    """Character n-gram cosine distance used as a second lexical baseline."""

    left_counts = _character_ngrams(left)
    right_counts = _character_ngrams(right)
    if not left_counts and not right_counts:
        return 0.0
    if not left_counts or not right_counts:
        return 1.0
    dot = sum(value * right_counts[token] for token, value in left_counts.items())
    left_norm = math.sqrt(sum(value * value for value in left_counts.values()))
    right_norm = math.sqrt(sum(value * value for value in right_counts.values()))
    similarity = dot / (left_norm * right_norm)
    return round(max(0.0, min(1.0, 1.0 - similarity)), 6)


def score_units(units: Iterable[AlignmentUnit]) -> list[dict[str, object]]:
    """Add reproducible baseline measurements to aligned units.

    Missing or unresolved units are retained with null scores. Consumers must
    not interpret missing text as zero distance.
    """

    scored: list[dict[str, object]] = []
    for index, unit in enumerate(units):
        record = unit.to_dict()
        record["id"] = f"{unit.book}-{unit.chapter}-{unit.verse}"
        record["order"] = index
        if unit.status == "matched" and unit.left_text is not None and unit.right_text is not None:
            record["wordingDistance"] = wording_distance(unit.left_text, unit.right_text)
            record["lexicalDistance"] = lexical_distance(unit.left_text, unit.right_text)
        else:
            record["wordingDistance"] = None
            record["lexicalDistance"] = None
        scored.append(record)
    return scored
