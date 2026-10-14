from __future__ import annotations

import re
from pathlib import Path

from .models import TextSegment

_BOOK = re.compile(r"\\id\s+(\S+)")
_CHAPTER = re.compile(r"\\c\s+(\d+)")
_VERSE = re.compile(r"\\v\s+([0-9]+(?:-[0-9]+)?)\s*(.*?)(?=\s\\v\s+|$)")
_WORD_MARKER = re.compile(r"\\w\s*([^|\\]*?)\|[^\\]*?\\w\*", re.DOTALL)
_INLINE_MARKER = re.compile(r"\\(?:add|bd|bdit|it|nd|no|pn|qt|rq|sc|tl|wj|em|k|sig)\*?|\\[a-z0-9]+\s*")
_NOTE = re.compile(r"\\(?:f|x)\s.*?\\(?:f|x)\*", re.DOTALL)
_WHITESPACE = re.compile(r"\s+")


def _clean_text(text: str) -> str:
    """Remove USFM display markup while preserving the visible words."""

    text = _NOTE.sub(" ", text)
    text = _WORD_MARKER.sub(r"\1", text)
    text = _INLINE_MARKER.sub("", text)
    text = text.replace("\\", "")
    return _WHITESPACE.sub(" ", text).strip()


def parse_usfm(path: str | Path, edition_id: str) -> list[TextSegment]:
    """Parse verse records from one USFM file.

    This deliberately handles the common verse-per-line form used by the
    initial eBible and Berean downloads. Unsupported or malformed markers are
    ignored rather than guessed; the source file is retained on each segment.
    """

    source_path = Path(path)
    book = ""
    chapter: int | None = None
    segments: list[TextSegment] = []

    for raw_line in source_path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        book_match = _BOOK.search(line)
        if book_match:
            book = book_match.group(1).upper()
            continue
        chapter_match = _CHAPTER.search(line)
        if chapter_match:
            chapter = int(chapter_match.group(1))
            continue
        verse_matches = list(_VERSE.finditer(line))
        if not verse_matches or not book or chapter is None:
            continue
        for verse_match in verse_matches:
            segments.append(
                TextSegment(
                    edition_id=edition_id,
                    book=book,
                    chapter=chapter,
                    verse=verse_match.group(1),
                    text=_clean_text(verse_match.group(2)),
                    source_file=source_path.name,
                )
            )

    return segments


def parse_usfm_directory(directory: str | Path, edition_id: str) -> list[TextSegment]:
    """Parse all likely USFM files in a directory in stable filename order."""

    root = Path(directory)
    paths = sorted(p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in {".sfm", ".usfm", ".usx", ".txt"})
    segments: list[TextSegment] = []
    for path in paths:
        segments.extend(parse_usfm(path, edition_id))
    return segments
