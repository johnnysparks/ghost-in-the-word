from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
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

    def to_dict(self) -> dict[str, object]:
        return {
            "modelId": self.model_id,
            "dimensions": self.dimensions,
            "maxSeqLength": self.max_seq_length,
            "inputHash": self.input_hash,
            "prefix": self.prefix,
        }


def input_hash(texts: Iterable[str]) -> str:
    digest = hashlib.sha256()
    for text in texts:
        digest.update(text.encode("utf-8"))
        digest.update(b"\0")
    return digest.hexdigest()


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
) -> tuple[list[list[float]], EmbeddingRun]:
    """Encode texts with sentence-transformers, kept optional by design."""

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
    return vectors, EmbeddingRun(
        model_id=model_id,
        dimensions=dimensions,
        max_seq_length=int(max_seq_length) if max_seq_length is not None else None,
        input_hash=input_hash(texts),
        prefix=prefix,
    )
