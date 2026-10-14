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
    parser.add_argument("--cache-dir", type=Path, help="Optional directory for content-addressed embedding vectors")
    parser.add_argument("--model-revision", help="Immutable model revision for cache identity")
    parser.add_argument("--preprocessing-version", default="1")
    parser.add_argument("--prefix", default="query: ")
    parser.add_argument("--context-strategy", default="synthetic-triplet")
    args = parser.parse_args()
    cases = json.loads(args.challenge.read_text(encoding="utf-8"))

    distances: list[tuple[float, float]] = []
    lexical_distances: list[tuple[float, float]] | None = None
    if args.metric == "embedding":
        if not args.model:
            raise SystemExit("--model is required for --metric embedding")
        texts = [text for case in cases for text in (case["anchor"], case["meaning_preserving"], case["meaning_changed"])]
        try:
            vectors, run = encode_texts(
                texts,
                args.model,
                cache_dir=args.cache_dir,
                model_revision=args.model_revision,
                preprocessing_version=args.preprocessing_version,
                prefix=args.prefix,
                context_strategy=args.context_strategy,
            )
        except EmbeddingBackendUnavailable as exc:
            raise SystemExit(str(exc)) from exc
        for index in range(0, len(vectors), 3):
            distances.append((cosine_distance(vectors[index], vectors[index + 1]), cosine_distance(vectors[index], vectors[index + 2])))
        lexical_distances = [
            (lexical_distance(case["anchor"], case["meaning_preserving"]), lexical_distance(case["anchor"], case["meaning_changed"]))
            for case in cases
        ]
        run_metadata = run.to_dict()
    else:
        distances = [(lexical_distance(case["anchor"], case["meaning_preserving"]), lexical_distance(case["anchor"], case["meaning_changed"])) for case in cases]
        run_metadata = {"metric": "character-ngram-lexical-baseline"}

    results = []
    for index, (case, (preserved_distance, changed_distance)) in enumerate(zip(cases, distances)):
        result: dict[str, object] = {
            "id": case["id"],
            "genre": case.get("genre", "unspecified"),
            "kind": case.get("kind", "unspecified"),
            "preservedDistance": preserved_distance,
            "changedDistance": changed_distance,
            "margin": round(changed_distance - preserved_distance, 6),
            "changedRanksFarther": changed_distance > preserved_distance,
        }
        if lexical_distances is not None:
            lexical_preserved, lexical_changed = lexical_distances[index]
            result.update(
                {
                    "lexicalPreservedDistance": lexical_preserved,
                    "lexicalChangedDistance": lexical_changed,
                    "lexicalMargin": round(lexical_changed - lexical_preserved, 6),
                    "lexicalChangedRanksFarther": lexical_changed > lexical_preserved,
                }
            )
        results.append(result)
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
        "baselineComparison": compare_to_baseline(results, bootstrap_samples=args.bootstrap_samples, seed=args.seed),
        "threshold": args.threshold,
        "gatePassed": pass_rate >= args.threshold,
        "interpretation": "A synthetic ranking check only; this does not establish translation faithfulness or model quality on Scripture.",
    }
    encoded = json.dumps(report, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
    print(encoded, end="")


def compare_to_baseline(
    results: list[dict[str, object]],
    *,
    bootstrap_samples: int,
    seed: int,
) -> dict[str, object] | None:
    """Report paired embedding-versus-lexical effects for the same cases."""

    pairs = [
        result
        for result in results
        if "lexicalChangedRanksFarther" in result and "lexicalMargin" in result
    ]
    if not pairs:
        return None
    outcome_deltas = [
        (1.0 if result["changedRanksFarther"] else 0.0)
        - (1.0 if result["lexicalChangedRanksFarther"] else 0.0)
        for result in pairs
    ]
    margin_deltas = [float(result["margin"]) - float(result["lexicalMargin"]) for result in pairs]
    embedding_pass_rate = sum(1.0 if result["changedRanksFarther"] else 0.0 for result in pairs) / len(pairs)
    lexical_pass_rate = sum(1.0 if result["lexicalChangedRanksFarther"] else 0.0 for result in pairs) / len(pairs)
    outcome_ci, margin_ci = _paired_bootstrap(outcome_deltas, margin_deltas, samples=bootstrap_samples, seed=seed)
    return {
        "baselineMetric": "character-ngram-lexical",
        "comparedMetric": "embedding",
        "pairedCases": len(pairs),
        "embeddingPassRate": round(embedding_pass_rate, 6),
        "lexicalPassRate": round(lexical_pass_rate, 6),
        "passRateDelta": round(embedding_pass_rate - lexical_pass_rate, 6),
        "meanMarginDelta": round(sum(margin_deltas) / len(margin_deltas), 6),
        "bootstrap": {
            "samples": bootstrap_samples,
            "seed": seed,
            "unit": "challenge-case",
            "passRateDelta95CI": outcome_ci,
            "meanMarginDelta95CI": margin_ci,
        },
        "interpretation": "Paired synthetic effect against the lexical baseline; this does not establish translation faithfulness or model quality on Scripture.",
    }


def _paired_bootstrap(
    outcome_deltas: list[float],
    margin_deltas: list[float],
    *,
    samples: int,
    seed: int,
) -> tuple[list[float] | None, list[float] | None]:
    if not outcome_deltas or samples == 0:
        return None, None
    generator = random.Random(seed)
    outcome_means: list[float] = []
    margin_means: list[float] = []
    for _ in range(samples):
        indexes = [generator.randrange(len(outcome_deltas)) for _ in outcome_deltas]
        outcome_means.append(sum(outcome_deltas[index] for index in indexes) / len(indexes))
        margin_means.append(sum(margin_deltas[index] for index in indexes) / len(indexes))
    return (
        [_percentile(outcome_means, 0.025), _percentile(outcome_means, 0.975)],
        [_percentile(margin_means, 0.025), _percentile(margin_means, 0.975)],
    )


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
