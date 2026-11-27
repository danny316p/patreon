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
    rotate_crop,
    safe_filename_text,
    stamp_shape_mask,
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

    def test_clockwise_rotation_preserves_full_crop(self):
        image = np.zeros((20, 40, 3), dtype=np.uint8)
        image[0, 39] = (255, 0, 0)
        rotated, _ = rotate_crop(image, 90)
        self.assertEqual(rotated.shape[:2], (40, 20))
        self.assertEqual(rotated[39, 19, 0], 255)

    def test_irregular_stamp_mask_follows_ink_silhouette(self):
        image = np.full((300, 400, 3), 255, dtype=np.uint8)
        color = (210, 220, 225)
        outline = np.array(
            [[140, 90], [260, 90], [260, 210], [230, 210],
             [230, 140], [170, 140], [170, 210], [140, 210]],
            dtype=np.int32,
        )
        cv2.fillPoly(image, [outline], color)
        region = find_stamp_regions(image)[0]
        _, _, width, height = region
        mask = stamp_shape_mask(image, region, 0)

        self.assertEqual(mask.shape, (height, width))
        self.assertEqual(mask[height // 4, width // 2], 255)
        self.assertEqual(mask[3 * height // 4, width // 2], 0)

    def test_groups_fragmented_ink_within_one_stamp(self):
        image = np.full((300, 400, 3), 255, dtype=np.uint8)
        color = (210, 220, 225)
        cv2.ellipse(image, (200, 150), (110, 75), 0, 0, 300, color, 8)
        cv2.putText(
            image, "ENTRY", (165, 155), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2
        )

        regions = find_stamp_regions(image)

        self.assertEqual(len(regions), 1)

    def test_mask_includes_inside_of_an_incomplete_round_stamp(self):
        image = np.full((300, 400, 3), 255, dtype=np.uint8)
        color = (210, 220, 225)
        cv2.ellipse(image, (200, 150), (110, 75), 0, 0, 300, color, 8)
        region = find_stamp_regions(image)[0]
        _, _, width, height = region
        mask = stamp_shape_mask(image, region, 0)

        self.assertEqual(mask[height // 2, width // 2], 255)


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
                count = extract_page(
                    page_path, output_dir, 0.04, False, "eng", 0, False
                )

            self.assertEqual(count, 1)
            output_path = output_dir / "page-stamp-01-PARIS-2025.jpg"
            self.assertTrue(output_path.is_file())
            self.assertIsNotNone(cv2.imread(str(output_path)))


if __name__ == "__main__":
    unittest.main()
