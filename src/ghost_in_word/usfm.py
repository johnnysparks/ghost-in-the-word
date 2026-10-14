from __future__ import annotations

import re
from pathlib import Path

from .models import TextSegment

_BOOK = re.compile(r"\\id\s+(\S+)")
_CHAPTER = re.compile(r"\\c\s+(\d+)")
_VERSE = re.compile(r"\\v\s+([0-9]+(?:-[0-9]+)?)\s*(.*?)(?=\s\\v\s+|$)")
_WORD_MARKER = re.compile(r"\\\+?w\s*([^|\\]*?)\|[^\\]*?\\\+?w\*", re.DOTALL)
_INLINE_MARKER = re.compile(r"\\\+?(?:add|bd|bdit|it|nd|no|pn|qt|rq|sc|tl|wj|em|k|sig)\*?|\\\+?[a-z0-9]+\s*")
_NOTE = re.compile(r"\\(?:f|x)\s.*?\\(?:f|x)\*", re.DOTALL)
_WHITESPACE = re.compile(r"\s+")


def _clean_text(text: str) -> str:
    """Remove USFM display markup while preserving the visible words."""

    text = _NOTE.sub(" ", text)
    text = _WORD_MARKER.sub(r"\1", text)
    text = _INLINE_MARKER.sub("", text)
    text = text.replace("\\", "")
    return _WHITESPACE.sub(" ", text).strip()


def _extract_notes(text: str) -> tuple[str, ...]:
    notes = []
    for note in _NOTE.findall(text):
        without_open = re.sub(r"^\\(?:f|x)\s*", "", note)
        without_close = re.sub(r"\\(?:f|x)\*\s*$", "", without_open)
        cleaned = _clean_text(re.sub(r"^\+\s*", "", without_close))
        if cleaned:
            notes.append(cleaned)
    return tuple(notes)


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
    current_verse: str | None = None
    current_parts: list[str] = []

    def flush_current() -> None:
        nonlocal current_verse, current_parts
        if current_verse is None or not book or chapter is None:
            current_verse = None
            current_parts = []
            return
        raw_text = " ".join(part for part in current_parts if part)
        segments.append(
            TextSegment(
                edition_id=edition_id,
                book=book,
                chapter=chapter,
                verse=current_verse,
                text=_clean_text(raw_text),
                source_file=source_path.name,
                notes=_extract_notes(raw_text),
            )
        )
        current_verse = None
        current_parts = []

    for raw_line in source_path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        book_match = _BOOK.search(line)
        if book_match:
            flush_current()
            book = book_match.group(1).upper()
            continue
        chapter_match = _CHAPTER.search(line)
        if chapter_match:
            flush_current()
            chapter = int(chapter_match.group(1))
            continue
        verse_matches = list(_VERSE.finditer(line))
        if verse_matches and book and chapter is not None:
            for verse_match in verse_matches:
                flush_current()
                current_verse = verse_match.group(1)
                verse_text = verse_match.group(2).strip()
                if verse_text:
                    current_parts.append(verse_text)
            continue
        # Some valid USFM sources put the verse marker on its own line and
        # place each word (often a \w field) on following lines. Keep those
        # continuation lines with the open verse until the next marker.
        if current_verse is not None:
            current_parts.append(line)

    flush_current()
    return segments


def parse_usfm_directory(directory: str | Path, edition_id: str) -> list[TextSegment]:
    """Parse all likely USFM files in a directory in stable filename order."""

    root = Path(directory)
    paths = sorted(p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in {".sfm", ".usfm", ".usx", ".txt"})
    segments: list[TextSegment] = []
    for path in paths:
        segments.extend(parse_usfm(path, edition_id))
    return segments
