"""seed_province_code

Seeds the 63-province CCCD code table (§4.4.15), used by V-OCR-021 to check
that a CCCD's first 3 digits are a real province code.

⭐ Source: codes 001–096 are the fixed province codes from Circular
07/2016/TT-BCA Appendix I, cross-checked across 3 independent secondary
sources during this session (all converged on an identical 63-entry list;
the 3 anchors 001=Hà Nội / 079=TP.HCM / 048=Đà Nẵng were confirmed). These
codes are permanent — already-issued CCCDs keep them even after the 2025
province mergers, so the pre-2025 63-province structure is deliberately
what's seeded here, not the current administrative map.

⚠️ The `region` column is a conventional 7-vùng geo-economic grouping
(Tổng cục Thống kê) applied for display/filtering purposes — it is NOT
verified against the circular's own text (no legal weight) and isn't used
by any validation rule.

Idempotent: `ON CONFLICT (code) DO NOTHING`.

Revision ID: 20260811_005_seed_province
Revises: 20260811_004_seed_alias
Create Date: 2026-08-11

"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import insert as pg_insert

# revision identifiers, used by Alembic.
revision = "20260811_005_seed_province"
down_revision = "20260811_004_seed_alias"
branch_labels = None
depends_on = None

_province_code = sa.table(
    "province_code",
    sa.column("code", sa.String),
    sa.column("name", sa.String),
    sa.column("region", sa.String),
    sa.column("is_active", sa.Boolean),
)

_DBSH = "Đồng bằng sông Hồng"
_TDMNPB = "Trung du và miền núi phía Bắc"
_BTB = "Bắc Trung Bộ"
_DHNTB = "Duyên hải Nam Trung Bộ"
_TN = "Tây Nguyên"
_DNB = "Đông Nam Bộ"
_DBSCL = "Đồng bằng sông Cửu Long"

# (code, name, region)
_SEED_ROWS: list[tuple[str, str, str]] = [
    ("001", "Hà Nội", _DBSH),
    ("002", "Hà Giang", _TDMNPB),
    ("004", "Cao Bằng", _TDMNPB),
    ("006", "Bắc Kạn", _TDMNPB),
    ("008", "Tuyên Quang", _TDMNPB),
    ("010", "Lào Cai", _TDMNPB),
    ("011", "Điện Biên", _TDMNPB),
    ("012", "Lai Châu", _TDMNPB),
    ("014", "Sơn La", _TDMNPB),
    ("015", "Yên Bái", _TDMNPB),
    ("017", "Hòa Bình", _TDMNPB),
    ("019", "Thái Nguyên", _TDMNPB),
    ("020", "Lạng Sơn", _TDMNPB),
    ("022", "Quảng Ninh", _DBSH),
    ("024", "Bắc Giang", _TDMNPB),
    ("025", "Phú Thọ", _TDMNPB),
    ("026", "Vĩnh Phúc", _DBSH),
    ("027", "Bắc Ninh", _DBSH),
    ("030", "Hải Dương", _DBSH),
    ("031", "Hải Phòng", _DBSH),
    ("033", "Hưng Yên", _DBSH),
    ("034", "Thái Bình", _DBSH),
    ("035", "Hà Nam", _DBSH),
    ("036", "Nam Định", _DBSH),
    ("037", "Ninh Bình", _DBSH),
    ("038", "Thanh Hóa", _BTB),
    ("040", "Nghệ An", _BTB),
    ("042", "Hà Tĩnh", _BTB),
    ("044", "Quảng Bình", _BTB),
    ("045", "Quảng Trị", _BTB),
    ("046", "Thừa Thiên Huế", _BTB),
    ("048", "Đà Nẵng", _DHNTB),
    ("049", "Quảng Nam", _DHNTB),
    ("051", "Quảng Ngãi", _DHNTB),
    ("052", "Bình Định", _DHNTB),
    ("054", "Phú Yên", _DHNTB),
    ("056", "Khánh Hòa", _DHNTB),
    ("058", "Ninh Thuận", _DHNTB),
    ("060", "Bình Thuận", _DHNTB),
    ("062", "Kon Tum", _TN),
    ("064", "Gia Lai", _TN),
    ("066", "Đắk Lắk", _TN),
    ("067", "Đắk Nông", _TN),
    ("068", "Lâm Đồng", _TN),
    ("070", "Bình Phước", _DNB),
    ("072", "Tây Ninh", _DNB),
    ("074", "Bình Dương", _DNB),
    ("075", "Đồng Nai", _DNB),
    ("077", "Bà Rịa - Vũng Tàu", _DNB),
    ("079", "TP. Hồ Chí Minh", _DNB),
    ("080", "Long An", _DBSCL),
    ("082", "Tiền Giang", _DBSCL),
    ("083", "Bến Tre", _DBSCL),
    ("084", "Trà Vinh", _DBSCL),
    ("086", "Vĩnh Long", _DBSCL),
    ("087", "Đồng Tháp", _DBSCL),
    ("089", "An Giang", _DBSCL),
    ("091", "Kiên Giang", _DBSCL),
    ("092", "Cần Thơ", _DBSCL),
    ("093", "Hậu Giang", _DBSCL),
    ("094", "Sóc Trăng", _DBSCL),
    ("095", "Bạc Liêu", _DBSCL),
    ("096", "Cà Mau", _DBSCL),
]


def upgrade() -> None:
    assert len(_SEED_ROWS) == 63
    for code, name, region in _SEED_ROWS:
        op.execute(
            pg_insert(_province_code)
            .values(code=code, name=name, region=region, is_active=True)
            .on_conflict_do_nothing(index_elements=["code"])
        )


def downgrade() -> None:
    codes = [row[0] for row in _SEED_ROWS]
    op.execute(_province_code.delete().where(_province_code.c.code.in_(codes)))
