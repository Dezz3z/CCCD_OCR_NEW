"""ExportNameGenerator — safe Windows filenames from `export_name_pattern` (§12.18).

⭐ Invariant enforced unconditionally: the result never contains
`\\ / : * ? " < > |`, is never a Windows-reserved device name, is at most
180 characters, and never collides with `existing_names`.
"""
from __future__ import annotations

import re

from cocas.domain.exceptions import BusinessRuleViolation
from cocas.domain.value_objects._vn_text import collapse_whitespace, strip_diacritics

MAX_LENGTH = 180
_FORBIDDEN_CHARS = re.compile(r'[\\/:*?"<>|\x00-\x1f]')
_TOKEN_PATTERN = re.compile(r"\{([a-zA-Z0-9_.]+)\}")
_RESERVED_NAMES = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{i}" for i in range(1, 10)}
    | {f"LPT{i}" for i in range(1, 10)}
)


class ExportNameGenerator:
    """Domain Service — generate a Windows-safe, non-colliding export filename."""

    def generate(
        self,
        pattern: str,
        context: dict[str, object],
        existing_names: set[str],
        *,
        strip_diacritics_flag: bool = False,
    ) -> str:
        if not pattern:
            raise BusinessRuleViolation(
                "Mẫu tên file xuất không được để trống.", code="EMPTY_EXPORT_NAME_PATTERN"
            )

        filled = _TOKEN_PATTERN.sub(lambda m: str(context.get(m.group(1), "")), pattern)
        cleaned = _FORBIDDEN_CHARS.sub("", filled)
        cleaned = collapse_whitespace(cleaned)
        cleaned = cleaned.rstrip(". ")

        if strip_diacritics_flag:
            cleaned = strip_diacritics(cleaned)

        if not cleaned:
            cleaned = "Tài liệu"

        if cleaned.upper() in _RESERVED_NAMES:
            cleaned = f"_{cleaned}"

        cleaned = cleaned[:MAX_LENGTH].rstrip(". ")

        return self._disambiguate(cleaned, existing_names)

    def _disambiguate(self, name: str, existing_names: set[str]) -> str:
        if name not in existing_names:
            return name
        counter = 2
        while True:
            suffix = f" ({counter})"
            truncated = name[: MAX_LENGTH - len(suffix)]
            candidate = f"{truncated}{suffix}"
            if candidate not in existing_names:
                return candidate
            counter += 1
