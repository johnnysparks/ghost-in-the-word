from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Edition:
    id: str
    name: str
    language: str
    source: str
    download: str
    format: str
    license: str
    canon: str


@dataclass(frozen=True)
class TextSegment:
    """A displayable, source-addressed unit from one translation."""

    edition_id: str
    book: str
    chapter: int
    verse: str
    text: str
    source_file: str = ""

    @property
    def key(self) -> tuple[str, int, str]:
        return (self.book, self.chapter, self.verse)

    @property
    def reference(self) -> str:
        return f"{self.book} {self.chapter}:{self.verse}"
