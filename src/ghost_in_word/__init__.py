"""Data primitives for the Ghost in the Word corpus pipeline."""

from .alignment import AlignmentUnit, align_segments
from .embeddings import EmbeddingBackendUnavailable, EmbeddingRun, cosine_distance, encode_texts, input_hash
from .models import Edition, TextSegment
from .scoring import lexical_distance, score_units, tokenize, wording_distance
from .summary import summarize_units
from .usfm import parse_usfm

__all__ = [
    "AlignmentUnit",
    "Edition",
    "EmbeddingBackendUnavailable",
    "EmbeddingRun",
    "TextSegment",
    "align_segments",
    "cosine_distance",
    "encode_texts",
    "input_hash",
    "lexical_distance",
    "parse_usfm",
    "score_units",
    "summarize_units",
    "tokenize",
    "wording_distance",
]
