#!/usr/bin/env python3
"""Build a browser-ready comparison artifact from an alignment report."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ghost_in_word.alignment import alignment_method
from ghost_in_word.sources import comparison_edition_metadata

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("alignment", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--book", action="append", help="Filter to one or more USFM book IDs")
    parser.add_argument("--left-id", required=True)
    parser.add_argument("--right-id", required=True)
    parser.add_argument("--left-language", default="en")
    parser.add_argument("--right-language", default="en")
    parser.add_argument("--left-name", default="Translation A")
    parser.add_argument("--right-name", default="Translation B")
    parser.add_argument("--left-role", default="translation")
    parser.add_argument("--right-role", default="translation")
    parser.add_argument("--manifest", type=Path, help="Edition manifest used to attach provenance metadata")
    args = parser.parse_args()

    if args.left_language != args.right_language:
        raise SystemExit("build_comparison.py provides a same-language lexical baseline; use build_embedding_comparison.py for cross-language artifacts")

    try:
        left_edition = comparison_edition_metadata(
            args.left_id,
            name=args.left_name,
            language=args.left_language,
            role=args.left_role,
            manifest=args.manifest,
        )
        right_edition = comparison_edition_metadata(
            args.right_id,
            name=args.right_name,
            language=args.right_language,
            role=args.right_role,
            manifest=args.manifest,
        )
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc

    alignment = json.loads(args.alignment.read_text(encoding="utf-8"))
    if args.book:
        allowed = {book.upper() for book in args.book}
        alignment = [unit for unit in alignment if unit["book"].upper() in allowed]

    # Reconstruct the public, scored record shape without coupling the browser
    # artifact to Python dataclass serialization details.
    scored: list[dict[str, object]] = []
    for index, unit in enumerate(alignment):
        record: dict[str, object] = {
            "book": unit["book"],
            "chapter": unit["chapter"],
            "verse": unit["verse"],
            "leftEdition": unit["left_edition"],
            "rightEdition": unit["right_edition"],
            "leftText": unit["left_text"],
            "rightText": unit["right_text"],
            "status": unit["status"],
            "reference": unit["reference"],
        }
        if "mapping_type" in unit:
            record["mappingType"] = unit["mapping_type"]
        if "left_references" in unit:
            record["leftReferences"] = unit["left_references"]
        if "right_references" in unit:
            record["rightReferences"] = unit["right_references"]
        if "mapping_method" in unit:
            record["mappingMethod"] = unit["mapping_method"]
        if "left_notes" in unit:
            record["leftNotes"] = unit["left_notes"]
        if "right_notes" in unit:
            record["rightNotes"] = unit["right_notes"]
        if "review" in unit:
            record["review"] = unit["review"]
        record["id"] = f"{unit['book']}-{unit['chapter']}-{unit['verse']}"
        record["order"] = index
        if unit["status"] == "matched" and unit["left_text"] is not None and unit["right_text"] is not None:
            from ghost_in_word.scoring import lexical_distance, wording_distance

            record["wordingDistance"] = wording_distance(unit["left_text"], unit["right_text"])
            record["lexicalDistance"] = lexical_distance(unit["left_text"], unit["right_text"])
        else:
            record["wordingDistance"] = None
            record["lexicalDistance"] = None
        scored.append(record)

    matched = [unit for unit in scored if unit["status"] == "matched"]
    statuses: dict[str, int] = {}
    for unit in scored:
        status = str(unit["status"])
        statuses[status] = statuses.get(status, 0) + 1

    output = {
        "schemaVersion": 1,
        "metadata": {
            "leftEdition": left_edition,
            "rightEdition": right_edition,
            "scope": {"books": sorted({str(unit["book"]) for unit in scored}), "unit": "verse"},
            "alignment": {"method": alignment_method(scored), "statuses": statuses},
            "metric": {
                "id": "lexical-baseline",
                "label": "Lexical baseline",
                "distanceField": "lexicalDistance",
                "wordingField": "wordingDistance",
                "description": "Character n-gram cosine distance. This is a reproducible lexical baseline, not a semantic or faithfulness score.",
            },
            "source": {"alignment": str(args.alignment)},
        },
        "units": scored,
        "summary": {
            "totalUnits": len(scored),
            "matchedUnits": len(matched),
            "scoredUnits": sum(1 for unit in matched if unit["lexicalDistance"] is not None),
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "summary": output["summary"], "statuses": statuses}, indent=2))


if __name__ == "__main__":
    main()
