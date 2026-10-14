from __future__ import annotations

import hashlib
import json
import math
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence


class EmbeddingBackendUnavailable(RuntimeError):
    """Raised when the optional sentence-transformers backend is not installed."""


@dataclass(frozen=True)
class EmbeddingRun:
    model_id: str
    dimensions: int
    max_seq_length: int | None
    input_hash: str
    prefix: str
    model_revision: str = ""
    preprocessing_version: str = "1"
    cache_key: str | None = None
    cache_hit: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            "modelId": self.model_id,
            "dimensions": self.dimensions,
            "maxSeqLength": self.max_seq_length,
            "inputHash": self.input_hash,
            "prefix": self.prefix,
            "modelRevision": self.model_revision or self.model_id,
            "preprocessingVersion": self.preprocessing_version,
            "cacheKey": self.cache_key,
            "cacheHit": self.cache_hit,
        }


def input_hash(texts: Iterable[str]) -> str:
    digest = hashlib.sha256()
    for text in texts:
        digest.update(text.encode("utf-8"))
        digest.update(b"\0")
    return digest.hexdigest()


def embedding_cache_key(
    texts: Sequence[str],
    model_id: str,
    *,
    prefix: str = "query: ",
    model_revision: str | None = None,
    preprocessing_version: str = "1",
) -> str:
    """Return a stable key for one exact embedding input and recipe.

    The model identifier alone is not enough for reproducibility when a local
    directory is updated in place, so callers can provide an immutable model
    revision (for example a Hub commit hash). The preprocessing version must
    change whenever the input recipe changes.
    """

    payload = {
        "modelId": model_id,
        "modelRevision": model_revision or model_id,
        "preprocessingVersion": preprocessing_version,
        "prefix": prefix,
        "inputHash": input_hash(texts),
        "count": len(texts),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _cache_path(cache_dir: Path, key: str) -> Path:
    return cache_dir / f"embedding-{key}.json"


def _read_cached_embeddings(
    path: Path,
    *,
    key: str,
    texts: Sequence[str],
    model_id: str,
    prefix: str,
    model_revision: str,
    preprocessing_version: str,
) -> tuple[list[list[float]], EmbeddingRun] | None:
    """Read a cache entry only when every recipe field still matches."""

    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return None
    if not isinstance(document, dict) or document.get("schemaVersion") != 1:
        return None
    recipe = document.get("recipe")
    vectors = document.get("vectors")
    if not isinstance(recipe, dict) or not isinstance(vectors, list):
        return None
    expected = {
        "modelId": model_id,
        "modelRevision": model_revision,
        "preprocessingVersion": preprocessing_version,
        "prefix": prefix,
        "inputHash": input_hash(texts),
        "count": len(texts),
    }
    if recipe != expected or document.get("cacheKey") != key:
        return None
    normalized: list[list[float]] = []
    dimensions: int | None = None
    for vector in vectors:
        if not isinstance(vector, list) or not vector:
            return None
        try:
            row = [float(value) for value in vector]
        except (TypeError, ValueError):
            return None
        if dimensions is None:
            dimensions = len(row)
        if len(row) != dimensions:
            return None
        normalized.append(row)
    if len(normalized) != len(texts):
        return None
    metadata = document.get("embeddingRun")
    if not isinstance(metadata, dict):
        return None
    max_seq_length = metadata.get("maxSeqLength")
    if max_seq_length is not None and not isinstance(max_seq_length, int):
        return None
    return normalized, EmbeddingRun(
        model_id=model_id,
        dimensions=dimensions or 0,
        max_seq_length=max_seq_length,
        input_hash=expected["inputHash"],
        prefix=prefix,
        model_revision=model_revision,
        preprocessing_version=preprocessing_version,
        cache_key=key,
        cache_hit=True,
    )


def _write_cached_embeddings(
    path: Path,
    *,
    key: str,
    texts: Sequence[str],
    vectors: list[list[float]],
    run: EmbeddingRun,
) -> None:
    """Write a cache entry atomically so interrupted runs cannot poison it."""

    path.parent.mkdir(parents=True, exist_ok=True)
    document = {
        "schemaVersion": 1,
        "cacheKey": key,
        "recipe": {
            "modelId": run.model_id,
            "modelRevision": run.model_revision or run.model_id,
            "preprocessingVersion": run.preprocessing_version,
            "prefix": run.prefix,
            "inputHash": run.input_hash,
            "count": len(texts),
        },
        "embeddingRun": {
            "dimensions": run.dimensions,
            "maxSeqLength": run.max_seq_length,
        },
        "vectors": vectors,
    }
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(document, handle, ensure_ascii=False, separators=(",", ":"))
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, path)
    finally:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass


def embedding_storage_bytes(
    unit_count: int,
    edition_count: int,
    dimensions: int,
    *,
    bytes_per_value: int = 4,
) -> int:
    """Estimate raw dense-vector storage before metadata or compression."""

    if min(unit_count, edition_count, dimensions, bytes_per_value) < 0:
        raise ValueError("embedding storage dimensions must be non-negative")
    return unit_count * edition_count * dimensions * bytes_per_value


def cosine_distance(left: Sequence[float], right: Sequence[float]) -> float:
    if len(left) != len(right):
        raise ValueError("embedding dimensions do not match")
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0 or right_norm == 0:
        return 1.0
    similarity = sum(a * b for a, b in zip(left, right)) / (left_norm * right_norm)
    return round(max(0.0, min(2.0, 1.0 - similarity)), 6)


def encode_texts(
    texts: Sequence[str],
    model_id: str,
    *,
    batch_size: int = 32,
    prefix: str = "query: ",
    cache_dir: str | Path | None = None,
    model_revision: str | None = None,
    preprocessing_version: str = "1",
) -> tuple[list[list[float]], EmbeddingRun]:
    """Encode texts with sentence-transformers, kept optional by design."""

    if batch_size < 1:
        raise ValueError("batch_size must be positive")
    if not texts:
        raise ValueError("cannot encode an empty text sequence")
    resolved_model_revision = model_revision or model_id
    key = embedding_cache_key(
        texts,
        model_id,
        prefix=prefix,
        model_revision=resolved_model_revision,
        preprocessing_version=preprocessing_version,
    )
    path = _cache_path(Path(cache_dir), key) if cache_dir is not None else None
    if path is not None:
        cached = _read_cached_embeddings(
            path,
            key=key,
            texts=texts,
            model_id=model_id,
            prefix=prefix,
            model_revision=resolved_model_revision,
            preprocessing_version=preprocessing_version,
        )
        if cached is not None:
            return cached

    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as exc:
        raise EmbeddingBackendUnavailable(
            "sentence-transformers is not installed; install the optional "
            "embedding dependencies before running an embedding experiment"
        ) from exc

    model = SentenceTransformer(model_id)
    encoded = model.encode(
        [f"{prefix}{text}" for text in texts],
        batch_size=batch_size,
        normalize_embeddings=True,
        convert_to_numpy=True,
        show_progress_bar=True,
    )
    vectors = [[float(value) for value in row] for row in encoded.tolist()]
    max_seq_length = getattr(model, "max_seq_length", None)
    dimensions = len(vectors[0]) if vectors else 0
    run = EmbeddingRun(
        model_id=model_id,
        dimensions=dimensions,
        max_seq_length=int(max_seq_length) if max_seq_length is not None else None,
        input_hash=input_hash(texts),
        prefix=prefix,
        model_revision=resolved_model_revision,
        preprocessing_version=preprocessing_version,
        cache_key=key,
    )
    if path is not None:
        _write_cached_embeddings(path, key=key, texts=texts, vectors=vectors, run=run)
    return vectors, run
