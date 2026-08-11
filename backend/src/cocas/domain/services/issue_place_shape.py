"""Tell the 2 issue places apart from their first letters — tier 5 of §12.5.

⭐ **This field is a choice between 2 values, not a string to be read.** Every
other tier of `IssuePlaceNormalizer` matches the whole line against a catalogue
of spellings, which is the right shape for an open-ended field and the wrong
shape for a closed one: it makes the answer depend on how much of a 23-letter
authority name the recognizer got right, when only the opening is needed to
decide.

The two values open differently and never converge:

| Canonical | Printed on the card | First 3 letters |
|---|---|---|
| `BỘ CÔNG AN` | `BỘ CÔNG AN` (2024) | `BOC` |
| `CỤC CẢNH SÁT QUẢN LÝ HÀNH CHÍNH VỀ TRẬT TỰ XÃ HỘI` | `CỤC TRƯỞNG CỤC CẢNH SÁT…` (2021) | `CUC` |

⭐ **Measured 2026-08-10 on the 46 real photos, 22 of which carry this field:
22/22 correct, every one of them at 100 vs 33** — the head is never close.
Sweeping the *other* 752 recognized lines through the same test fired **0**
times, so the rule is as narrow as it is decisive.

⚠️ **The obvious length signal does not work, and this is the finding worth
keeping.** On the canonical strings it looks unbeatable — 8 letters against 38,
a gap of nearly 5 to 1. On the text that actually reaches this function it is
gone:
the 2021 zone captures only the authority's first line (`CỤC TRƯỞNG CỤC CẢNH
SÁT`, 19 letters) while the 2024 zone swallows the English subtitle underneath
(`BO CONGAN MINISTRY OF PUBLIC SECURITY`, 31 letters). Measured spread: 2021 =
19–20, 2024 = 15 and 31 — overlapping, and inverted. Length is a property of
the *zone*, not of the field.

What survives from that idea is the length of the **first word**: `BỘ` is 2
letters, `CỤC` is 3, and the recognizer keeps that boundary even when it merges
everything after it (`CUCTRUONG`). Measured 22/22 as well — but on only 2 cards
of the short generation, so it corroborates the head rather than deciding
anything on its own.
"""
from __future__ import annotations

from dataclasses import dataclass

from rapidfuzz import fuzz

from cocas.domain.value_objects._vn_text import nfc_upper, strip_diacritics
from cocas.domain.value_objects.issue_place import BO_CONG_AN, CUC_CANH_SAT_QLHC_TTXH

HEAD_LEN = 3
"""Letters compared. 3 is where the two canonical openings first differ in
every position (`BOC` / `CUC`); a 4th letter adds nothing and one more chance
to be misread."""

MIN_TOKEN_LETTERS = 2
"""⭐ Leading tokens shorter than this are dropped before the head is taken, and
this is also what stops a *single* letter from ever deciding: `B` scored against
`BOC[:1]` is a perfect match with a 100-point margin, so without the filter tier
5 would answer for every line on the card that starts with a B or a C.

Neither `BỘ` nor `CỤC` is one letter, so a 1-letter opening token is always
noise. Real case from the sample — `S CUC TRUONG CUC CANH SAT`, where the stray
`S` would otherwise drag the head to `SCU` (67 against `CUC`, below the bar)."""

DECISIVE_SCORE = 80.0
"""⚠️ **In practice this means "the head matched exactly", and the threshold form
is kept only so `HEAD_LEN` stays tunable.** `fuzz.ratio` on 3 characters can
return just 0, 33.3, 66.7 or 100 (on 2 characters: 0, 50, 100) — there is no
value between 66.7 and 100 for a bar to sit at, so any bar in that gap says the
same thing. 80 is placed there rather than at 100 to make the intent legible: it
must clear the highest score any non-authority line in the sample reached,
`BOT`→`BOC` at 66.7 from an address line (`Bố Trạch, Quảng Bình`), and it must
admit a one-letter-short read like `BO`→`BOC[:2]`."""

MIN_MARGIN = 25.0
"""The runner-up must be this far behind. Real openings clear it by 66.7; the
ties that matter (`CON`, `CAN`, `BUI` — equidistant from both) are rejected here
rather than by the score."""

# ⭐ Ceilings, not measurements. This field has no exact channel to check it
# against — neither QR nor MRZ carries the issuing authority — so a wrong answer
# here is invisible to the False Confidence proxy (§7.9). 0.92 clears fusion's
# 0.85 review threshold, which is the whole point, and stops short of the
# certainty only tier 1's exact match earns.
CONF_CORROBORATED = 0.92
CONF_HEAD_ONLY = 0.85
"""The head decided but the first word's length disagreed — reachable when the
recognizer merges the short authority into one token (`BOCONGAN`), which makes
the length signal vote for the long value. The head is still right; the
disagreement is worth a lower number, not a different answer."""

SHORT_FIRST_WORD_MAX = 2
"""`BỘ` is 2 letters; `CỤC` and every longer merge of it are 3 or more."""

_HEADS: dict[str, str] = {
    BO_CONG_AN: "".join(ch for ch in strip_diacritics(BO_CONG_AN) if ch.isalpha())[:HEAD_LEN],
    CUC_CANH_SAT_QLHC_TTXH: "".join(
        ch for ch in strip_diacritics(CUC_CANH_SAT_QLHC_TTXH) if ch.isalpha()
    )[:HEAD_LEN],
}

# ⭐ The whole method rests on the openings being distinct *and* differing from
# the very first letter — `MIN_HEAD_LEN` only pays off if 2 letters already
# separate them. If a canonical value is ever added that shares an opening, this
# file needs a different signal; fail at import rather than start guessing.
assert len(set(_HEADS.values())) == len(_HEADS), "canonical issue places share a head"
assert len({head[0] for head in _HEADS.values()}) == len(_HEADS), (
    "canonical issue places share a first letter"
)


@dataclass(frozen=True, slots=True)
class ShapeVerdict:
    """Which of the 2 canonical values the opening points at, and how surely.

    `value is None` means "no verdict" — the head was unreadable or ambiguous —
    and the caller falls through to the whole-string tiers. It never means
    "neither value applies", because for this field there is no third option.
    """

    value: str | None
    confidence: float
    head: str = ""
    head_score: float = 0.0
    first_word_agrees: bool = False

    def __post_init__(self) -> None:
        if self.value is None and self.confidence != 0.0:
            raise ValueError("a verdict with no value must carry no confidence")


NO_VERDICT = ShapeVerdict(value=None, confidence=0.0)


def _tokens(raw: str) -> list[str]:
    """Letters only, split on everything else, with leading noise dropped.

    Digits become separators rather than being deleted: the recognizer renders
    `BỘ CÔNG AN` as `BO C0NG AI`, and treating that `0` as a break still leaves
    `BO` + `C` → head `BOC`, whereas deleting it would too.  What matters is
    that neither choice can shift a *later* letter into the head.
    """
    upper = strip_diacritics(nfc_upper(raw or ""))
    tokens = "".join(ch if ch.isalpha() else " " for ch in upper).split()
    while tokens and len(tokens[0]) < MIN_TOKEN_LETTERS:
        tokens.pop(0)
    return tokens


def discriminate(raw: str) -> ShapeVerdict:
    """Pick one of the 2 canonical issue places from the opening letters.

    Pure, synchronous, and repository-free — the one tier of §12.5 that needs
    no data because the field's whole domain is 2 values known at compile time.
    """
    tokens = _tokens(raw)
    if not tokens:
        return NO_VERDICT

    # ≥ MIN_TOKEN_LETTERS by construction — `_tokens` dropped everything shorter
    # off the front, so there is no separate minimum-length guard to write here.
    head = "".join(tokens)[:HEAD_LEN]

    # Compare against each canonical opening truncated to the same length, so a
    # partial read (`BO`) is scored on what it has instead of being punished for
    # what the recognizer never produced.
    scores = {canonical: fuzz.ratio(head, canonical_head[: len(head)])
              for canonical, canonical_head in _HEADS.items()}
    best = max(scores, key=lambda canonical: scores[canonical])
    runner_up = max(scores[c] for c in scores if c != best)
    if scores[best] < DECISIVE_SCORE or scores[best] - runner_up < MIN_MARGIN:
        return NO_VERDICT

    first_word_vote = (
        BO_CONG_AN if len(tokens[0]) <= SHORT_FIRST_WORD_MAX else CUC_CANH_SAT_QLHC_TTXH
    )
    corroborated = first_word_vote == best

    return ShapeVerdict(
        value=best,
        confidence=CONF_CORROBORATED if corroborated else CONF_HEAD_ONLY,
        head=head,
        head_score=scores[best],
        first_word_agrees=corroborated,
    )
