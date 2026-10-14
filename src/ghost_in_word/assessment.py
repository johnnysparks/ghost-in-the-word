"""Validated source-conditioned assessment records.

Assessments are evidence records for later calibration. They deliberately do
not aggregate into a translation-quality grade here: source tradition, reviewer
competence, uncertainty, and disagreement must remain visible to downstream
analysis.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Iterable, Mapping

ASSESSMENT_ORIGINS = {"human", "model", "adjudicated"}
JUDGMENT_TYPES = {"source-faithfulness", "meaning-equivalence", "alignment", "usefulness"}
UNCERTAINTY_VALUES = {"low", "medium", "high", "uncertain"}


@dataclass(frozen=True)
class Assessment:
    """One source-conditioned judgment with its provenance attached."""

    item_id: str
    source_edition: str
    origin: str
    judgment_type: str
    judgment: str
    evidence: tuple[str, ...]
    uncertainty: str
    version: str
    reviewer_id: str | None = None
    model_id: str | None = None
    disagreement: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _validate_assessment(self)

    def to_dict(self) -> dict[str, object]:
        record: dict[str, object] = {
            "id": self.item_id,
            "sourceEdition": self.source_edition,
            "origin": self.origin,
            "judgmentType": self.judgment_type,
            "judgment": self.judgment,
            "evidence": list(self.evidence),
            "uncertainty": self.uncertainty,
            "version": self.version,
        }
        if self.reviewer_id is not None:
            record["reviewerId"] = self.reviewer_id
        if self.model_id is not None:
            record["modelId"] = self.model_id
        if self.disagreement:
            record["disagreement"] = list(self.disagreement)
        return record

    @classmethod
    def from_dict(cls, record: Mapping[str, object], *, source_edition: str | None = None) -> "Assessment":
        evidence = record.get("evidence")
        disagreement = record.get("disagreement", [])
        if not isinstance(evidence, list):
            raise ValueError("assessment evidence must be an array of strings")
        if not isinstance(disagreement, list):
            raise ValueError("assessment disagreement must be an array of strings")
        return cls(
            item_id=str(record.get("id", "")),
            source_edition=str(record.get("sourceEdition", source_edition or "")),
            origin=str(record.get("origin", "")),
            judgment_type=str(record.get("judgmentType", "")),
            judgment=str(record.get("judgment", "")),
            evidence=tuple(str(value) for value in evidence),
            uncertainty=str(record.get("uncertainty", "")),
            version=str(record.get("version", "")),
            reviewer_id=_optional_string(record.get("reviewerId")),
            model_id=_optional_string(record.get("modelId")),
            disagreement=tuple(str(value) for value in disagreement),
        )


def validate_assessment_document(document: Mapping[str, object]) -> dict[str, object]:
    """Validate and summarize an assessment document without hiding votes."""

    if document.get("kind") != "source-conditioned-assessments":
        raise ValueError("assessment document kind must be source-conditioned-assessments")
    if document.get("schemaVersion") != 1:
        raise ValueError("unsupported assessment schema version")
    source_edition = document.get("sourceEdition")
    if not isinstance(source_edition, Mapping) or not isinstance(source_edition.get("id"), str) or not source_edition["id"]:
        raise ValueError("assessment document needs a sourceEdition object with an id")
    records = document.get("assessments")
    if not isinstance(records, list):
        raise ValueError("assessment document needs an assessments array")
    assessments = [Assessment.from_dict(record, source_edition=str(source_edition["id"])) for record in records if isinstance(record, Mapping)]
    if len(assessments) != len(records):
        raise ValueError("assessment records must be objects")
    ids = [assessment.item_id for assessment in assessments]
    if len(ids) != len(set(ids)):
        raise ValueError("assessment ids must be unique within a document")
    normalized_source = {key: value for key, value in source_edition.items()}
    return {
        "schemaVersion": 1,
        "kind": "source-conditioned-assessments",
        "sourceEdition": normalized_source,
        "assessments": [assessment.to_dict() for assessment in assessments],
        "summary": {
            "total": len(assessments),
            "origins": dict(Counter(assessment.origin for assessment in assessments)),
            "judgmentTypes": dict(Counter(assessment.judgment_type for assessment in assessments)),
            "uncertainty": dict(Counter(assessment.uncertainty for assessment in assessments)),
            "disagreementRecords": sum(1 for assessment in assessments if assessment.disagreement),
            "versions": sorted({assessment.version for assessment in assessments}),
        },
    }


def _validate_assessment(assessment: Assessment) -> None:
    if not assessment.item_id.strip():
        raise ValueError("assessment id must be non-empty")
    if not assessment.source_edition.strip():
        raise ValueError("assessment source edition must be non-empty")
    if assessment.origin not in ASSESSMENT_ORIGINS:
        raise ValueError(f"invalid assessment origin: {assessment.origin!r}")
    if assessment.judgment_type not in JUDGMENT_TYPES:
        raise ValueError(f"invalid assessment judgment type: {assessment.judgment_type!r}")
    if not assessment.judgment.strip():
        raise ValueError("assessment judgment must be non-empty")
    if not assessment.evidence or any(not evidence.strip() for evidence in assessment.evidence):
        raise ValueError("assessment needs at least one non-empty evidence entry")
    if assessment.uncertainty not in UNCERTAINTY_VALUES:
        raise ValueError(f"invalid assessment uncertainty: {assessment.uncertainty!r}")
    if not assessment.version.strip():
        raise ValueError("assessment version must be non-empty")
    if assessment.origin in {"human", "adjudicated"} and not assessment.reviewer_id:
        raise ValueError("human and adjudicated assessments need reviewerId")
    if assessment.origin == "model" and not assessment.model_id:
        raise ValueError("model assessments need modelId")
    if any(not note.strip() for note in assessment.disagreement):
        raise ValueError("assessment disagreement entries must be non-empty")


def _optional_string(value: object) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if text else None
