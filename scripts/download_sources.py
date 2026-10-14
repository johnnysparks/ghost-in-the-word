#!/usr/bin/env python3
"""Download and unpack pinned edition sources from sources.json."""

from __future__ import annotations

import argparse
import json
import urllib.request
import zipfile
from pathlib import Path


def shutil_copyfileobj(source, destination, length: int = 1024 * 1024) -> None:
    """Copy a response without depending on a third-party HTTP client."""

    while True:
        chunk = source.read(length)
        if not chunk:
            return
        destination.write(chunk)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--edition", choices={"webp", "bsb", "asv"}, action="append")
    parser.add_argument("--output", type=Path, default=Path("data/raw"))
    args = parser.parse_args()

    manifest = json.loads(Path("sources.json").read_text(encoding="utf-8"))
    selected = set(args.edition or [item["id"] for item in manifest["editions"]])
    for edition in manifest["editions"]:
        if edition["id"] not in selected:
            continue
        target = args.output / edition["id"]
        if target.exists():
            raise SystemExit(f"refusing to overwrite existing directory: {target}")
        args.output.mkdir(parents=True, exist_ok=True)
        archive = args.output / f".{edition['id']}.source.zip"
        print(f"downloading {edition['id']} from {edition['download']}")
        request = urllib.request.Request(
            edition["download"],
            headers={"User-Agent": "ghost-in-the-word/0.1 (corpus-ingestion)"},
        )
        with urllib.request.urlopen(request, timeout=60) as response, archive.open("wb") as output:
            shutil_copyfileobj(response, output)
        target.mkdir(parents=True, exist_ok=False)
        with zipfile.ZipFile(archive) as zipped:
            zipped.extractall(target)
        archive.unlink()
        print(f"wrote {target}")


if __name__ == "__main__":
    main()
