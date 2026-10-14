#!/usr/bin/env python3
"""Add deterministic case-level bootstrap intervals to an existing report."""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    position = fraction * (len(ordered) - 1)
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return round(ordered[lower] + (ordered[upper] - ordered[lower]) * weight, 6)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("report", type=Path)
    parser.add_argument("--samples", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=20261014)
    args = parser.parse_args()
    if args.samples < 0:
        raise SystemExit("--samples must be non-negative")
    report = json.loads(args.report.read_text(encoding="utf-8"))
    cases = report.get("cases", [])
    bootstrap = {"samples": args.samples, "seed": args.seed, "unit": "challenge-case", "passRate95CI": None, "meanMargin95CI": None}
    if cases and args.samples:
        generator = random.Random(args.seed)
        outcomes = [1.0 if case["changedRanksFarther"] else 0.0 for case in cases]
        margins = [float(case["margin"]) for case in cases]
        rates = []
        means = []
        for _ in range(args.samples):
            sample = [generator.randrange(len(cases)) for _ in cases]
            rates.append(sum(outcomes[index] for index in sample) / len(sample))
            means.append(sum(margins[index] for index in sample) / len(sample))
        bootstrap["passRate95CI"] = [percentile(rates, 0.025), percentile(rates, 0.975)]
        bootstrap["meanMargin95CI"] = [percentile(means, 0.025), percentile(means, 0.975)]
    report["bootstrap"] = bootstrap
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(bootstrap, indent=2))


if __name__ == "__main__":
    main()
