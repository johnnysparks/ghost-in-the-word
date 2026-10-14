"""Validation and provenance reports for reviewed alignment mappings."""

from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
from typing import Iterable, Mapping

from .alignment import AlignmentMapping, alignment_method, align_with_mappings, mapping_from_dict
from .models import TextSegment


def validate_mapping_document(
    records: object,
    left: Iterable[TextSegment],
    right: Iterable[TextSegment],
    *,
    require_review: bool = True,
    require_independent_review: bool = False,
) -> dict[str, object]:
    """Validate an exception mapping and return an auditable compact report.

    The source segments are supplied by the caller so reference existence,
    duplicate consumption, and the resulting alignment are checked against the
    exact pinned snapshots being reviewed. This validates declared reviewer
    evidence; it cannot establish a reviewer's independence or expertise. When
    ``require_independent_review`` is enabled, each record must carry at least
    two distinct reviewer IDs and the explicit ``independence: declared``
    marker. That is a schema gate, not proof of real-world independence.
    """

    if require_independent_review and not require_review:
        raise ValueError("independent mapping review requires reviewer evidence")

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
            if require_independent_review:
                reviewers = review.get("reviewers")
                if not isinstance(reviewers, list):
                    raise ValueError(f"mapping record {index} independent review needs a reviewers array")
                normalized_reviewers = [str(reviewer).strip() for reviewer in reviewers]
                if len(normalized_reviewers) < 2 or any(not reviewer for reviewer in normalized_reviewers):
                    raise ValueError(f"mapping record {index} independent review needs at least two non-empty reviewers")
                if len(normalized_reviewers) != len(set(normalized_reviewers)):
                    raise ValueError(f"mapping record {index} independent review reviewers must be distinct")
                if review.get("independence") != "declared":
                    raise ValueError(f"mapping record {index} independent review needs independence: declared")
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
    independent_count = sum(
        1
        for mapping in parsed
        if isinstance(mapping.review, Mapping)
        and isinstance(mapping.review.get("reviewers"), list)
        and len({str(reviewer).strip() for reviewer in mapping.review["reviewers"] if str(reviewer).strip()}) >= 2
        and mapping.review.get("independence") == "declared"
    )
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
            "independentReviewCount": independent_count,
            "independentReviewRequired": require_independent_review,
            "independentReviewEligible": bool(parsed) and independent_count == len(parsed) if require_independent_review else None,
        },
        "mappings": entries,
    }


def bind_snapshot(root: str | Path, edition_id: str) -> dict[str, object]:
    """Read the content-addressed inventory for one parsed source snapshot."""

    root_path = Path(root)
    path = root_path / "snapshot.json"
    if not path.is_file():
        raise ValueError(f"missing source snapshot inventory: {path}")
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"could not read source snapshot inventory {path}: {exc}") from exc
    if not isinstance(document, Mapping):
        raise ValueError(f"source snapshot inventory must be an object: {path}")
    if document.get("edition") != edition_id or not str(document.get("directorySha256", "")):
        raise ValueError(f"source snapshot inventory does not bind to edition {edition_id}: {path}")
    files = document.get("files")
    return {
        "edition": edition_id,
        "path": str(path),
        "directorySha256": document["directorySha256"],
        "fileCount": len(files) if isinstance(files, list) else None,
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
