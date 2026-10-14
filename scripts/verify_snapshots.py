#!/usr/bin/env python3
"""Verify downloaded source directories against their snapshot inventories."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from snapshot_utils import verify_snapshot


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--edition", action="append", help="Edition ID from the manifest; repeat for multiple editions")
    parser.add_argument("--raw", type=Path, default=Path("data/raw"))
    parser.add_argument("--manifest", type=Path, default=Path("sources.json"))
    args = parser.parse_args()

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    available = {str(item["id"]) for item in manifest["editions"]}
    selected = args.edition or sorted(available)
    unknown = set(selected) - available
    if unknown:
        raise SystemExit(f"unknown edition(s): {', '.join(sorted(unknown))}")
    failures = {}
    for edition in selected:
        root = args.raw / edition
        try:
            problems = verify_snapshot(root)
        except (OSError, json.JSONDecodeError, KeyError) as exc:
            problems = [str(exc)]
        if problems:
            failures[edition] = problems
        else:
            print(json.dumps({"edition": edition, "verified": True}))
    if failures:
        print(json.dumps({"verified": False, "failures": failures}, indent=2))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
