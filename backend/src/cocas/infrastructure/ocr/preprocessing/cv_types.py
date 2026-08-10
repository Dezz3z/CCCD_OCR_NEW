"""Array aliases and the narrowing casts that undo cv2's widened stub types.

OpenCV's bundled stubs type every image-returning call as `cv2.typing.MatLike`
— `ndarray[Any, dtype[integer | floating]]`, the widest thing any overload of
any function could hand back. The calls used in this package all preserve the
dtype of their input (uint8 in → uint8 out), so that widening is a limitation
of the stubs, not a fact about the values. But `ndarray` is covariant in its
dtype, so the widened result will not go back into a `BgrArray` annotation, and
mypy reports an error at every such assignment.

The helpers below are where that gets undone — once, with the reasoning
attached, and narrowly typed so they only accept a cv2 result. A blanket
`# type: ignore` on the same lines would silence a genuine dtype mistake too.

⚠️ Each helper is an unchecked `cast`: it *asserts* the dtype rather than
verifying it. Only apply one to a call known to preserve its input dtype —
every cv2 call in this package does; `astype` and array arithmetic do not.

`BgrArray` itself stays in `image_data.py`, which imports numpy and nothing
else: it is the module Domain's `ImageData` Protocol is satisfied by (§7.3),
and it is deliberately free of any cv2 dependency.
"""
from __future__ import annotations

from typing import cast

import numpy as np
from cv2.typing import MatLike
from numpy.typing import NDArray

from .image_data import BgrArray

# Single-channel 8-bit: a mask, or a grayscale/binarized rendition. Identical
# to `BgrArray` as far as mypy is concerned — channel count is not in the type
# — so the distinction is for the reader, not the checker.
GrayArray = NDArray[np.uint8]

# An (N, 2) array of x/y coordinates: the card's 4 corners, a contour.
PointArray = NDArray[np.float32]

# A 2x3 affine or 3x3 perspective transform matrix, as cv2 builds them.
WarpMatrix = NDArray[np.float64]


def as_bgr(result: MatLike) -> BgrArray:
    """Narrow a dtype-preserving cv2 result back to the 3-channel BGR alias."""
    return cast(BgrArray, result)


def as_optional_bgr(result: MatLike | None) -> BgrArray | None:
    """Same, for `cv2.imdecode` — which returns None on a buffer it cannot
    decode, although its stub promises a plain `MatLike`."""
    return cast("BgrArray | None", result)


def as_gray(result: MatLike) -> GrayArray:
    """Narrow a dtype-preserving cv2 result back to the single-channel alias."""
    return cast(GrayArray, result)


def as_points(result: MatLike) -> PointArray:
    """Narrow a cv2 coordinate result to the float32 point alias."""
    return cast(PointArray, result)


def as_matrix(result: MatLike) -> WarpMatrix:
    """Narrow a cv2 transform matrix (`getPerspectiveTransform`, …) to float64."""
    return cast(WarpMatrix, result)
