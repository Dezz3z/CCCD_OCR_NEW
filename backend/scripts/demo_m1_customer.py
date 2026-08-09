"""M1 milestone demo (roadmap §14.3): tạo Customer giả qua Composition Root
thật (Container → UnitOfWork → SqlAlchemyCustomerRepository →
DpapiCryptoService thật với DPAPI Windows thật), đọc lại qua repository,
rồi đọc THÔ cột `id_number_enc` bằng SQL trực tiếp — bỏ qua repository và
crypto service hoàn toàn — để xác nhận nó là nhị phân không đọc được.

Yêu cầu trước khi chạy: CSDL đích đã có bảng `customer` (chạy
`alembic upgrade head` nhắm vào cùng CSDL trước).

Cách chạy (từ thư mục `backend/`, virtualenv đã `pip install -e ".[dev]"`):

    $env:COCAS_DEMO_DATABASE_URL = "postgresql+asyncpg://user:pass@127.0.0.1:5432/cocas_m1_demo"
    python scripts/demo_m1_customer.py

Script tự dọn dẹp bản ghi demo ở bước cuối — không để lại dữ liệu rác.
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from datetime import UTC, date, datetime

from sqlalchemy import text

from cocas.config.settings import Settings
from cocas.container import Container
from cocas.domain.entities.customer import Customer
from cocas.domain.enums.data_quality import DataQuality
from cocas.domain.value_objects.citizen_id import CitizenId
from cocas.domain.value_objects.email_address import EmailAddress
from cocas.domain.value_objects.id_card_dates import IdCardDates
from cocas.domain.value_objects.issue_place import BO_CONG_AN, IssuePlace
from cocas.domain.value_objects.person_name import PersonName
from cocas.domain.value_objects.vietnamese_phone import VietnamesePhone

DEMO_ID_NUMBER = "001199012345"


async def main() -> None:
    database_url = os.environ.get("COCAS_DEMO_DATABASE_URL")
    if not database_url:
        print("Thiếu biến môi trường COCAS_DEMO_DATABASE_URL.", file=sys.stderr)
        sys.exit(1)

    settings = Settings(database_url=database_url)
    container = Container(settings)

    customer_id = uuid.uuid4()
    now = datetime(2026, 8, 9, 12, 0, tzinfo=UTC)

    print("== Mốc demo M1 — Composition Root thật · DPAPI thật · PostgreSQL thật ==\n")

    async with container.unit_of_work() as uow:
        customer = Customer(
            id=customer_id,
            created_by="demo-m1",
            full_name=PersonName("NGUYỄN VĂN AN"),
            id_number=CitizenId(DEMO_ID_NUMBER),
            date_of_birth=date(1990, 5, 14),
            issue_place=IssuePlace(BO_CONG_AN),
            id_card_dates=IdCardDates(date(2021, 5, 14), date(2031, 5, 14)),
            phone=VietnamesePhone("0912345678"),
            email=EmailAddress("an@example.com"),
            address="123 Đường Láng, Đống Đa, Hà Nội",
            data_quality=DataQuality.OCR_VERIFIED,
            created_at=now,
        )
        await uow.customers.add(customer)
        await uow.commit()
    print(f"1. Đã tạo Customer giả qua repository thật. id={customer_id}")

    async with container.unit_of_work() as uow:
        loaded = await uow.customers.get(customer_id)
        assert loaded is not None
        assert loaded.id_number.value == DEMO_ID_NUMBER
    print(f"2. Đọc lại qua repository → giải mã đúng: id_number = {loaded.id_number.value}")

    async with container.engine.connect() as conn:
        row = (
            await conn.execute(
                text("SELECT id_number_enc, id_number_masked FROM customer WHERE id = :id"),
                {"id": customer_id},
            )
        ).one()
    id_number_enc, id_number_masked = row
    raw_bytes = bytes(id_number_enc)

    print("3. Đọc THÔ cột id_number_enc bằng SQL trực tiếp (bỏ qua repository/crypto service):")
    print(f"   id_number_enc (hex, {len(raw_bytes)} bytes) = {raw_bytes.hex()}")
    print(f"   id_number_masked (dùng cho danh sách/log)   = {id_number_masked}")

    assert DEMO_ID_NUMBER.encode() not in raw_bytes, "PII LỘ RA Ở DẠNG NHỊ PHÂN THÔ!"
    print(f"\n✅ Xác nhận: chuỗi '{DEMO_ID_NUMBER}' KHÔNG xuất hiện trong nhị phân đã lưu.")
    print("   Có thể tự kiểm chứng thêm bằng công cụ DB ngoài (psql/pgAdmin) với:")
    print(f"   SELECT id_number_enc FROM customer WHERE id = '{customer_id}';")

    async with container.engine.begin() as conn:
        await conn.execute(text("DELETE FROM customer WHERE id = :id"), {"id": customer_id})
    print("\n4. Đã dọn dẹp bản ghi demo.")

    await container.close()


if __name__ == "__main__":
    asyncio.run(main())
