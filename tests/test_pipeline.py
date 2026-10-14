import tempfile
import unittest
from pathlib import Path

from ghost_in_word.alignment import align_segments
from ghost_in_word.models import TextSegment
from ghost_in_word.scoring import lexical_distance, score_units, wording_distance
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


if __name__ == "__main__":
    unittest.main()
