#!/usr/bin/env python3
"""Build a JSON alignment report from downloaded USFM directories."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ghost_in_word.alignment import align_segments, align_with_mappings, mapping_from_dict
from ghost_in_word.usfm import parse_usfm_directory


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("left", type=Path)
    parser.add_argument("right", type=Path)
    parser.add_argument("--left-id", required=True)
    parser.add_argument("--right-id", required=True)
    parser.add_argument("--output", type=Path, default=Path("data/derived/alignment.json"))
    parser.add_argument(
        "--mapping",
        type=Path,
        help="Optional JSON array of reviewed mappings; each record has left/right reference arrays.",
    )
    args = parser.parse_args()

    left = parse_usfm_directory(args.left, args.left_id)
    right = parse_usfm_directory(args.right, args.right_id)
    if args.mapping:
        mapping_records = json.loads(args.mapping.read_text(encoding="utf-8"))
        if not isinstance(mapping_records, list):
            raise ValueError("mapping file must contain a JSON array")
        units = align_with_mappings(left, right, [mapping_from_dict(record) for record in mapping_records])
    else:
        units = align_segments(left, right)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps([unit.to_dict() for unit in units], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    counts: dict[str, int] = {}
    for unit in units:
        counts[unit.status] = counts.get(unit.status, 0) + 1
    print(json.dumps({"left": args.left_id, "right": args.right_id, "units": len(units), "statuses": counts}, indent=2))


if __name__ == "__main__":
    main()
