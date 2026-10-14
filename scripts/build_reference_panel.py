#!/usr/bin/env python3
"""Build an offline latent-reference artifact from per-passage vectors.

Input format:

{
  "schemaVersion": 1,
  "metadata": {"model": "...", "panel": ["webp", "bsb", "asv"]},
  "passages": [
    {"id": "JHN-1-1", "reference": "JHN 1:1",
     "vectors": {"webp": [0.1, 0.2], "bsb": [0.1, 0.19]}}
  ]
}

The command intentionally keeps vectors and diagnostics offline. It does not
write a browser faithfulness score.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ghost_in_word.reference import estimate_reference


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("panel", type=Path, help="JSON vector-panel artifact")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--exclude", action="append", default=[], help="Edition to leave out of the reference panel; repeatable")
    parser.add_argument("--weight", action="append", default=[], metavar="EDITION=WEIGHT", help="Base edition weight; repeatable")
    parser.add_argument("--family", action="append", default=[], metavar="EDITION=FAMILY", help="Related-family assignment; repeatable")
    parser.add_argument("--family-cap", type=float, default=1.0, help="Maximum combined weight per named family")
    args = parser.parse_args()

    source = json.loads(args.panel.read_text(encoding="utf-8"))
    passages = source.get("passages") if isinstance(source, dict) else None
    if not isinstance(passages, list):
        raise SystemExit("panel input must contain a passages array")
    weights = _parse_assignments(args.weight, float, "weight")
    families = _parse_assignments(args.family, str, "family")
    output_passages: list[dict[str, object]] = []
    estimated = 0
    insufficient = 0
    unresolved = 0
    for passage in passages:
        if not isinstance(passage, dict) or not isinstance(passage.get("vectors"), dict):
            raise SystemExit("each passage must contain a vectors object")
        vectors = passage["vectors"]
        try:
            estimate = estimate_reference(
                {str(edition): vector for edition, vector in vectors.items()},
                exclude=args.exclude,
                weights=weights,
                families=families,
                family_cap=args.family_cap,
            )
        except ValueError as exc:
            unresolved += 1
            output_passages.append(
                {
                    "id": passage.get("id"),
                    "reference": passage.get("reference"),
                    "status": "unresolved",
                    "reason": str(exc),
                    "availableEditions": sorted(str(edition) for edition in vectors),
                }
            )
            continue
        status = "estimated" if len(estimate.included_editions) >= 2 else "insufficient-panel"
        if status == "estimated":
            estimated += 1
        else:
            insufficient += 1
        record: dict[str, object] = {
            "id": passage.get("id"),
            "reference": passage.get("reference"),
            "status": status,
            "panelSize": len(estimate.included_editions),
        }
        record.update(estimate.to_dict())
        output_passages.append(record)

    metadata = source.get("metadata", {}) if isinstance(source, dict) else {}
    output = {
        "schemaVersion": 1,
        "metadata": {
            "source": str(args.panel),
            "model": metadata.get("model"),
            "embeddingRuns": metadata.get("embeddingRuns", {}),
            "referenceMethod": "normalized-weighted-panel-centroid",
            "medoidMethod": "minimum-weighted-pairwise-cosine-distance",
            "excludedEditions": sorted(args.exclude),
            "weights": weights,
            "families": families,
            "familyCap": args.family_cap,
            "interpretation": "Panel-relative representation; distance is not a faithfulness grade.",
        },
        "passages": output_passages,
        "summary": {"totalPassages": len(output_passages), "estimated": estimated, "insufficientPanel": insufficient, "unresolved": unresolved},
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "summary": output["summary"]}, indent=2))


def _parse_assignments(values: list[str], value_type: type, label: str) -> dict[str, object]:
    parsed: dict[str, object] = {}
    for value in values:
        edition, separator, assignment = value.partition("=")
        if not separator or not edition or not assignment:
            raise SystemExit(f"{label} must use EDITION=VALUE syntax")
        if edition in parsed:
            raise SystemExit(f"duplicate {label} for edition {edition}")
        try:
            parsed[edition] = value_type(assignment)
        except ValueError as exc:
            raise SystemExit(f"invalid {label} for {edition}: {assignment}") from exc
    return parsed


if __name__ == "__main__":
    main()
