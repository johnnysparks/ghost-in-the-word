#!/usr/bin/env python3
"""Build a comparison artifact using an optional sentence-transformers model."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ghost_in_word.alignment import alignment_method
from ghost_in_word.embeddings import EmbeddingBackendUnavailable, cosine_distance, encode_texts
from ghost_in_word.scoring import lexical_distance, wording_distance


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("alignment", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model", required=True, help="Sentence-transformers model ID or local path")
    parser.add_argument("--left-id", required=True)
    parser.add_argument("--right-id", required=True)
    parser.add_argument("--left-name", default="Translation A")
    parser.add_argument("--right-name", default="Translation B")
    parser.add_argument("--book", action="append")
    parser.add_argument("--batch-size", type=int, default=32)
    args = parser.parse_args()

    alignment = json.loads(args.alignment.read_text(encoding="utf-8"))
    if args.book:
        allowed = {book.upper() for book in args.book}
        alignment = [unit for unit in alignment if unit["book"].upper() in allowed]
    matched = [unit for unit in alignment if unit["status"] == "matched" and unit["left_text"] and unit["right_text"]]
    left_texts = [unit["left_text"] for unit in matched]
    right_texts = [unit["right_text"] for unit in matched]

    try:
        left_vectors, run = encode_texts(left_texts, args.model, batch_size=args.batch_size)
        right_vectors, right_run = encode_texts(right_texts, args.model, batch_size=args.batch_size)
    except EmbeddingBackendUnavailable as exc:
        raise SystemExit(str(exc)) from exc
    if run.dimensions != right_run.dimensions:
        raise SystemExit("model returned different dimensions for the two editions")

    distances = {id(unit): cosine_distance(left_vectors[index], right_vectors[index]) for index, unit in enumerate(matched)}
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
        record["id"] = f"{unit['book']}-{unit['chapter']}-{unit['verse']}"
        record["order"] = index
        if unit["status"] == "matched" and unit["left_text"] and unit["right_text"]:
            record["embeddingDistance"] = distances[id(unit)]
            record["wordingDistance"] = wording_distance(unit["left_text"], unit["right_text"])
            record["lexicalDistance"] = lexical_distance(unit["left_text"], unit["right_text"])
        else:
            record["embeddingDistance"] = None
            record["wordingDistance"] = None
            record["lexicalDistance"] = None
        scored.append(record)

    statuses: dict[str, int] = {}
    for unit in scored:
        statuses[str(unit["status"])] = statuses.get(str(unit["status"]), 0) + 1
    output = {
        "schemaVersion": 1,
        "metadata": {
            "leftEdition": {"id": args.left_id, "name": args.left_name},
            "rightEdition": {"id": args.right_id, "name": args.right_name},
            "scope": {"books": sorted({str(unit["book"]) for unit in scored}), "unit": "verse"},
            "alignment": {"method": alignment_method(scored), "statuses": statuses},
            "metric": {
                "id": f"embedding:{args.model}",
                "label": f"Embedding distance · {args.model}",
                "distanceField": "embeddingDistance",
                "wordingField": "wordingDistance",
                "description": "Cosine distance between normalized sentence embeddings. It is a model estimate of representational divergence, not a faithfulness grade.",
            },
            "embeddingRun": run.to_dict(),
            "source": {"alignment": str(args.alignment)},
        },
        "units": scored,
        "summary": {
            "totalUnits": len(scored),
            "matchedUnits": len(matched),
            "scoredUnits": len(matched),
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "summary": output["summary"], "embeddingRun": run.to_dict()}, indent=2))


if __name__ == "__main__":
    main()
