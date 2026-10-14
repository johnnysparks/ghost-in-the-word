#!/usr/bin/env python3
"""Validate the shape and optional holdout scope of a natural review packet."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ghost_in_word.review import validate_natural_benchmark_packet


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("packet", type=Path)
    parser.add_argument("--expected-count", type=int, default=200)
    parser.add_argument("--require-holdout-scope", action="store_true")
    parser.add_argument("--exclude-book", action="append", default=[])
    args = parser.parse_args()
    packet = json.loads(args.packet.read_text(encoding="utf-8"))
    report = validate_natural_benchmark_packet(
        packet,
        expected_count=args.expected_count,
        require_holdout_scope=args.require_holdout_scope,
        excluded_books=args.exclude_book,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
