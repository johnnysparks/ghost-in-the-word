from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping

from .models import TextSegment

ReferenceKey = tuple[str, int, str]


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
    mapping_type: str = "one-to-one"
    left_references: tuple[str, ...] = ()
    right_references: tuple[str, ...] = ()
    mapping_method: str = "exact-reference"
    left_notes: tuple[str, ...] = ()
    right_notes: tuple[str, ...] = ()
    review: Mapping[str, object] | None = None

    @property
    def reference(self) -> str:
        return f"{self.book} {self.chapter}:{self.verse}"

    def to_dict(self) -> dict[str, object]:
        record: dict[str, object] = {
            "book": self.book,
            "chapter": self.chapter,
            "verse": self.verse,
            "left_edition": self.left_edition,
            "right_edition": self.right_edition,
            "left_text": self.left_text,
            "right_text": self.right_text,
            "status": self.status,
            "reference": self.reference,
        }
        if self.mapping_type != "one-to-one" or self.left_references or self.right_references or self.mapping_method != "exact-reference":
            record.update(
                {
                    "mapping_type": self.mapping_type,
                    "left_references": list(self.left_references),
                    "right_references": list(self.right_references),
                    "mapping_method": self.mapping_method,
                }
            )
        if self.left_notes or self.right_notes:
            record.update({"left_notes": list(self.left_notes), "right_notes": list(self.right_notes)})
        if self.review is not None:
            record["review"] = dict(self.review)
        return record


@dataclass(frozen=True)
class AlignmentMapping:
    """A reviewed mapping from one or more source references on each side."""

    left: tuple[ReferenceKey, ...]
    right: tuple[ReferenceKey, ...]
    status: str = "matched"
    method: str = "curated"
    review: Mapping[str, object] | None = None


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
                left_notes=left_segment.notes if left_segment else (),
                right_notes=right_segment.notes if right_segment else (),
            )
        )
    return units


def align_with_mappings(
    left: Iterable[TextSegment],
    right: Iterable[TextSegment],
    mappings: Iterable[AlignmentMapping],
) -> list[AlignmentUnit]:
    """Apply explicit one-to-many/many-to-one mappings.

    Every segment must be consumed by at most one mapping. Unmentioned
    segments become explicit missing units, while mappings marked unresolved
    remain visible but receive no score downstream.
    """

    left_by_key = _index(left)
    right_by_key = _index(right)
    left_edition = _edition_id(left_by_key)
    right_edition = _edition_id(right_by_key)
    consumed_left: set[ReferenceKey] = set()
    consumed_right: set[ReferenceKey] = set()
    units: list[AlignmentUnit] = []

    for mapping in mappings:
        if not mapping.left and not mapping.right:
            raise ValueError("alignment mapping must contain a left or right reference")
        if consumed_left.intersection(mapping.left) or consumed_right.intersection(mapping.right):
            raise ValueError("alignment mapping reuses a segment reference")
        missing_left = [key for key in mapping.left if key not in left_by_key]
        missing_right = [key for key in mapping.right if key not in right_by_key]
        if missing_left or missing_right:
            raise ValueError(f"alignment mapping references unknown segments: left={missing_left}, right={missing_right}")
        consumed_left.update(mapping.left)
        consumed_right.update(mapping.right)
        primary = (mapping.left or mapping.right)[0]
        left_segments = [left_by_key[key] for key in mapping.left]
        right_segments = [right_by_key[key] for key in mapping.right]
        mapping_type = _mapping_type(len(mapping.left), len(mapping.right))
        status = mapping.status if mapping.status != "matched" else ("matched" if mapping.left and mapping.right else ("missing-right" if mapping.left else "missing-left"))
        units.append(
            AlignmentUnit(
                book=primary[0],
                chapter=primary[1],
                verse=primary[2],
                left_edition=left_edition,
                right_edition=right_edition,
                left_text=" ".join(segment.text for segment in left_segments) or None,
                right_text=" ".join(segment.text for segment in right_segments) or None,
                status=status,
                mapping_type=mapping_type,
                left_references=tuple(segment.reference for segment in left_segments),
                right_references=tuple(segment.reference for segment in right_segments),
                mapping_method=mapping.method,
                left_notes=tuple(note for segment in left_segments for note in segment.notes),
                right_notes=tuple(note for segment in right_segments for note in segment.notes),
                review=mapping.review,
            )
        )

    for key, segment in left_by_key.items():
        if key not in consumed_left:
            units.append(
                AlignmentUnit(
                    book=segment.book,
                    chapter=segment.chapter,
                    verse=segment.verse,
                    left_edition=left_edition,
                    right_edition=right_edition,
                    left_text=segment.text,
                    right_text=None,
                    status="missing-right",
                    mapping_type="missing",
                    left_references=(segment.reference,),
                    mapping_method="unmapped",
                    left_notes=segment.notes,
                )
            )
    for key, segment in right_by_key.items():
        if key not in consumed_right:
            units.append(
                AlignmentUnit(
                    book=segment.book,
                    chapter=segment.chapter,
                    verse=segment.verse,
                    left_edition=left_edition,
                    right_edition=right_edition,
                    left_text=None,
                    right_text=segment.text,
                    status="missing-left",
                    mapping_type="missing",
                    right_references=(segment.reference,),
                    mapping_method="unmapped",
                    right_notes=segment.notes,
                )
            )
    return sorted(units, key=lambda unit: (unit.book, unit.chapter, _verse_sort_key(unit.verse)))


def mapping_from_dict(record: Mapping[str, object]) -> AlignmentMapping:
    """Parse a JSON mapping record with references like ``JHN 1:1``."""

    def parse_many(value: object) -> tuple[ReferenceKey, ...]:
        if not isinstance(value, list):
            raise ValueError("mapping left/right values must be lists")
        return tuple(parse_reference(str(reference)) for reference in value)

    review = record.get("review")
    if review is not None and not isinstance(review, Mapping):
        raise ValueError("mapping review must be an object when supplied")
    return AlignmentMapping(
        left=parse_many(record.get("left", [])),
        right=parse_many(record.get("right", [])),
        status=str(record.get("status", "matched")),
        method=str(record.get("method", "curated")),
        review=dict(review) if review is not None else None,
    )


def parse_reference(reference: str) -> ReferenceKey:
    book_and_verse = reference.strip().split()
    if len(book_and_verse) != 2 or ":" not in book_and_verse[1]:
        raise ValueError(f"invalid Bible reference: {reference}")
    book, chapter_verse = book_and_verse
    chapter, verse = chapter_verse.split(":", 1)
    return book.upper(), int(chapter), verse


def alignment_method(units: Iterable[Mapping[str, object]]) -> str:
    """Describe whether a report used exact keys or reviewed mappings."""

    for unit in units:
        if unit.get("mapping_method", "exact-reference") != "exact-reference" or unit.get("mapping_type", "one-to-one") != "one-to-one":
            return "explicit-reviewed-mapping"
    return "exact-book-chapter-verse"


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


def _mapping_type(left_count: int, right_count: int) -> str:
    if not left_count or not right_count:
        return "missing"
    if left_count == 1 and right_count == 1:
        return "one-to-one"
    if left_count == 1:
        return "one-to-many"
    if right_count == 1:
        return "many-to-one"
    return "many-to-many"
