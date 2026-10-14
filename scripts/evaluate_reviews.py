#!/usr/bin/env python3
"""Aggregate independent human-review JSON documents."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ghost_in_word.review import summarize_reviews


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("reviews", nargs="+", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    documents = [json.loads(path.read_text(encoding="utf-8")) for path in args.reviews]
    report = summarize_reviews(documents)
    encoded = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
    print(encoded, end="")


if __name__ == "__main__":
    main()
