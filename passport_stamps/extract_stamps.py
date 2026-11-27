#!/usr/bin/env python3
"""Extract passport stamps from scanned pages and name each crop with OCR text.

Requires OpenCV, pytesseract, and the Tesseract OCR executable. See README.md
in this directory for installation and usage.
"""

from __future__ import annotations

import argparse
import math
import re
import sys
from pathlib import Path

try:
    import cv2
    import numpy as np
    import pytesseract
except ImportError as exc:
    missing = exc.name or "a required package"
    raise SystemExit(
        f"Missing {missing}. Install the Python requirements with: "
        "python3 -m pip install -r passport_stamps/requirements.txt"
    ) from exc


IMAGE_EXTENSIONS = {".bmp", ".jpeg", ".jpg", ".png", ".tif", ".tiff", ".webp"}


def safe_filename_text(text: str, limit: int = 64) -> str:
    """Make OCR text safe and reasonably short for use in a filename."""
    text = re.sub(r"\s+", "-", text.strip())
    text = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", text)
    text = re.sub(r"[^\w.-]", "", text, flags=re.UNICODE)
    text = re.sub(r"-{2,}", "-", text).strip(" .-_")
    return text[:limit].rstrip(" .-_")


def colored_ink_mask(image):
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    saturation = hsv[:, :, 1]
    otsu_threshold, _ = cv2.threshold(
        saturation, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU
    )
    threshold = max(10, min(35, round(otsu_threshold * 0.5)))
    return cv2.inRange(hsv, (0, threshold, 35), (180, 255, 255))


def find_stamp_regions(image) -> list[tuple[int, int, int, int]]:
    """Find likely colored stamp regions as (x, y, width, height) rectangles."""
    height, width = image.shape[:2]
    minimum_dimension = min(height, width)
    saturation_mask = colored_ink_mask(image)

    kernel_size = max(3, round(minimum_dimension * 0.012))
    if kernel_size % 2 == 0:
        kernel_size += 1
    kernel = cv2.getStructuringElement(
        cv2.MORPH_ELLIPSE, (kernel_size, kernel_size)
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
        ink_area = cv2.countNonZero(
            saturation_mask[y : y + box_height, x : x + box_width]
        )
        if (
            area < page_area * 0.00002
            or area > page_area * 0.35
            or ink_area < max(20, page_area * 0.00002)
            or not 0.12 <= aspect_ratio <= 8.5
        ):
            continue
        regions.append((x, y, box_width, box_height))

    merged = []
    for region in regions:
        x, y, box_width, box_height = region
        right, bottom = x + box_width, y + box_height
        index = 0
        while index < len(merged):
            other_x, other_y, other_width, other_height = merged[index]
            other_right = other_x + other_width
            other_bottom = other_y + other_height
            overlaps = (
                x <= other_right
                and right >= other_x
                and y <= other_bottom
                and bottom >= other_y
            )
            if overlaps:
                x = min(x, other_x)
                y = min(y, other_y)
                right = max(right, other_right)
                bottom = max(bottom, other_bottom)
                merged.pop(index)
                index = 0
            else:
                index += 1
        merged.append((x, y, right - x, bottom - y))
    return sorted(merged, key=lambda box: (box[1], box[0]))


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


def stamp_shape_mask(image, region, padding: float):
    """Build a filled, irregular silhouette around colored stamp ink."""
    height, width = image.shape[:2]
    left, top, right, bottom = expand_region(region, width, height, padding)
    ink = colored_ink_mask(image)
    local_ink = ink[top:bottom, left:right]
    if cv2.countNonZero(local_ink) == 0:
        return None

    close_size = max(3, round(min(local_ink.shape[:2]) * 0.06))
    if close_size % 2 == 0:
        close_size += 1
    kernel = cv2.getStructuringElement(
        cv2.MORPH_ELLIPSE, (close_size, close_size)
    )
    grouped = cv2.morphologyEx(local_ink, cv2.MORPH_CLOSE, kernel)
    contours, _ = cv2.findContours(
        grouped, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
    )
    if not contours:
        return None
    mask = cv2.drawContours(
        np.zeros_like(local_ink), contours, -1, 255, thickness=cv2.FILLED
    )
    points = cv2.findNonZero(local_ink)
    hull = cv2.convexHull(points)
    hull_mask = cv2.drawContours(
        np.zeros_like(local_ink), [hull], -1, 255, thickness=cv2.FILLED
    )
    if cv2.countNonZero(mask) < cv2.countNonZero(hull_mask) * 0.5:
        return hull_mask
    return mask


def rotate_crop(crop, clockwise_degrees: float, mask=None):
    """Rotate a crop clockwise without clipping its corners."""
    angle = clockwise_degrees % 360
    if angle == 0:
        return crop, mask

    height, width = crop.shape[:2]
    radians = math.radians(angle)
    cosine = abs(math.cos(radians))
    sine = abs(math.sin(radians))
    output_width = max(1, math.ceil(width * cosine + height * sine - 1e-9))
    output_height = max(1, math.ceil(height * cosine + width * sine - 1e-9))
    center = ((width - 1) / 2, (height - 1) / 2)
    matrix = cv2.getRotationMatrix2D(center, -angle, 1)
    matrix[0, 2] += (output_width - 1) / 2 - center[0]
    matrix[1, 2] += (output_height - 1) / 2 - center[1]
    rotated_crop = cv2.warpAffine(
        crop,
        matrix,
        (output_width, output_height),
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(255, 255, 255),
    )
    rotated_mask = None
    if mask is not None:
        rotated_mask = cv2.warpAffine(
            mask,
            matrix,
            (output_width, output_height),
            flags=cv2.INTER_NEAREST,
            borderMode=cv2.BORDER_CONSTANT,
            borderValue=0,
        )
    return rotated_crop, rotated_mask


def read_stamp_rotation(index: int, total: int) -> float:
    while True:
        entered = input(
            f"Clockwise rotation in degrees for stamp {index}/{total} "
            "(Enter for 0): "
        ).strip()
        if not entered:
            return 0
        try:
            return float(entered)
        except ValueError:
            print("Enter a number of degrees, such as 90 or -15.")


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
    image_path: Path,
    output_dir: Path,
    padding: float,
    manual: bool,
    language: str,
    rotation: float,
    rotate_each: bool,
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
        mask = None if manual else stamp_shape_mask(image, region, padding)
        stamp_rotation = (
            read_stamp_rotation(index, len(regions)) if rotate_each else rotation
        )
        crop, mask = rotate_crop(crop, stamp_rotation, mask)
        if mask is not None:
            crop[mask == 0] = (255, 255, 255)
        text = safe_filename_text(ocr_text(crop, language))
        name_parts = [image_path.stem, f"stamp-{index:02d}"]
        if text:
            name_parts.append(text)
        if stamp_rotation % 360:
            name_parts.append(f"rotated-{stamp_rotation:g}deg")
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
        help="Select stamp regions manually instead of using automatic detection.",
    )
    parser.add_argument(
        "--rotation",
        type=float,
        default=0,
        help="Rotate every extracted stamp clockwise by this many degrees.",
    )
    parser.add_argument(
        "--rotate-each",
        action="store_true",
        help="Prompt for a clockwise rotation angle for each stamp.",
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
            extract_page(
                image,
                output_dir,
                args.padding,
                args.manual,
                args.lang,
                args.rotation,
                args.rotate_each,
            )
            for image in images
        )
    except (OSError, RuntimeError, pytesseract.TesseractNotFoundError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print(f"Extracted {count} stamp(s) from {len(images)} page(s) into {output_dir}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
