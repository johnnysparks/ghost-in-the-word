import tempfile
import unittest
from pathlib import Path

from ghost_in_word.alignment import AlignmentMapping, alignment_method, align_segments, align_with_mappings
from ghost_in_word.embeddings import cosine_distance, input_hash
from ghost_in_word.models import TextSegment
from ghost_in_word.review import select_review_items, summarize_reviews
from ghost_in_word.scoring import lexical_distance, score_units, wording_distance
from ghost_in_word.summary import summarize_units
from ghost_in_word.usfm import parse_usfm


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


if __name__ == "__main__":
    unittest.main()
