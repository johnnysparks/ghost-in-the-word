#!/usr/bin/env python3
"""Aggregate independent human-review JSON documents."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ghost_in_word.review import summarize_reviews, validate_review_packet


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("reviews", nargs="+", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--packet", type=Path, help="Blinded packet used to check response IDs and coverage")
    parser.add_argument("--key", type=Path, help="Private selection key created alongside the blind packet")
    args = parser.parse_args()

    documents = [json.loads(path.read_text(encoding="utf-8")) for path in args.reviews]
    packet = json.loads(args.packet.read_text(encoding="utf-8")) if args.packet else None
    if packet is not None:
        validate_review_packet(packet)
    selection_key = json.loads(args.key.read_text(encoding="utf-8")) if args.key else None
    report = summarize_reviews(documents, selection_key=selection_key, packet=packet)
    encoded = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
    print(encoded, end="")


if __name__ == "__main__":
    main()
