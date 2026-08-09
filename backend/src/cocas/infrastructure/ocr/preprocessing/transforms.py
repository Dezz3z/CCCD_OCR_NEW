"""The 9 preprocessing transforms of §7.4.1, as pure functions on BGR arrays.

Each function takes an array and returns a NEW array — nothing is modified in
place, which is what lets `LazyPreprocessedImageSet` hand out `v0` unchanged
forever (§12.4 invariant).

Only the four `preproc.*` keys listed in §4.4 `system_setting` are runtime
configuration (they arrive on `PreprocessProfile`). The remaining thresholds
below are adapter tuning constants, deliberately not DB-configurable.
"""
from __future__ import annotations

import cv2
import numpy as np

from cocas.domain.ports.ocr import ImageQuality

from .image_data import BgrArray

# --- Transform 3: perspective warp -------------------------------------------
CARD_FRAME_WIDTH = 1012
CARD_FRAME_HEIGHT = 638
CARD_ASPECT_MIN = 1.45
CARD_ASPECT_MAX = 1.72
CARD_MIN_AREA_RATIO = 0.25
CONTOUR_DETECTION_LONG_EDGE = 800

# --- Transform 4: 180° detection via the TD1 MRZ block ------------------------
MRZ_MIN_WIDTH_FRACTION = 0.80
MRZ_LINE_HEIGHT_MIN = 0.010
MRZ_LINE_HEIGHT_MAX = 0.075
MRZ_LINE_GAP_MIN = 0.04
MRZ_LINE_GAP_MAX = 0.12
MRZ_GAP_TOLERANCE = 0.025
MRZ_HEIGHT_TOLERANCE = 0.020
MRZ_EDGE_ZONE = 0.35

# --- Transform 5: deskew ------------------------------------------------------
DESKEW_MAX_ANGLE = 15.0

# --- Transform 7: lighting ----------------------------------------------------
CLAHE_CLIP_LIMIT = 2.0
EXPOSURE_EXPONENT_MIN = 0.6
EXPOSURE_EXPONENT_MAX = 1.6

# --- Transform 8: sharpen -----------------------------------------------------
SHARPEN_LAPLACIAN_THRESHOLD = 120.0

# --- Transform 9: deglare -----------------------------------------------------
GLARE_VALUE_THRESHOLD = 250

# --- Quality flags ------------------------------------------------------------
BLUR_VARIANCE_FLOOR = 100.0
DARK_MEAN_FLOOR = 70.0
BRIGHT_MEAN_CEILING = 200.0
GLARE_RATIO_CEILING = 0.02
LOW_RESOLUTION_SHORT_EDGE = 600


def apply_exif_orientation(image: BgrArray, orientation: int | None) -> BgrArray:
    """Transform 1 — apply the EXIF `Orientation` value (1–8) captured at upload.

    A scan with no EXIF passes `None` and is left alone rather than failing.
    """
    if orientation is None or orientation == 1:
        return image
    if orientation == 2:
        return cv2.flip(image, 1)
    if orientation == 3:
        return cv2.rotate(image, cv2.ROTATE_180)
    if orientation == 4:
        return cv2.flip(image, 0)
    if orientation == 5:
        return cv2.rotate(cv2.flip(image, 1), cv2.ROTATE_90_COUNTERCLOCKWISE)
    if orientation == 6:
        return cv2.rotate(image, cv2.ROTATE_90_CLOCKWISE)
    if orientation == 7:
        return cv2.rotate(cv2.flip(image, 1), cv2.ROTATE_90_CLOCKWISE)
    if orientation == 8:
        return cv2.rotate(image, cv2.ROTATE_90_COUNTERCLOCKWISE)
    return image


def limit_long_edge(image: BgrArray, target_long_edge: int) -> BgrArray:
    """Transform 2 — scale so the long edge equals `target_long_edge`."""
    height, width = image.shape[:2]
    long_edge = max(height, width)
    if long_edge == target_long_edge:
        return image
    scale = target_long_edge / long_edge
    interpolation = cv2.INTER_AREA if scale < 1 else cv2.INTER_CUBIC
    new_size = (max(1, round(width * scale)), max(1, round(height * scale)))
    resized: BgrArray = cv2.resize(image, new_size, interpolation=interpolation)
    return resized


def _order_quad(points: np.ndarray) -> np.ndarray:
    """Order 4 points as top-left, top-right, bottom-right, bottom-left."""
    coordinate_sum = points.sum(axis=1)
    coordinate_diff = np.diff(points, axis=1).ravel()
    return np.array(
        [
            points[int(np.argmin(coordinate_sum))],
            points[int(np.argmin(coordinate_diff))],
            points[int(np.argmax(coordinate_sum))],
            points[int(np.argmax(coordinate_diff))],
        ],
        dtype=np.float32,
    )


def _quad_aspect(quad: np.ndarray) -> float:
    top_left, top_right, bottom_right, bottom_left = quad
    width = (
        float(np.linalg.norm(top_right - top_left))
        + float(np.linalg.norm(bottom_right - bottom_left))
    ) / 2
    height = (
        float(np.linalg.norm(bottom_left - top_left))
        + float(np.linalg.norm(bottom_right - top_right))
    ) / 2
    if height <= 0:
        return 0.0
    return width / height


def _as_landscape(quad: np.ndarray) -> np.ndarray:
    """Re-label the corners so the card's LONG edge becomes the top edge.

    Cards are routinely photographed sideways; without this the aspect guard
    rejects a perfectly good quad for being 1/1.585 instead of 1.585. Which of
    the two landscape orientations results is settled later by `is_upside_down`.
    """
    if _quad_aspect(quad) >= 1.0:
        return quad
    return np.roll(quad, -1, axis=0)


def find_card_quad(image: BgrArray) -> np.ndarray | None:
    """Locate the card's 4 corners, or None when no candidate passes the guards.

    ⭐ The aspect and area guards are what stop a table edge or the sheet of
    paper underneath the card from being warped as if it were the card (§7.4.1).
    """
    scale = min(1.0, CONTOUR_DETECTION_LONG_EDGE / max(image.shape[:2]))
    working = (
        cv2.resize(image, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
        if scale < 1.0
        else image
    )

    grayscale = cv2.cvtColor(working, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(cv2.GaussianBlur(grayscale, (5, 5), 0), 50, 150)
    edges = cv2.dilate(edges, np.ones((3, 3), np.uint8), iterations=1)
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    working_area = float(working.shape[0] * working.shape[1])
    for contour in sorted(contours, key=cv2.contourArea, reverse=True)[:8]:
        if cv2.contourArea(contour) < CARD_MIN_AREA_RATIO * working_area:
            break
        perimeter = cv2.arcLength(contour, True)
        approximation = cv2.approxPolyDP(contour, 0.02 * perimeter, True)
        if len(approximation) != 4 or not cv2.isContourConvex(approximation):
            continue
        quad = _as_landscape(_order_quad(approximation.reshape(4, 2).astype(np.float32)))
        if CARD_ASPECT_MIN <= _quad_aspect(quad) <= CARD_ASPECT_MAX:
            return quad / scale
    return None


def full_frame_quad(image: BgrArray) -> np.ndarray | None:
    """The image's own corners, when the image IS the card (already cropped).

    Uploads cropped tight to the card have no outline for `find_card_quad` to
    latch onto, yet they are exactly the case where ZONE extraction works best.
    The aspect guard is the same one, applied to the frame itself.
    """
    height, width = image.shape[:2]
    quad = _as_landscape(
        np.array(
            [[0, 0], [width - 1, 0], [width - 1, height - 1], [0, height - 1]], dtype=np.float32
        )
    )
    if not CARD_ASPECT_MIN <= _quad_aspect(quad) <= CARD_ASPECT_MAX:
        return None
    return quad


def warp_to_card_frame(image: BgrArray, quad: np.ndarray) -> tuple[BgrArray, np.ndarray]:
    """Transform 3 — rectify `quad` onto the canonical 1012x638 frame."""
    destination = np.array(
        [
            [0, 0],
            [CARD_FRAME_WIDTH - 1, 0],
            [CARD_FRAME_WIDTH - 1, CARD_FRAME_HEIGHT - 1],
            [0, CARD_FRAME_HEIGHT - 1],
        ],
        dtype=np.float32,
    )
    matrix = cv2.getPerspectiveTransform(quad, destination)
    warped: BgrArray = cv2.warpPerspective(
        image, matrix, (CARD_FRAME_WIDTH, CARD_FRAME_HEIGHT)
    )
    return warped, matrix


def _wide_text_bands(image: BgrArray) -> list[tuple[float, float]]:
    """Full-width lines of text as (relative y-centre, relative height), top-down.

    Measured by row-density projection rather than contours: on a rectified
    card the frame border touches every line, so connected components merge
    into one useless blob.
    """
    height, width = image.shape[:2]
    grayscale = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    gradient = cv2.morphologyEx(
        grayscale, cv2.MORPH_GRADIENT, cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    )
    _, binary = cv2.threshold(gradient, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
    joined = cv2.morphologyEx(
        binary,
        cv2.MORPH_CLOSE,
        cv2.getStructuringElement(cv2.MORPH_RECT, (max(3, width // 25), 1)),
    )

    dense_rows = (joined.mean(axis=1) / 255.0) >= MRZ_MIN_WIDTH_FRACTION
    padded = np.concatenate(([False], dense_rows, [False]))
    starts = np.flatnonzero(~padded[:-1] & padded[1:])
    ends = np.flatnonzero(padded[:-1] & ~padded[1:])

    bands = []
    for start, end in zip(starts, ends, strict=True):
        relative_height = (end - start) / height
        if MRZ_LINE_HEIGHT_MIN <= relative_height <= MRZ_LINE_HEIGHT_MAX:
            bands.append((float((start + end) / 2 / height), float(relative_height)))
    return bands


def find_mrz_candidates(image: BgrArray) -> list[float]:
    """Relative y-centres of every three-line block that could be the TD1 MRZ.

    Three full-width lines of equal height at even spacing. ⚠️ The address
    block on the back of a CCCD matches that description too, which is why
    this returns every candidate instead of pretending to know which is which.
    """
    bands = _wide_text_bands(image)
    candidates = []
    for index in range(len(bands) - 2):
        centres = [bands[index + offset][0] for offset in range(3)]
        heights = [bands[index + offset][1] for offset in range(3)]
        gaps = (centres[1] - centres[0], centres[2] - centres[1])
        if not all(MRZ_LINE_GAP_MIN <= gap <= MRZ_LINE_GAP_MAX for gap in gaps):
            continue
        if abs(gaps[0] - gaps[1]) > MRZ_GAP_TOLERANCE:
            continue
        if max(heights) - min(heights) > MRZ_HEIGHT_TOLERANCE:
            continue
        candidates.append(float(sum(centres) / 3))
    return candidates


def is_upside_down(image: BgrArray) -> bool:
    """Transform 4 — decide whether the (already rectified) card is rotated 180°.

    ⭐ Acts only on an UNAMBIGUOUS MRZ: exactly one three-line block hugging
    one edge of the card. A back showing such a block at both edges (its MRZ
    and its address block) is left alone — flipping a correctly-oriented card
    is a far worse outcome than leaving an inverted one for the OCR engine.

    Only the MRZ signal of §7.4.1 exists before the engine adapter, so fronts
    are never rotated here; the PaddleOCR `cls` vote and the
    text-count-at-0°-vs-180° vote join in with the engine.
    """
    at_edges = [
        centre
        for centre in find_mrz_candidates(image)
        if centre < MRZ_EDGE_ZONE or centre > 1.0 - MRZ_EDGE_ZONE
    ]
    if len(at_edges) != 1:
        return False
    return at_edges[0] < 0.5


def rotate_180(image: BgrArray) -> BgrArray:
    rotated: BgrArray = cv2.rotate(image, cv2.ROTATE_180)
    return rotated


def estimate_skew_angle(image: BgrArray, max_angle: float = DESKEW_MAX_ANGLE) -> float:
    """Median tilt of the dominant near-horizontal lines, in degrees."""
    grayscale = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(grayscale, 50, 150)
    segments = cv2.HoughLinesP(
        edges, 1, np.pi / 360, threshold=100, minLineLength=image.shape[1] // 4, maxLineGap=20
    )
    if segments is None:
        return 0.0
    angles = []
    for x1, y1, x2, y2 in segments.reshape(-1, 4):
        angle = float(np.degrees(np.arctan2(float(y2 - y1), float(x2 - x1))))
        if abs(angle) <= max_angle:
            angles.append(angle)
    if not angles:
        return 0.0
    return float(np.median(angles))


def deskew(image: BgrArray, max_angle: float = DESKEW_MAX_ANGLE) -> tuple[BgrArray, float]:
    """Transform 5 — rotate out a small tilt, capped at ±`max_angle`."""
    angle = estimate_skew_angle(image, max_angle)
    if abs(angle) < 0.2:
        return image, 0.0
    height, width = image.shape[:2]
    matrix = cv2.getRotationMatrix2D((width / 2, height / 2), angle, 1.0)
    rotated: BgrArray = cv2.warpAffine(
        image, matrix, (width, height), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE
    )
    return rotated, angle


def denoise(image: BgrArray, method: str) -> BgrArray:
    """Transform 6 — bilateral by default; parameters stay conservative.

    Over-smoothing erases Vietnamese diacritics, which costs more accuracy
    than the noise it removes.
    """
    if method == "nlmeans":
        cleaned: BgrArray = cv2.fastNlMeansDenoisingColored(image, None, 5, 5, 7, 21)
        return cleaned
    filtered: BgrArray = cv2.bilateralFilter(image, 7, 50, 50)
    return filtered


def equalize_lighting(image: BgrArray, clip_limit: float = CLAHE_CLIP_LIMIT) -> BgrArray:
    """Transform 7 — CLAHE on the L channel of LAB, then automatic gamma."""
    lightness, green_red, blue_yellow = cv2.split(cv2.cvtColor(image, cv2.COLOR_BGR2LAB))
    clahe = cv2.createCLAHE(clipLimit=clip_limit, tileGridSize=(8, 8))
    balanced = cv2.cvtColor(
        cv2.merge((clahe.apply(lightness), green_red, blue_yellow)), cv2.COLOR_LAB2BGR
    )

    mean_luminance = float(cv2.cvtColor(balanced, cv2.COLOR_BGR2GRAY).mean())
    if not 0.0 < mean_luminance < 255.0:
        return balanced
    # Exponent < 1 brightens, > 1 darkens; solving for a mid-grey mean of 0.5.
    exponent = float(
        np.clip(
            np.log(0.5) / np.log(mean_luminance / 255.0),
            EXPOSURE_EXPONENT_MIN,
            EXPOSURE_EXPONENT_MAX,
        )
    )
    if abs(exponent - 1.0) < 0.05:
        return balanced
    table = np.array(
        [((value / 255.0) ** exponent) * 255 for value in range(256)], dtype=np.uint8
    )
    corrected: BgrArray = cv2.LUT(balanced, table)
    return corrected


def laplacian_variance(image: BgrArray) -> float:
    grayscale = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    return float(cv2.Laplacian(grayscale, cv2.CV_64F).var())


def sharpen_if_soft(
    image: BgrArray, laplacian_threshold: float = SHARPEN_LAPLACIAN_THRESHOLD
) -> BgrArray:
    """Transform 8 — unsharp mask, ⭐ only when the image is measurably soft.

    Sharpening an already-crisp image LOWERS recognition accuracy, so the
    threshold is a precondition, not a tuning knob.
    """
    if laplacian_variance(image) >= laplacian_threshold:
        return image
    blurred = cv2.GaussianBlur(image, (0, 0), 3)
    sharpened: BgrArray = cv2.addWeighted(image, 1.5, blurred, -0.5, 0)
    return sharpened


def glare_ratio(image: BgrArray) -> float:
    value_channel = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)[:, :, 2]
    return float((value_channel > GLARE_VALUE_THRESHOLD).mean())


def remove_glare(image: BgrArray) -> BgrArray:
    """Transform 9 — inpaint saturated blobs. Off by default (`preproc.deglare_enabled`)."""
    value_channel = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)[:, :, 2]
    mask = (value_channel > GLARE_VALUE_THRESHOLD).astype(np.uint8) * 255
    if not mask.any():
        return image
    mask = cv2.dilate(mask, np.ones((5, 5), np.uint8), iterations=1)
    repaired: BgrArray = cv2.inpaint(image, mask, 3, cv2.INPAINT_TELEA)
    return repaired


def binarize(image: BgrArray) -> BgrArray:
    """Adaptive binarization for the MRZ channel (variant `v4`).

    Kept 3-channel so every variant is interchangeable at the port boundary.
    """
    grayscale = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    binary = cv2.adaptiveThreshold(
        grayscale, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 15
    )
    restored: BgrArray = cv2.cvtColor(binary, cv2.COLOR_GRAY2BGR)
    return restored


def assess_quality(image: BgrArray) -> ImageQuality:
    """Score the image 0..1 and flag what a user could fix by re-shooting."""
    sharpness = laplacian_variance(image)
    brightness = float(cv2.cvtColor(image, cv2.COLOR_BGR2GRAY).mean())
    glare = glare_ratio(image)
    short_edge = min(image.shape[:2])

    flags: list[str] = []
    if sharpness < BLUR_VARIANCE_FLOOR:
        flags.append("BLURRY")
    if brightness < DARK_MEAN_FLOOR:
        flags.append("DARK")
    if brightness > BRIGHT_MEAN_CEILING:
        flags.append("BRIGHT")
    if glare > GLARE_RATIO_CEILING:
        flags.append("GLARE")
    if short_edge < LOW_RESOLUTION_SHORT_EDGE:
        flags.append("LOW_RESOLUTION")

    sharpness_score = min(sharpness / 300.0, 1.0)
    exposure_score = 1.0 - min(abs(brightness - 128.0) / 128.0, 1.0)
    glare_score = 1.0 - min(glare / 0.10, 1.0)
    score = 0.5 * sharpness_score + 0.3 * exposure_score + 0.2 * glare_score
    return ImageQuality(score=round(float(np.clip(score, 0.0, 1.0)), 3), flags=flags)
