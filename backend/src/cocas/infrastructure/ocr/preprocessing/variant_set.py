"""`PreprocessedImageSet` with ⭐ lazily-built, cached variants (§7.4.1, §12.4).

The five variants form a chain, each built from the one before it:

| Variant | Built from | Channel |
|---|---|---|
| `v0` | decoded source, never modified | last-resort fallback |
| `v1` | v0 + EXIF + resize | QR |
| `v2` | v1 + perspective warp (or deskew when refused) + 180° correction | base for v3/v4 |
| `v3` | v2 + deglare + denoise + CLAHE + sharpen | OCR text |
| `v4` | v2 → adaptive binarization | MRZ |

⭐ A variant is built on first access and cached, so a front image whose QR
decodes at `v1` never pays for `v3`/`v4` at all (~15% of peak RAM and runtime).
"""
from __future__ import annotations

from collections.abc import Callable

import numpy as np

from cocas.domain.ports.ocr import ImageQuality, PreprocessProfile

from . import transforms
from .cv_types import PointArray
from .image_data import BgrArray, NumpyImageData
from .orientation import IOrientationOracle


class LazyPreprocessedImageSet:
    """One source image and its five channel-tuned renditions."""

    def __init__(
        self,
        source: BgrArray,
        exif_orientation: int | None,
        profile: PreprocessProfile,
        orientation_oracle: IOrientationOracle | None = None,
    ) -> None:
        source.setflags(write=False)  # enforces "v0 is never modified"
        self._source = source
        self._exif_orientation = exif_orientation
        self._profile = profile
        self._orientation_oracle = orientation_oracle
        self._cache: dict[str, NumpyImageData] = {}
        self._transform_matrix: list[list[float]] | None = None
        self._warped: BgrArray | None = None
        self._warp_succeeded = False
        self._quality: ImageQuality | None = None

    @property
    def v0(self) -> NumpyImageData:
        return self._cached("v0", lambda: self._source)

    @property
    def v1(self) -> NumpyImageData:
        return self._cached("v1", self._build_v1)

    @property
    def v2(self) -> NumpyImageData:
        return self._cached("v2", self._build_v2)

    @property
    def v3(self) -> NumpyImageData:
        return self._cached("v3", self._build_v3)

    @property
    def v4(self) -> NumpyImageData:
        return self._cached("v4", self._build_v4)

    @property
    def transform_matrix(self) -> list[list[float]] | None:
        """The 3x3 v1→v2 perspective matrix, or None when the warp was refused.

        ⭐ This is what maps a bbox found on `v2`/`v3`/`v4` back onto the
        image the user actually sees.
        """
        self._resolve_warp()
        return self._transform_matrix

    @property
    def warp_succeeded(self) -> bool:
        self._resolve_warp()
        return self._warp_succeeded

    @property
    def quality(self) -> ImageQuality:
        if self._quality is None:
            self._quality = transforms.assess_quality(self.v1.array)
        return self._quality

    def built_variants(self) -> set[str]:
        """Which variants have been materialized so far — used to assert laziness."""
        return set(self._cache)

    def _cached(self, name: str, build: Callable[[], BgrArray]) -> NumpyImageData:
        cached = self._cache.get(name)
        if cached is None:
            cached = NumpyImageData(build())
            self._cache[name] = cached
        return cached

    def _build_v1(self) -> BgrArray:
        image = transforms.apply_exif_orientation(self._source, self._exif_orientation)
        image = transforms.limit_long_edge(image, self._profile.target_long_edge)
        if image is self._source:
            image = self._source.copy()
        return image

    def _build_v2(self) -> BgrArray:
        self._resolve_warp()
        assert self._warped is not None
        return self._warped

    def _resolve_warp(self) -> None:
        """Run the warp attempt once, recording its outcome and fallback.

        When no quad passes the guards the image is only deskewed, which keeps
        `v2` usable while `warp_succeeded=False` tells the field extractor to
        use the ANCHOR strategy instead of ZONE (§7.3 `IFieldExtractor`).

        ⭐ The 180° correction runs here rather than on `v1`: its left-vs-right
        signal only means anything once the card has been rectified to
        landscape. `v1` feeds the QR channel, which is rotation-invariant.
        """
        if self._warped is not None:
            return
        base = self.v1.array
        quad = self._find_quad(base)
        if quad is None:
            rectified, _ = transforms.deskew(base)
            self._warp_succeeded = False
            self._transform_matrix = None
        else:
            rectified, matrix = transforms.warp_to_card_frame(base, quad)
            self._warp_succeeded = True
            self._transform_matrix = [[float(cell) for cell in row] for row in matrix]

        self._warped = (
            transforms.rotate_180(rectified)
            if self._is_upside_down(rectified)
            else rectified
        )

    def _is_upside_down(self, rectified: BgrArray) -> bool:
        """Transform 4 — poll the orientation signals in order of precision.

        ⭐ The MRZ signal goes first and wins outright when it has an opinion.
        It reads the card's own geometry, it was right on 19 of 19 real backs,
        and it costs about 20 ms. The oracle only gets asked about the cards
        the MRZ signal cannot see — which is every front.
        """
        mrz_vote = transforms.mrz_orientation_vote(rectified)
        if mrz_vote is not None:
            return mrz_vote
        if self._orientation_oracle is None:
            return False
        return bool(self._orientation_oracle.is_upside_down(NumpyImageData(rectified)))

    def _find_quad(self, base: BgrArray) -> PointArray | None:
        if not self._profile.perspective_enabled:
            return None
        quad = transforms.find_card_quad(base)
        return quad if quad is not None else transforms.full_frame_quad(base)

    def _build_v3(self) -> BgrArray:
        image = self.v2.array
        if self._profile.deglare_enabled:
            image = transforms.remove_glare(image)
        image = transforms.denoise(image, self._profile.denoise_method)
        image = transforms.equalize_lighting(image)
        image = transforms.sharpen_if_soft(image)
        if image is self.v2.array:
            image = np.ascontiguousarray(image).copy()
        return image

    def _build_v4(self) -> BgrArray:
        return transforms.binarize(self.v2.array)
