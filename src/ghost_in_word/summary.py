from __future__ import annotations

from collections import Counter, defaultdict
from statistics import mean, median
from typing import Iterable, Mapping

CANONICAL_BOOKS = "GEN EXO LEV NUM DEU JOS JDG RUT 1SA 2SA 1KI 2KI 1CH 2CH EZR NEH EST JOB PSA PRO ECC SNG ISA JER LAM EZK DAN HOS JOL AMO OBA JON MIC NAM HAB ZEP HAG ZEC MAL MAT MRK LUK JHN ACT ROM 1CO 2CO GAL EPH PHP COL 1TH 2TH 1TI 2TI TIT PHM HEB JAS 1PE 2PE 1JN 2JN 3JN JUD REV".split()

def _stats(units: list[Mapping[str, object]], distance_field: str) -> dict[str, object]:
    scores = [float(unit[distance_field]) for unit in units if isinstance(unit.get(distance_field), (int, float))]
    statuses = Counter(str(unit["status"]) for unit in units)
    matched = statuses.get("matched", 0)
    return {
        "totalUnits": len(units),
        "matchedUnits": matched,
        "scoredUnits": len(scores),
        "coverage": round(matched / len(units), 6) if units else 0.0,
        "score": {
            "mean": round(mean(scores), 6) if scores else None,
            "median": round(median(scores), 6) if scores else None,
            "max": round(max(scores), 6) if scores else None,
        },
        "statuses": dict(statuses),
    }

def summarize_units(units: Iterable[Mapping[str, object]], distance_field: str) -> dict[str, object]:
    """Aggregate comparison units without scoring missing passages."""
    records = list(units)
    by_book: dict[str, list[Mapping[str, object]]] = defaultdict(list)
    by_chapter: dict[tuple[str, int], list[Mapping[str, object]]] = defaultdict(list)
    for unit in records:
        book = str(unit["book"])
        chapter = int(unit["chapter"])
        by_book[book].append(unit)
        by_chapter[(book, chapter)].append(unit)
    book_order = {book: index for index, book in enumerate(CANONICAL_BOOKS)}
    books = []
    for book in sorted(by_book, key=lambda item: (book_order.get(item, len(book_order)), item)):
        books.append({"book": book, **_stats(by_book[book], distance_field)})
    chapters = []
    for book, chapter in sorted(by_chapter, key=lambda item: (book_order.get(item[0], len(book_order)), item[0], item[1])):
        chapters.append({"book": book, "chapter": chapter, **_stats(by_chapter[(book, chapter)], distance_field)})
    return {"books": books, "chapters": chapters, "overall": _stats(records, distance_field)}
