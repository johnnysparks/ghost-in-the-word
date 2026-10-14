"""Validation and provenance reports for reviewed alignment mappings."""

from __future__ import annotations

from collections import Counter
from typing import Iterable, Mapping

from .alignment import AlignmentMapping, alignment_method, align_with_mappings, mapping_from_dict
from .models import TextSegment


def validate_mapping_document(
    records: object,
    left: Iterable[TextSegment],
    right: Iterable[TextSegment],
    *,
    require_review: bool = True,
) -> dict[str, object]:
    """Validate an exception mapping and return an auditable compact report.

    The source segments are supplied by the caller so reference existence,
    duplicate consumption, and the resulting alignment are checked against the
    exact pinned snapshots being reviewed. This validates declared reviewer
    evidence; it cannot establish a reviewer's independence or expertise.
    """

    if not isinstance(records, list):
        raise ValueError("mapping document must contain a JSON array")
    parsed: list[AlignmentMapping] = []
    entries: list[dict[str, object]] = []
    statuses: Counter[str] = Counter()
    mapping_types: Counter[str] = Counter()
    for index, record in enumerate(records):
        if not isinstance(record, Mapping):
            raise ValueError(f"mapping record {index} must be an object")
        mapping = mapping_from_dict(record)
        if not mapping.left and not mapping.right:
            raise ValueError(f"mapping record {index} must contain a left or right reference")
        if not str(mapping.method).strip():
            raise ValueError(f"mapping record {index} needs a non-empty method")
        if require_review:
            review = mapping.review
            if not isinstance(review, Mapping):
                raise ValueError(f"mapping record {index} needs review evidence")
            for field in ("reviewer", "reviewType", "evidence"):
                if not str(review.get(field, "")).strip():
                    raise ValueError(f"mapping record {index} review needs {field}")
        mapping_type = _mapping_type(len(mapping.left), len(mapping.right))
        status = mapping.status if mapping.status != "matched" else (
            "matched" if mapping.left and mapping.right else ("missing-right" if mapping.left else "missing-left")
        )
        statuses[status] += 1
        mapping_types[mapping_type] += 1
        parsed.append(mapping)
        entries.append(
            {
                "index": index,
                "left": [f"{book} {chapter}:{verse}" for book, chapter, verse in mapping.left],
                "right": [f"{book} {chapter}:{verse}" for book, chapter, verse in mapping.right],
                "status": status,
                "mappingType": mapping_type,
                "method": mapping.method,
                "review": dict(mapping.review) if mapping.review is not None else None,
            }
        )

    units = align_with_mappings(left, right, parsed)
    return {
        "schemaVersion": 1,
        "kind": "alignment-review-report",
        "alignmentMethod": alignment_method([unit.to_dict() for unit in units]),
        "summary": {
            "mappingCount": len(parsed),
            "reviewedCount": sum(1 for mapping in parsed if mapping.review is not None),
            "statuses": dict(sorted(statuses.items())),
            "mappingTypes": dict(sorted(mapping_types.items())),
            "alignedUnitCount": len(units),
        },
        "mappings": entries,
    }


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
