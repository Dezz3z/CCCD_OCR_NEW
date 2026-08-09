"""Numpy-backed `ImageData` — the concrete object Domain only ever sees as a Protocol (§7.3).

Domain names the shape it needs (`width`/`height`) without importing numpy or
cv2 (P-02); this module is where that shape becomes a real BGR array.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

BgrArray = NDArray[np.uint8]


@dataclass(frozen=True, slots=True)
class NumpyImageData:
    """One decoded 3-channel BGR image."""

    array: BgrArray

    @property
    def width(self) -> int:
        return int(self.array.shape[1])

    @property
    def height(self) -> int:
        return int(self.array.shape[0])
