import tempfile
import unittest
import json
import sys
import types
from pathlib import Path
from unittest.mock import patch

from ghost_in_word.alignment import AlignmentMapping, alignment_method, align_segments, align_with_mappings, mapping_from_dict
from ghost_in_word.assessment import Assessment, validate_assessment_document
from ghost_in_word.assessment_attachment import attach_assessment_document
from ghost_in_word.embeddings import cosine_distance, embedding_cache_key, embedding_storage_bytes, encode_texts, input_hash
from ghost_in_word.models import TextSegment
from ghost_in_word.matrix import build_translation_matrix
from ghost_in_word.mapping_review import (
    bind_snapshot,
    build_mapping_review_packet,
    summarize_mapping_reviews,
    validate_mapping_document,
    validate_mapping_review_packet,
)
from ghost_in_word.review import (
    build_review_key,
    select_natural_benchmark,
    select_review_items,
    summarize_reviews,
    validate_natural_benchmark_packet,
    validate_review_packet,
)
from ghost_in_word.reference import distance_to_reference, estimate_reference
from ghost_in_word.scoring import lexical_distance, score_units, wording_distance
from ghost_in_word.sources import comparison_edition_metadata, load_editions
from ghost_in_word.summary import summarize_units
from ghost_in_word.usfm import parse_usfm
from ghost_in_word.windows import build_windows
from scripts.evaluate_challenge import compare_to_baseline
from scripts.render_mapping_review_form import render_mapping_review_form
from scripts.render_review_form import render_review_form


class PipelineTests(unittest.TestCase):
    def test_usfm_parser_removes_notes_and_inline_markers(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "JHN.SFM"
            path.write_text(
                "\\id JHN\n\\c 3\n\\p\n\\v 16 For God \\add so\\add* loved the world. \\f + \\ft note\\f*\n",
                encoding="utf-8",
            )
            segments = parse_usfm(path, "webp")

        self.assertEqual(len(segments), 1)
        self.assertEqual(segments[0].key, ("JHN", 3, "16"))
        self.assertEqual(segments[0].text, "For God so loved the world.")

    def test_usfm_parser_removes_plus_word_markers_and_attributes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "JHN.SFM"
            path.write_text(
                '\\id JHN\n\\c 1\n\\v 1 In the beginning \\+w was|strong="G1510"\\+w* the Word.\n',
                encoding="utf-8",
            )
            segments = parse_usfm(path, "webp")

        self.assertEqual(segments[0].text, "In the beginning was the Word.")

    def test_usfm_parser_preserves_cleaned_notes_separately(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "JHN.SFM"
            path.write_text(
                '\\id JHN\n\\c 1\n\\v 1 Text.\\f + \\fr 1:1 \\ft A translator note.\\f*\n',
                encoding="utf-8",
            )
            segments = parse_usfm(path, "webp")

        self.assertEqual(segments[0].text, "Text.")
        self.assertEqual(len(segments[0].notes), 1)
        self.assertIn("A translator note.", segments[0].notes[0])

    def test_usfm_parser_supports_verse_markers_on_separate_lines(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "JHN.SFM"
            path.write_text(
                '\\id JHN\n\\c 1\n\\p\n\\v 1\n\\w Ἐν|lemma="ἐν"\\w* \\w ἀρχῇ|lemma="ἀρχή"\\w*\n\\v 2\n\\w Οὗτος|lemma="οὗτος"\\w* ἦν.\n',
                encoding="utf-8",
            )
            segments = parse_usfm(path, "srgrc")

        self.assertEqual([segment.verse for segment in segments], ["1", "2"])
        self.assertEqual(segments[0].text, "Ἐν ἀρχῇ")
        self.assertEqual(segments[1].text, "Οὗτος ἦν.")

    def test_alignment_exposes_missing_references(self) -> None:
        left = [TextSegment("a", "JHN", 3, "16", "For God so loved the world.")]
        right = [TextSegment("b", "JHN", 3, "17", "For God did not send the Son.")]

        units = align_segments(left, right)

        self.assertEqual([unit.status for unit in units], ["missing-right", "missing-left"])
        self.assertEqual([unit.reference for unit in units], ["JHN 3:16", "JHN 3:17"])

    def test_duplicate_reference_is_rejected(self) -> None:
        segments = [
            TextSegment("a", "JHN", 3, "16", "one"),
            TextSegment("a", "JHN", 3, "16", "two"),
        ]
        with self.assertRaisesRegex(ValueError, "duplicate segment reference"):
            align_segments(segments, [])

    def test_reviewed_mapping_can_merge_multiple_references(self) -> None:
        left = [
            TextSegment("a", "JHN", 3, "16", "For God so loved the world."),
            TextSegment("a", "JHN", 3, "17", "He sent his Son."),
        ]
        right = [TextSegment("b", "JHN", 3, "16", "For God loved the world and sent his Son.")]

        units = align_with_mappings(
            left,
            right,
            [AlignmentMapping((left[0].key, left[1].key), (right[0].key,))],
        )

        self.assertEqual(len(units), 1)
        self.assertEqual(units[0].mapping_type, "many-to-one")
        self.assertEqual(units[0].left_references, ("JHN 3:16", "JHN 3:17"))
        self.assertEqual(units[0].right_references, ("JHN 3:16",))
        self.assertEqual(units[0].status, "matched")
        self.assertIn("He sent his Son.", units[0].left_text)
        self.assertEqual(alignment_method([units[0].to_dict()]), "explicit-reviewed-mapping")

    def test_reviewed_exception_file_keeps_unmentioned_exact_references(self) -> None:
        left = [
            TextSegment("a", "JHN", 3, "16", "For God so loved the world."),
            TextSegment("a", "JHN", 3, "17", "He sent his Son."),
        ]
        right = [
            TextSegment("b", "JHN", 3, "16", "For God loved the world."),
            TextSegment("b", "JHN", 3, "17", "He sent his Son."),
        ]
        units = align_with_mappings(
            left,
            right,
            [
                AlignmentMapping(
                    (left[0].key,),
                    (right[0].key,),
                    method="reviewed-verse-bridge",
                    review={"evidence": "reviewed"},
                )
            ],
        )

        self.assertEqual(len(units), 2)
        exact = next(unit for unit in units if unit.reference == "JHN 3:17")
        self.assertEqual(exact.status, "matched")
        self.assertEqual(exact.mapping_method, "exact-reference")
        reviewed = next(unit for unit in units if unit.reference == "JHN 3:16")
        self.assertEqual(reviewed.mapping_method, "reviewed-verse-bridge")

    def test_reviewed_mapping_preserves_review_evidence(self) -> None:
        left = [TextSegment("a", "JHN", 3, "16", "For God so loved the world.")]
        right = [TextSegment("b", "JHN", 3, "16", "For God loved the world.")]
        mapping = mapping_from_dict(
            {
                "left": ["JHN 3:16"],
                "right": ["JHN 3:16"],
                "method": "reviewed-verse-bridge",
                "review": {"reviewer": "source-reviewer-1", "evidence": "Reference checked against the edition notes."},
            }
        )
        unit = align_with_mappings(left, right, [mapping])[0]
        self.assertEqual(unit.review["reviewer"], "source-reviewer-1")
        self.assertEqual(unit.to_dict()["review"]["evidence"], "Reference checked against the edition notes.")

    def test_reviewed_mapping_with_one_side_empty_is_missing(self) -> None:
        left = [TextSegment("a", "JHN", 3, "16", "For God so loved the world.")]
        units = align_with_mappings(left, [], [AlignmentMapping((left[0].key,), ())])
        self.assertEqual(units[0].mapping_type, "missing")
        self.assertEqual(units[0].status, "missing-right")

    def test_unresolved_mapping_is_retained_without_a_score(self) -> None:
        left = [TextSegment("a", "JHN", 3, "16", "For God so loved the world.")]
        right = [TextSegment("b", "JHN", 3, "16", "For God loved the world.")]

        units = align_with_mappings(
            left,
            right,
            [AlignmentMapping((left[0].key,), (right[0].key,), status="unresolved", method="review")],
        )

        self.assertEqual(units[0].status, "unresolved")
        self.assertIsNone(score_units(units)[0]["lexicalDistance"])

    def test_reviewed_mapping_rejects_reused_reference(self) -> None:
        segment = TextSegment("a", "JHN", 3, "16", "one")
        with self.assertRaisesRegex(ValueError, "reuses"):
            align_with_mappings(
                [segment],
                [TextSegment("b", "JHN", 3, "16", "one")],
                [
                    AlignmentMapping((segment.key,), (segment.key,)),
                    AlignmentMapping((segment.key,), (segment.key,)),
                ],
            )

    def test_mapping_review_report_requires_evidence_and_binds_alignment(self) -> None:
        left = [TextSegment("a", "ROM", 14, "24", "A reviewed span.")]
        right = [TextSegment("b", "ROM", 16, "25", "The corresponding span.")]
        records = [{
            "left": ["ROM 14:24"],
            "right": ["ROM 16:25"],
            "method": "reviewed-verse-bridge",
            "review": {
                "reviewer": "reviewer-1",
                "reviewType": "snapshot-comparison",
                "evidence": "Edition note checked against both pinned snapshots.",
            },
        }]
        report = validate_mapping_document(records, left, right)
        self.assertEqual(report["summary"]["mappingCount"], 1)
        self.assertEqual(report["summary"]["reviewedCount"], 1)
        self.assertEqual(report["summary"]["mappingTypes"], {"one-to-one": 1})
        self.assertEqual(report["mappings"][0]["left"], ["ROM 14:24"])

        records[0]["review"] = {"reviewer": "reviewer-1"}
        with self.assertRaisesRegex(ValueError, "reviewType"):
            validate_mapping_document(records, left, right)

    def test_mapping_review_can_require_a_declared_independent_panel(self) -> None:
        left = [TextSegment("a", "ROM", 14, "24", "A reviewed span.")]
        right = [TextSegment("b", "ROM", 16, "25", "The corresponding span.")]
        records = [{
            "left": ["ROM 14:24"],
            "right": ["ROM 16:25"],
            "method": "reviewed-verse-bridge",
            "review": {
                "reviewer": "independent-review-panel",
                "reviewers": ["reviewer-1", "reviewer-2"],
                "reviewType": "independent-mapping-review",
                "independence": "declared",
                "evidence": "Both reviewers checked the pinned snapshots independently.",
            },
        }]
        report = validate_mapping_document(records, left, right, require_independent_review=True)
        self.assertEqual(report["summary"]["independentReviewCount"], 1)
        self.assertTrue(report["summary"]["independentReviewEligible"])

        records[0]["review"]["reviewers"] = ["reviewer-1"]
        with self.assertRaisesRegex(ValueError, "at least two"):
            validate_mapping_document(records, left, right, require_independent_review=True)

    def test_mapping_review_packet_aggregates_unanimous_independent_acceptance(self) -> None:
        left = [
            TextSegment("a", "JHN", 1, "1", "In the beginning."),
            TextSegment("a", "JHN", 1, "2", "He was in the beginning."),
        ]
        right = [TextSegment("b", "JHN", 1, "1", "In the beginning he was there.")]
        packet = build_mapping_review_packet(
            [{"left": ["JHN 1:1", "JHN 1:2"], "right": ["JHN 1:1"], "method": "candidate"}],
            left,
            right,
            left_source={"edition": "a", "path": "/private/source/snapshot.json", "directorySha256": "abc"},
            right_source={"edition": "b", "path": "/private/source/snapshot.json", "directorySha256": "def"},
        )
        self.assertEqual(validate_mapping_review_packet(packet)["itemCount"], 1)
        self.assertNotIn("path", packet["source"]["leftSnapshot"])
        rendered = render_mapping_review_form(packet, reviewer_id="reviewer-1")
        self.assertEqual(rendered.count('class="review-card"'), 1)
        self.assertIn('data-field="decision"', rendered)
        self.assertIn('id="independence"', rendered)
        self.assertIn("blind-mapping-review-response", rendered)
        self.assertNotIn('"review":', rendered)
        self.assertNotIn('"status":', rendered)
        item_id = packet["items"][0]["id"]
        candidate_records = [{
            "left": ["JHN 1:1", "JHN 1:2"],
            "right": ["JHN 1:1"],
            "status": "unresolved",
            "method": "candidate-bridge",
        }]
        responses = [
            {
                "schemaVersion": 1,
                "kind": "blind-mapping-review-response",
                "reviewerId": reviewer,
                "independence": "declared",
                "items": [{"id": item_id, "decision": "accept", "evidence": f"{reviewer} checked both spans."}],
            }
            for reviewer in ("reviewer-1", "reviewer-2")
        ]
        report = summarize_mapping_reviews(responses, packet=packet, candidate_records=candidate_records)
        self.assertTrue(report["gate"]["eligible"])
        self.assertEqual(report["approvedMappingCount"], 1)
        approved = report["approvedMappings"][0]
        self.assertEqual(approved["status"], "unresolved")
        self.assertEqual(approved["method"], "candidate-bridge")
        self.assertEqual(approved["review"]["reviewers"], ["reviewer-1", "reviewer-2"])
        self.assertEqual(approved["review"]["independence"], "declared")
        self.assertEqual(approved["review"]["sourceBindings"]["left"]["directorySha256"], "abc")
        applied_report = validate_mapping_document(
            report["approvedMappings"],
            left,
            right,
            require_independent_review=True,
            require_snapshot_binding=True,
            source_bindings={
                "left": packet["source"]["leftSnapshot"],
                "right": packet["source"]["rightSnapshot"],
            },
        )
        self.assertTrue(applied_report["summary"]["independentReviewEligible"])
        self.assertTrue(applied_report["summary"]["snapshotBindingEligible"])
        bad_bindings = {
            "left": {**packet["source"]["leftSnapshot"], "directorySha256": "changed"},
            "right": packet["source"]["rightSnapshot"],
        }
        with self.assertRaisesRegex(ValueError, "does not match"):
            validate_mapping_document(
                report["approvedMappings"],
                left,
                right,
                require_snapshot_binding=True,
                source_bindings=bad_bindings,
            )

        responses[1]["items"][0]["decision"] = "uncertain"
        rejected = summarize_mapping_reviews(responses, packet=packet, candidate_records=candidate_records)
        self.assertTrue(rejected["gate"]["eligible"])
        self.assertEqual(rejected["approvedMappingCount"], 0)

    def test_mapping_snapshot_binding_requires_matching_inventory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "snapshot.json").write_text(
                json.dumps({"edition": "webp", "directorySha256": "abc123", "files": []}),
                encoding="utf-8",
            )
            binding = bind_snapshot(root, "webp")
            self.assertEqual(binding["directorySha256"], "abc123")
            with self.assertRaisesRegex(ValueError, "does not bind"):
                bind_snapshot(root, "bsb")

    def test_committed_mapping_records_declare_review_provenance(self) -> None:
        records = json.loads(
            (Path(__file__).parents[1] / "mappings/webp-bsb-reviewed.json").read_text(encoding="utf-8")
        )
        self.assertGreater(len(records), 0)
        for record in records:
            self.assertIn("review", record)
            self.assertTrue(record["review"].get("reviewer"))
            self.assertTrue(record["review"].get("reviewType"))
            self.assertTrue(record["review"].get("evidence"))

    def test_lexical_baselines_are_bounded_and_deterministic(self) -> None:
        left = "For God so loved the world"
        right = "Because God loved the world so much"
        self.assertEqual(wording_distance(left, left), 0.0)
        self.assertEqual(lexical_distance(left, left), 0.0)
        self.assertGreaterEqual(wording_distance(left, right), 0.0)
        self.assertLessEqual(wording_distance(left, right), 1.0)
        self.assertGreaterEqual(lexical_distance(left, right), 0.0)
        self.assertLessEqual(lexical_distance(left, right), 1.0)

    def test_missing_units_have_null_scores(self) -> None:
        left = [TextSegment("a", "JHN", 3, "16", "For God so loved the world.")]
        right = [TextSegment("b", "JHN", 3, "17", "For God did not send the Son.")]
        scored = score_units(align_segments(left, right))
        self.assertTrue(all(unit["lexicalDistance"] is None for unit in scored))

    def test_summary_excludes_missing_scores(self) -> None:
        units = [
            {"book": "JHN", "chapter": 3, "status": "matched", "lexicalDistance": 0.2},
            {"book": "JHN", "chapter": 3, "status": "missing-right", "lexicalDistance": None},
            {"book": "JHN", "chapter": 4, "status": "matched", "lexicalDistance": 0.6},
        ]
        summary = summarize_units(units, "lexicalDistance")
        self.assertEqual(summary["overall"]["totalUnits"], 3)
        self.assertEqual(summary["overall"]["matchedUnits"], 2)
        self.assertEqual(summary["overall"]["scoredUnits"], 2)
        self.assertEqual(summary["chapters"][0]["coverage"], 0.5)

    def test_summary_reports_middle_fifty_percentile_bounds(self) -> None:
        units = [
            {"book": "JHN", "chapter": 3, "status": "matched", "lexicalDistance": 0.0},
            {"book": "JHN", "chapter": 3, "status": "matched", "lexicalDistance": 0.2},
            {"book": "JHN", "chapter": 3, "status": "matched", "lexicalDistance": 0.4},
            {"book": "JHN", "chapter": 3, "status": "matched", "lexicalDistance": 0.6},
            {"book": "JHN", "chapter": 3, "status": "missing-right", "lexicalDistance": None},
        ]
        score = summarize_units(units, "lexicalDistance")["overall"]["score"]
        self.assertEqual(score["p25"], 0.15)
        self.assertEqual(score["median"], 0.3)
        self.assertEqual(score["p75"], 0.45)

    def test_embedding_primitives_are_deterministic(self) -> None:
        self.assertEqual(cosine_distance([1.0, 0.0], [1.0, 0.0]), 0.0)
        self.assertEqual(cosine_distance([1.0, 0.0], [0.0, 1.0]), 1.0)
        self.assertEqual(input_hash(["one", "two"]), input_hash(["one", "two"]))
        self.assertNotEqual(input_hash(["one", "two"]), input_hash(["two", "one"]))
        self.assertNotEqual(
            embedding_cache_key(["one"], "model", model_revision="rev-a"),
            embedding_cache_key(["one"], "model", model_revision="rev-b"),
        )
        self.assertNotEqual(
            embedding_cache_key(["one"], "model", context_strategy="verse-only"),
            embedding_cache_key(["one"], "model", context_strategy="chapter-window"),
        )
        self.assertEqual(embedding_storage_bytes(10, 3, 384), 46080)

    def test_embedding_cache_reuses_exact_recipe_and_invalidates_inputs(self) -> None:
        class FakeModel:
            calls = 0
            max_seq_length = 2

            class Tokenizer:
                def __call__(self, texts, **kwargs):
                    return {"input_ids": [[0] * (len(text.split()) + 1) for text in texts]}

            tokenizer = Tokenizer()

            def __init__(self, model_id: str) -> None:
                self.model_id = model_id

            def encode(self, texts, **kwargs):
                type(self).calls += 1
                class Encoded(list):
                    def tolist(self):
                        return list(self)

                return Encoded([[float(len(text)), 1.0] for text in texts])

        fake_module = types.ModuleType("sentence_transformers")
        fake_module.SentenceTransformer = FakeModel
        with tempfile.TemporaryDirectory() as directory, patch.dict(sys.modules, {"sentence_transformers": fake_module}):
            first_vectors, first_run = encode_texts(
                ["one", "two"],
                "fixture-model",
                cache_dir=directory,
                model_revision="commit-a",
            )
            second_vectors, second_run = encode_texts(
                ["one", "two"],
                "fixture-model",
                cache_dir=directory,
                model_revision="commit-a",
            )
            changed_vectors, changed_run = encode_texts(
                ["one", "changed"],
                "fixture-model",
                cache_dir=directory,
                model_revision="commit-a",
            )
            revised_vectors, revised_run = encode_texts(
                ["one", "two"],
                "fixture-model",
                cache_dir=directory,
                model_revision="commit-b",
            )
            recipe_vectors, recipe_run = encode_texts(
                ["one", "two"],
                "fixture-model",
                cache_dir=directory,
                model_revision="commit-a",
                preprocessing_version="2",
            )

        self.assertEqual(first_vectors, second_vectors)
        self.assertEqual(first_run.cache_key, second_run.cache_key)
        self.assertFalse(first_run.cache_hit)
        self.assertTrue(second_run.cache_hit)
        self.assertEqual(first_run.input_count, 2)
        self.assertEqual(first_run.truncated_inputs, 2)
        self.assertEqual(second_run.truncated_inputs, 2)
        self.assertFalse(changed_run.cache_hit)
        self.assertNotEqual(first_run.cache_key, changed_run.cache_key)
        self.assertNotEqual(first_vectors, changed_vectors)
        self.assertFalse(revised_run.cache_hit)
        self.assertFalse(recipe_run.cache_hit)
        self.assertEqual(first_vectors, revised_vectors)
        self.assertEqual(first_vectors, recipe_vectors)
        self.assertEqual(FakeModel.calls, 4)

    def test_reference_estimate_excludes_pair_and_caps_related_family(self) -> None:
        estimate = estimate_reference(
            {
                "webp": [1.0, 0.0],
                "bsb": [0.99, 0.1],
                "asv": [1.0, 0.0],
                "nlt": [0.0, 1.0],
            },
            exclude={"webp", "bsb"},
            families={"asv": "older", "nlt": "modern"},
            family_cap=1.0,
        )
        self.assertEqual(estimate.included_editions, ("asv", "nlt"))
        self.assertEqual(estimate.excluded_editions, ("bsb", "webp"))
        self.assertEqual(dict(estimate.weights), {"asv": 1.0, "nlt": 1.0})
        self.assertEqual(estimate.medoid_edition, "asv")
        self.assertGreater(estimate.dispersion, 0.0)
        self.assertEqual(estimate.pairwise_distances, (("asv", "nlt", 1.0),))
        self.assertEqual(distance_to_reference([1.0, 0.0], [1.0, 0.0]), 0.0)

    def test_reference_estimate_limits_duplicate_family_weight(self) -> None:
        estimate = estimate_reference(
            {"a": [1.0, 0.0], "b": [1.0, 0.0], "c": [0.0, 1.0]},
            families={"a": "family-a", "b": "family-a", "c": "family-c"},
            family_cap=1.0,
        )
        self.assertEqual(dict(estimate.weights), {"a": 0.5, "b": 0.5, "c": 1.0})
        self.assertEqual(estimate.vector, (0.707106781, 0.707106781))

    def test_reference_estimate_rejects_empty_panel_after_exclusion(self) -> None:
        with self.assertRaisesRegex(ValueError, "leaves no reference panel"):
            estimate_reference({"a": [1.0, 0.0]}, exclude={"a"})

    def test_translation_matrix_joins_pairwise_artifacts(self) -> None:
        matrix = build_translation_matrix(
            [
                {
                    "metadata": {"leftEdition": {"id": "a", "name": "A"}, "rightEdition": {"id": "b", "name": "B"}},
                    "units": [{"id": "JHN-1-1", "book": "JHN", "chapter": 1, "verse": "1", "reference": "JHN 1:1", "order": 0, "leftText": "one", "rightText": "two", "status": "matched"}],
                },
                {
                    "metadata": {"leftEdition": {"id": "a", "name": "A"}, "rightEdition": {"id": "c", "name": "C"}},
                    "units": [
                        {"id": "JHN-1-1", "book": "JHN", "chapter": 1, "verse": "1", "reference": "JHN 1:1", "order": 0, "leftText": "one", "rightText": "three", "status": "matched"},
                        {"id": "JHN-1-2", "book": "JHN", "chapter": 1, "verse": "2", "reference": "JHN 1:2", "order": 1, "leftText": "next", "rightText": "next", "status": "matched"},
                        {"id": "JHN-1-3", "book": "JHN", "chapter": 1, "verse": "3", "reference": "JHN 1:3", "order": 2, "leftText": "only one side", "rightText": None, "status": "missing-right"},
                    ],
                },
            ]
        )
        self.assertEqual([edition["id"] for edition in matrix["metadata"]["editions"]], ["a", "b", "c"])
        self.assertEqual(matrix["summary"]["scoredPassages"], 2)
        first = matrix["passages"][0]
        self.assertEqual(first["status"], "matched")
        self.assertEqual(set(first["distances"]), {"a|b", "a|c", "b|c"})
        self.assertEqual(matrix["passages"][-1]["status"], "insufficient-panel")

    def test_source_conditioned_assessment_preserves_provenance_and_disagreement(self) -> None:
        document = {
            "schemaVersion": 1,
            "kind": "source-conditioned-assessments",
            "sourceEdition": {"id": "source-greek-v1", "name": "Example Greek source", "language": "grc"},
            "assessments": [
                {
                    "id": "JHN-3-16",
                    "origin": "human",
                    "reviewerId": "source-reader-1",
                    "judgmentType": "source-faithfulness",
                    "judgment": "uncertain",
                    "evidence": ["The displayed source span permits more than one reading."],
                    "uncertainty": "high",
                    "disagreement": ["A second reader preferred preserved."],
                    "version": "review-2026-10-14",
                },
                {
                    "id": "JHN-3-17",
                    "origin": "model",
                    "modelId": "example-model-v1",
                    "judgmentType": "meaning-equivalence",
                    "judgment": "preserved",
                    "evidence": ["Model output is retained as an observation."],
                    "uncertainty": "medium",
                    "version": "model-run-1",
                },
            ],
        }
        normalized = validate_assessment_document(document)
        self.assertEqual(normalized["summary"]["total"], 2)
        self.assertEqual(normalized["summary"]["disagreementRecords"], 1)
        self.assertEqual(normalized["assessments"][0]["sourceEdition"], "source-greek-v1")
        self.assertEqual(Assessment.from_dict(document["assessments"][0], source_edition="source-greek-v1").reviewer_id, "source-reader-1")

    def test_source_conditioned_assessment_rejects_missing_origin_identity(self) -> None:
        with self.assertRaisesRegex(ValueError, "reviewerId"):
            Assessment(
                item_id="JHN-3-16",
                source_edition="source-v1",
                origin="human",
                judgment_type="source-faithfulness",
                judgment="uncertain",
                evidence=("No adjudication yet.",),
                uncertainty="high",
                version="review-1",
            )

    def test_source_conditioned_assessment_rejects_mixed_source_ids(self) -> None:
        document = {
            "schemaVersion": 1,
            "kind": "source-conditioned-assessments",
            "sourceEdition": {"id": "source-a"},
            "assessments": [{
                "id": "JHN-3-16",
                "sourceEdition": "source-b",
                "origin": "model",
                "modelId": "fixture-model",
                "judgmentType": "meaning-equivalence",
                "judgment": "uncertain",
                "evidence": ["mixed-source fixture"],
                "uncertainty": "uncertain",
                "version": "fixture-1",
            }],
        }
        with self.assertRaisesRegex(ValueError, "match the document sourceEdition"):
            validate_assessment_document(document)

    def test_source_assessment_attachment_requires_source_and_preserves_evidence(self) -> None:
        comparison = {
            "schemaVersion": 1,
            "metadata": {
                "leftEdition": {"id": "webp", "role": "translation"},
                "rightEdition": {"id": "srgrc", "role": "source"},
            },
            "units": [{"id": "JHN-3-16", "status": "matched"}],
        }
        document = {
            "schemaVersion": 1,
            "kind": "source-conditioned-assessments",
            "sourceEdition": {"id": "srgrc", "name": "Greek source", "language": "grc"},
            "assessments": [{
                "id": "JHN-3-16",
                "origin": "human",
                "reviewerId": "source-reader",
                "judgmentType": "source-faithfulness",
                "judgment": "uncertain",
                "evidence": ["The source span permits more than one reading."],
                "uncertainty": "high",
                "version": "review-1",
            }],
        }
        attached = attach_assessment_document(comparison, document, source_document="review.json")
        self.assertEqual(attached["metadata"]["assessmentAttachment"]["sourceEdition"]["id"], "srgrc")
        self.assertEqual(attached["units"][0]["assessments"][0]["reviewerId"], "source-reader")
        self.assertEqual(attached["metadata"]["assessmentAttachment"]["sourceDocument"], "review.json")

        comparison["metadata"]["rightEdition"] = {"id": "bsb", "role": "translation"}
        with self.assertRaisesRegex(ValueError, "not part of the comparison"):
            attach_assessment_document(comparison, document)

    def test_review_sample_hides_rank_and_is_seeded(self) -> None:
        comparison = {
            "metadata": {
                "leftEdition": {"id": "a"},
                "rightEdition": {"id": "b"},
                "metric": {"id": "lexical-baseline", "label": "Lexical"},
            },
            "units": [
                {"id": "JHN-1-1", "reference": "JHN 1:1", "status": "matched", "left_text": "one", "right_text": "uno", "lexicalDistance": 0.9},
                {"id": "JHN-1-2", "reference": "JHN 1:2", "status": "matched", "left_text": "two", "right_text": "dos", "lexicalDistance": 0.8},
                {"id": "JHN-1-3", "reference": "JHN 1:3", "status": "matched", "left_text": "three", "right_text": "tres", "lexicalDistance": 0.1},
            ],
        }
        packet = select_review_items(comparison, count=2, metric_field="lexicalDistance", seed=7)
        self.assertEqual(packet["selection"]["selectedCount"], 2)
        self.assertTrue(all("lexicalDistance" not in item and "rank" not in item for item in packet["items"]))
        self.assertEqual(packet, select_review_items(comparison, count=2, metric_field="lexicalDistance", seed=7))

        comparison["units"] = [
            {"id": "JHN-1-1", "reference": "JHN 1:1", "status": "matched", "leftText": "one", "rightText": "uno", "lexicalDistance": 0.9},
            {"id": "JHN-1-2", "reference": "JHN 1:2", "status": "matched", "leftText": "two", "rightText": "dos", "lexicalDistance": 0.8},
        ]
        camel_packet = select_review_items(comparison, count=1, metric_field="lexicalDistance", seed=7)
        self.assertEqual(camel_packet["items"][0]["leftText"], "one")

    def test_review_key_keeps_rank_private_and_enables_bucket_summary(self) -> None:
        comparison = {
            "metadata": {"metric": {"id": "lexical-baseline", "label": "Lexical"}},
            "units": [
                {"id": "a", "status": "matched", "leftText": "one", "rightText": "uno", "lexicalDistance": 0.9},
                {"id": "b", "status": "matched", "leftText": "two", "rightText": "dos", "lexicalDistance": 0.8},
                {"id": "c", "status": "matched", "leftText": "three", "rightText": "tres", "lexicalDistance": 0.1},
            ],
        }
        packet = select_review_items(comparison, count=2, metric_field="lexicalDistance", seed=7)
        key = build_review_key(comparison, count=2, metric_field="lexicalDistance", seed=7)
        self.assertTrue(all("rank" not in item for item in packet["items"]))
        self.assertEqual(key["selection"]["topCount"], 1)
        report = summarize_reviews(
            [
                {"reviewerId": "r1", "items": [
                    {"id": item["id"], "useful": "yes", "differenceType": "wording", "confidence": "high", "evidence": "evidence"}
                    for item in packet["items"]
                ]}
            ],
            selection_key=key,
        )
        self.assertEqual(report["selection"]["topRanked"]["majorityUsefulRate"], 1.0)
        self.assertEqual(report["selection"]["seededRandom"]["reviewedCount"], 1)

    def test_review_summary_preserves_uncertainty_and_disagreement(self) -> None:
        report = summarize_reviews(
            [
                {
                    "reviewerId": "r1",
                    "items": [{"id": "x", "useful": "yes", "differenceType": "likely meaning", "confidence": "high", "evidence": "wording differs"}],
                },
                {
                    "reviewerId": "r2",
                    "items": [{"id": "x", "useful": "no", "differenceType": "wording", "confidence": "medium", "evidence": "not useful"}],
                },
                {
                    "reviewerId": "r3",
                    "items": [{"id": "y", "useful": "uncertain", "differenceType": "unclear", "confidence": "low", "evidence": "unclear"}],
                },
            ]
        )
        self.assertEqual(report["binaryAgreementItems"], 0)
        self.assertEqual(report["binaryComparedItems"], 1)
        self.assertEqual(report["consensusItems"], 0)
        self.assertEqual(report["items"][1]["majorityUseful"], "uncertain")
        self.assertEqual(report["items"][0]["votes"][0]["evidence"], "wording differs")

    def test_review_packet_validation_rejects_score_leaks(self) -> None:
        comparison = {
            "metadata": {
                "leftEdition": {"id": "a"},
                "rightEdition": {"id": "b"},
                "metric": {"id": "lexical-baseline", "label": "Lexical"},
            },
            "units": [
                {
                    "id": "JHN-1-1",
                    "reference": "JHN 1:1",
                    "book": "JHN",
                    "chapter": 1,
                    "verse": "1",
                    "status": "matched",
                    "leftText": "one",
                    "rightText": "uno",
                    "lexicalDistance": 0.9,
                },
            ],
        }
        packet = select_review_items(comparison, count=1, metric_field="lexicalDistance", seed=7)
        summary = validate_review_packet(packet)
        self.assertEqual(summary["itemCount"], 1)
        self.assertNotIn("lexicalDistance", packet["items"][0])
        packet["items"][0]["rank"] = 1
        with self.assertRaisesRegex(ValueError, "forbidden"):
            validate_review_packet(packet)

    def test_review_form_contains_only_blind_packet_and_response_controls(self) -> None:
        comparison = {
            "metadata": {
                "leftEdition": {"id": "a", "name": "Edition A"},
                "rightEdition": {"id": "b", "name": "Edition B"},
                "metric": {"id": "lexical-baseline", "label": "Lexical baseline", "description": "Fixture method."},
            },
            "units": [
                {
                    "id": "JHN-1-1",
                    "reference": "JHN 1:1",
                    "book": "JHN",
                    "chapter": 1,
                    "verse": "1",
                    "status": "matched",
                    "leftText": "A <word> & a phrase",
                    "rightText": "A different phrase",
                    "lexicalDistance": 0.9,
                }
            ],
        }
        packet = select_review_items(comparison, count=1, metric_field="lexicalDistance", seed=7)
        rendered = render_review_form(packet, reviewer_id="reviewer-1")
        self.assertIn("A &lt;word&gt; &amp; a phrase", rendered)
        self.assertIn('data-field="differenceType"', rendered)
        self.assertIn('data-field="evidence"', rendered)
        self.assertIn('id="independence"', rendered)
        self.assertIn("independence: 'declared'", rendered)
        self.assertIn("schemaVersion: 1, reviewerId, independence: 'declared', items: collect()", rendered)
        self.assertNotIn('"lexicalDistance"', rendered)
        self.assertNotIn('"rank"', rendered)
        self.assertNotIn('"score"', rendered)

    def test_review_evaluation_checks_packet_ids_and_reports_gate_status(self) -> None:
        comparison = {
            "metadata": {
                "leftEdition": {"id": "a"},
                "rightEdition": {"id": "b"},
                "metric": {"id": "lexical-baseline", "label": "Lexical"},
            },
            "units": [
                {"id": "a", "reference": "JHN 1:1", "book": "JHN", "chapter": 1, "verse": "1", "status": "matched", "leftText": "one", "rightText": "uno", "lexicalDistance": 0.9},
                {"id": "b", "reference": "JHN 1:2", "book": "JHN", "chapter": 1, "verse": "2", "status": "matched", "leftText": "two", "rightText": "dos", "lexicalDistance": 0.8},
                {"id": "c", "reference": "JHN 1:3", "book": "JHN", "chapter": 1, "verse": "3", "status": "matched", "leftText": "three", "rightText": "tres", "lexicalDistance": 0.1},
            ],
        }
        packet = select_review_items(comparison, count=2, metric_field="lexicalDistance", seed=7)
        key = build_review_key(comparison, count=2, metric_field="lexicalDistance", seed=7)
        response = {
            "schemaVersion": 1,
            "reviewerId": "r1",
            "items": [
                {"id": item["id"], "useful": "yes", "differenceType": "wording", "confidence": "high", "evidence": "visible wording"}
                for item in packet["items"]
            ],
        }
        report = summarize_reviews([response], selection_key=key, packet=packet)
        self.assertEqual(report["packet"]["reviewedItemCount"], 2)
        self.assertFalse(report["naturalEvaluation"]["eligible"])
        response["independence"] = "declared"
        strict_report = summarize_reviews(
            [response],
            selection_key=key,
            packet=packet,
            require_independent_reviewers=True,
        )
        self.assertTrue(strict_report["reviewerIndependence"]["allDeclared"])
        self.assertTrue(strict_report["naturalEvaluation"]["prerequisites"]["independentReviewersRequired"])
        missing_declaration = dict(response)
        missing_declaration.pop("independence")
        with self.assertRaisesRegex(ValueError, "declare independence"):
            summarize_reviews(
                [missing_declaration],
                selection_key=key,
                packet=packet,
                require_independent_reviewers=True,
            )
        response["items"][0]["id"] = "outside-packet"
        with self.assertRaisesRegex(ValueError, "unknown packet item"):
            summarize_reviews([response], selection_key=key, packet=packet)
        response["items"][0]["id"] = packet["items"][0]["id"]
        incomplete_key = dict(key)
        incomplete_key["items"] = key["items"][:-1]
        with self.assertRaisesRegex(ValueError, "missing packet ids"):
            summarize_reviews([response], selection_key=incomplete_key, packet=packet)
        duplicate_key = dict(key)
        duplicate_key["items"] = key["items"] + [key["items"][0]]
        with self.assertRaisesRegex(ValueError, "duplicate id"):
            summarize_reviews([response], selection_key=duplicate_key, packet=packet)
        response["items"][0]["modelOutput"] = "leak"
        with self.assertRaisesRegex(ValueError, "unsupported fields"):
            summarize_reviews([response], selection_key=key, packet=packet)

    def test_review_selection_bootstrap_resamples_books_deterministically(self) -> None:
        items = [
            {
                "id": f"{book}-1-1",
                "reference": f"{book} 1:1",
                "book": book,
                "chapter": 1,
                "verse": "1",
                "leftText": "left",
                "rightText": "right",
            }
            for book in ("GEN", "PSA", "LEV", "ROM")
        ]
        packet = {
            "schemaVersion": 1,
            "kind": "blind-review-packet",
            "source": {"leftEdition": {"id": "a"}, "rightEdition": {"id": "b"}},
            "selection": {"strategy": "fixture", "selectedCount": 4, "candidateCount": 4},
            "items": items,
        }
        genres = {"GEN-1-1": "narrative", "PSA-1-1": "poetry", "LEV-1-1": "law", "ROM-1-1": "argument"}
        key = {
            "schemaVersion": 1,
            "kind": "blind-review-key",
            "selection": {"seed": 19, "metric": "lexicalDistance"},
            "items": [
                {"id": item["id"], "rank": index + 1, "bucket": "top-ranked", "genre": genres[item["id"]], "lengthBand": "short"}
                for index, item in enumerate(items)
            ],
        }
        responses = [
            {
                "reviewerId": reviewer,
                "items": [
                    {"id": item["id"], "useful": "yes", "differenceType": "wording", "confidence": "high", "evidence": "visible difference"}
                    for item in items
                ],
            }
            for reviewer in ("r1", "r2")
        ]
        report = summarize_reviews(responses, selection_key=key, packet=packet, bootstrap_samples=25)
        interval = report["selection"]["topRanked"]["majorityUsefulRate95CI"]
        self.assertEqual(interval["unit"], "book")
        self.assertEqual(interval["samples"], 25)
        self.assertEqual(interval["seed"], 19)
        self.assertEqual(report["selection"]["breakdowns"]["genre"]["poetry"]["majorityUsefulRate"], 1.0)
        self.assertEqual(report["selection"]["breakdowns"]["lengthBand"]["short"]["selectedCount"], 4)
        repeat = summarize_reviews(responses, selection_key=key, packet=packet, bootstrap_samples=25)
        self.assertEqual(interval, repeat["selection"]["topRanked"]["majorityUsefulRate95CI"])

    def test_review_selection_reports_model_ranking_agreement(self) -> None:
        packet = {
            "schemaVersion": 1,
            "kind": "blind-review-packet",
            "source": {"leftEdition": {"id": "a"}, "rightEdition": {"id": "b"}},
            "selection": {"strategy": "fixture", "selectedCount": 4, "candidateCount": 4},
            "items": [
                {"id": f"{book}-1-1", "reference": f"{book} 1:1", "book": book, "chapter": 1, "verse": "1", "leftText": "left", "rightText": "right"}
                for book in ("GEN", "PSA", "LEV", "ROM")
            ],
        }
        key = {
            "schemaVersion": 1,
            "kind": "blind-review-key",
            "selection": {"seed": 23, "metric": "lexicalDistance"},
            "items": [
                {"id": item["id"], "rank": index + 1, "bucket": "top-ranked", "genre": "other", "lengthBand": "short"}
                for index, item in enumerate(packet["items"])
            ],
        }
        responses = [
            {
                "reviewerId": reviewer,
                "items": [
                    {
                        "id": item["id"],
                        "useful": "yes" if index < 2 else "no",
                        "differenceType": "wording",
                        "confidence": "high",
                        "evidence": "visible difference",
                    }
                    for index, item in enumerate(packet["items"])
                ],
            }
            for reviewer in ("r1", "r2")
        ]
        report = summarize_reviews(responses, selection_key=key, packet=packet, bootstrap_samples=25)
        agreement = report["selection"]["rankingAgreement"]
        self.assertEqual(agreement["auc"], 1.0)
        self.assertEqual(agreement["rankBiserial"], 1.0)
        self.assertEqual(agreement["comparablePairs"], 4)
        self.assertEqual(agreement["auc95CI"]["unit"], "book")

    def test_committed_natural_benchmark_is_score_blinded(self) -> None:
        packet = json.loads(
            (Path(__file__).parents[1] / "benchmarks/natural-review-packet.example.json").read_text(encoding="utf-8")
        )
        summary = validate_review_packet(packet)
        self.assertEqual(summary["itemCount"], 200)
        self.assertEqual(packet["selection"]["topCount"], 30)
        self.assertEqual(packet["selection"]["backgroundCount"], 170)
        self.assertTrue(all(not set(item).intersection({"rank", "score", "lexicalDistance", "embeddingDistance", "wordingDistance"}) for item in packet["items"]))

    def test_natural_benchmark_validator_enforces_holdout_scope(self) -> None:
        root = Path(__file__).parents[1] / "benchmarks"
        development = json.loads((root / "natural-review-packet.example.json").read_text(encoding="utf-8"))
        heldout = json.loads((root / "natural-review-heldout.example.json").read_text(encoding="utf-8"))
        self.assertFalse(validate_natural_benchmark_packet(development)["holdoutScopeDeclared"])
        with self.assertRaisesRegex(ValueError, "holdout"):
            validate_natural_benchmark_packet(development, require_holdout_scope=True)
        report = validate_natural_benchmark_packet(
            heldout,
            require_holdout_scope=True,
            excluded_books=["GEN", "JHN"],
        )
        self.assertTrue(report["holdoutScopeDeclared"])
        self.assertEqual(report["excludedBooks"], ["GEN", "JHN"])
        with self.assertRaisesRegex(ValueError, "does not declare"):
            validate_natural_benchmark_packet(heldout, require_holdout_scope=True, excluded_books=["MAT"])

    def test_natural_benchmark_can_scope_to_held_out_books(self) -> None:
        comparison = {
            "metadata": {
                "leftEdition": {"id": "a"},
                "rightEdition": {"id": "b"},
                "metric": {"id": "lexical-baseline", "label": "Lexical", "description": "fixture"},
            },
            "units": [
                {
                    "id": f"JHN-1-{index}",
                    "reference": f"JHN 1:{index}",
                    "book": "JHN",
                    "chapter": 1,
                    "verse": str(index),
                    "status": "matched",
                    "leftText": f"left {index}",
                    "rightText": f"right {index}",
                    "lexicalDistance": index / 100,
                }
                for index in range(1, 31)
            ],
        }
        packet, key = select_natural_benchmark(comparison, count=30, books=["jhn"])
        self.assertEqual(packet["selection"]["scope"]["includeBooks"], ["JHN"])
        self.assertEqual(key["selection"]["scope"]["includeBooks"], ["JHN"])
        self.assertEqual(validate_review_packet(packet)["itemCount"], 30)

    def test_committed_natural_holdout_packet_excludes_development_books(self) -> None:
        packet = json.loads(
            (Path(__file__).parents[1] / "benchmarks/natural-review-heldout.example.json").read_text(encoding="utf-8")
        )
        self.assertEqual(validate_review_packet(packet)["itemCount"], 200)
        self.assertEqual(packet["selection"]["scope"]["excludeBooks"], ["GEN", "JHN"])
        self.assertTrue(all(item["book"] not in {"GEN", "JHN"} for item in packet["items"]))

    def test_model_exposure_record_does_not_claim_clean_pretraining(self) -> None:
        record = json.loads(
            (Path(__file__).parents[1] / "benchmarks/model_exposure.json").read_text(encoding="utf-8")
        )
        self.assertEqual(record["kind"], "model-exposure-record")
        self.assertEqual(record["status"], "unknown")
        self.assertTrue(all(model["bibleExposure"] == "unknown" for model in record["models"]))
        self.assertTrue(all(isinstance(model["revision"], str) and len(model["revision"]) == 40 for model in record["models"]))

    def test_committed_heldout_reports_include_paired_baseline_effects(self) -> None:
        root = Path(__file__).parents[1] / "benchmarks/reports"
        for name in ("e5-small-heldout.json", "bge-m3-heldout.json"):
            report = json.loads((root / name).read_text(encoding="utf-8"))
            comparison = report["baselineComparison"]
            self.assertEqual(comparison["baselineMetric"], "character-ngram-lexical")
            self.assertEqual(comparison["pairedCases"], report["total"])
            self.assertIn("passRateDelta95CI", comparison["bootstrap"])

    def test_challenge_reports_paired_baseline_effect(self) -> None:
        results = [
            {
                "changedRanksFarther": True,
                "margin": 0.4,
                "lexicalChangedRanksFarther": False,
                "lexicalMargin": -0.1,
            },
            {
                "changedRanksFarther": False,
                "margin": -0.2,
                "lexicalChangedRanksFarther": False,
                "lexicalMargin": -0.3,
            },
        ]
        comparison = compare_to_baseline(results, bootstrap_samples=25, seed=11)
        self.assertEqual(comparison["pairedCases"], 2)
        self.assertEqual(comparison["passRateDelta"], 0.5)
        self.assertEqual(comparison["meanMarginDelta"], 0.3)
        self.assertEqual(comparison["bootstrap"]["unit"], "challenge-case")

    def test_committed_browser_fixture_uses_public_schema(self) -> None:
        fixture = json.loads((Path(__file__).parents[1] / "web/public/data/john-webp-bsb.json").read_text(encoding="utf-8"))
        unit = fixture["units"][0]
        self.assertIn("leftText", unit)
        self.assertIn("rightText", unit)
        self.assertNotIn("left_text", unit)
        self.assertEqual(fixture["metadata"]["leftEdition"]["language"], "en")
        self.assertEqual(fixture["metadata"]["rightEdition"]["language"], "en")

    def test_third_english_pair_fixture_uses_public_schema(self) -> None:
        fixture = json.loads((Path(__file__).parents[1] / "web/public/data/john-bsb-asv.json").read_text(encoding="utf-8"))
        self.assertEqual(fixture["metadata"]["leftEdition"]["id"], "bsb")
        self.assertEqual(fixture["metadata"]["rightEdition"]["id"], "asv")
        self.assertEqual(fixture["metadata"]["leftEdition"]["language"], "en")
        self.assertEqual(fixture["metadata"]["rightEdition"]["language"], "en")
        self.assertEqual(fixture["metadata"]["metric"]["distanceField"], "lexicalDistance")
        self.assertEqual(fixture["summary"]["scoredUnits"], 878)
        self.assertIn("missing-left", fixture["metadata"]["alignment"]["statuses"])

    def test_public_full_atlas_declares_reviewed_mapping_method(self) -> None:
        manifest = json.loads((Path(__file__).parents[1] / "web/public/data/webp-bsb/manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["comparison"]["alignment"]["method"], "explicit-reviewed-mapping")
        rom = json.loads((Path(__file__).parents[1] / "web/public/data/webp-bsb/ROM.json").read_text(encoding="utf-8"))
        bridge = next(unit for unit in rom["units"] if unit["reference"] == "ROM 14:24")
        self.assertEqual(bridge["mappingMethod"], "reviewed-verse-bridge")

    def test_all_english_pairs_have_full_partition_manifests(self) -> None:
        root = Path(__file__).parents[1] / "web/public/data"
        expected = {
            "webp-bsb": ("webp", "bsb", 31103),
            "webp-asv": ("webp", "asv", 31105),
            "bsb-asv": ("bsb", "asv", 31102),
        }
        for pair, (left_id, right_id, total_units) in expected.items():
            manifest = json.loads((root / pair / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(len(manifest["books"]), 66)
            self.assertEqual(manifest["comparison"]["leftEdition"]["id"], left_id)
            self.assertEqual(manifest["comparison"]["rightEdition"]["id"], right_id)
            self.assertEqual(manifest["summary"]["totalUnits"], total_units)
            self.assertEqual(sum(book["totalUnits"] for book in manifest["books"]), total_units)

    def test_cross_language_fixture_suppresses_lexical_fields(self) -> None:
        fixture = json.loads((Path(__file__).parents[1] / "web/public/data/john-webp-rv1909-e5-small.json").read_text(encoding="utf-8"))
        self.assertEqual(fixture["metadata"]["leftEdition"]["language"], "en")
        self.assertEqual(fixture["metadata"]["rightEdition"]["language"], "es")
        self.assertEqual(fixture["metadata"]["metric"]["distanceField"], "embeddingDistance")
        self.assertIsNone(fixture["units"][0]["wordingDistance"])
        self.assertIsNone(fixture["units"][0]["lexicalDistance"])
        self.assertIsInstance(fixture["units"][0]["embeddingDistance"], float)

        source_fixture = json.loads((Path(__file__).parents[1] / "web/public/data/john-webp-srgrc-e5-small.json").read_text(encoding="utf-8"))
        self.assertEqual(source_fixture["metadata"]["rightEdition"]["role"], "source")
        self.assertEqual(source_fixture["metadata"]["rightEdition"]["language"], "grc")
        self.assertEqual(source_fixture["metadata"]["rightEdition"]["license"], "CC-BY-4.0")
        self.assertIn("Center for New Testament Restoration", source_fixture["metadata"]["rightEdition"]["attribution"])
        self.assertLess(source_fixture["summary"]["scoredUnits"], source_fixture["summary"]["totalUnits"])

    def test_source_manifest_validates_roles_and_attribution(self) -> None:
        editions = load_editions(Path(__file__).parents[1] / "sources.json")
        self.assertEqual(editions["rv1909"].language, "es")
        self.assertEqual(editions["srgrc"].role, "source")
        self.assertIn("Center for New Testament Restoration", editions["srgrc"].attribution)

    def test_comparison_metadata_carries_source_provenance(self) -> None:
        metadata = comparison_edition_metadata(
            "srgrc",
            name="Translation B",
            language="en",
            role="translation",
            manifest=Path(__file__).parents[1] / "sources.json",
        )
        self.assertEqual(metadata["language"], "grc")
        self.assertEqual(metadata["role"], "source")
        self.assertEqual(metadata["license"], "CC-BY-4.0")
        self.assertIn("Center for New Testament Restoration", metadata["attribution"])

    def test_atlas_manifest_exposes_book_and_chapter_summaries(self) -> None:
        manifest = json.loads((Path(__file__).parents[1] / "web/public/data/webp-bsb/manifest.json").read_text(encoding="utf-8"))
        self.assertIn("score", manifest["summary"])
        self.assertIn("statuses", manifest["summary"])
        genesis = next(book for book in manifest["books"] if book["id"] == "GEN")
        self.assertIn("score", genesis)
        self.assertGreater(len(genesis["chapters"]), 1)
        self.assertIn("coverage", genesis["chapters"][0])
        self.assertIn("score", genesis["chapters"][0])

    def test_partition_preserves_passage_granularity(self) -> None:
        from scripts.partition_comparison import main as partition_main

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "comparison.json"
            output_dir = root / "partitioned"
            source.write_text(
                json.dumps(
                    {
                        "schemaVersion": 1,
                        "metadata": {
                            "leftEdition": {"id": "a", "name": "A"},
                            "rightEdition": {"id": "b", "name": "B"},
                            "scope": {"books": ["JHN"], "unit": "multi-verse-window"},
                            "metric": {"distanceField": "lexicalDistance", "label": "window"},
                            "alignment": {},
                        },
                        "units": [
                            {
                                "id": "JHN-1-1-2",
                                "book": "JHN",
                                "chapter": 1,
                                "verse": "1-2",
                                "reference": "JHN 1:1–JHN 1:2",
                                "status": "matched",
                                "lexicalDistance": 0.2,
                                "wordingDistance": 0.1,
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            with patch.object(sys, "argv", ["partition_comparison.py", str(source), "--output-dir", str(output_dir)]):
                partition_main()
            manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
            payload = json.loads((output_dir / "JHN.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["comparison"]["scope"]["unit"], "multi-verse-window")
            self.assertEqual(payload["metadata"]["scope"]["unit"], "multi-verse-window")

    def test_committed_passage_manifest_is_full_corpus(self) -> None:
        manifest = json.loads(
            (Path(__file__).parents[1] / "web/public/data/webp-bsb-windows-2/manifest.json").read_text(encoding="utf-8")
        )
        self.assertEqual(manifest["comparison"]["scope"]["unit"], "multi-verse-window")
        self.assertEqual(len(manifest["books"]), 66)
        self.assertEqual(manifest["summary"]["scoredUnits"], 15230)

    def test_multi_verse_windows_are_separate_and_preserve_gaps(self) -> None:
        units = [
            {"id": "JHN-1-1", "order": 0, "book": "JHN", "chapter": 1, "verse": "1", "reference": "JHN 1:1", "status": "matched", "leftText": "In the beginning.", "rightText": "At the start."},
            {"id": "JHN-1-2", "order": 1, "book": "JHN", "chapter": 1, "verse": "2", "reference": "JHN 1:2", "status": "matched", "leftText": "The Word was there.", "rightText": "The Word existed."},
            {"id": "JHN-1-3", "order": 2, "book": "JHN", "chapter": 1, "verse": "3", "reference": "JHN 1:3", "status": "missing-right", "leftText": "All things were made.", "rightText": None},
        ]
        windows = build_windows(units, window_size=2, stride=1)
        self.assertEqual(len(windows), 2)
        self.assertEqual(windows[0]["status"], "matched")
        self.assertEqual(windows[0]["windowSize"], 2)
        self.assertEqual(windows[1]["status"], "unresolved")
        self.assertIsNone(windows[1]["lexicalDistance"])


if __name__ == "__main__":
    unittest.main()
