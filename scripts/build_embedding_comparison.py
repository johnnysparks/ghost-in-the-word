#!/usr/bin/env python3
"""Build a comparison artifact using an optional sentence-transformers model."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ghost_in_word.alignment import alignment_method
from ghost_in_word.embeddings import EmbeddingBackendUnavailable, cosine_distance, encode_texts
from ghost_in_word.scoring import lexical_distance, wording_distance
from ghost_in_word.sources import comparison_edition_metadata


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("alignment", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model", required=True, help="Sentence-transformers model ID or local path")
    parser.add_argument("--left-id", required=True)
    parser.add_argument("--right-id", required=True)
    parser.add_argument("--left-language", default="en")
    parser.add_argument("--right-language", default="en")
    parser.add_argument("--left-name", default="Translation A")
    parser.add_argument("--right-name", default="Translation B")
    parser.add_argument("--left-role", default="translation")
    parser.add_argument("--right-role", default="translation")
    parser.add_argument("--manifest", type=Path, help="Edition manifest used to attach provenance metadata")
    parser.add_argument("--book", action="append")
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--cache-dir", type=Path, help="Optional directory for content-addressed embedding vectors")
    parser.add_argument(
        "--model-revision",
        help="Immutable model revision for cache identity (defaults to --model)",
    )
    parser.add_argument(
        "--preprocessing-version",
        default="1",
        help="Version of the text preprocessing recipe; change it to invalidate the cache",
    )
    parser.add_argument("--prefix", default="query: ", help="Prefix passed to the embedding model")
    parser.add_argument(
        "--context-strategy",
        default="verse-only",
        help="Context recipe recorded in the run and included in cache identity",
    )
    args = parser.parse_args()

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
    matched = [unit for unit in alignment if unit["status"] == "matched" and unit["left_text"] and unit["right_text"]]
    left_texts = [unit["left_text"] for unit in matched]
    right_texts = [unit["right_text"] for unit in matched]

    try:
        left_vectors, run = encode_texts(
            left_texts,
            args.model,
            batch_size=args.batch_size,
            prefix=args.prefix,
            cache_dir=args.cache_dir,
            model_revision=args.model_revision,
            preprocessing_version=args.preprocessing_version,
            context_strategy=args.context_strategy,
        )
        right_vectors, right_run = encode_texts(
            right_texts,
            args.model,
            batch_size=args.batch_size,
            prefix=args.prefix,
            cache_dir=args.cache_dir,
            model_revision=args.model_revision,
            preprocessing_version=args.preprocessing_version,
            context_strategy=args.context_strategy,
        )
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
        if "left_notes" in unit:
            record["leftNotes"] = unit["left_notes"]
        if "right_notes" in unit:
            record["rightNotes"] = unit["right_notes"]
        if "review" in unit:
            record["review"] = unit["review"]
        record["id"] = f"{unit['book']}-{unit['chapter']}-{unit['verse']}"
        record["order"] = index
        if unit["status"] == "matched" and unit["left_text"] and unit["right_text"]:
            record["embeddingDistance"] = distances[id(unit)]
            if args.left_language == args.right_language:
                record["wordingDistance"] = wording_distance(unit["left_text"], unit["right_text"])
                record["lexicalDistance"] = lexical_distance(unit["left_text"], unit["right_text"])
            else:
                record["wordingDistance"] = None
                record["lexicalDistance"] = None
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
            "leftEdition": left_edition,
            "rightEdition": right_edition,
            "scope": {"books": sorted({str(unit["book"]) for unit in scored}), "unit": "verse"},
            "alignment": {"method": alignment_method(scored), "statuses": statuses},
            "metric": {
                "id": f"embedding:{args.model}",
                "label": f"Embedding distance · {args.model}",
                "distanceField": "embeddingDistance",
                "wordingField": "wordingDistance",
                "description": "Cosine distance between normalized sentence embeddings. It is a model estimate of representational divergence, not a faithfulness grade.",
            },
            "embeddingRun": {
                **run.to_dict(),
                "leftInputHash": run.input_hash,
                "rightInputHash": right_run.input_hash,
                "leftCacheKey": run.cache_key,
                "rightCacheKey": right_run.cache_key,
                "leftCacheHit": run.cache_hit,
                "rightCacheHit": right_run.cache_hit,
            },
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
