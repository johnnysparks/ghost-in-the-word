#!/usr/bin/env python3
"""Evaluate a distance function on the synthetic challenge set."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
import random

from ghost_in_word.embeddings import EmbeddingBackendUnavailable, cosine_distance, encode_texts
from ghost_in_word.scoring import lexical_distance


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("challenge", type=Path)
    parser.add_argument("--metric", choices=("lexical", "embedding"), default="lexical")
    parser.add_argument("--model", help="Required for --metric embedding")
    parser.add_argument("--threshold", type=float, default=0.8)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--bootstrap-samples", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=20261014)
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
            "genre": case.get("genre", "unspecified"),
            "kind": case.get("kind", "unspecified"),
            "preservedDistance": preserved_distance,
            "changedDistance": changed_distance,
            "margin": round(changed_distance - preserved_distance, 6),
            "changedRanksFarther": changed_distance > preserved_distance,
        })
    passed = sum(1 for result in results if result["changedRanksFarther"])
    pass_rate = passed / len(results) if results else 0.0
    by_slice: dict[str, list[dict[str, object]]] = defaultdict(list)
    for result in results:
        by_slice[str(result["genre"])].append(result)
    slices = {}
    for name, slice_results in sorted(by_slice.items()):
        slice_passed = sum(1 for result in slice_results if result["changedRanksFarther"])
        slices[name] = {
            "passed": slice_passed,
            "total": len(slice_results),
            "passRate": round(slice_passed / len(slice_results), 6) if slice_results else 0.0,
            "meanMargin": round(sum(float(result["margin"]) for result in slice_results) / len(slice_results), 6) if slice_results else None,
        }
    if args.bootstrap_samples < 0:
        raise SystemExit("--bootstrap-samples must be non-negative")
    bootstrap = {"samples": args.bootstrap_samples, "seed": args.seed, "unit": "challenge-case", "passRate95CI": None, "meanMargin95CI": None}
    if results and args.bootstrap_samples:
        generator = random.Random(args.seed)
        outcomes = [1.0 if result["changedRanksFarther"] else 0.0 for result in results]
        margins = [float(result["margin"]) for result in results]
        pass_rates = []
        mean_margins = []
        for _ in range(args.bootstrap_samples):
            sample = [generator.randrange(len(results)) for _ in results]
            pass_rates.append(sum(outcomes[index] for index in sample) / len(sample))
            mean_margins.append(sum(margins[index] for index in sample) / len(sample))
        bootstrap["passRate95CI"] = [_percentile(pass_rates, 0.025), _percentile(pass_rates, 0.975)]
        bootstrap["meanMargin95CI"] = [_percentile(mean_margins, 0.025), _percentile(mean_margins, 0.975)]
    report = {
        "metric": args.metric,
        "run": run_metadata,
        "cases": results,
        "passed": passed,
        "total": len(results),
        "passRate": round(pass_rate, 6),
        "meanMargin": round(sum(float(result["margin"]) for result in results) / len(results), 6) if results else None,
        "byGenre": slices,
        "bootstrap": bootstrap,
        "threshold": args.threshold,
        "gatePassed": pass_rate >= args.threshold,
        "interpretation": "A synthetic ranking check only; this does not establish translation faithfulness or model quality on Scripture.",
    }
    encoded = json.dumps(report, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
    print(encoded, end="")


def _percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    position = fraction * (len(ordered) - 1)
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return round(ordered[lower] + (ordered[upper] - ordered[lower]) * weight, 6)


if __name__ == "__main__":
    main()
