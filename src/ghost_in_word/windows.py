from __future__ import annotations

from collections import defaultdict
from typing import Iterable, Mapping

from .scoring import lexical_distance, wording_distance


def _value(unit: Mapping[str, object], camel: str, snake: str) -> object:
    return unit[camel] if camel in unit else unit.get(snake)


def build_windows(
    units: Iterable[Mapping[str, object]],
    *,
    window_size: int,
    stride: int | None = None,
) -> list[dict[str, object]]:
    """Build independent passage windows from verse comparison records.

    Windows are formed within a book and chapter. A window containing a missing
    or unresolved verse stays visible with null scores. The default stride is
    the window size so generated windows do not overlap unless callers opt in.
    """

    if window_size < 1:
        raise ValueError("window_size must be positive")
    stride = window_size if stride is None else stride
    if stride < 1:
        raise ValueError("stride must be positive")

    grouped: dict[tuple[str, int], list[Mapping[str, object]]] = defaultdict(list)
    for unit in units:
        grouped[(str(unit["book"]), int(unit["chapter"]))].append(unit)

    output: list[dict[str, object]] = []
    order = 0
    for (book, chapter), chapter_units in sorted(grouped.items()):
        chapter_units = sorted(chapter_units, key=lambda unit: (_verse_sort_key(str(unit["verse"])), int(unit.get("order", 0))))
        for start in range(0, len(chapter_units), stride):
            chunk = chapter_units[start : start + window_size]
            if len(chunk) < window_size:
                break
            left_texts = [str(value) for unit in chunk if (value := _value(unit, "leftText", "left_text")) is not None]
            right_texts = [str(value) for unit in chunk if (value := _value(unit, "rightText", "right_text")) is not None]
            complete = all(unit.get("status") == "matched" for unit in chunk) and len(left_texts) == len(chunk) and len(right_texts) == len(chunk)
            references = [str(unit["reference"]) for unit in chunk]
            record: dict[str, object] = {
                "id": f"{book}-{chapter}-{chunk[0]['verse']}-{chunk[-1]['verse']}",
                "order": order,
                "book": book,
                "chapter": chapter,
                "verse": f"{chunk[0]['verse']}-{chunk[-1]['verse']}",
                "reference": f"{references[0]}–{references[-1]}",
                "references": references,
                "windowSize": len(chunk),
                "requestedWindowSize": window_size,
                "status": "matched" if complete else "unresolved",
                "leftText": " ".join(left_texts) if left_texts else None,
                "rightText": " ".join(right_texts) if right_texts else None,
                "wordingDistance": None,
                "lexicalDistance": None,
            }
            if complete:
                record["wordingDistance"] = wording_distance(str(record["leftText"]), str(record["rightText"]))
                record["lexicalDistance"] = lexical_distance(str(record["leftText"]), str(record["rightText"]))
            output.append(record)
            order += 1
    return output


def _verse_sort_key(verse: str) -> tuple[int, int]:
    start, _, end = verse.partition("-")
    return int(start), int(end or start)
