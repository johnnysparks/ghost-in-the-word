"""Data primitives for the Ghost in the Word corpus pipeline."""

from .alignment import AlignmentMapping, AlignmentUnit, align_segments, align_with_mappings, mapping_from_dict, parse_reference
from .embeddings import EmbeddingBackendUnavailable, EmbeddingRun, cosine_distance, encode_texts, input_hash
from .models import Edition, TextSegment
from .scoring import lexical_distance, score_units, tokenize, wording_distance
from .summary import summarize_units
from .usfm import parse_usfm

__all__ = [
    "AlignmentUnit",
    "AlignmentMapping",
    "Edition",
    "EmbeddingBackendUnavailable",
    "EmbeddingRun",
    "TextSegment",
    "align_segments",
    "align_with_mappings",
    "cosine_distance",
    "encode_texts",
    "input_hash",
    "lexical_distance",
    "mapping_from_dict",
    "parse_usfm",
    "parse_reference",
    "score_units",
    "summarize_units",
    "tokenize",
    "wording_distance",
]
