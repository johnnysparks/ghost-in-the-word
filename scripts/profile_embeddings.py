#!/usr/bin/env python3
"""Measure an embedding pilot before scaling it to a larger corpus."""

from __future__ import annotations

import argparse
import json
import platform
import resource
import sys
import time
from pathlib import Path

from ghost_in_word.embeddings import EmbeddingBackendUnavailable, embedding_storage_bytes, input_hash


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("comparison", type=Path)
    parser.add_argument("--model", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--book", action="append")
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--limit", type=int, help="Profile only the first N matched units")
    parser.add_argument("--target-units", type=int, help="Corpus unit count for projection; defaults to comparison totalUnits")
    parser.add_argument("--edition-count", type=int, default=3)
    parser.add_argument("--prefix", default="query: ")
    args = parser.parse_args()
    if args.batch_size < 1:
        raise SystemExit("--batch-size must be positive")
    if args.edition_count < 1:
        raise SystemExit("--edition-count must be positive")

    comparison = json.loads(args.comparison.read_text(encoding="utf-8"))
    units = comparison.get("units")
    if not isinstance(units, list):
        raise SystemExit("comparison artifact must contain a units array")
    allowed = {book.upper() for book in args.book} if args.book else None
    matched = [
        unit
        for unit in units
        if isinstance(unit, dict)
        and unit.get("status") == "matched"
        and unit.get("leftText")
        and unit.get("rightText")
        and (allowed is None or str(unit.get("book", "")).upper() in allowed)
    ]
    if args.limit is not None:
        if args.limit < 1:
            raise SystemExit("--limit must be positive")
        matched = matched[: args.limit]
    if not matched:
        raise SystemExit("comparison contains no matched units with both texts")

    texts = [str(unit["leftText"]) for unit in matched] + [str(unit["rightText"]) for unit in matched]
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as exc:
        raise SystemExit(
            "sentence-transformers is not installed; install the optional embedding dependencies before profiling"
        ) from exc

    try:
        started = time.perf_counter()
        model = SentenceTransformer(args.model)
        loaded_seconds = time.perf_counter() - started
        tokenizer = model.tokenizer
        tokenized = tokenizer([f"{args.prefix}{text}" for text in texts], add_special_tokens=True, truncation=False, padding=False)
        token_counts = [len(ids) for ids in tokenized["input_ids"]]
        max_seq_length = getattr(model, "max_seq_length", None)
        max_seq_length = int(max_seq_length) if max_seq_length is not None else None
        encode_started = time.perf_counter()
        vectors = model.encode(
            [f"{args.prefix}{text}" for text in texts],
            batch_size=args.batch_size,
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=True,
        )
        encode_seconds = time.perf_counter() - encode_started
    except Exception as exc:
        raise SystemExit(f"embedding profile failed: {exc}") from exc

    dimensions = int(vectors.shape[1]) if len(vectors.shape) > 1 else 0
    target_units = args.target_units
    if target_units is None:
        summary = comparison.get("summary")
        target_units = int(summary.get("totalUnits", len(matched))) if isinstance(summary, dict) else len(matched)
    if target_units < len(matched):
        raise SystemExit("--target-units cannot be less than the profiled unit count")
    rss_raw = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    peak_rss_bytes = int(rss_raw if sys.platform == "darwin" else rss_raw * 1024)
    observed_inputs = len(texts)
    observed_units_per_second = len(matched) / encode_seconds if encode_seconds else None
    projected_seconds = target_units / observed_units_per_second if observed_units_per_second else None
    report = {
        "schemaVersion": 1,
        "kind": "embedding-profile",
        "comparison": str(args.comparison),
        "scope": {"books": sorted(allowed) if allowed else "comparison", "unitCount": len(matched)},
        "run": {
            "modelId": args.model,
            "dimensions": dimensions,
            "maxSeqLength": max_seq_length,
            "prefix": args.prefix,
            "inputHash": input_hash(texts),
        },
        "tokens": {
            "inputCount": observed_inputs,
            "total": sum(token_counts),
            "mean": round(sum(token_counts) / len(token_counts), 3),
            "max": max(token_counts),
            "overMaxSeqLength": sum(1 for count in token_counts if max_seq_length is not None and count > max_seq_length),
        },
        "performance": {
            "batchSize": args.batch_size,
            "modelLoadSeconds": round(loaded_seconds, 6),
            "encodeSeconds": round(encode_seconds, 6),
            "unitsPerSecond": round(observed_units_per_second, 6) if observed_units_per_second else None,
            "inputsPerSecond": round(observed_inputs / encode_seconds, 6) if encode_seconds else None,
            "peakRssBytes": peak_rss_bytes,
            "platform": platform.platform(),
        },
        "projection": {
            "targetUnits": target_units,
            "editionCount": args.edition_count,
            "rawFloat32VectorBytes": embedding_storage_bytes(target_units, args.edition_count, dimensions),
            "estimatedEncodeSeconds": round(projected_seconds, 3) if projected_seconds is not None else None,
        },
        "interpretation": "Capacity and throughput measurements for planning only; they do not evaluate translation quality.",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
