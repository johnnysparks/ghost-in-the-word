#!/usr/bin/env python3
"""Aggregate independent mapping reviews and emit approved mappings."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ghost_in_word.mapping_review import summarize_mapping_reviews, validate_mapping_review_packet


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("reviews", nargs="+", type=Path)
    parser.add_argument("--packet", type=Path, required=True)
    parser.add_argument("--mapping-candidates", type=Path, required=True, help="Private candidate mapping JSON used to preserve status and method")
    parser.add_argument("--output", type=Path, required=True, help="Mapping review report")
    parser.add_argument("--mapping-output", type=Path, required=True, help="Approved mapping JSON array")
    parser.add_argument("--minimum-reviewers", type=int, default=2)
    args = parser.parse_args()
    if args.minimum_reviewers < 2:
        raise SystemExit("--minimum-reviewers must be at least 2")

    packet = json.loads(args.packet.read_text(encoding="utf-8"))
    validate_mapping_review_packet(packet)
    candidate_records = json.loads(args.mapping_candidates.read_text(encoding="utf-8"))
    documents = [json.loads(path.read_text(encoding="utf-8")) for path in args.reviews]
    report = summarize_mapping_reviews(
        documents,
        packet=packet,
        candidate_records=candidate_records,
        minimum_reviewers=args.minimum_reviewers,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.mapping_output.parent.mkdir(parents=True, exist_ok=True)
    args.mapping_output.write_text(json.dumps(report["approvedMappings"], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "mappingOutput": str(args.mapping_output), "gate": report["gate"], "approvedMappingCount": report["approvedMappingCount"]}, indent=2))


if __name__ == "__main__":
    main()
