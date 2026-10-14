#!/usr/bin/env python3
"""Build a panel distance matrix from pairwise comparison JSON artifacts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ghost_in_word.matrix import build_translation_matrix


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("comparisons", nargs="+", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--book", action="append", help="Restrict the matrix to one or more book IDs")
    args = parser.parse_args()

    comparisons = [json.loads(path.read_text(encoding="utf-8")) for path in args.comparisons]
    matrix = build_translation_matrix(comparisons, books=args.book)
    matrix["metadata"]["sourceArtifacts"] = [str(path) for path in args.comparisons]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(matrix, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "summary": matrix["summary"]}, indent=2))


if __name__ == "__main__":
    main()
