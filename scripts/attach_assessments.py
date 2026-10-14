#!/usr/bin/env python3
"""Attach a validated source-conditioned assessment document to a comparison."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ghost_in_word.assessment_attachment import attach_assessment_document


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("comparison", type=Path)
    parser.add_argument("assessments", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    comparison = json.loads(args.comparison.read_text(encoding="utf-8"))
    assessments = json.loads(args.assessments.read_text(encoding="utf-8"))
    if not isinstance(comparison, dict) or not isinstance(assessments, dict):
        raise SystemExit("comparison and assessment inputs must be JSON objects")
    output = attach_assessment_document(comparison, assessments, source_document=str(args.assessments))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "assessmentAttachment": output["metadata"]["assessmentAttachment"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
