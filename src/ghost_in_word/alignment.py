from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Iterable

from .models import TextSegment


@dataclass(frozen=True)
class AlignmentUnit:
    """A comparison unit for two editions.

    The first spike only scores exact one-to-one references. Missing records
    remain visible with a status so downstream charts cannot mistake absence
    for semantic distance zero.
    """

    book: str
    chapter: int
    verse: str
    left_edition: str
    right_edition: str
    left_text: str | None
    right_text: str | None
    status: str

    @property
    def reference(self) -> str:
        return f"{self.book} {self.chapter}:{self.verse}"

    def to_dict(self) -> dict[str, object]:
        return {**asdict(self), "reference": self.reference}


def align_segments(left: Iterable[TextSegment], right: Iterable[TextSegment]) -> list[AlignmentUnit]:
    """Align two editions by explicit book/chapter/verse keys.

    Duplicate keys are rejected because silently choosing one rendering would
    make the resulting comparison irreproducible.
    """

    left_by_key = _index(left)
    right_by_key = _index(right)
    left_edition = _edition_id(left_by_key)
    right_edition = _edition_id(right_by_key)
    keys = sorted(set(left_by_key) | set(right_by_key), key=lambda key: (key[0], key[1], _verse_sort_key(key[2])))

    units: list[AlignmentUnit] = []
    for book, chapter, verse in keys:
        left_segment = left_by_key.get((book, chapter, verse))
        right_segment = right_by_key.get((book, chapter, verse))
        if left_segment and right_segment:
            status = "matched"
        elif left_segment:
            status = "missing-right"
        else:
            status = "missing-left"
        units.append(
            AlignmentUnit(
                book=book,
                chapter=chapter,
                verse=verse,
                left_edition=left_edition,
                right_edition=right_edition,
                left_text=left_segment.text if left_segment else None,
                right_text=right_segment.text if right_segment else None,
                status=status,
            )
        )
    return units


def _index(segments: Iterable[TextSegment]) -> dict[tuple[str, int, str], TextSegment]:
    indexed: dict[tuple[str, int, str], TextSegment] = {}
    for segment in segments:
        if segment.key in indexed:
            raise ValueError(f"duplicate segment reference: {segment.reference}")
        indexed[segment.key] = segment
    return indexed


def _edition_id(indexed: dict[tuple[str, int, str], TextSegment]) -> str:
    return next(iter(indexed.values())).edition_id if indexed else ""


def _verse_sort_key(verse: str) -> tuple[int, int]:
    start, _, end = verse.partition("-")
    return int(start), int(end or start)
