"""Validation and loading for traceable edition manifests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Mapping

from .models import Edition

EDITION_ROLES = {"translation", "source"}
SUPPORTED_FORMATS = {"usfm"}
REQUIRED_FIELDS = ("id", "name", "language", "source", "download", "format", "license", "canon")


def load_editions(path: str | Path) -> dict[str, Edition]:
    """Load and validate a manifest keyed by stable edition ID."""

    document = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(document, Mapping) or not isinstance(document.get("editions"), list):
        raise ValueError("source manifest must contain an editions array")
    editions: dict[str, Edition] = {}
    for record in document["editions"]:
        if not isinstance(record, Mapping):
            raise ValueError("each source manifest edition must be an object")
        missing = [field for field in REQUIRED_FIELDS if not str(record.get(field, "")).strip()]
        if missing:
            raise ValueError(f"edition is missing required fields: {', '.join(missing)}")
        edition_id = str(record["id"])
        if edition_id in editions:
            raise ValueError(f"duplicate edition ID: {edition_id}")
        format_name = str(record["format"]).lower()
        if format_name not in SUPPORTED_FORMATS:
            raise ValueError(f"unsupported source format for {edition_id}: {format_name}")
        role = str(record.get("role", "translation")).lower()
        if role not in EDITION_ROLES:
            raise ValueError(f"unsupported edition role for {edition_id}: {role}")
        attribution = str(record.get("attribution", ""))
        if role == "source" and not attribution:
            raise ValueError(f"source edition {edition_id} must declare attribution")
        editions[edition_id] = Edition(
            id=edition_id,
            name=str(record["name"]),
            language=str(record["language"]),
            source=str(record["source"]),
            download=str(record["download"]),
            format=format_name,
            license=str(record["license"]),
            canon=str(record["canon"]),
            revision=str(record.get("revision", "")),
            versification=str(record.get("versification", "")),
            role=role,
            source_tradition=str(record.get("sourceTradition", "")),
            family=str(record.get("family", "")),
            attribution=attribution,
        )
    if not editions:
        raise ValueError("source manifest must contain at least one edition")
    return editions


def edition_to_dict(edition: Edition) -> dict[str, object]:
    """Return the public camelCase representation used by manifests and UI."""

    record: dict[str, object] = {
        "id": edition.id,
        "name": edition.name,
        "language": edition.language,
        "source": edition.source,
        "download": edition.download,
        "format": edition.format,
        "license": edition.license,
        "canon": edition.canon,
        "role": edition.role,
    }
    if edition.revision:
        record["revision"] = edition.revision
    if edition.versification:
        record["versification"] = edition.versification
    if edition.source_tradition:
        record["sourceTradition"] = edition.source_tradition
    if edition.family:
        record["family"] = edition.family
    if edition.attribution:
        record["attribution"] = edition.attribution
    return record


def comparison_edition_metadata(
    edition_id: str,
    *,
    name: str,
    language: str,
    role: str,
    manifest: str | Path | None = None,
) -> dict[str, object]:
    """Build comparison metadata, optionally resolving an edition manifest.

    When a manifest is supplied it is authoritative for language, role,
    provenance, license, canon, and attribution. Explicit custom names remain
    available for small experiments, while mismatched language or role flags
    fail instead of silently producing misleading provenance.
    """

    if manifest is None:
        return {"id": edition_id, "name": name, "language": language, "role": role}
    edition = load_editions(manifest).get(edition_id)
    if edition is None:
        raise ValueError(f"edition {edition_id!r} is not present in manifest {manifest}")
    if language != edition.language and language != "en":
        raise ValueError(f"language flag {language!r} does not match manifest edition {edition_id!r} ({edition.language!r})")
    if role != edition.role and role != "translation":
        raise ValueError(f"role flag {role!r} does not match manifest edition {edition_id!r} ({edition.role!r})")
    record = edition_to_dict(edition)
    if name not in {"Translation A", "Translation B"}:
        record["name"] = name
    return record
