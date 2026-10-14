#!/usr/bin/env python3
"""Evaluate a distance function on the synthetic challenge set."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ghost_in_word.embeddings import EmbeddingBackendUnavailable, cosine_distance, encode_texts
from ghost_in_word.scoring import lexical_distance


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("challenge", type=Path)
    parser.add_argument("--metric", choices=("lexical", "embedding"), default="lexical")
    parser.add_argument("--model", help="Required for --metric embedding")
    parser.add_argument("--threshold", type=float, default=0.8)
    args = parser.parse_args()
    cases = json.loads(args.challenge.read_text(encoding="utf-8"))

    distances: list[tuple[float, float]] = []
    if args.metric == "embedding":
        if not args.model:
            raise SystemExit("--model is required for --metric embedding")
        texts = [text for case in cases for text in (case["anchor"], case["meaning_preserving"], case["meaning_changed"])]
        try:
            vectors, run = encode_texts(texts, args.model)
        except EmbeddingBackendUnavailable as exc:
            raise SystemExit(str(exc)) from exc
        for index in range(0, len(vectors), 3):
            distances.append((cosine_distance(vectors[index], vectors[index + 1]), cosine_distance(vectors[index], vectors[index + 2])))
        run_metadata = run.to_dict()
    else:
        distances = [(lexical_distance(case["anchor"], case["meaning_preserving"]), lexical_distance(case["anchor"], case["meaning_changed"])) for case in cases]
        run_metadata = {"metric": "character-ngram-lexical-baseline"}

    results = []
    for case, (preserved_distance, changed_distance) in zip(cases, distances):
        results.append({
            "id": case["id"],
            "preservedDistance": preserved_distance,
            "changedDistance": changed_distance,
            "changedRanksFarther": changed_distance > preserved_distance,
        })
    passed = sum(1 for result in results if result["changedRanksFarther"])
    pass_rate = passed / len(results) if results else 0.0
    report = {
        "metric": args.metric,
        "run": run_metadata,
        "cases": results,
        "passed": passed,
        "total": len(results),
        "passRate": round(pass_rate, 6),
        "threshold": args.threshold,
        "gatePassed": pass_rate >= args.threshold,
        "interpretation": "A synthetic ranking check only; this does not establish translation faithfulness or model quality on Scripture.",
    }
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
