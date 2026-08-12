"""Mốc demo M3 — gọi API tuần tự, nhận về một file `.docx` mở được bằng Word.

Đi đúng 16 lượt gọi của [`05-thiet-ke-api.md §5.4`], trên một server đang chạy
thật, từ 2 ảnh CCCD thật tới file hợp đồng tải về. Không mock, không fake, không
gọi tắt vào Use Case: mọi thứ đi qua HTTP, qua middleware token, qua hàng đợi.

    # cửa sổ 1
    python backend/scripts/pgctl.ps1 start        # nếu cụm chưa chạy
    python -m uvicorn cocas.main:create_app --factory --port 8000

    # cửa sổ 2
    python backend/scripts/demo_m3_contract.py --images "C:\\Users\\ph7mt\\Downloads\\CCCD"

⭐ **Bộ ảnh được ghép cặp bằng số CCCD mà QR/MRZ cùng in, không bằng tên file.**
Ghép theo tên file liền nhau từng tạo ra một bộ số hoàn toàn giả (23/26 cặp báo
`SOURCE_CONFLICT`) vì nó đưa ảnh của hai người khác nhau vào cùng một thẻ —
phát hiện #35 trong `progress.md`. Ở đây chỉ cần một cặp, nhưng cặp đó phải
đúng, nên script mượn lại đúng cách ghép của `verify_pipeline.py`.

⚠️ Script này **không đo hiệu năng**. Đo thời gian xen kẽ với việc nặng khác đã
ba lần cho ra kết quả đảo chỗ giữa hai lần chạy giống hệt nhau; muốn con số thì
dùng `verify_docx_render.py` và `verify_contract_generation.py`, mỗi phép đo
một tiến trình sạch.
"""
from __future__ import annotations

import argparse
import gc
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any
from urllib.parse import unquote

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cocas.config.settings import Settings
from cocas.domain.enums.field_key import FieldKey
from cocas.domain.exceptions import OcrProcessingError
from cocas.domain.ports.ocr import DocumentTypeSpec, PreprocessProfile
from cocas.infrastructure.ocr.channels.mrz_reader import Td1MrzReader
from cocas.infrastructure.ocr.channels.qr_decoder import ZxingQrDecoder
from cocas.infrastructure.ocr.engines.paddle_ocr_adapter import (
    PaddleOcrAdapter,
)
from cocas.infrastructure.ocr.preprocessing.opencv_preprocessor import (
    OpenCvPreprocessor,
)

#: Minimal spec for the MRZ reader — it only consults `has_mrz` and the scan
#: band, never the zone map, so the harness does not need the seeded row.
_MRZ_DOC_TYPE = DocumentTypeSpec(
    code="CCCD_CHIP",
    name="CCCD gắn chip",
    field_schema=[],
    zone_map={},
    anchor_patterns={},
    has_qr=True,
    has_mrz=True,
    is_ocr_supported=True,
    expected_aspect_ratio=1.585,
)

DEFAULT_BASE_URL = "http://127.0.0.1:8000"
DEFAULT_IMAGES = Path(r"C:\Users\ph7mt\Downloads\CCCD")

#: How long to poll `GET /ocr/{id}/progress`. Generous on purpose: constraint
#: #8 measured p95 at 12.4 s/pair on a 4-core/4 GB machine, and a cold
#: PaddleOCR warm-up adds several more the first time.
POLL_TIMEOUT_SECONDS = 180.0
POLL_INTERVAL_SECONDS = 0.8

_OK = "\u2705"
_BAD = "\u274c"
_WARN = "\u26a0\ufe0f "


class DemoFailed(RuntimeError):
    """A step did not do what §5.4 says it should."""


class Api:
    """Thin wrapper that fails loudly and prints every call."""

    def __init__(self, client: httpx.Client) -> None:
        self._client = client
        self.step = 0

    def call(
        self, method: str, path: str, *, expect: int | tuple[int, ...] = 200, **kwargs: Any
    ) -> httpx.Response:
        self.step += 1
        response = self._client.request(method, path, **kwargs)
        wanted = (expect,) if isinstance(expect, int) else expect
        mark = _OK if response.status_code in wanted else _BAD
        print(f"  {mark} {self.step:>2}. {method:<6} {path:<48} → {response.status_code}")
        if response.status_code not in wanted:
            body = response.text[:400]
            raise DemoFailed(f"{method} {path} trả {response.status_code}: {body}")
        return response


def _find_pair(folder: Path, models_dir: Path) -> tuple[Path, Path]:
    """Two photos of the same card, matched by the id number QR/MRZ both print.

    ⚠️ Uses the QR channel only, and releases the engine before returning.
    Constraint #9: two PaddleOCR passes at once on this 4-core/4 GB machine
    raise `Insufficient memory` **from inside OpenCV**, which surfaces as a
    decode error rather than as memory pressure. The server is about to run its
    own pass, so this process must not still be holding model weights.
    """
    images = sorted(
        p for p in folder.iterdir() if p.suffix.lower() in {".jpg", ".jpeg", ".png"}
    )
    if not images:
        raise DemoFailed(f"Không có ảnh nào trong {folder}")

    # 🔴 BOTH channels, and the channel is recorded. Pairing on QR alone
    # produced two photographs of the **same** side (measured 2026-08-12: the
    # server answered `DUPLICATE_SIDE`), because on a 2021 card the QR is on
    # the front — so "two images whose QR gives this id" means "two fronts".
    # The two sides are distinguishable precisely because different channels
    # read them: QR → front, MRZ → back (2021). One channel cannot pair a card;
    # it can only group photos of one face of it.
    engine = PaddleOcrAdapter(str(models_dir))
    engine.warm_up()
    preprocessor = OpenCvPreprocessor()
    qr_decoder = ZxingQrDecoder()
    mrz_reader = Td1MrzReader(engine)
    profile = PreprocessProfile()

    by_id: dict[str, dict[str, Path]] = defaultdict(dict)
    try:
        for path in images:
            try:
                image_set = preprocessor.prepare(path.read_bytes(), None, profile)
            except (OcrProcessingError, OSError):
                continue

            qr = qr_decoder.decode(image_set)
            if qr.available and qr.layout_recognized:
                citizen_id = qr.fields.get(FieldKey.ID_NUMBER)
                if citizen_id:
                    by_id[citizen_id].setdefault("qr", path)
            else:
                mrz = mrz_reader.read(image_set, _MRZ_DOC_TYPE)
                if mrz.available:
                    citizen_id = mrz.fields.get(FieldKey.ID_NUMBER)
                    if citizen_id:
                        by_id[citizen_id].setdefault("mrz", path)

            for citizen_id, sides in by_id.items():
                if "qr" in sides and "mrz" in sides:
                    print(
                        f"  cặp ảnh: {sides['qr'].name} (QR) + "
                        f"{sides['mrz'].name} (MRZ)  ·  CCCD …{citizen_id[-4:]}"
                    )
                    return sides["qr"], sides["mrz"]
    finally:
        # Release the model weights before the server loads its own — two
        # concurrent PaddleOCR passes on 4 GB raise `Insufficient memory`
        # from inside OpenCV (constraint #9).
        del engine, mrz_reader
        gc.collect()

    raise DemoFailed(
        "Không ghép được cặp ảnh nào (cần một ảnh đọc được QR và một ảnh đọc "
        "được MRZ của cùng số CCCD). Truyền --front và --back để chỉ định tay."
    )


def _fields(payload: dict[str, Any]) -> dict[str, Any]:
    return {field["field_key"]: field for field in payload.get("fields", [])}


def _upload(api: Api, side: str, path: Path) -> str:
    """Tải một ảnh lên, hoặc dùng lại ảnh đã có nếu trùng nội dung.

    ⭐ `COCAS-3007` là hành vi đúng, không phải lỗi cần né: `card_image.sha256`
    UNIQUE để một tấm ảnh không nằm hai lần trong Vault. Nhưng nó khiến script
    demo chạy lần thứ hai là hỏng, nên ở đây bắt đúng mã đó và lấy `image_id`
    mà API trả kèm — cũng chính là điều giao diện sẽ làm ở P4.
    """
    with path.open("rb") as handle:
        response = api.call(
            "POST", f"/api/v1/upload/{side}", expect=(201, 409),
            files={"file": (path.name, handle, "image/jpeg")},
        )
    if response.status_code == 201:
        return str(response.json()["id"])

    error = response.json().get("error", {})
    if error.get("code") != "COCAS-3007":
        raise DemoFailed(f"Tải ảnh {side} thất bại: {error}")
    reused = next(
        (
            item["message"]
            for item in error.get("details", [])
            if item.get("field") == "image_id"
        ),
        None,
    )
    if reused is None:
        raise DemoFailed("API báo ảnh trùng nhưng không trả về image_id.")
    print(f"       ↳ ảnh đã có sẵn, dùng lại {reused[:8]}…")
    return str(reused)


def _disposition_name(response: httpx.Response) -> str:
    """The RFC 5987 `filename*` value out of `Content-Disposition`."""
    disposition = response.headers.get("content-disposition", "")
    marker = "filename*=UTF-8''"
    if marker not in disposition:
        return ""
    return disposition.split(marker, 1)[1].strip().strip('"')


def run(base_url: str, front: Path, back: Path, token: str) -> int:
    headers = {"X-Local-Token": token}
    with httpx.Client(base_url=base_url, headers=headers, timeout=60.0) as client:
        api = Api(client)

        print("\n§5.4 — luồng gọi API hoàn chỉnh cho một hợp đồng\n")

        # 1 — sẵn sàng chưa
        health = api.call("GET", "/api/v1/system/health").json()
        if health["components"]["database"]["status"] != "ok":
            raise DemoFailed(f"CSDL không sẵn sàng: {health['components']['database']}")

        # 2 — có mẫu nào
        templates = api.call("GET", "/api/v1/templates").json()["items"]
        usable = [t for t in templates if t["has_active_version"]]
        if not usable:
            raise DemoFailed(
                "Không mẫu nào có phiên bản kích hoạt — chạy bootstrap_templates.py trước."
            )
        template = usable[0]

        # 3 — party_schema điều khiển wizard
        requirements = api.call(
            "GET", f"/api/v1/templates/{template['id']}/requirements"
        ).json()
        needs_bank = any(
            "bank_account" in party.get("collect", [])
            for party in requirements["party_schema"]
        )

        # 4, 5 — hai ảnh
        front_id = _upload(api, "front", front)
        back_id = _upload(api, "back", back)

        # 6 — xếp hàng
        queued = api.call(
            "POST", "/api/v1/ocr", expect=202,
            json={"front_image_id": front_id, "back_image_id": back_id},
        ).json()
        session_id = queued["session_id"]

        # 7 — poll cho tới khi xong
        deadline = time.monotonic() + POLL_TIMEOUT_SECONDS
        status = queued["status"]
        polls = 0
        while time.monotonic() < deadline:
            time.sleep(POLL_INTERVAL_SECONDS)
            polls += 1
            progress = client.get(f"/api/v1/ocr/{session_id}/progress").json()
            status = progress["status"]
            if status in {"COMPLETED", "COMPLETED_WITH_WARNINGS", "FAILED"}:
                break
        api.step += 1
        mark = _OK if status.startswith("COMPLETED") else _BAD
        print(f"  {mark} {api.step:>2}. POLL   /ocr/{{id}}/progress x{polls:<28} -> {status}")
        if not status.startswith("COMPLETED"):
            detail = client.get(f"/api/v1/ocr/{session_id}").json()
            raise DemoFailed(
                f"OCR kết thúc ở {status}: "
                f"{detail.get('error_code')} {detail.get('error_message')}"
            )

        # 8 — kết quả đầy đủ
        result = api.call("GET", f"/api/v1/ocr/{session_id}").json()
        fields = _fields(result)
        missing = [key for key in _REQUIRED_FIELDS if not fields.get(key, {}).get("value")]
        if missing:
            raise DemoFailed(f"Thiếu trường sau OCR: {', '.join(missing)}")

        # 9 — sửa những ô hệ thống tự đánh dấu cần xem lại
        review = [f for f in result["fields"] if f["needs_review"]]
        if review:
            api.call(
                "PATCH", f"/api/v1/ocr/{session_id}/fields",
                json={
                    "fields": [
                        {"field_id": f["id"], "value": f["value"] or "KHÔNG RÕ"}
                        for f in review
                    ]
                },
            )
        else:
            api.step += 1
            print(f"  {_OK} {api.step:>2}. PATCH  /ocr/{{id}}/fields (0 ô cần sửa){'':<15} → bỏ qua")

        # 10 — xác nhận
        api.call("POST", f"/api/v1/ocr/{session_id}/confirm")

        # 11 — khách này đã có chưa
        id_number = fields[FieldKey.ID_NUMBER.value]["value"]
        existing = api.call(
            "GET", "/api/v1/customers",
            params={"id_number": id_number, "exact": "true"},
        ).json()["items"]

        # 12 — gợi ý ngân hàng
        banks = api.call(
            "GET", "/api/v1/reference/banks", params={"q": "ngoai thuong"}
        ).json()["items"]

        # 13 — tạo khách hàng (hoặc dùng lại)
        if existing:
            customer_id = existing[0]["id"]
            # ⚠️ Lấy luôn TK ngân hàng của khách cũ. Bỏ qua bước này khiến
            # `V-CTR-007` (`COCAS-7012`) chặn ở bước 14 với mẫu GDN — và đó là
            # quy tắc đúng: script mới là thứ quên mang theo dữ liệu.
            accounts = existing[0].get("bank_accounts", [])
            bank_account_id = accounts[0]["id"] if accounts else None
            api.step += 1
            print(
                f"  {_OK} {api.step:>2}. (khách đã có, dùng lại){'':<28} "
                f"-> {customer_id[:8]}… · {len(accounts)} TK ngân hàng"
            )
        else:
            body = _customer_body(fields, id_number, session_id)
            if needs_bank:
                bank = banks[0] if banks else {"short_name": "Vietcombank", "code": "VCB"}
                body["bank_account"] = {
                    "account_number": "0011001234567",
                    "bank_name": bank["short_name"],
                    "bank_code": bank["code"],
                    "branch": "Sở giao dịch",
                }
            created = api.call("POST", "/api/v1/customers", expect=201, json=body).json()
            customer_id = created["id"]
            bank_account_id = created["bank_account_id"]

        # 14 — sinh hợp đồng
        contract = api.call(
            "POST", "/api/v1/contracts/generate", expect=201,
            json={
                "template_id": template["id"],
                "parties": [
                    {
                        "party_key": requirements["party_schema"][0]["key"],
                        "customer_id": customer_id,
                        "bank_account_id": bank_account_id,
                        "ocr_session_id": session_id,
                    }
                ],
                "created_by": "demo",
                "created_by_name": "Nhân viên Demo",
            },
        ).json()

        # 15 — tải file về
        download = api.call(
            "GET", f"/api/v1/contracts/{contract['id']}/documents/docx"
        )

    return _report(
        template, requirements, result, fields, contract, download, needs_bank
    )


_REQUIRED_FIELDS = (
    FieldKey.FULL_NAME.value,
    FieldKey.ID_NUMBER.value,
    FieldKey.DATE_OF_BIRTH.value,
    FieldKey.ISSUE_DATE.value,
    FieldKey.ISSUE_PLACE.value,
)


def _customer_body(
    fields: dict[str, Any], id_number: str, session_id: str
) -> dict[str, Any]:
    """Map the OCR result onto §5.3.7's request body.

    ⚠️ `expiry_date` absent means KHÔNG THỜI HẠN, which is a real value rather
    than a gap (`IdCardDates`) — so an unread expiry is passed as `None`, not
    as an invented date.
    """

    def value(key: str) -> Any:
        return fields.get(key, {}).get("value")

    return {
        "full_name": value(FieldKey.FULL_NAME.value),
        "id_number": id_number,
        "date_of_birth": value(FieldKey.DATE_OF_BIRTH.value),
        "issue_date": value(FieldKey.ISSUE_DATE.value),
        "expiry_date": _expiry(value(FieldKey.EXPIRY_DATE.value)),
        "issue_place": value(FieldKey.ISSUE_PLACE.value),
        "phone": "0912345678",
        "email": "demo@example.com",
        "address": "Số 1 Đường Demo, Phường Demo, Quận Demo, Hà Nội",
        "created_by": "demo",
        "ocr_session_id": session_id,
    }


def _expiry(raw: Any) -> str | None:
    if not raw or not isinstance(raw, str):
        return None
    return None if raw.upper().startswith("KH") else raw


def _report(
    template: dict[str, Any],
    requirements: dict[str, Any],
    result: dict[str, Any],
    fields: dict[str, Any],
    contract: dict[str, Any],
    download: httpx.Response,
    needs_bank: bool,
) -> int:
    print("\n" + "=" * 74)
    print("KẾT QUẢ")
    print("=" * 74)
    print(f"  Mẫu               {template['code']} — {template['name']}")
    print(
        f"  Wizard            {requirements['wizard_steps']} bước · "
        f"{len(requirements['party_schema'])} bên · "
        f"{'có' if needs_bank else 'không'} TK ngân hàng"
    )
    print(f"  Phiên OCR         {result['status']} · {result['duration_ms']} ms")
    print(f"  Kênh              {result['channels']}")
    print(f"  Trường đọc được   {len(result['fields'])}/6")
    for key in _REQUIRED_FIELDS:
        field = fields.get(key, {})
        flag = _WARN if field.get("needs_review") else "  "
        print(
            f"    {flag}{key:<16} {str(field.get('value'))[:34]:<36}"
            f"{field.get('source', ''):<5} {field.get('confidence', 0):.2f}"
        )
    print(f"  Hợp đồng          {contract['contract_no']}")
    print(f"  Tên file xuất     {contract['export_name']}")
    print(f"  Sinh trong        {contract['generation_ms']} ms")
    for warning in contract.get("warnings", []):
        print(f"    {_WARN}{warning['code']} {warning['message']}")

    body = download.content
    checks = [
        ("file tải về là .docx (PK zip magic)", body[:2] == b"PK"),
        (
            "content-type đúng",
            "wordprocessingml" in download.headers.get("content-type", ""),
        ),
        (
            "sha256 header khớp nội dung",
            download.headers.get("x-content-sha256") == contract["file_sha256"],
        ),
        ("kích thước khớp bản ghi", len(body) == contract["file_size_bytes"]),
        (
            "Cache-Control: no-store (§5.5 #4)",
            download.headers.get("cache-control") == "no-store",
        ),
        (
            "tên file tiếng Việt qua được header",
            "filename*=UTF-8" in download.headers.get("content-disposition", ""),
        ),
        (
            "tên file có đuôi .docx",
            ".docx" in _disposition_name(download),
        ),
    ]
    print("\n  Kiểm tra file tải về:")
    failed = 0
    for label, passed in checks:
        print(f"    {_OK if passed else _BAD} {label}")
        failed += 0 if passed else 1

    out = Path.cwd() / (unquote(_disposition_name(download)) or "contract.docx")
    out.write_bytes(body)
    print(f"\n  Đã ghi: {out}")

    print("\n" + "=" * 74)
    if failed:
        print(f"{_BAD} M3 CHƯA ĐẠT — {failed} phép kiểm tra trượt")
        return 1
    print(f"{_OK} M3 ĐẠT — hai ảnh CCCD → một file .docx, đi trọn qua HTTP")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--images", type=Path, default=DEFAULT_IMAGES)
    parser.add_argument("--front", type=Path, default=None)
    parser.add_argument("--back", type=Path, default=None)
    parser.add_argument(
        "--models",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "resources" / "ocr-models",
    )
    args = parser.parse_args()

    try:
        if args.front and args.back:
            front, back = args.front, args.back
        else:
            print("Đang ghép cặp ảnh bằng số CCCD trong QR…")
            front, back = _find_pair(args.images, args.models)
        return run(args.base_url, front, back, Settings().local_token_secret)
    except DemoFailed as exc:
        print(f"\n{_BAD} {exc}")
        return 1
    except httpx.ConnectError:
        print(
            f"\n{_BAD} Không kết nối được {args.base_url}.\n"
            "   Khởi động server trước:\n"
            "   python -m uvicorn cocas.main:create_app --factory --port 8000"
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
