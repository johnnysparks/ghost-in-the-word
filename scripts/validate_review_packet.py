#!/usr/bin/env python3
"""Validate a score-blinded natural-review packet."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ghost_in_word.review import validate_review_packet


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("packet", type=Path)
    args = parser.parse_args()
    packet = json.loads(args.packet.read_text(encoding="utf-8"))
    print(json.dumps(validate_review_packet(packet), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
