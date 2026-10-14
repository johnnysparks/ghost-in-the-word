#!/usr/bin/env python3
"""Create a blinded, reproducible human-review packet from a comparison artifact."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ghost_in_word.review import select_review_items


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("comparison", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--count", type=int, default=30)
    parser.add_argument("--seed", type=int, default=20261014)
    parser.add_argument("--metric", default="lexicalDistance")
    args = parser.parse_args()

    comparison = json.loads(args.comparison.read_text(encoding="utf-8"))
    packet = select_review_items(comparison, count=args.count, metric_field=args.metric, seed=args.seed)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(packet, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(packet["selection"], indent=2))


if __name__ == "__main__":
    main()
