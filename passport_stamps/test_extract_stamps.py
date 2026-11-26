import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import cv2
import numpy as np

from extract_stamps import (
    expand_region,
    extract_page,
    find_stamp_regions,
    safe_filename_text,
)


class FilenameTests(unittest.TestCase):
    def test_sanitizes_ocr_text_for_filenames(self):
        self.assertEqual(
            safe_filename_text("  PARIS / 12:34\nFRANCE? "),
            "PARIS-1234-FRANCE",
        )

    def test_limits_ocr_text_length(self):
        self.assertEqual(safe_filename_text("A" * 100), "A" * 64)

    def test_empty_ocr_text_stays_empty(self):
        self.assertEqual(safe_filename_text(" \n "), "")


class CropTests(unittest.TestCase):
    def test_padding_is_clipped_to_image_boundaries(self):
        self.assertEqual(
            expand_region((2, 4, 20, 10), 100, 100, 0.1),
            (0, 3, 24, 15),
        )

    def test_padding_zero_preserves_region(self):
        self.assertEqual(
            expand_region((12, 14, 20, 10), 100, 100, 0),
            (12, 14, 32, 24),
        )


class ExtractionTests(unittest.TestCase):
    def test_detects_colored_stamp_and_saves_ocr_named_jpg(self):
        image = np.full((400, 500, 3), 255, dtype=np.uint8)
        cv2.rectangle(image, (100, 80), (300, 220), (180, 0, 0), 12)
        self.assertEqual(len(find_stamp_regions(image)), 1)

        with tempfile.TemporaryDirectory() as directory:
            page_path = Path(directory) / "page.jpg"
            output_dir = Path(directory) / "stamps"
            self.assertTrue(cv2.imwrite(str(page_path), image))
            with patch("extract_stamps.ocr_text", return_value="PARIS 2025"):
                count = extract_page(page_path, output_dir, 0, False, "eng")

            self.assertEqual(count, 1)
            output_path = output_dir / "page-stamp-01-PARIS-2025.jpg"
            self.assertTrue(output_path.is_file())
            self.assertIsNotNone(cv2.imread(str(output_path)))


if __name__ == "__main__":
    unittest.main()
