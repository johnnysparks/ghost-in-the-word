#!/usr/bin/env python3
"""Build a score-blind review packet for explicit alignment candidates."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ghost_in_word.mapping_review import bind_snapshot, build_mapping_review_packet
from ghost_in_word.usfm import parse_usfm_directory


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("left", type=Path)
    parser.add_argument("right", type=Path)
    parser.add_argument("mapping", type=Path, help="Candidate mapping JSON array")
    parser.add_argument("--left-id", required=True)
    parser.add_argument("--right-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    left = parse_usfm_directory(args.left, args.left_id)
    right = parse_usfm_directory(args.right, args.right_id)
    records = json.loads(args.mapping.read_text(encoding="utf-8"))
    packet = build_mapping_review_packet(
        records,
        left,
        right,
        left_source=bind_snapshot(args.left, args.left_id),
        right_source=bind_snapshot(args.right, args.right_id),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(packet, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "itemCount": len(packet["items"])}, indent=2))


if __name__ == "__main__":
    main()
