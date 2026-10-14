#!/usr/bin/env python3
"""Build a JSON alignment report from downloaded USFM directories."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ghost_in_word.alignment import align_segments, align_with_mappings, mapping_from_dict
from ghost_in_word.mapping_review import bind_snapshot, validate_mapping_document
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
    parser.add_argument(
        "--mapping-report",
        type=Path,
        help="Optional path for the validated mapping report bound to both source snapshots.",
    )
    parser.add_argument(
        "--allow-unreviewed",
        action="store_true",
        help="Permit mapping records without reviewer, reviewType, and evidence fields for exploratory work.",
    )
    args = parser.parse_args()

    left = parse_usfm_directory(args.left, args.left_id)
    right = parse_usfm_directory(args.right, args.right_id)
    mapping_report = None
    if args.mapping:
        try:
            mapping_records = json.loads(args.mapping.read_text(encoding="utf-8"))
            mapping_report = validate_mapping_document(
                mapping_records,
                left,
                right,
                require_review=not args.allow_unreviewed,
            )
            mapping_report["mappingFile"] = {
                "path": str(args.mapping),
                "sha256": _sha256(args.mapping),
            }
            mapping_report["sources"] = {
                "left": bind_snapshot(args.left, args.left_id),
                "right": bind_snapshot(args.right, args.right_id),
            }
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            raise SystemExit(str(exc)) from exc
        units = align_with_mappings(left, right, [mapping_from_dict(record) for record in mapping_records])
    else:
        if args.mapping_report:
            raise SystemExit("--mapping-report requires --mapping")
        units = align_segments(left, right)
    if args.mapping_report and mapping_report is not None:
        args.mapping_report.parent.mkdir(parents=True, exist_ok=True)
        args.mapping_report.write_text(json.dumps(mapping_report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps([unit.to_dict() for unit in units], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    counts: dict[str, int] = {}
    for unit in units:
        counts[unit.status] = counts.get(unit.status, 0) + 1
    print(json.dumps({"left": args.left_id, "right": args.right_id, "units": len(units), "statuses": counts}, indent=2))


def _sha256(path: Path) -> str:
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()


if __name__ == "__main__":
    main()
