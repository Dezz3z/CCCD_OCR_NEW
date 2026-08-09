"""Display-masking for PII — the `_masked` columns (§4.4.6, §4.4.7).

⭐ These columns exist ONLY for logs and list views — never returned as the
"real" value from an API response (CLAUDE.md pitfall #6: full PII goes in
the response body; `_masked` is for `activity_log` and list-screen display).
"""
from __future__ import annotations

VISIBLE_SUFFIX_LENGTH = 4
MASK_CHAR = "•"


def mask_keep_suffix(value: str, visible: int = VISIBLE_SUFFIX_LENGTH) -> str:
    """`"001199012345"` -> `"••••••••2345"` — keep the last `visible` characters."""
    if len(value) <= visible:
        return MASK_CHAR * len(value)
    return MASK_CHAR * (len(value) - visible) + value[-visible:]
