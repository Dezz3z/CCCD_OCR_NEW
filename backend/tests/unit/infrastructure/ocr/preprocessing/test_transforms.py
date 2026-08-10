"""The 9 transforms of §7.4.1, each checked against the risk its spec row names."""
from __future__ import annotations

import cv2
import numpy as np
import pytest

from cocas.infrastructure.ocr.preprocessing import transforms

from .conftest import draw_card, place_on_background


class TestExifOrientation:
    def test_orientation_1_and_none_leave_the_image_alone(self, card_image):
        assert transforms.apply_exif_orientation(card_image, None) is card_image
        assert transforms.apply_exif_orientation(card_image, 1) is card_image

    def test_orientation_3_rotates_180(self, card_image):
        rotated = transforms.apply_exif_orientation(card_image, 3)
        assert np.array_equal(rotated, cv2.rotate(card_image, cv2.ROTATE_180))

    @pytest.mark.parametrize("orientation", [5, 6, 7, 8])
    def test_quarter_turns_swap_the_axes(self, card_image, orientation):
        turned = transforms.apply_exif_orientation(card_image, orientation)
        assert turned.shape[:2] == card_image.shape[:2][::-1]

    def test_unknown_value_is_ignored_rather_than_raising(self, card_image):
        assert transforms.apply_exif_orientation(card_image, 99) is card_image


class TestLimitLongEdge:
    def test_shrinks_to_the_target(self, card_on_background):
        resized = transforms.limit_long_edge(card_on_background, 1600)
        assert max(resized.shape[:2]) == 1600

    def test_enlarges_to_the_target(self, card_image):
        resized = transforms.limit_long_edge(card_image, 1600)
        assert max(resized.shape[:2]) == 1600

    def test_preserves_the_aspect_ratio(self, card_on_background):
        height, width = card_on_background.shape[:2]
        resized = transforms.limit_long_edge(card_on_background, 800)
        assert abs(resized.shape[1] / resized.shape[0] - width / height) < 0.01


class TestPerspectiveWarp:
    def test_finds_the_card_and_rectifies_it_to_the_canonical_frame(self, card_on_background):
        quad = transforms.find_card_quad(card_on_background)
        assert quad is not None

        warped, matrix = transforms.warp_to_card_frame(card_on_background, quad)
        assert warped.shape[:2] == (transforms.CARD_FRAME_HEIGHT, transforms.CARD_FRAME_WIDTH)
        assert matrix.shape == (3, 3)

    def test_refuses_a_square_contour(self):
        """⭐ The aspect guard is what stops a book or a sheet of paper being warped."""
        canvas = np.full((1000, 1000, 3), 30, np.uint8)
        canvas[150:850, 150:850] = 240
        assert transforms.find_card_quad(canvas) is None

    def test_refuses_a_card_shaped_contour_that_is_too_small(self, card_image):
        """A correctly-proportioned card filling <25% of the frame is not the subject."""
        small = cv2.resize(card_image, (280, 176))
        assert transforms.find_card_quad(place_on_background(small)) is None

    def test_returns_none_on_a_featureless_image(self):
        assert transforms.find_card_quad(np.full((600, 900, 3), 200, np.uint8)) is None

    def test_accepts_a_card_photographed_sideways(self, card_on_background):
        """⭐ Without landscape re-labelling the aspect guard rejects 1/1.585."""
        sideways = cv2.rotate(card_on_background, cv2.ROTATE_90_CLOCKWISE)
        quad = transforms.find_card_quad(sideways)
        assert quad is not None

        warped, _ = transforms.warp_to_card_frame(sideways, quad)
        assert warped.shape[:2] == (transforms.CARD_FRAME_HEIGHT, transforms.CARD_FRAME_WIDTH)


class TestFullFrameQuad:
    def test_accepts_a_frame_with_card_proportions(self, card_image):
        assert transforms.full_frame_quad(card_image) is not None

    def test_accepts_a_sideways_frame(self, card_image):
        assert transforms.full_frame_quad(cv2.rotate(card_image, cv2.ROTATE_90_CLOCKWISE)) is not None

    def test_rejects_a_frame_with_room_around_the_card(self, card_on_background):
        assert transforms.full_frame_quad(np.zeros((1000, 1400, 3), np.uint8)) is None


class TestMrzCandidates:
    def test_locates_the_block_at_the_bottom_of_an_upright_card(self, card_image):
        assert transforms.find_mrz_candidates(card_image) == pytest.approx([0.79], abs=0.03)

    def test_locates_the_block_at_the_top_of_an_inverted_card(self, card_image):
        inverted = cv2.rotate(card_image, cv2.ROTATE_180)
        assert transforms.find_mrz_candidates(inverted) == pytest.approx([0.21], abs=0.03)

    def test_a_card_without_an_mrz_produces_nothing(self):
        assert transforms.find_mrz_candidates(draw_card(with_mrz=False)) == []


class TestUpsideDownDetection:
    """⭐ Three-state: True, False, or None for "I cannot tell".

    The abstention is what lets the engine-backed oracle vote afterwards. A
    `False` returned out of ignorance would be indistinguishable from an
    informed "upright" and would silence every later signal (§7.4.1).
    """

    def test_upright_card_is_not_flagged(self, card_image):
        assert transforms.mrz_orientation_vote(card_image) is False

    def test_rotated_card_is_flagged(self, card_image):
        rotated = cv2.rotate(card_image, cv2.ROTATE_180)
        assert transforms.mrz_orientation_vote(rotated) is True

    def test_correction_is_idempotent(self, card_image):
        inverted = cv2.rotate(card_image, cv2.ROTATE_180)
        corrected = transforms.rotate_180(inverted)
        assert transforms.mrz_orientation_vote(corrected) is False

    def test_a_card_with_a_block_at_both_edges_abstains(self, card_image):
        """⭐ The real failure this guards: the address block on a CCCD back is
        also three even full-width lines, and flipping an upright card is worse
        than leaving an inverted one."""
        height = card_image.shape[0]
        ambiguous = card_image.copy()
        block = card_image[int(height * 0.68):int(height * 0.92)]
        ambiguous[int(height * 0.08):int(height * 0.08) + block.shape[0]] = block

        assert len(transforms.find_mrz_candidates(ambiguous)) == 2
        assert transforms.mrz_orientation_vote(ambiguous) is None

    def test_a_face_without_an_mrz_abstains(self):
        """⭐ Every front lands here — which is why abstaining, not returning
        False, is what hands the decision to `PaddleOrientationOracle`."""
        front = draw_card(with_mrz=False)
        assert transforms.mrz_orientation_vote(front) is None
        assert transforms.mrz_orientation_vote(cv2.rotate(front, cv2.ROTATE_180)) is None

    def test_a_blank_image_abstains(self):
        blank = np.full((638, 1012, 3), 240, np.uint8)
        assert transforms.mrz_orientation_vote(blank) is None


class TestDeskew:
    def test_straightens_a_known_tilt(self, card_image):
        height, width = card_image.shape[:2]
        matrix = cv2.getRotationMatrix2D((width / 2, height / 2), -6.0, 1.0)
        tilted = cv2.warpAffine(card_image, matrix, (width, height),
                                borderMode=cv2.BORDER_REPLICATE)

        straightened, angle = transforms.deskew(tilted)
        assert abs(angle) == pytest.approx(6.0, abs=1.5)
        assert abs(transforms.estimate_skew_angle(straightened)) < 1.0

    def test_leaves_a_straight_image_untouched(self, card_image):
        straightened, angle = transforms.deskew(card_image)
        assert angle == 0.0
        assert straightened is card_image

    def test_never_exceeds_the_angle_cap(self, card_image):
        matrix = cv2.getRotationMatrix2D((506, 319), 40.0, 1.0)
        badly_rotated = cv2.warpAffine(card_image, matrix, (1012, 638))
        _, angle = transforms.deskew(badly_rotated)
        assert abs(angle) <= transforms.DESKEW_MAX_ANGLE


class TestPhotometricTransforms:
    def test_clahe_lifts_a_dark_image(self, card_image):
        dark = (card_image * 0.25).astype(np.uint8)
        brightened = transforms.equalize_lighting(dark)
        assert brightened.mean() > dark.mean()

    def test_denoise_keeps_the_shape_and_reduces_noise(self, card_image):
        rng = np.random.default_rng(7)
        noise = rng.normal(0, 18, card_image.shape)
        noisy = np.clip(card_image + noise, 0, 255).astype(np.uint8)

        cleaned = transforms.denoise(noisy, "bilateral")
        assert cleaned.shape == noisy.shape
        assert float(np.abs(cleaned.astype(int) - card_image.astype(int)).mean()) < float(
            np.abs(noisy.astype(int) - card_image.astype(int)).mean()
        )

    def test_sharpen_skips_an_already_crisp_image(self, card_image):
        """⭐ Unsharp masking a crisp image LOWERS accuracy — the guard is mandatory."""
        assert transforms.laplacian_variance(card_image) >= transforms.SHARPEN_LAPLACIAN_THRESHOLD
        assert transforms.sharpen_if_soft(card_image) is card_image

    def test_sharpen_acts_on_a_soft_image(self, card_image):
        soft = cv2.GaussianBlur(card_image, (0, 0), 3)
        sharpened = transforms.sharpen_if_soft(soft)
        assert transforms.laplacian_variance(sharpened) > transforms.laplacian_variance(soft)

    def test_deglare_repairs_a_blown_out_patch(self, card_image):
        glared = card_image.copy()
        glared[100:200, 400:600] = 255
        assert transforms.glare_ratio(transforms.remove_glare(glared)) < transforms.glare_ratio(
            glared
        )

    def test_deglare_is_a_no_op_without_glare(self, card_image):
        assert transforms.remove_glare(card_image) is card_image


class TestBinarize:
    def test_produces_two_tone_output_for_the_mrz_channel(self, card_image):
        binary = transforms.binarize(card_image)
        assert binary.shape == card_image.shape
        assert set(np.unique(binary)).issubset({0, 255})


class TestQuality:
    def test_a_clean_card_scores_well_and_flags_nothing(self, card_image):
        quality = transforms.assess_quality(card_image)
        assert quality.score > 0.5
        assert quality.flags == []

    def test_flags_a_dark_image(self, card_image):
        quality = transforms.assess_quality((card_image * 0.2).astype(np.uint8))
        assert "DARK" in quality.flags

    def test_flags_a_blurry_image(self, card_image):
        quality = transforms.assess_quality(cv2.GaussianBlur(card_image, (0, 0), 6))
        assert "BLURRY" in quality.flags

    def test_flags_a_glared_image(self, card_image):
        glared = card_image.copy()
        glared[50:400, 100:900] = 255
        assert "GLARE" in transforms.assess_quality(glared).flags

    def test_flags_a_low_resolution_image(self):
        quality = transforms.assess_quality(draw_card(width=760, height=479))
        assert "LOW_RESOLUTION" in quality.flags

    def test_score_stays_within_bounds(self, card_image):
        for candidate in (card_image, np.zeros_like(card_image), np.full_like(card_image, 255)):
            assert 0.0 <= transforms.assess_quality(candidate).score <= 1.0
