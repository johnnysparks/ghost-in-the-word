#!/usr/bin/env python3
"""Build a score-blinded, genre-stratified natural review benchmark."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ghost_in_word.review import select_natural_benchmark, validate_review_packet


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("comparison", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--key-output", type=Path, required=True)
    parser.add_argument("--count", type=int, default=200)
    parser.add_argument("--seed", type=int, default=20261014)
    parser.add_argument("--metric", default="lexicalDistance")
    args = parser.parse_args()

    comparison = json.loads(args.comparison.read_text(encoding="utf-8"))
    packet, key = select_natural_benchmark(
        comparison,
        count=args.count,
        metric_field=args.metric,
        seed=args.seed,
    )
    validate_review_packet(packet)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(packet, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.key_output.parent.mkdir(parents=True, exist_ok=True)
    args.key_output.write_text(json.dumps(key, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(packet["selection"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
