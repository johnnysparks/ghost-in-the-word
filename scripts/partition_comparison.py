#!/usr/bin/env python3
"""Partition a comparison artifact into one browser payload per book."""

from __future__ import annotations

import argparse
import copy
import json
from collections import defaultdict
from pathlib import Path

from ghost_in_word.summary import summarize_units

BOOK_NAMES = {
    "GEN": "Genesis", "EXO": "Exodus", "LEV": "Leviticus", "NUM": "Numbers", "DEU": "Deuteronomy",
    "JOS": "Joshua", "JDG": "Judges", "RUT": "Ruth", "1SA": "1 Samuel", "2SA": "2 Samuel",
    "1KI": "1 Kings", "2KI": "2 Kings", "1CH": "1 Chronicles", "2CH": "2 Chronicles", "EZR": "Ezra",
    "NEH": "Nehemiah", "EST": "Esther", "JOB": "Job", "PSA": "Psalms", "PRO": "Proverbs",
    "ECC": "Ecclesiastes", "SNG": "Song of Solomon", "ISA": "Isaiah", "JER": "Jeremiah", "LAM": "Lamentations",
    "EZK": "Ezekiel", "DAN": "Daniel", "HOS": "Hosea", "JOL": "Joel", "AMO": "Amos", "OBA": "Obadiah",
    "JON": "Jonah", "MIC": "Micah", "NAM": "Nahum", "HAB": "Habakkuk", "ZEP": "Zephaniah", "HAG": "Haggai",
    "ZEC": "Zechariah", "MAL": "Malachi", "MAT": "Matthew", "MRK": "Mark", "LUK": "Luke", "JHN": "John",
    "ACT": "Acts", "ROM": "Romans", "1CO": "1 Corinthians", "2CO": "2 Corinthians", "GAL": "Galatians",
    "EPH": "Ephesians", "PHP": "Philippians", "COL": "Colossians", "1TH": "1 Thessalonians", "2TH": "2 Thessalonians",
    "1TI": "1 Timothy", "2TI": "2 Timothy", "TIT": "Titus", "PHM": "Philemon", "HEB": "Hebrews", "JAS": "James",
    "1PE": "1 Peter", "2PE": "2 Peter", "1JN": "1 John", "2JN": "2 John", "3JN": "3 John", "JUD": "Jude", "REV": "Revelation",
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("comparison", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    comparison = json.loads(args.comparison.read_text(encoding="utf-8"))
    distance_field = comparison["metadata"]["metric"]["distanceField"]
    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    for unit in comparison["units"]:
        grouped[str(unit["book"])].append(unit)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    books = []
    for book, units in grouped.items():
        metadata = copy.deepcopy(comparison["metadata"])
        metadata["scope"] = {"books": [book], "unit": "verse"}
        summary = summarize_units(units, distance_field)["overall"]
        payload = {
            "schemaVersion": comparison["schemaVersion"],
            "metadata": metadata,
            "units": units,
            "summary": {
                "totalUnits": summary["totalUnits"],
                "matchedUnits": summary["matchedUnits"],
                "scoredUnits": summary["scoredUnits"],
            },
        }
        filename = f"{book}.json"
        (args.output_dir / filename).write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
        books.append({
            "id": book,
            "name": BOOK_NAMES.get(book, book),
            "dataUrl": f"/data/{args.output_dir.name}/{filename}",
            "totalUnits": summary["totalUnits"],
            "matchedUnits": summary["matchedUnits"],
            "coverage": summary["coverage"],
        })

    manifest = {
        "schemaVersion": comparison["schemaVersion"],
        "kind": "comparison-partition-manifest",
        "comparison": {
            "leftEdition": comparison["metadata"]["leftEdition"],
            "rightEdition": comparison["metadata"]["rightEdition"],
            "metric": comparison["metadata"]["metric"],
            "alignment": comparison["metadata"]["alignment"],
            "scope": {"books": [book["id"] for book in books], "unit": "verse"},
        },
        "summary": comparison["summary"],
        "books": books,
    }
    book_order = {book: index for index, book in enumerate(BOOK_NAMES)}
    manifest["books"].sort(key=lambda book: (book_order.get(book["id"], len(book_order)), book["id"]))
    (args.output_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output_dir), "books": len(books), "units": sum(book["totalUnits"] for book in books)}, indent=2))


if __name__ == "__main__":
    main()
