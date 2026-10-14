import tempfile
import unittest
import json
from pathlib import Path

from ghost_in_word.alignment import AlignmentMapping, alignment_method, align_segments, align_with_mappings, mapping_from_dict
from ghost_in_word.assessment import Assessment, validate_assessment_document
from ghost_in_word.embeddings import cosine_distance, input_hash
from ghost_in_word.models import TextSegment
from ghost_in_word.matrix import build_translation_matrix
from ghost_in_word.review import build_review_key, select_review_items, summarize_reviews
from ghost_in_word.reference import distance_to_reference, estimate_reference
from ghost_in_word.scoring import lexical_distance, score_units, wording_distance
from ghost_in_word.sources import load_editions
from ghost_in_word.summary import summarize_units
from ghost_in_word.usfm import parse_usfm
from ghost_in_word.windows import build_windows


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

    def test_embedding_primitives_are_deterministic(self) -> None:
        self.assertEqual(cosine_distance([1.0, 0.0], [1.0, 0.0]), 0.0)
        self.assertEqual(cosine_distance([1.0, 0.0], [0.0, 1.0]), 1.0)
        self.assertEqual(input_hash(["one", "two"]), input_hash(["one", "two"]))
        self.assertNotEqual(input_hash(["one", "two"]), input_hash(["two", "one"]))

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

    def test_committed_browser_fixture_uses_public_schema(self) -> None:
        fixture = json.loads((Path(__file__).parents[1] / "web/public/data/john-webp-bsb.json").read_text(encoding="utf-8"))
        unit = fixture["units"][0]
        self.assertIn("leftText", unit)
        self.assertIn("rightText", unit)
        self.assertNotIn("left_text", unit)
        self.assertEqual(fixture["metadata"]["leftEdition"]["language"], "en")
        self.assertEqual(fixture["metadata"]["rightEdition"]["language"], "en")

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
        self.assertLess(source_fixture["summary"]["scoredUnits"], source_fixture["summary"]["totalUnits"])

    def test_source_manifest_validates_roles_and_attribution(self) -> None:
        editions = load_editions(Path(__file__).parents[1] / "sources.json")
        self.assertEqual(editions["rv1909"].language, "es")
        self.assertEqual(editions["srgrc"].role, "source")
        self.assertIn("Center for New Testament Restoration", editions["srgrc"].attribution)

    def test_atlas_manifest_exposes_book_and_chapter_summaries(self) -> None:
        manifest = json.loads((Path(__file__).parents[1] / "web/public/data/webp-bsb/manifest.json").read_text(encoding="utf-8"))
        self.assertIn("score", manifest["summary"])
        self.assertIn("statuses", manifest["summary"])
        genesis = next(book for book in manifest["books"] if book["id"] == "GEN")
        self.assertIn("score", genesis)
        self.assertGreater(len(genesis["chapters"]), 1)
        self.assertIn("coverage", genesis["chapters"][0])
        self.assertIn("score", genesis["chapters"][0])

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
