#!/usr/bin/env python3
"""Validate a reviewed mapping against two pinned USFM snapshots."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from ghost_in_word.mapping_review import bind_snapshot, validate_mapping_document
from ghost_in_word.usfm import parse_usfm_directory


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("left", type=Path)
    parser.add_argument("right", type=Path)
    parser.add_argument("mapping", type=Path)
    parser.add_argument("--left-id", required=True)
    parser.add_argument("--right-id", required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--allow-unreviewed",
        action="store_true",
        help="Permit mapping records without reviewer, reviewType, and evidence fields",
    )
    parser.add_argument(
        "--require-independent",
        action="store_true",
        help="Require at least two distinct declared reviewers on every mapping record",
    )
    args = parser.parse_args()

    left = parse_usfm_directory(args.left, args.left_id)
    right = parse_usfm_directory(args.right, args.right_id)
    records = json.loads(args.mapping.read_text(encoding="utf-8"))
    if args.require_independent and args.allow_unreviewed:
        raise SystemExit("--require-independent cannot be combined with --allow-unreviewed")
    report = validate_mapping_document(
        records,
        left,
        right,
        require_review=not args.allow_unreviewed,
        require_independent_review=args.require_independent,
    )
    report["mappingFile"] = {
        "path": str(args.mapping),
        "sha256": hashlib.sha256(args.mapping.read_bytes()).hexdigest(),
    }
    report["sources"] = {
        "left": bind_snapshot(args.left, args.left_id),
        "right": bind_snapshot(args.right, args.right_id),
    }
    encoded = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
    print(encoded, end="")


if __name__ == "__main__":
    main()
