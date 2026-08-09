# PyInstaller build spec — trial build per roadmap §14.3 P1 checkpoint:
# "Build .exe thử lần đầu — đừng để đến P6 mới phát hiện PyInstaller không
# đóng gói được PaddleOCR." (§14.5, nguyên tắc chống rủi ro #1)
#
# This packages the FastAPI backend (`cocas.main`) as a PyInstaller `onedir`
# bundle — the same shape the final desktop build will use for
# `cocas-backend/` (§13.12). It intentionally does NOT yet bundle real
# PaddleOCR *model files* (`resources/ocr-models/` doesn't exist until P2 —
# there's no OCR adapter to point at them yet). The purpose of this trial is
# narrower: prove PyInstaller can successfully analyze and bundle the heavy
# native dependencies (paddlepaddle, paddleocr's own package data, OpenCV,
# cryptography/pywin32, asyncpg) at all, and produce a `.exe` that starts.
#
# Run from `backend/`:
#     pyinstaller build.spec --noconfirm
from __future__ import annotations

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

# ⭐ §11.8 lưu ý #2 — PyInstaller không tự phát hiện dữ liệu nạp động của
# paddleocr (font/config bên trong gói). `pyinstaller-hooks-contrib` (đã cài,
# xem pyproject.toml) cung cấp hook cho `paddle`/`cv2`; paddleocr's own
# package-internal data files still need to be collected explicitly.
datas = collect_data_files("paddleocr")
datas += [
    ("migrations", "migrations"),
]

# ⭐ §11.8 lưu ý #2 — DLL ngoài không được tự thu thập vì được nạp qua ctypes,
# không qua `import`.
binaries = []
import os as _os  # noqa: E402

import magic as _magic  # noqa: E402

_magic_dll = _os.path.join(_os.path.dirname(_magic.__file__), "libmagic", "libmagic.dll")
if _os.path.exists(_magic_dll):
    binaries.append((_magic_dll, "magic/libmagic"))

# ⭐ §11.8 / §13.13 — module nạp động bằng chuỗi, import-linter/mypy không
# thấy được nên PyInstaller's static analysis cũng bỏ sót.
hiddenimports = [
    "paddle",
    # ⭐ Lỗi thật phát hiện ở lần build trial đầu tiên: liệt kê mỗi
    # "asyncpg.pgproto" KHÔNG đủ — submodule biên dịch Cython thật cần nạp là
    # `asyncpg.pgproto.pgproto` (và các codec dưới nó). PyInstaller's static
    # analysis không thấy được vì asyncpg tự `import` chúng từ bên trong một
    # extension .pyx đã biên dịch. `collect_submodules` liệt kê đủ toàn bộ
    # cây con thay vì phải đoán từng tên.
    *collect_submodules("asyncpg"),
    "uvicorn.protocols.http.h11_impl",
    "uvicorn.protocols.http.httptools_impl",
    "uvicorn.protocols.websockets.websockets_impl",
    "uvicorn.lifespan.on",
    "uvicorn.loops.auto",
    "uvicorn.loops.asyncio",
    "alembic.ddl.postgresql",
]

# ⭐ §11.8 lưu ý #4 — giảm kích thước gói.
excludes = [
    "tkinter",
    "matplotlib",
    "PyQt5",
    "IPython",
    "pytest",
    "notebook",
]

a = Analysis(
    ["src/cocas/main.py"],
    pathex=["src"],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=excludes,
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="cocas-backend",
    console=True,  # ⭐ trial build only — production windowed build (console=False)
    # is a separate, deliberate change: it requires first fixing
    # loguru_config.configure_logging's console sink (sys.stderr is None
    # under windowed/noconsole mode, which crashes `logger.add(sys.stderr)`
    # at Container startup). Tracked for the real P5/P6 packaging pass.
)

# ⭐ §11.8 lưu ý #4 / §13.13 — UPX nén DLL của OpenCV và Paddle GÂY CRASH.
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    upx=True,
    upx_exclude=["opencv*.dll", "paddle*.dll", "libpaddle*.dll", "*.pyd"],
    name="cocas-backend",
)
