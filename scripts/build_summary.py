#!/usr/bin/env python3
"""Build book and chapter summaries for a comparison artifact."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ghost_in_word.summary import summarize_units


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("comparison", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    comparison = json.loads(args.comparison.read_text(encoding="utf-8"))
    metric = comparison["metadata"]["metric"]
    summary = summarize_units(comparison["units"], metric["distanceField"])
    output = {
        "schemaVersion": comparison["schemaVersion"],
        "comparison": {
            "leftEdition": comparison["metadata"]["leftEdition"],
            "rightEdition": comparison["metadata"]["rightEdition"],
            "metric": metric,
            "scope": comparison["metadata"]["scope"],
        },
        "summary": summary,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "overall": summary["overall"], "books": len(summary["books"]), "chapters": len(summary["chapters"])}, indent=2))


if __name__ == "__main__":
    main()
