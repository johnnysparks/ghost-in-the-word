#!/usr/bin/env python3
"""Validate and summarize source-conditioned assessment records."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ghost_in_word.assessment import validate_assessment_document


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("document", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    document = json.loads(args.document.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise SystemExit("assessment document must be a JSON object")
    normalized = validate_assessment_document(document)
    encoded = json.dumps(normalized, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
    print(encoded, end="")


if __name__ == "__main__":
    main()
