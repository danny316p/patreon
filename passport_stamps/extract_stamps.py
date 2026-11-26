#!/usr/bin/env python3
"""Extract passport stamps from scanned pages and name each crop with OCR text.

Requires OpenCV, pytesseract, and the Tesseract OCR executable. See README.md
in this directory for installation and usage.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

try:
    import cv2
    import pytesseract
except ImportError as exc:
    missing = exc.name or "a required package"
    raise SystemExit(
        f"Missing {missing}. Install the Python requirements with: "
        "python -m pip install -r passport_stamps/requirements.txt"
    ) from exc


IMAGE_EXTENSIONS = {".bmp", ".jpeg", ".jpg", ".png", ".tif", ".tiff", ".webp"}


def safe_filename_text(text: str, limit: int = 64) -> str:
    """Make OCR text safe and reasonably short for use in a filename."""
    text = re.sub(r"\s+", "-", text.strip())
    text = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", text)
    text = re.sub(r"[^\w.-]", "", text, flags=re.UNICODE)
    text = re.sub(r"-{2,}", "-", text).strip(" .-_")
    return text[:limit].rstrip(" .-_")


def find_stamp_regions(image) -> list[tuple[int, int, int, int]]:
    """Find likely colored stamp regions as (x, y, width, height) rectangles."""
    height, width = image.shape[:2]
    minimum_dimension = min(height, width)
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    saturation_mask = cv2.inRange(hsv, (0, 35, 35), (180, 255, 255))

    kernel_size = max(3, round(minimum_dimension * 0.008))
    if kernel_size % 2 == 0:
        kernel_size += 1
    kernel = cv2.getStructuringElement(
        cv2.MORPH_RECT, (kernel_size, kernel_size)
    )
    closed = cv2.morphologyEx(saturation_mask, cv2.MORPH_CLOSE, kernel)
    contours, _ = cv2.findContours(
        closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
    )

    regions = []
    page_area = width * height
    for contour in contours:
        x, y, box_width, box_height = cv2.boundingRect(contour)
        area = box_width * box_height
        aspect_ratio = box_width / box_height
        if (
            area < page_area * 0.0002
            or area > page_area * 0.2
            or box_width < width * 0.02
            or box_height < height * 0.02
            or not 0.2 <= aspect_ratio <= 5
        ):
            continue
        regions.append((x, y, box_width, box_height))
    return sorted(regions, key=lambda box: (box[1], box[0]))


def expand_region(
    region: tuple[int, int, int, int],
    image_width: int,
    image_height: int,
    padding: float,
) -> tuple[int, int, int, int]:
    x, y, width, height = region
    pad_x = round(width * padding)
    pad_y = round(height * padding)
    left = max(0, x - pad_x)
    top = max(0, y - pad_y)
    right = min(image_width, x + width + pad_x)
    bottom = min(image_height, y + height + pad_y)
    return left, top, right, bottom


def select_regions(image) -> list:
    print(
        "Select stamp rectangles in the image; press Enter when finished."
    )
    selected = cv2.selectROIs(
        "Select stamp regions - press Enter when finished",
        image,
        showCrosshair=True,
        fromCenter=False,
    )
    cv2.destroyAllWindows()
    return [tuple(map(int, region)) for region in selected if region[2] and region[3]]


def ocr_text(crop, language: str) -> str:
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    scale = max(1, round(1200 / max(gray.shape)))
    if scale > 1:
        gray = cv2.resize(
            gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC
        )
    return pytesseract.image_to_string(
        gray, config="--psm 11", lang=language
    ).strip()


def unique_output_path(directory: Path, stem: str) -> Path:
    candidate = directory / f"{stem}.jpg"
    suffix = 2
    while candidate.exists():
        candidate = directory / f"{stem}-{suffix}.jpg"
        suffix += 1
    return candidate


def extract_page(
    image_path: Path, output_dir: Path, padding: float, manual: bool, language: str
) -> int:
    image = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
    if image is None:
        raise RuntimeError(f"Could not read image: {image_path}")
    height, width = image.shape[:2]
    if manual:
        regions = select_regions(image)
    else:
        regions = find_stamp_regions(image)
    if not regions:
        print(f"No stamp regions selected or detected in {image_path.name}.")
        return 0

    output_dir.mkdir(parents=True, exist_ok=True)
    saved = 0
    for index, region in enumerate(regions, start=1):
        left, top, right, bottom = expand_region(region, width, height, padding)
        crop = image[top:bottom, left:right]
        text = safe_filename_text(ocr_text(crop, language))
        name_parts = [image_path.stem, f"stamp-{index:02d}"]
        if text:
            name_parts.append(text)
        output_path = unique_output_path(output_dir, "-".join(name_parts))
        if not cv2.imwrite(str(output_path), crop):
            raise RuntimeError(f"Could not save stamp image: {output_path}")
        print(f"Saved {output_path.name}")
        saved += 1
    return saved


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "input",
        type=Path,
        help="A scanned page image or a directory of scanned page images.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Directory for extracted JPGs (default: INPUT/passport_stamps).",
    )
    parser.add_argument(
        "--padding",
        type=float,
        default=0.04,
        help="Extra crop margin as a fraction of stamp size (default: 0.04).",
    )
    parser.add_argument(
        "--manual",
        action="store_true",
        help="Select stamp rectangles manually instead of using automatic detection.",
    )
    parser.add_argument(
        "--tesseract-cmd",
        help="Path to the Tesseract executable, if it is not on PATH.",
    )
    parser.add_argument(
        "--lang",
        default="eng",
        help="Tesseract language code(s), such as eng or eng+fra (default: eng).",
    )
    args = parser.parse_args()

    if not 0 <= args.padding <= 0.5:
        parser.error("--padding must be between 0 and 0.5")
    if args.tesseract_cmd:
        pytesseract.pytesseract.tesseract_cmd = args.tesseract_cmd
    if not args.input.exists():
        parser.error(f"Input does not exist: {args.input}")
    if args.input.is_file():
        images = [args.input]
        default_output = args.input.parent / "passport_stamps"
    elif args.input.is_dir():
        images = sorted(
            path
            for path in args.input.iterdir()
            if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
        )
        default_output = args.input / "passport_stamps"
    else:
        parser.error(f"Input is neither a file nor a directory: {args.input}")
    if not images:
        parser.error(f"No supported image files found in {args.input}")

    output_dir = args.output or default_output
    try:
        count = sum(
            extract_page(image, output_dir, args.padding, args.manual, args.lang)
            for image in images
        )
    except (OSError, RuntimeError, pytesseract.TesseractNotFoundError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print(f"Extracted {count} stamp(s) from {len(images)} page(s) into {output_dir}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
