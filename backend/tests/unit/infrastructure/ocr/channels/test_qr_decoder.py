"""`ZxingQrDecoder` — decoding, layout defence, and the never-raise contract (§7.4.3)."""
from __future__ import annotations

import numpy as np
import pytest

from cocas.domain.enums.field_key import FieldKey
from cocas.infrastructure.ocr.channels.qr_decoder import ZxingQrDecoder

from .conftest import SAMPLE_PAYLOAD, StubImageSet, card_with_qr


@pytest.fixture
def decoder() -> ZxingQrDecoder:
    return ZxingQrDecoder()


class TestSuccessfulDecode:
    @pytest.fixture
    def result(self, decoder, qr_card_set):
        return decoder.decode(qr_card_set)

    def test_reports_the_channel_as_available(self, result):
        assert result.available is True
        assert result.layout_recognized is True

    def test_extracts_the_four_fields_qr_can_vouch_for(self, result):
        assert set(result.fields) == {
            FieldKey.ID_NUMBER,
            FieldKey.FULL_NAME,
            FieldKey.DATE_OF_BIRTH,
            FieldKey.ISSUE_DATE,
        }

    def test_field_values_come_straight_from_the_payload(self, result):
        assert result.fields[FieldKey.ID_NUMBER] == "048179002546"
        assert result.fields[FieldKey.FULL_NAME] == "VO HUYNH NGAN GIAO"
        assert result.fields[FieldKey.DATE_OF_BIRTH] == "27021979"
        assert result.fields[FieldKey.ISSUE_DATE] == "08112022"

    def test_keeps_the_raw_payload_for_cross_checking(self, result):
        assert result.raw_payload == SAMPLE_PAYLOAD

    def test_stops_at_the_first_successful_attempt(self, result):
        assert result.attempts == 1

    def test_gender_and_address_stay_out_of_fields(self, result):
        """Neither is a `FieldKey`; fusion reads them from `raw_payload` instead."""
        assert "Nu" not in result.fields.values()


class TestNoQrPresent:
    def test_reports_unavailable_rather_than_raising(self, decoder, blank_set):
        result = decoder.decode(blank_set)
        assert result.available is False

    def test_spends_every_attempt_before_giving_up(self, decoder, blank_set):
        assert decoder.decode(blank_set).attempts == 5

    def test_carries_no_fields(self, decoder, blank_set):
        assert decoder.decode(blank_set).fields == {}


class TestBlueChannelAttempts:
    """⭐ Attempts 4 and 5, added after 3 real cards defeated attempts 1–3.

    A CCCD's background is a fine turquoise guilloche printed straight through
    the QR. Cyan is bright in blue and dark in red, so the blue channel erases
    the interference while the near-black modules stay dark.
    """

    def test_the_blue_channel_is_the_one_where_a_turquoise_pattern_vanishes(self):
        from cocas.infrastructure.ocr.channels import qr_decoder

        # A cyan patch with a black square on it — the card's situation.
        card = np.zeros((20, 20, 3), dtype=np.uint8)
        card[:, :] = (230, 220, 40)  # BGR: bright blue+green, dark red
        card[5:15, 5:15] = (20, 20, 20)

        blue = qr_decoder._blue_channel(card)
        background, module = int(blue[0, 0]), int(blue[10, 10])
        assert background - module > 150

    def test_the_red_channel_would_have_hidden_the_module(self):
        """The control: why the choice of channel is not arbitrary."""
        card = np.zeros((20, 20, 3), dtype=np.uint8)
        card[:, :] = (230, 220, 40)
        card[5:15, 5:15] = (20, 20, 20)

        red_background, red_module = int(card[0, 0, 2]), int(card[10, 10, 2])
        assert red_background - red_module < 30

    def test_a_readable_card_still_wins_on_the_first_attempt(self, decoder, qr_card_set):
        """⭐ Appending attempts must not change what already worked — the whole
        reason attempt 3 was left alone instead of retuned."""
        assert decoder.decode(qr_card_set).attempts == 1


class TestLayoutDefence:
    """⭐ A changed card format must silence the channel, not poison fusion."""

    @pytest.mark.parametrize(
        "payload",
        [
            "not-a-cccd-payload",
            "12345|179002546|VO HUYNH|27021979|Nu|Nha Trang|08112022",
            "04817900254X|179002546|VO HUYNH|27021979|Nu|Nha Trang|08112022",
            "048179002546|179002546|VO HUYNH",
            "048179002546|179002546|VO HUYNH|99999999|Nu|Nha Trang|08112022",
            "048179002546|179002546|VO HUYNH|27021979|Nu|Nha Trang|08112022|EXTRA",
        ],
    )
    def test_unknown_layouts_yield_no_fields(self, decoder, payload):
        result = decoder.decode(StubImageSet(card_with_qr(payload)))
        assert result.available is True
        assert result.layout_recognized is False
        assert result.fields == {}

    def test_trailing_empty_parts_are_tolerated(self, decoder):
        """Observed on real cards: 11 parts, the last four empty."""
        payload = SAMPLE_PAYLOAD + "||||"
        result = decoder.decode(StubImageSet(card_with_qr(payload)))
        assert result.layout_recognized is True
        assert result.fields[FieldKey.ID_NUMBER] == "048179002546"


class TestNeverRaises:
    @pytest.mark.parametrize(
        "image",
        [
            np.zeros((0, 0, 3), np.uint8),
            np.zeros((1, 1, 3), np.uint8),
            np.full((4, 4, 3), 255, np.uint8),
        ],
    )
    def test_degenerate_images_are_reported_not_raised(self, decoder, image):
        assert decoder.decode(StubImageSet(image)).available is False

    def test_an_image_set_that_explodes_is_survived(self, decoder):
        class ExplodingSet(StubImageSet):
            @property
            def v1(self):
                raise RuntimeError("variant build failed")

        result = decoder.decode(ExplodingSet(np.full((80, 80, 3), 200, np.uint8)))
        assert result.available is False
