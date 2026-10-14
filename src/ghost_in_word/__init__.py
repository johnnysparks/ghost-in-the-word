"""Data primitives for the Ghost in the Word corpus pipeline."""

from .alignment import AlignmentMapping, AlignmentUnit, alignment_method, align_segments, align_with_mappings, mapping_from_dict, parse_reference
from .embeddings import EmbeddingBackendUnavailable, EmbeddingRun, cosine_distance, encode_texts, input_hash
from .models import Edition, TextSegment
from .review import select_review_items, summarize_reviews
from .reference import ReferenceEstimate, distance_to_reference, estimate_reference
from .scoring import lexical_distance, score_units, tokenize, wording_distance
from .summary import summarize_units
from .usfm import parse_usfm
from .windows import build_windows

__all__ = [
    "AlignmentUnit",
    "AlignmentMapping",
    "Edition",
    "EmbeddingBackendUnavailable",
    "EmbeddingRun",
    "ReferenceEstimate",
    "TextSegment",
    "align_segments",
    "align_with_mappings",
    "alignment_method",
    "cosine_distance",
    "encode_texts",
    "input_hash",
    "estimate_reference",
    "distance_to_reference",
    "lexical_distance",
    "mapping_from_dict",
    "parse_usfm",
    "parse_reference",
    "select_review_items",
    "score_units",
    "summarize_units",
    "summarize_reviews",
    "tokenize",
    "wording_distance",
    "build_windows",
]
