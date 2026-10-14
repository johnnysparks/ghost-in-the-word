"""Validation and provenance reports for reviewed alignment mappings."""

from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
from typing import Iterable, Mapping

from .alignment import AlignmentMapping, alignment_method, align_with_mappings, mapping_from_dict
from .models import TextSegment

MAPPING_REVIEW_DECISIONS = {"accept", "reject", "uncertain"}
MAPPING_REVIEW_ITEM_FIELDS = {
    "id",
    "leftReferences",
    "rightReferences",
    "leftText",
    "rightText",
    "mappingType",
}
MAPPING_REVIEW_RESPONSE_FIELDS = {"id", "decision", "evidence"}


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


def build_mapping_review_packet(
    records: object,
    left: Iterable[TextSegment],
    right: Iterable[TextSegment],
    *,
    left_source: Mapping[str, object] | None = None,
    right_source: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Create a blind packet for reviewing explicit alignment candidates.

    Existing review metadata, methods, and statuses are intentionally omitted
    from the packet. Reviewers receive only the candidate references, the text
    present on each side, and the mapping shape. The source snapshot bindings
    remain in packet provenance so a later evaluator can verify what was shown.
    """

    if not isinstance(records, list):
        raise ValueError("mapping document must contain a JSON array")
    left_segments = list(left)
    right_segments = list(right)
    left_by_key = {segment.key: segment for segment in left_segments}
    right_by_key = {segment.key: segment for segment in right_segments}
    if len(left_by_key) != len(left_segments) or len(right_by_key) != len(right_segments):
        raise ValueError("source segments must have unique references")
    mappings = [mapping_from_dict(record) for record in records if isinstance(record, Mapping)]
    if len(mappings) != len(records):
        raise ValueError("mapping records must be objects")
    # This catches unknown/reused references before any packet is sent out.
    align_with_mappings(left_segments, right_segments, mappings)

    items: list[dict[str, object]] = []
    for index, mapping in enumerate(mappings, start=1):
        left_refs = [left_by_key[key].reference for key in mapping.left]
        right_refs = [right_by_key[key].reference for key in mapping.right]
        left_text = " ".join(left_by_key[key].text for key in mapping.left)
        right_text = " ".join(right_by_key[key].text for key in mapping.right)
        items.append(
            {
                "id": f"mapping-{index:04d}",
                "leftReferences": left_refs,
                "rightReferences": right_refs,
                "leftText": left_text,
                "rightText": right_text,
                "mappingType": _mapping_type(len(mapping.left), len(mapping.right)),
            }
        )
    def public_source(source: Mapping[str, object] | None) -> dict[str, object] | None:
        if source is None:
            return None
        return {key: value for key, value in source.items() if key != "path"}

    packet: dict[str, object] = {
        "schemaVersion": 1,
        "kind": "blind-mapping-review-packet",
        "source": {
            "leftEdition": {"id": left_segments[0].edition_id if left_segments else ""},
            "rightEdition": {"id": right_segments[0].edition_id if right_segments else ""},
            "leftSnapshot": public_source(left_source),
            "rightSnapshot": public_source(right_source),
        },
        "selection": {
            "strategy": "explicit-mapping-candidates",
            "requestedCount": len(items),
            "selectedCount": len(items),
        },
        "items": items,
    }
    validate_mapping_review_packet(packet)
    return packet


def validate_mapping_review_packet(packet: Mapping[str, object]) -> dict[str, object]:
    """Validate a score-blind mapping packet before sending it to reviewers."""

    if packet.get("kind") != "blind-mapping-review-packet":
        raise ValueError("mapping review packet kind must be blind-mapping-review-packet")
    if packet.get("schemaVersion") != 1:
        raise ValueError("unsupported mapping review packet schema version")
    source = packet.get("source")
    if not isinstance(source, Mapping):
        raise ValueError("mapping review packet needs a source object")
    for side in ("leftEdition", "rightEdition"):
        edition = source.get(side)
        if not isinstance(edition, Mapping) or not str(edition.get("id", "")).strip():
            raise ValueError(f"mapping review packet source needs a {side} id")
    selection = packet.get("selection")
    if not isinstance(selection, Mapping) or not str(selection.get("strategy", "")).strip():
        raise ValueError("mapping review packet needs a selection strategy")
    items = packet.get("items")
    if not isinstance(items, list) or not items:
        raise ValueError("mapping review packet needs a non-empty items array")
    ids: list[str] = []
    for item in items:
        if not isinstance(item, Mapping):
            raise ValueError("mapping review packet items must be objects")
        unknown = set(item) - MAPPING_REVIEW_ITEM_FIELDS
        if unknown:
            raise ValueError(f"mapping review packet item contains unsupported fields: {', '.join(sorted(unknown))}")
        item_id = item.get("id")
        if not isinstance(item_id, str) or not item_id.strip() or item_id in ids:
            raise ValueError("mapping review packet item IDs must be non-empty and unique")
        for field in ("leftReferences", "rightReferences"):
            refs = item.get(field)
            if not isinstance(refs, list) or any(not isinstance(ref, str) or not ref.strip() for ref in refs):
                raise ValueError(f"mapping review packet item {item_id!r} needs a {field} string array")
        if not item.get("leftReferences") and not item.get("rightReferences"):
            raise ValueError(f"mapping review packet item {item_id!r} needs a reference on one side")
        for field in ("leftText", "rightText", "mappingType"):
            if not isinstance(item.get(field), str):
                raise ValueError(f"mapping review packet item {item_id!r} needs {field}")
        ids.append(item_id)
    selected_count = selection.get("selectedCount")
    if selected_count is not None and selected_count != len(items):
        raise ValueError("mapping review packet selectedCount does not match items")
    return {
        "schemaVersion": 1,
        "kind": "blind-mapping-review-packet",
        "itemCount": len(items),
        "itemIds": ids,
        "strategy": str(selection["strategy"]),
        "leftEdition": str(source["leftEdition"]["id"]),
        "rightEdition": str(source["rightEdition"]["id"]),
    }


def summarize_mapping_reviews(
    review_documents: Iterable[Mapping[str, object]],
    *,
    packet: Mapping[str, object],
    candidate_records: object | None = None,
    minimum_reviewers: int = 2,
) -> dict[str, object]:
    """Aggregate independent mapping votes and emit unanimously accepted mappings.

    A mapping is eligible only when every distinct reviewer has reviewed it,
    every response declares independence, and all decisions are ``accept``.
    Rejections and uncertainty remain in the report and never become applied
    alignment records.
    """

    if minimum_reviewers < 2:
        raise ValueError("minimum_reviewers must be at least 2")
    packet_summary = validate_mapping_review_packet(packet)
    packet_ids = set(packet_summary["itemIds"])
    packet_items = {str(item["id"]): item for item in packet["items"] if isinstance(item, Mapping)}
    candidate_by_id: dict[str, dict[str, object]] = {}
    if candidate_records is not None:
        if not isinstance(candidate_records, list) or len(candidate_records) != len(packet_ids):
            raise ValueError("candidate mapping records must match the packet item count")
        for index, record in enumerate(candidate_records, start=1):
            if not isinstance(record, Mapping):
                raise ValueError("candidate mapping records must be objects")
            item_id = f"mapping-{index:04d}"
            if item_id not in packet_items:
                raise ValueError(f"candidate mapping has no packet item {item_id!r}")
            mapping = mapping_from_dict(record)
            packet_item = packet_items[item_id]
            expected_left = list(packet_item["leftReferences"])
            expected_right = list(packet_item["rightReferences"])
            actual_left = [f"{book} {chapter}:{verse}" for book, chapter, verse in mapping.left]
            actual_right = [f"{book} {chapter}:{verse}" for book, chapter, verse in mapping.right]
            if actual_left != expected_left or actual_right != expected_right:
                raise ValueError(f"candidate mapping {item_id!r} does not match the blind packet")
            candidate_by_id[item_id] = dict(record)
    documents = list(review_documents)
    if len(documents) < minimum_reviewers:
        reviewer_count_error = True
    else:
        reviewer_count_error = False
    seen_reviewers: set[str] = set()
    votes_by_item: dict[str, list[dict[str, str]]] = {item_id: [] for item_id in packet_ids}
    for document in documents:
        if document.get("schemaVersion") != 1 or document.get("kind") != "blind-mapping-review-response":
            raise ValueError("unsupported mapping review response schema")
        reviewer = str(document.get("reviewerId", "")).strip()
        if not reviewer:
            raise ValueError("mapping review response needs reviewerId")
        if reviewer in seen_reviewers:
            raise ValueError(f"reviewer {reviewer!r} appears in more than one document")
        seen_reviewers.add(reviewer)
        if document.get("independence") != "declared":
            raise ValueError(f"reviewer {reviewer!r} must declare independence")
        items = document.get("items")
        if not isinstance(items, list):
            raise ValueError(f"reviewer {reviewer!r} must provide an items array")
        seen_items: set[str] = set()
        for item in items:
            if not isinstance(item, Mapping):
                raise ValueError(f"reviewer {reviewer!r} contains a non-object item")
            unknown = set(item) - MAPPING_REVIEW_RESPONSE_FIELDS
            if unknown:
                raise ValueError(f"reviewer {reviewer!r} response contains unsupported fields: {', '.join(sorted(unknown))}")
            item_id = str(item.get("id", ""))
            if item_id not in packet_ids:
                raise ValueError(f"reviewer {reviewer!r} returned unknown mapping item {item_id!r}")
            if item_id in seen_items:
                raise ValueError(f"reviewer {reviewer!r} reviewed mapping {item_id!r} more than once")
            seen_items.add(item_id)
            decision = item.get("decision")
            if decision not in MAPPING_REVIEW_DECISIONS:
                raise ValueError(f"invalid mapping decision for {item_id!r}: {decision!r}")
            evidence = item.get("evidence")
            if not isinstance(evidence, str) or not evidence.strip():
                raise ValueError(f"mapping review evidence for {item_id!r} must be non-empty")
            votes_by_item[item_id].append({"reviewerId": reviewer, "decision": str(decision), "evidence": evidence})

    item_reports: list[dict[str, object]] = []
    approved: list[dict[str, object]] = []
    for item_id in sorted(packet_ids):
        votes = votes_by_item[item_id]
        decisions = [vote["decision"] for vote in votes]
        complete = len(votes) == len(documents) and len(documents) >= minimum_reviewers
        unanimous_accept = complete and all(decision == "accept" for decision in decisions)
        item_report = {
            "id": item_id,
            "reviewCount": len(votes),
            "complete": complete,
            "decisions": {decision: decisions.count(decision) for decision in sorted(MAPPING_REVIEW_DECISIONS) if decision in decisions},
            "approved": unanimous_accept and not reviewer_count_error,
            "votes": votes,
        }
        item_reports.append(item_report)
        if item_report["approved"]:
            source_item = packet_items[item_id]
            reviewer_ids = sorted(seen_reviewers)
            evidence = "; ".join(f"{vote['reviewerId']}: {vote['evidence']}" for vote in votes)
            mapping_record = dict(candidate_by_id[item_id]) if candidate_by_id else {
                "left": list(source_item["leftReferences"]),
                "right": list(source_item["rightReferences"]),
                "method": "independently-reviewed-mapping",
            }
            mapping_record["review"] = {
                "reviewer": "independent-review-panel",
                "reviewers": reviewer_ids,
                "reviewType": "independent-mapping-review",
                "independence": "declared",
                "evidence": evidence,
                "reviewEvidence": votes,
            }
            approved.append(mapping_record)

    gate = {
        "minimumReviewers": minimum_reviewers,
        "reviewerCount": len(documents),
        "reviewerCountMet": len(documents) >= minimum_reviewers,
        "allReviewersDeclaredIndependent": all(
            document.get("independence") == "declared" for document in documents
        ) and bool(documents),
        "completeItems": sum(1 for item in item_reports if item["complete"]),
        "itemCount": len(item_reports),
        "allItemsUnanimouslyAccepted": bool(item_reports) and all(bool(item["approved"]) for item in item_reports),
        "eligible": bool(item_reports)
        and len(documents) >= minimum_reviewers
        and all(bool(item["complete"]) for item in item_reports)
        and all(document.get("independence") == "declared" for document in documents),
    }
    return {
        "schemaVersion": 1,
        "kind": "mapping-review-report",
        "packet": packet_summary,
        "gate": gate,
        "approvedMappingCount": len(approved),
        "approvedMappings": approved,
        "items": item_reports,
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
