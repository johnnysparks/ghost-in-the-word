import tempfile
import unittest
from pathlib import Path

from ghost_in_word.alignment import align_segments
from ghost_in_word.models import TextSegment
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


if __name__ == "__main__":
    unittest.main()
