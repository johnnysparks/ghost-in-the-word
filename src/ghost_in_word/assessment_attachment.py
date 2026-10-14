"""Attach validated source-conditioned assessments to comparison units."""

from __future__ import annotations

from typing import Mapping

from .assessment import validate_assessment_document


def attach_assessment_document(
    comparison: Mapping[str, object],
    document: Mapping[str, object],
    *,
    source_document: str | None = None,
) -> dict[str, object]:
    """Return a comparison copy with validated assessments attached by unit ID.

    The source edition must be one of the comparison editions and must be marked
    as a source role. Unknown assessment IDs are rejected so a typo cannot
    silently create an orphan judgment. No score or faithfulness aggregate is
    computed here; the attachment only preserves evidence and provenance.
    """

    normalized = validate_assessment_document(document)
    source = normalized["sourceEdition"]
    if not isinstance(source, Mapping):
        raise ValueError("normalized assessment source edition must be an object")
    source_id = str(source["id"])
    metadata = comparison.get("metadata")
    if not isinstance(metadata, Mapping):
        raise ValueError("comparison artifact must contain metadata")
    editions = [metadata.get("leftEdition"), metadata.get("rightEdition")]
    source_matches = [edition for edition in editions if isinstance(edition, Mapping) and edition.get("id") == source_id]
    if not source_matches:
        raise ValueError(f"assessment source edition {source_id!r} is not part of the comparison")
    if source_matches[0].get("role", "translation") != "source":
        raise ValueError(f"assessment source edition {source_id!r} is not marked as a source role")

    units = comparison.get("units")
    if not isinstance(units, list):
        raise ValueError("comparison artifact must contain a units array")
    unit_ids = [unit.get("id") for unit in units if isinstance(unit, Mapping)]
    if len(unit_ids) != len(units) or any(not isinstance(unit_id, str) or not unit_id for unit_id in unit_ids):
        raise ValueError("comparison units must have non-empty ids")
    if len(unit_ids) != len(set(unit_ids)):
        raise ValueError("comparison unit ids must be unique")

    assessments = normalized["assessments"]
    if not isinstance(assessments, list):
        raise ValueError("normalized assessment document must contain assessments")
    assessment_by_id = {str(record["id"]): record for record in assessments if isinstance(record, Mapping)}
    unknown = sorted(set(assessment_by_id) - set(unit_ids))
    if unknown:
        raise ValueError(f"assessment ids do not occur in comparison units: {', '.join(unknown)}")

    output = dict(comparison)
    output["metadata"] = dict(metadata)
    attachment: dict[str, object] = {
        "schemaVersion": normalized["schemaVersion"],
        "kind": normalized["kind"],
        "sourceEdition": dict(source),
        "summary": normalized["summary"],
    }
    if source_document:
        attachment["sourceDocument"] = source_document
    output["metadata"]["assessmentAttachment"] = attachment
    output["units"] = []
    for unit in units:
        if not isinstance(unit, Mapping):
            raise ValueError("comparison units must be objects")
        copied = dict(unit)
        item_id = str(unit["id"])
        if item_id in assessment_by_id:
            copied["assessments"] = [assessment_by_id[item_id]]
        output["units"].append(copied)
    return output
