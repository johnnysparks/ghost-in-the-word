"""Data primitives for the Ghost in the Word corpus pipeline."""

from .alignment import AlignmentMapping, AlignmentUnit, alignment_method, align_segments, align_with_mappings, mapping_from_dict, parse_reference
from .assessment import Assessment, validate_assessment_document
from .assessment_attachment import attach_assessment_document
from .embeddings import EmbeddingBackendUnavailable, EmbeddingRun, cosine_distance, encode_texts, input_hash
from .models import Edition, TextSegment
from .matrix import build_translation_matrix
from .review import build_review_key, select_natural_benchmark, select_review_items, summarize_reviews, validate_review_packet
from .reference import ReferenceEstimate, distance_to_reference, estimate_reference
from .scoring import lexical_distance, score_units, tokenize, wording_distance
from .sources import comparison_edition_metadata, edition_to_dict, load_editions
from .summary import summarize_units
from .usfm import parse_usfm
from .windows import build_windows

__all__ = [
    "AlignmentUnit",
    "AlignmentMapping",
    "Assessment",
    "Edition",
    "EmbeddingBackendUnavailable",
    "EmbeddingRun",
    "ReferenceEstimate",
    "TextSegment",
    "build_translation_matrix",
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
    "select_natural_benchmark",
    "build_review_key",
    "score_units",
    "summarize_units",
    "summarize_reviews",
    "validate_review_packet",
    "tokenize",
    "wording_distance",
    "validate_assessment_document",
    "attach_assessment_document",
    "edition_to_dict",
    "comparison_edition_metadata",
    "load_editions",
    "build_windows",
]
