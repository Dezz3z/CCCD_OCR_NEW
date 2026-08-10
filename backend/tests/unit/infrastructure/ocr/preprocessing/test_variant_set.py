"""The lazy variant chain — §7.4.1 variant table and the §12.4 invariants."""
from __future__ import annotations

import cv2
import numpy as np
import pytest

from cocas.domain.ports.ocr import PreprocessedImageSet, PreprocessProfile
from cocas.infrastructure.ocr.preprocessing import OpenCvPreprocessor
from cocas.infrastructure.ocr.preprocessing.transforms import (
    CARD_FRAME_HEIGHT,
    CARD_FRAME_WIDTH,
)

from .conftest import draw_card, encode, place_on_background


@pytest.fixture
def image_set(card_bytes):
    return OpenCvPreprocessor().prepare(card_bytes, None, PreprocessProfile())


def build_set(image, *, exif_orientation=None, profile=None):
    return OpenCvPreprocessor().prepare(
        encode(image), exif_orientation, profile or PreprocessProfile()
    )


def test_satisfies_the_port(image_set):
    assert isinstance(image_set, PreprocessedImageSet)


class TestLaziness:
    def test_a_variant_is_built_only_when_first_touched(self, image_set):
        assert image_set.built_variants() == set()
        _ = image_set.v1
        assert image_set.built_variants() == {"v1"}

    def test_the_qr_path_never_pays_for_the_ocr_or_mrz_variants(self, image_set):
        """⭐ The whole point of the lazy strategy: QR reads `v1` and stops."""
        _ = image_set.v1
        assert "v3" not in image_set.built_variants()
        assert "v4" not in image_set.built_variants()

    def test_v3_pulls_its_whole_chain_but_not_v4(self, image_set):
        _ = image_set.v3
        assert image_set.built_variants() == {"v1", "v2", "v3"}

    def test_a_built_variant_is_cached_not_rebuilt(self, image_set):
        assert image_set.v3 is image_set.v3
        assert image_set.v2 is image_set.v2

    def test_quality_is_computed_once(self, image_set):
        assert image_set.quality is image_set.quality


class TestV0IsNeverModified:
    def test_source_pixels_survive_every_variant(self, card_on_background):
        image_set = build_set(card_on_background)
        original = image_set.v0.array.copy()

        _ = (image_set.v1, image_set.v2, image_set.v3, image_set.v4)

        assert np.array_equal(image_set.v0.array, original)

    def test_v0_is_write_protected(self, image_set):
        assert not image_set.v0.array.flags.writeable

    def test_v1_does_not_alias_v0_even_when_no_transform_applies(self):
        """A 1600px upright image needs no EXIF fix and no resize — still a copy."""
        image_set = build_set(place_on_background(draw_card(), 1600, 1000))
        assert image_set.v1.array is not image_set.v0.array
        assert image_set.v1.array.flags.writeable


class TestV1:
    def test_resizes_to_the_profile_long_edge(self, card_on_background):
        image_set = build_set(card_on_background, profile=PreprocessProfile(target_long_edge=900))
        assert max(image_set.v1.height, image_set.v1.width) == 900

    def test_applies_the_exif_orientation(self, card_on_background):
        image_set = build_set(card_on_background, exif_orientation=6)
        assert image_set.v1.height > image_set.v1.width

    def test_leaves_rotation_to_v2(self, card_on_background):
        """`v1` feeds the QR channel, which does not care about rotation."""
        upright = build_set(card_on_background).v1.array
        inverted = build_set(cv2.rotate(card_on_background, cv2.ROTATE_180)).v1.array
        assert np.array_equal(inverted, cv2.rotate(upright, cv2.ROTATE_180))


class TestV2:
    def test_rectifies_to_the_canonical_frame_when_the_card_is_found(self, image_set):
        assert image_set.warp_succeeded is True
        assert (image_set.v2.height, image_set.v2.width) == (CARD_FRAME_HEIGHT, CARD_FRAME_WIDTH)

    def test_corrects_an_upside_down_card(self, card_on_background):
        upright = build_set(card_on_background).v2.array
        corrected = build_set(cv2.rotate(card_on_background, cv2.ROTATE_180)).v2.array
        assert np.abs(corrected.astype(int) - upright.astype(int)).mean() < 12

    def test_exposes_the_matrix_that_maps_boxes_back(self, image_set):
        matrix = image_set.transform_matrix
        assert matrix is not None
        assert len(matrix) == 3 and all(len(row) == 3 for row in matrix)

    def test_accepts_an_already_cropped_card_as_its_own_frame(self):
        """Uploads cropped tight to the card have no outline to detect, but the
        frame itself is the card — ZONE extraction must stay available."""
        image_set = build_set(draw_card())
        assert image_set.warp_succeeded is True
        assert (image_set.v2.height, image_set.v2.width) == (CARD_FRAME_HEIGHT, CARD_FRAME_WIDTH)

    def test_recovers_a_card_photographed_sideways(self):
        """⭐ The dominant real-world case: a phone photo held portrait."""
        sideways = cv2.rotate(place_on_background(draw_card()), cv2.ROTATE_90_CLOCKWISE)
        image_set = build_set(sideways)
        assert image_set.warp_succeeded is True
        assert image_set.v2.width > image_set.v2.height

    def test_falls_back_to_deskew_when_nothing_card_shaped_is_found(self):
        """⭐ Failure keeps a usable image; `warp_succeeded=False` routes the
        extractor to the ANCHOR strategy instead of ZONE."""
        image_set = build_set(draw_card(width=1400, height=1000))
        assert image_set.warp_succeeded is False
        assert image_set.transform_matrix is None
        assert (image_set.v2.height, image_set.v2.width) == (
            image_set.v1.height,
            image_set.v1.width,
        )

    def test_perspective_can_be_switched_off_by_profile(self, card_on_background):
        image_set = build_set(card_on_background, profile=PreprocessProfile(
            perspective_enabled=False
        ))
        assert image_set.warp_succeeded is False

    def test_reading_warp_succeeded_alone_resolves_the_warp(self, image_set):
        assert image_set.warp_succeeded is True
        assert "v2" not in image_set.built_variants()


class TestV3AndV4:
    def test_v3_is_a_distinct_image_derived_from_v2(self, image_set):
        assert image_set.v3.array is not image_set.v2.array
        assert image_set.v3.array.shape == image_set.v2.array.shape

    def test_v3_sharpens_a_soft_capture(self, card_on_background):
        soft = cv2.GaussianBlur(card_on_background, (0, 0), 3)
        image_set = build_set(soft)
        assert cv2.Laplacian(
            cv2.cvtColor(image_set.v3.array, cv2.COLOR_BGR2GRAY), cv2.CV_64F
        ).var() > cv2.Laplacian(
            cv2.cvtColor(image_set.v2.array, cv2.COLOR_BGR2GRAY), cv2.CV_64F
        ).var()

    def test_v4_is_binary_for_the_mrz_channel(self, image_set):
        assert set(np.unique(image_set.v4.array)).issubset({0, 255})

    def test_deglare_is_off_unless_the_profile_asks(self, card_on_background):
        glared = card_on_background.copy()
        glared[300:500, 500:900] = 255

        default_set = build_set(glared)
        deglared_set = build_set(glared, profile=PreprocessProfile(deglare_enabled=True))

        blown_out = lambda image: float((image.min(axis=2) > 250).mean())  # noqa: E731
        assert blown_out(deglared_set.v3.array) < blown_out(default_set.v3.array)


class TestQuality:
    def test_reports_flags_for_a_dark_capture(self, card_on_background):
        image_set = build_set((card_on_background * 0.2).astype(np.uint8))
        assert "DARK" in image_set.quality.flags

    def test_a_clean_capture_scores_well(self, image_set):
        assert image_set.quality.score > 0.4


class TestOrientationOracle:
    """⭐ How the front finally gets its 180° correction (§7.4.1 transform 4).

    The MRZ signal covers backs and abstains on every front, so preprocessing
    accepts a one-method oracle and the Composition Root supplies an
    engine-backed one. Preprocessing itself stays usable with no models
    installed, which is what keeps these tests engine-free.
    """

    class RecordingOracle:
        def __init__(self, verdict):
            self.verdict = verdict
            self.calls = 0

        def is_upside_down(self, image):
            self.calls += 1
            return self.verdict

    def build(self, image, oracle):
        return OpenCvPreprocessor(oracle).prepare(
            encode(image), None, PreprocessProfile()
        )

    def test_a_front_is_rotated_when_the_oracle_says_so(self):
        front = place_on_background(draw_card(with_mrz=False))
        upright = self.build(front, self.RecordingOracle(False))
        flipped = self.build(front, self.RecordingOracle(True))
        assert np.array_equal(
            cv2.rotate(upright.v2.array, cv2.ROTATE_180), flipped.v2.array
        )

    def test_an_abstaining_oracle_leaves_the_card_alone(self):
        front = place_on_background(draw_card(with_mrz=False))
        left_alone = self.build(front, self.RecordingOracle(None))
        untouched = self.build(front, self.RecordingOracle(False))
        assert np.array_equal(left_alone.v2.array, untouched.v2.array)

    def test_the_mrz_signal_wins_and_the_oracle_is_never_asked(self):
        """⭐ It reads the card's own geometry, was right on 19 of 19 real
        backs, and costs ~20 ms against the oracle's ~1.1 s."""
        oracle = self.RecordingOracle(True)
        assert self.build(place_on_background(draw_card(with_mrz=True)), oracle).v2 is not None
        assert oracle.calls == 0

    def test_a_front_consults_the_oracle_exactly_once(self):
        oracle = self.RecordingOracle(False)
        image_set = self.build(place_on_background(draw_card(with_mrz=False)), oracle)
        assert (image_set.v2, image_set.v3, image_set.v4) is not None
        assert oracle.calls == 1

    def test_no_oracle_means_no_rotation_rather_than_an_error(self):
        front = place_on_background(draw_card(with_mrz=False))
        assert OpenCvPreprocessor().prepare(
            encode(front), None, PreprocessProfile()
        ).v2 is not None
