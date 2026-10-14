import tempfile
import unittest
from pathlib import Path

from ghost_in_word.alignment import AlignmentMapping, align_segments, align_with_mappings
from ghost_in_word.embeddings import cosine_distance, input_hash
from ghost_in_word.models import TextSegment
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


if __name__ == "__main__":
    unittest.main()
