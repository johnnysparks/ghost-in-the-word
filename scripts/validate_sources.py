#!/usr/bin/env python3
"""Validate a traceable source-edition manifest."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ghost_in_word.sources import edition_to_dict, load_editions


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path, nargs="?", default=Path("sources.json"))
    args = parser.parse_args()
    editions = load_editions(args.manifest)
    roles: dict[str, int] = {}
    for edition in editions.values():
        roles[edition.role] = roles.get(edition.role, 0) + 1
    print(json.dumps({"manifest": str(args.manifest), "editions": [edition_to_dict(item) for item in editions.values()], "roles": roles}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
