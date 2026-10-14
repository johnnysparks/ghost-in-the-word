"""Helpers for content-addressed source-directory snapshots."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Mapping

SNAPSHOT_NAME = "snapshot.json"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def snapshot_directory(
    root: Path,
    edition: Mapping[str, object],
    *,
    archive_sha256: str | None = None,
    archive_bytes: int | None = None,
) -> dict[str, object]:
    files: list[dict[str, object]] = []
    for path in sorted(item for item in root.rglob("*") if item.is_file() and item.name != SNAPSHOT_NAME):
        relative = path.relative_to(root).as_posix()
        files.append({"path": relative, "bytes": path.stat().st_size, "sha256": sha256_file(path)})

    directory_digest = hashlib.sha256()
    for item in files:
        directory_digest.update(str(item["path"]).encode("utf-8"))
        directory_digest.update(b"\0")
        directory_digest.update(str(item["sha256"]).encode("ascii"))
        directory_digest.update(b"\n")
    return {
        "schemaVersion": 1,
        "edition": edition["id"],
        "source": edition.get("source"),
        "download": edition.get("download"),
        "directorySha256": directory_digest.hexdigest(),
        "files": files,
        "archive": {"sha256": archive_sha256, "bytes": archive_bytes} if archive_sha256 else None,
    }


def write_snapshot(root: Path, snapshot: Mapping[str, object]) -> Path:
    path = root / SNAPSHOT_NAME
    path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def verify_snapshot(root: Path) -> list[str]:
    snapshot_path = root / SNAPSHOT_NAME
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    problems: list[str] = []
    expected_files = {str(item["path"]): item for item in snapshot.get("files", [])}
    actual_files = {
        path.relative_to(root).as_posix(): path
        for path in root.rglob("*")
        if path.is_file() and path.name != SNAPSHOT_NAME
    }
    for relative in sorted(set(expected_files) - set(actual_files)):
        problems.append(f"missing file: {relative}")
    for relative in sorted(set(actual_files) - set(expected_files)):
        problems.append(f"unexpected file: {relative}")
    for relative in sorted(set(expected_files) & set(actual_files)):
        path = actual_files[relative]
        expected = expected_files[relative]
        actual_hash = sha256_file(path)
        if actual_hash != expected.get("sha256"):
            problems.append(f"hash mismatch: {relative}")
        if path.stat().st_size != expected.get("bytes"):
            problems.append(f"size mismatch: {relative}")
    return problems
