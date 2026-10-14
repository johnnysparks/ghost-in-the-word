"""Build per-passage distance matrices from pairwise comparison artifacts."""

from __future__ import annotations

from itertools import combinations
from typing import Iterable, Mapping

from .scoring import lexical_distance, wording_distance


def build_translation_matrix(
    comparisons: Iterable[Mapping[str, object]],
    *,
    books: Iterable[str] | None = None,
) -> dict[str, object]:
    """Join pairwise artifacts into a panel view for each aligned passage.

    Texts are joined by the stable unit id. The function checks that repeated
    edition metadata and text values agree before deriving any new pairwise
    lexical distances. A matrix is descriptive: it does not choose a preferred
    translation or turn the distances into a faithfulness score.
    """

    allowed_books = {book.upper() for book in books} if books else None
    edition_metadata: dict[str, dict[str, object]] = {}
    passages: dict[str, dict[str, object]] = {}
    order: list[str] = []
    for comparison in comparisons:
        metadata = comparison.get("metadata")
        if not isinstance(metadata, Mapping):
            raise ValueError("comparison artifact must contain metadata")
        editions = {
            "left": metadata.get("leftEdition"),
            "right": metadata.get("rightEdition"),
        }
        for side in ("left", "right"):
            edition = editions[side]
            if not isinstance(edition, Mapping) or not isinstance(edition.get("id"), str) or not edition["id"]:
                raise ValueError("comparison metadata must identify both editions")
            edition_id = str(edition["id"])
            normalized = {
                "id": edition_id,
                "name": str(edition.get("name", edition_id)),
                "language": edition.get("language"),
            }
            for field in (
                "role",
                "source",
                "download",
                "format",
                "license",
                "canon",
                "revision",
                "versification",
                "sourceTradition",
                "family",
                "attribution",
            ):
                if field in edition:
                    normalized[field] = edition[field]
            previous = edition_metadata.get(edition_id)
            if previous is not None and previous != normalized:
                raise ValueError(f"conflicting metadata for edition {edition_id}")
            edition_metadata[edition_id] = normalized

        units = comparison.get("units")
        if not isinstance(units, list):
            raise ValueError("comparison artifact must contain units")
        for unit in units:
            if not isinstance(unit, Mapping):
                raise ValueError("comparison units must be objects")
            book = str(unit.get("book", "")).upper()
            if allowed_books is not None and book not in allowed_books:
                continue
            unit_id = unit.get("id")
            if not isinstance(unit_id, str) or not unit_id:
                unit_id = f"{book}-{unit.get('chapter')}-{unit.get('verse')}"
            if unit_id not in passages:
                passages[unit_id] = {
                    "id": unit_id,
                    "order": int(unit.get("order", len(order))),
                    "book": book,
                    "chapter": int(unit["chapter"]),
                    "verse": str(unit["verse"]),
                    "reference": str(unit.get("reference", f"{book} {unit['chapter']}:{unit['verse']}")),
                    "texts": {},
                }
                order.append(unit_id)
            passage = passages[unit_id]
            _add_text(passage, str(editions["left"]["id"]), _value(unit, "leftText", "left_text"))
            _add_text(passage, str(editions["right"]["id"]), _value(unit, "rightText", "right_text"))

    ordered_passages = sorted((passages[unit_id] for unit_id in order), key=lambda passage: (int(passage["order"]), str(passage["id"])))
    output_passages: list[dict[str, object]] = []
    for passage in ordered_passages:
        texts = passage.pop("texts")
        edition_ids = sorted(str(edition) for edition in texts)
        distances: dict[str, dict[str, float]] = {}
        for left, right in combinations(edition_ids, 2):
            left_text = str(texts[left])
            right_text = str(texts[right])
            distances[f"{left}|{right}"] = {
                "wordingDistance": wording_distance(left_text, right_text),
                "lexicalDistance": lexical_distance(left_text, right_text),
            }
        output_passages.append(
            {
                **passage,
                "status": "matched" if len(edition_ids) >= 2 else "insufficient-panel",
                "texts": texts,
                "distances": distances,
            }
        )

    return {
        "schemaVersion": 1,
        "kind": "translation-distance-matrix",
        "metadata": {
            "editions": [edition_metadata[edition_id] for edition_id in sorted(edition_metadata)],
            "scope": {"books": sorted({str(passage["book"]) for passage in output_passages}), "unit": "verse"},
            "metric": {
                "id": "lexical-baseline",
                "label": "Lexical baseline",
                "description": "Pairwise lexical distances across the named panel; this is a comparison aid, not a faithfulness grade.",
            },
        },
        "passages": output_passages,
        "summary": {
            "totalPassages": len(output_passages),
            "scoredPassages": sum(1 for passage in output_passages if passage["distances"]),
            "editionCoverage": {
                edition_id: sum(1 for passage in output_passages if edition_id in passage["texts"])
                for edition_id in sorted(edition_metadata)
            },
        },
    }


def _value(unit: Mapping[str, object], camel: str, snake: str) -> object:
    return unit[camel] if camel in unit else unit.get(snake)


def _add_text(passage: dict[str, object], edition_id: str, value: object) -> None:
    if value is None or not str(value).strip():
        return
    texts = passage["texts"]
    if not isinstance(texts, dict):
        raise ValueError("matrix passage texts must be an object")
    text = str(value)
    previous = texts.get(edition_id)
    if previous is not None and previous != text:
        raise ValueError(f"conflicting text for {passage['id']} in edition {edition_id}")
    texts[edition_id] = text
