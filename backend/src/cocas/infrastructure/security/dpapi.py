"""Windows DPAPI key-envelope management (§4.8.1, §4.8.5).

```
Windows DPAPI (phạm vi TÀI KHOẢN người dùng + optional_entropy riêng của app)
       │  bảo vệ file data/keys/master.key.dpapi
       ▼
     KEK (32 byte, chỉ tồn tại trong RAM)
```

`DpapiKeyManager` owns exactly that: load the wrapped KEK from disk and
unwrap it (normal startup), or generate a fresh KEK and wrap it (first
run). It never returns anything but the raw 32-byte KEK — HKDF derivation
of PEPPER/VAULT_KEY happens in `crypto.py`, one level up.
"""
from __future__ import annotations

import hashlib
import os
import secrets
from pathlib import Path

import win32crypt

from cocas.domain.exceptions import KeyUnavailableError

KEK_LENGTH_BYTES = 32

# ⭐ App-specific (not user-specific) entropy mixed into every DPAPI call —
# a defense-in-depth measure so a DPAPI-capable process can't unwrap this
# specific blob without also knowing this constant. Not a secret on its
# own (it's compiled into the app), but raises the bar above "any process
# running as this Windows user can read it".
_APP_ENTROPY = hashlib.sha256(b"cocas-dpapi-entropy-v1").digest()


class DpapiKeyManager:
    """Loads or creates the KEK, wrapped at rest by Windows DPAPI."""

    def __init__(self, key_file_path: Path) -> None:
        self._key_file_path = key_file_path

    def load_or_create_kek(self) -> bytes:
        """Return the 32-byte KEK, creating it on first run.

        ⭐ §4.8.5: if a different Windows account (or a reinstalled Windows)
        tries to unwrap this file, DPAPI fails and this raises
        `KeyUnavailableError` — there is no recovery path except restoring
        from a `.cocasbak` backup, by design.
        """
        if self._key_file_path.exists():
            return self._unwrap(self._key_file_path.read_bytes())

        kek = secrets.token_bytes(KEK_LENGTH_BYTES)
        self._write_wrapped(kek)
        return kek

    def rewrap_for_this_machine(self, kek: bytes) -> None:
        """Re-wrap an externally-supplied KEK (e.g. from backup restore, §4.8.6
        step 5: "bọc lại bằng DPAPI của máy mới") and persist it.
        """
        self._write_wrapped(kek)

    def _write_wrapped(self, kek: bytes) -> None:
        wrapped = self._wrap(kek)
        self._key_file_path.parent.mkdir(parents=True, exist_ok=True)
        # ⭐ CLAUDE.md convention: write-temp → verify → rename.
        tmp_path = self._key_file_path.with_suffix(".tmp")
        tmp_path.write_bytes(wrapped)
        if self._unwrap(tmp_path.read_bytes()) != kek:
            tmp_path.unlink(missing_ok=True)
            raise KeyUnavailableError("Xác minh khoá vừa ghi thất bại — huỷ thao tác.")
        os.replace(tmp_path, self._key_file_path)

    def _wrap(self, kek: bytes) -> bytes:
        result: bytes = win32crypt.CryptProtectData(
            kek, "COCAS master key", _APP_ENTROPY, None, None, 0
        )
        return result

    def _unwrap(self, wrapped: bytes) -> bytes:
        try:
            _description, kek = win32crypt.CryptUnprotectData(
                wrapped, _APP_ENTROPY, None, None, 0
            )
        except Exception as exc:
            raise KeyUnavailableError(
                "Không thể mở khoá chính. Có thể tài khoản Windows đã đổi hoặc "
                "máy đã cài lại — cần khôi phục từ bản sao lưu.",
            ) from exc
        kek_bytes: bytes = kek
        return kek_bytes
