<#
.SYNOPSIS
    Điều khiển cụm PostgreSQL riêng của COCAS ở cổng 55432.

.DESCRIPTION
    Thiết kế (§4.1, P5) gọi đây là "PostgreSQL portable": một cụm thuộc về ứng
    dụng, chạy dưới tài khoản người dùng thường, không cần quyền admin, không
    đăng ký service. Script này là bản dựng tay của phần đó — Supervisor của
    Tauri sẽ làm đúng những lệnh này ở P5.

    ⚠️ Cụm này KHÔNG phải cụm PostgreSQL nào khác đang có trên máy. Nó nghe ở
    cổng 55432 và có thư mục dữ liệu riêng, nên chạy song song với một bản cài
    PostgreSQL ở 5432 mà không đụng nhau — đó là lý do chọn cổng lạ ngay từ
    thiết kế.

    Nhị phân lấy từ bản PostgreSQL đã cài sẵn trên máy (mặc định dò tìm). Bản
    đóng gói cuối cùng sẽ mang theo nhị phân riêng; ở giai đoạn phát triển thì
    mượn là đủ và tránh phải tải thêm.

.PARAMETER Command
    init | start | stop | status | reset

    init    initdb + tạo database `cocas` (chỉ chạy được khi chưa có dữ liệu)
    start   khởi động cụm
    stop    dừng cụm (chế độ fast)
    status  báo cụm sống hay chết
    reset   XOÁ TRẮNG thư mục dữ liệu rồi init lại — mất toàn bộ hợp đồng đã sinh

.EXAMPLE
    .\pgctl.ps1 start
#>
[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [ValidateSet("init", "start", "stop", "status", "reset")]
    [string]$Command = "status",

    [string]$PgBin = "",
    [string]$DataDir = "$env:LOCALAPPDATA\COCAS\pgdata",
    [int]$Port = 55432,
    [string]$Role = "cocas",
    [string]$Database = "cocas"
)

$ErrorActionPreference = "Stop"

function Resolve-PgBin {
    if ($PgBin -ne "") { return $PgBin }

    # Cụm đang chạy như một service là nguồn nhị phân đáng tin nhất.
    $svc = Get-CimInstance Win32_Service -Filter "Name LIKE 'postgresql%'" -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if ($null -ne $svc -and $svc.PathName -match '"([^"]+)\\pg_ctl\.exe"') {
        return $Matches[1]
    }

    foreach ($candidate in @(
            "D:\Software\PostgreSQL\bin",
            "C:\Program Files\PostgreSQL\18\bin",
            "C:\Program Files\PostgreSQL\17\bin",
            "C:\Program Files\PostgreSQL\16\bin")) {
        if (Test-Path (Join-Path $candidate "pg_ctl.exe")) { return $candidate }
    }

    throw "Không tìm thấy nhị phân PostgreSQL. Truyền -PgBin '<đường dẫn>\bin'."
}

$bin = Resolve-PgBin
$pgctl = Join-Path $bin "pg_ctl.exe"
$logFile = Join-Path $DataDir "server.log"

function Invoke-Init {
    if (Test-Path (Join-Path $DataDir "PG_VERSION")) {
        throw "Đã có cụm ở $DataDir. Dùng 'reset' nếu thật sự muốn xoá trắng."
    }
    New-Item -ItemType Directory -Force -Path (Split-Path $DataDir) | Out-Null

    # Mật khẩu đi qua file chứ không qua tham số dòng lệnh: tham số hiện trong
    # danh sách tiến trình cho mọi người dùng trên máy đọc được.
    $pwFile = Join-Path ([System.IO.Path]::GetTempPath()) "cocas_initdb_pw.txt"
    try {
        Set-Content -Path $pwFile -Value $Role -Encoding ascii -NoNewline
        & (Join-Path $bin "initdb.exe") -D $DataDir -U $Role --pwfile=$pwFile `
            --encoding=UTF8 --locale=C --auth-local=trust --auth-host=scram-sha-256
        if ($LASTEXITCODE -ne 0) { throw "initdb thất bại ($LASTEXITCODE)" }
    }
    finally {
        Remove-Item $pwFile -Force -ErrorAction SilentlyContinue
    }

    Add-Content -Path (Join-Path $DataDir "postgresql.conf") -Encoding ascii -Value @"

# --- COCAS ---
port = $Port
listen_addresses = 'localhost'
"@

    Invoke-Start
    $env:PGPASSWORD = $Role
    & (Join-Path $bin "createdb.exe") -h 127.0.0.1 -p $Port -U $Role $Database
    if ($LASTEXITCODE -ne 0) { throw "createdb thất bại ($LASTEXITCODE)" }
    Write-Host "Đã tạo cụm và database '$Database' ở cổng $Port." -ForegroundColor Green
    Write-Host "Bước tiếp theo: alembic upgrade head (trong backend\migrations)."
}

function Invoke-Start {
    & $pgctl -D $DataDir -l $logFile -w start
    if ($LASTEXITCODE -ne 0) { throw "pg_ctl start thất bại ($LASTEXITCODE) — xem $logFile" }
}

function Invoke-Stop {
    & $pgctl -D $DataDir -m fast -w stop
}

function Invoke-Status {
    & (Join-Path $bin "pg_isready.exe") -h 127.0.0.1 -p $Port
}

switch ($Command) {
    "init" { Invoke-Init }
    "start" { Invoke-Start; Invoke-Status }
    "stop" { Invoke-Stop }
    "status" { Invoke-Status }
    "reset" {
        Write-Host "XOÁ TRẮNG $DataDir" -ForegroundColor Yellow
        & $pgctl -D $DataDir -m immediate -w stop 2>$null
        Remove-Item -Recurse -Force $DataDir -ErrorAction SilentlyContinue
        Invoke-Init
    }
}
