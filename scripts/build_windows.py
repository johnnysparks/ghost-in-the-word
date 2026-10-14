#!/usr/bin/env python3
"""Build a separate lexical comparison artifact for multi-verse windows."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ghost_in_word.summary import summarize_units
from ghost_in_word.windows import build_windows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("comparison", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--window-size", type=int, default=2)
    parser.add_argument("--stride", type=int)
    args = parser.parse_args()

    comparison = json.loads(args.comparison.read_text(encoding="utf-8"))
    units = build_windows(comparison["units"], window_size=args.window_size, stride=args.stride)
    metadata = dict(comparison["metadata"])
    metadata["scope"] = {"books": sorted({str(unit["book"]) for unit in units}), "unit": "multi-verse-window"}
    metadata["metric"] = {
        "id": "lexical-window-baseline",
        "label": f"Lexical baseline · {args.window_size}-verse windows",
        "distanceField": "lexicalDistance",
        "wordingField": "wordingDistance",
        "description": "Character n-gram cosine distance over explicitly joined multi-verse windows. This is separate from verse-level scoring.",
    }
    summary = summarize_units(units, "lexicalDistance")["overall"]
    output = {
        "schemaVersion": comparison["schemaVersion"],
        "metadata": metadata,
        "units": units,
        "summary": {
            "totalUnits": summary["totalUnits"],
            "matchedUnits": summary["matchedUnits"],
            "scoredUnits": summary["scoredUnits"],
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "summary": output["summary"], "stride": args.stride or args.window_size}, indent=2))


if __name__ == "__main__":
    main()
