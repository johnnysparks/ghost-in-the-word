#!/usr/bin/env python3
"""Validate a reviewed mapping against two pinned USFM snapshots."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from ghost_in_word.mapping_review import validate_mapping_document
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
    args = parser.parse_args()

    left = parse_usfm_directory(args.left, args.left_id)
    right = parse_usfm_directory(args.right, args.right_id)
    records = json.loads(args.mapping.read_text(encoding="utf-8"))
    report = validate_mapping_document(records, left, right, require_review=not args.allow_unreviewed)
    report["mappingFile"] = {
        "path": str(args.mapping),
        "sha256": hashlib.sha256(args.mapping.read_bytes()).hexdigest(),
    }
    report["sources"] = {
        "left": _snapshot_binding(args.left, args.left_id),
        "right": _snapshot_binding(args.right, args.right_id),
    }
    encoded = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
    print(encoded, end="")


def _snapshot_binding(root: Path, edition_id: str) -> dict[str, object]:
    path = root / "snapshot.json"
    if not path.is_file():
        raise SystemExit(f"missing source snapshot inventory: {path}")
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"could not read source snapshot inventory {path}: {exc}") from exc
    if document.get("edition") != edition_id or not document.get("directorySha256"):
        raise SystemExit(f"source snapshot inventory does not bind to edition {edition_id}: {path}")
    return {
        "edition": edition_id,
        "path": str(path),
        "directorySha256": document["directorySha256"],
        "fileCount": len(document.get("files", [])) if isinstance(document.get("files"), list) else None,
    }


if __name__ == "__main__":
    main()
