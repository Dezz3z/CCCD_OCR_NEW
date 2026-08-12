"""Nạp 2 file `.docx` mẫu thật vào Template Store và kích hoạt chúng.

Migration `008` gieo 2 dòng `contract_template` nhưng cố ý để
`active_version_id` NULL — lúc viết nó chưa có file `.docx` nào. Một mẫu không
có phiên bản kích hoạt thì `V-CTR-002` chặn cứng (`COCAS-6006`), nên đây là
bước bootstrap còn thiếu giữa "đã chạy migration" và "sinh được hợp đồng".

⭐ Script này **đi qua `RegisterTemplateVersionUseCase` thật**, không chèn
thẳng SQL. Nghĩa là file cũng bị `DocxTemplateInspector` (Port 20) soi đúng
như khi người dùng tải lên qua `POST /templates/{id}/versions`, và
`declared_variables` trong CSDL là thứ Port 20 thực sự đọc được — không phải
một danh sách chép tay sẽ lạc hậu ngay lần sửa mẫu đầu tiên.

Chạy lại được nhiều lần: mỗi lần chạy tạo một `version_no` mới và kích hoạt
nó, phiên bản cũ chuyển sang `archived_at` chứ không bị xoá (P-09).

    python backend/scripts/bootstrap_templates.py
    python backend/scripts/bootstrap_templates.py --source "C:\\Users\\...\\HĐ"
"""
from __future__ import annotations

import argparse
import asyncio
import sys
import uuid
from pathlib import Path

from sqlalchemy import select

from cocas.application.use_cases.template.register_template_version import (
    RegisterTemplateVersionCommand,
)
from cocas.config.settings import Settings
from cocas.container import Container
from cocas.infrastructure.persistence.models.contract_template import ContractTemplateModel

#: Mặc định: cây `resources/` trong repo, cùng bố cục với Template Store.
DEFAULT_SOURCE = Path(__file__).resolve().parents[1] / "resources" / "templates"

#: `contract_template.code` -> tên file trong thư mục nguồn.
#:
#: ⚠️ Hai mã KHÁC nhau ở chỗ dễ nhầm: bảng dùng `01A_GDKQ`, còn file người dùng
#: đưa tên là `01A_HD_GDKQ.docx`. Ánh xạ tường minh ở đây thay vì suy từ tên
#: file, vì suy sai sẽ gắn file GDKQ vào mẫu GDN mà không có gì báo.
_FILENAMES = {
    "01A_HD_GDN": ("01A_HD_GDN", "01A_HD_GDN.docx"),
    "01A_GDKQ": ("01A_GDKQ", "01A_HD_GDKQ.docx"),
}


def _find_source_file(source: Path, code: str) -> Path:
    """Tìm file `.docx` cho một mã mẫu, ở cả hai bố cục nguồn."""
    subdir, flat_name = _FILENAMES[code]

    # (a) bố cục kho: `<source>/<code>/v1/template.docx`
    nested = source / subdir / "v1" / "template.docx"
    if nested.is_file():
        return nested

    # (b) bố cục người dùng đưa: `<source>/01A_HD_GDN.docx`
    flat = source / flat_name
    if flat.is_file():
        return flat

    raise SystemExit(
        f"Không tìm thấy file mẫu cho '{code}'.\n"
        f"  đã thử: {nested}\n"
        f"  đã thử: {flat}"
    )


async def _template_ids(container: Container) -> dict[str, uuid.UUID]:
    async with container.session_factory() as session:
        rows = (
            await session.execute(
                select(ContractTemplateModel.code, ContractTemplateModel.id)
            )
        ).all()
    return dict(rows)


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        type=Path,
        default=DEFAULT_SOURCE,
        help=f"thư mục chứa file .docx (mặc định: {DEFAULT_SOURCE})",
    )
    args = parser.parse_args()

    container = Container(Settings())
    try:
        ids = await _template_ids(container)
        if not ids:
            raise SystemExit(
                "Bảng contract_template rỗng — chạy 'alembic upgrade head' trước."
            )

        use_case = container.register_template_version_use_case()
        print(f"Kho mẫu: {container.template_store.root}\n")

        for code in _FILENAMES:
            if code not in ids:
                print(f"  ⚠️  {code}: không có trong CSDL, bỏ qua")
                continue

            path = _find_source_file(args.source, code)
            data = path.read_bytes()
            result = await use_case.execute(
                RegisterTemplateVersionCommand(
                    template_id=ids[code],
                    file_bytes=data,
                    original_filename=path.name,
                    created_by="bootstrap",
                    changelog="Bootstrap từ resources/templates",
                    activate=True,
                )
            )
            flag = "✅" if result.validation_status.value != "INVALID" else "❌"
            print(
                f"  {flag} {code}  v{result.version_no}  "
                f"{result.file_size_bytes / 1024:.0f} KB  "
                f"{len(result.declared_variables)} biến  "
                f"{result.validation_status.value}"
            )
            for diagnostic in result.diagnostics:
                print(f"       ↳ {diagnostic['code']} {diagnostic['message']}")
    finally:
        await container.close()

    print("\nXong. Hai mẫu đã có phiên bản kích hoạt.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
