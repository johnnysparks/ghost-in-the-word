#!/usr/bin/env python3
"""Record content hashes for already downloaded source directories."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from snapshot_utils import snapshot_directory, write_snapshot


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--edition", action="append", help="Edition ID from the manifest; repeat for multiple editions")
    parser.add_argument("--raw", type=Path, default=Path("data/raw"))
    parser.add_argument("--manifest", type=Path, default=Path("sources.json"))
    parser.add_argument("--output", type=Path, default=Path("source_snapshots.json"))
    args = parser.parse_args()

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    available = {str(item["id"]) for item in manifest["editions"]}
    selected = set(args.edition or available)
    unknown = selected - available
    if unknown:
        raise SystemExit(f"unknown edition(s): {', '.join(sorted(unknown))}")
    snapshots: dict[str, object] = {}
    for edition in manifest["editions"]:
        if edition["id"] not in selected:
            continue
        root = args.raw / edition["id"]
        if not root.is_dir():
            raise SystemExit(f"source directory does not exist: {root}")
        snapshot = snapshot_directory(root, edition)
        path = write_snapshot(root, snapshot)
        snapshots[str(edition["id"])] = snapshot
        print(json.dumps({"edition": edition["id"], "directorySha256": snapshot["directorySha256"], "files": len(snapshot["files"]), "output": str(path)}, indent=2))
    args.output.write_text(json.dumps({"schemaVersion": 1, "snapshots": snapshots}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"manifest": str(args.output), "editions": sorted(snapshots)}))


if __name__ == "__main__":
    main()
