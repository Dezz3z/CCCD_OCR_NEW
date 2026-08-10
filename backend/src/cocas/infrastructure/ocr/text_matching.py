"""Fuzzy matching of Vietnamese card text, shared by side classification and extraction.

⭐ **Every comparison runs on folded text** — diacritics stripped, uppercased,
whitespace collapsed (§7.4.6). Two independent reasons, and both are decisive:

1. The card prints `CỤC CẢNH SÁT`; the recognizer emits `CUC CANH SAT`, because
   `lang='vi'` resolves to the latin model whose charset has no output class for
   most accented Vietnamese capitals (see `PaddleOcrAdapter`). Comparing raw
   strings compares a card against a recognizer that cannot spell it.
2. Even with a perfect recognizer, NFC and NFD forms of the same word are
   different strings.

Folding is imported from Domain rather than reimplemented: `full_name_search`
in the customer repository folds the same way, so a name found here and a name
searched there stay comparable.
"""
from __future__ import annotations

from rapidfuzz import fuzz

from cocas.domain.value_objects._vn_text import (
    collapse_whitespace,
    nfc_upper,
    strip_diacritics,
)

# §7.4.2 uses 80 for side anchors, §7.4.6 uses 75 for field anchors — the
# latter matches against shorter, more damaged fragments.
SIDE_ANCHOR_THRESHOLD = 80.0
FIELD_ANCHOR_THRESHOLD = 75.0

# The recognizer renders the horn diacritic as a trailing apostrophe rather than
# dropping it: `CĂN CƯỚC` comes back as `CAN CU'O'C`. Stripping the apostrophe
# turns that into the correctly folded `CAN CUOC` instead of a 2-character
# mismatch on every word carrying ơ or ư.
_RECOGNIZER_ARTEFACTS = str.maketrans("", "", "'`’ʼ")  # noqa: RUF001


def fold(text: str) -> str:
    """Normalize for comparison: no diacritics, uppercase, single spaces."""
    return collapse_whitespace(
        strip_diacritics(nfc_upper(text)).translate(_RECOGNIZER_ARTEFACTS)
    )


def similarity(text: str, anchor: str) -> float:
    """0..100 confidence that `anchor` appears in `text`, both folded first.

    Partial matching is what makes label anchors work at all: `Full name` has
    to be findable inside `Họ và tên / Full name:` — the recognizer returns the
    label and its value as one line.

    ⭐ **Scaled by length coverage, and that scaling is not optional.**
    `partial_ratio` scores the best-matching *substring*, so a fragment shorter
    than the anchor matches perfectly whenever the anchor happens to contain
    it. A real card produced the two-character fragment `ON`, which scored
    100 against `CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM` — enough to convince the
    orientation check that six upside-down cards were the right way up.
    Coverage caps that at 2/34 of the score.
    """
    folded_text, folded_anchor = _compact(text), _compact(anchor)
    if not folded_text or not folded_anchor:
        return 0.0
    coverage = min(1.0, len(folded_text) / len(folded_anchor))
    return float(fuzz.partial_ratio(folded_anchor, folded_text)) * coverage


def _compact(text: str) -> str:
    """Fold, then drop spaces entirely — word boundaries are not evidence.

    ⭐ The recognizer merges words constantly: real cards produced
    `CONG HOAXAHOI CHU NGHIAVIET NAM`, `SOCIALISTREPUBLIC OFVIETNAM` and
    `DANGDUY NGHIA`. Scoring those against correctly-spaced anchors cost about
    18 points — enough to push a card's own printed title below the threshold
    that decides whether it is upside down.
    """
    return fold(text).replace(" ", "")


def best_match(text: str, anchors: list[str]) -> tuple[str | None, float]:
    """The anchor that matches `text` best, with its score."""
    best: tuple[str | None, float] = (None, 0.0)
    for anchor in anchors:
        score = similarity(text, anchor)
        if score > best[1]:
            best = (anchor, score)
    return best


def matches_any(text: str, anchors: list[str], threshold: float) -> bool:
    return best_match(text, anchors)[1] >= threshold


# ⭐ Text a card prints that is never a value read from one. Extraction rejects
# it: a zone that has drifted by one line otherwise hands `CITIZEN IDENTITY
# CARD` to fusion as a customer's name.
#
# ⭐ Covers BOTH generations. The 2024 `CĂN CƯỚC` shortens or renames most of
# these, and the longer 2021 phrases do not reach them: measured,
# `CĂN CƯỚC` scores 50.0 against `CĂN CƯỚC CÔNG DÂN` and `IDENTITY CARD` scores
# 63.2 against `Citizen Identity Card` — both far under the 85 threshold, so
# before this list grew, a 2024 card's own title was not recognized as printed
# text at all.
#
# ⚠️ Every phrase below was scored against all 774 recognized lines in the
# sample first; each one matches only titles and labels, never a value. The
# authority line (`BỘ CÔNG AN`, `CỤC TRƯỞNG CỤC CẢNH SÁT…`) is deliberately
# absent for the opposite reason: it **is** the `issue_place` value, and listing
# it here would make `find_place` throw away the only reading of that field.
PRINTED_ON_EVERY_CARD = [
    # -- shared --
    "CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM",
    "SOCIALIST REPUBLIC OF VIET NAM",
    "Độc lập - Tự do - Hạnh phúc",
    "Independence - Freedom - Happiness",
    "Quốc tịch",
    "Nationality",
    "Việt Nam",
    "Full name",
    "Date of birth",
    "Date of expiry",
    # -- CCCD 2021 --
    "CĂN CƯỚC CÔNG DÂN",
    "Citizen Identity Card",
    "Đặc điểm nhân dạng",
    "Personal identification",
    "Nơi thường trú",
    "Place of residence",
    "Quê quán",
    "Place of origin",
    # -- Căn cước 2024 --
    "CĂN CƯỚC",
    "IDENTITY CARD",
    "Số định danh cá nhân",
    "Họ, chữ đệm và tên khai sinh",
    "Nơi cư trú",
    "Nơi đăng ký khai sinh",
    "Place of birth",
    "Ngày, tháng, năm hết hạn",
    "Date of issue",
]
BOILERPLATE_THRESHOLD = 85.0

# ⭐ Phrases printed ONLY in the top third of a card — the fingerprint that says
# it is being read the right way up.
#
# ⚠️ Position is the whole point, and getting it wrong is not subtle. Built
# first from every printed phrase, this list called 6 of 46 inverted cards
# upright: `Nơi thường trú` and `Có giá trị đến` sit at the BOTTOM of a front,
# so rotating the card moves them straight into the band being searched, and
# PaddleOCR's per-line angle classifier renders them perfectly legibly. A
# fingerprint that appears at both ends of the card fingerprints nothing.
#
# Front: the republic header and the card's own title. Back: the identifying
# marks heading (2021) or the birth-registration label (2024). A flipped back
# shows its MRZ here, which matches none of them.
#
# ⭐ The 2024 additions were placement-checked, not assumed. Over the whole
# sample: `CĂN CƯỚC` appears only at y 0.22–0.28, `IDENTITY CARD` only at
# y 0.31–0.37, `Nơi đăng ký khai sinh` only at y 0.16 — all in the upper third,
# so rotating a card moves them out of the band instead of into it.
#
# ⚠️ `Số định danh cá nhân` is NOT here despite being printed on every 2024
# front: it sits at y≈0.40, below the band this reads, so it would contribute
# nothing either way up.
CARD_TOP_FINGERPRINT = [
    "CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM",
    "SOCIALIST REPUBLIC OF VIET NAM",
    "Độc lập - Tự do - Hạnh phúc",
    "Independence - Freedom - Happiness",
    "CĂN CƯỚC CÔNG DÂN",
    "Citizen Identity Card",
    "Đặc điểm nhân dạng",
    "Personal identification",
    # -- Căn cước 2024 --
    "CĂN CƯỚC",
    "IDENTITY CARD",
    "Nơi đăng ký khai sinh",
]


def is_printed_boilerplate(text: str) -> bool:
    """Whether this is text the card prints, rather than text about its holder."""
    return matches_any(text, PRINTED_ON_EVERY_CARD, BOILERPLATE_THRESHOLD)
