<#
  Development setup on the Windows laptop (Section 19.2). Run from the repository root in PowerShell:
    powershell -ExecutionPolicy Bypass -File scripts\setup-laptop.ps1 -PostgresPassword <postgres superuser password>
  Prerequisites: Python 3.11+, Node.js 20+, PostgreSQL 16+ with pgvector. Optional: LibreOffice, Tesseract OCR.
#>
param(
  [Parameter(Mandatory = $true)][string]$PostgresPassword,
  [string]$PgBin = "C:\Program Files\PostgreSQL\18\bin",
  [string]$AppDbUser = "presales_app"
)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$backend = Join-Path $root "backend"
$frontend = Join-Path $root "frontend"
$psql = Join-Path $PgBin "psql.exe"

function Step($t) { Write-Host "`n== $t" -ForegroundColor Cyan }

Step "Checking prerequisites"
foreach ($c in "python", "node", "npm") { if (-not (Get-Command $c -ErrorAction SilentlyContinue)) { throw "$c is not installed or not on PATH" } }
if (-not (Test-Path $psql)) { throw "psql not found at $psql. Pass -PgBin." }
$share = Join-Path (Split-Path $PgBin) "share\extension\vector.control"
if (-not (Test-Path $share)) { throw "pgvector is not installed in this PostgreSQL. See docs\SERVER-INSTALL.md (pgvector)." }
if (-not (Get-Command soffice -ErrorAction SilentlyContinue)) { Write-Warning "LibreOffice not found: .doc/.xls import and PDF export will be unavailable until LIBREOFFICE_PATH is set." }
if (-not (Get-Command tesseract -ErrorAction SilentlyContinue)) { Write-Warning "Tesseract not found: scanned PDFs need OCR_ENGINE_PATH." }

Step "Creating databases"
$env:PGPASSWORD = $PostgresPassword
$envFile = Join-Path $backend ".env"
if (Test-Path $envFile) {
  Write-Host ".env exists; keeping its database settings"
} else {
  $appPw = -join ((48..57) + (65..90) + (97..122) | Get-Random -Count 24 | ForEach-Object { [char]$_ })
  $secret = -join ((48..57) + (65..90) + (97..122) | Get-Random -Count 48 | ForEach-Object { [char]$_ })
  & $psql -U postgres -h localhost -w -c "DO `$`$BEGIN IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname='$AppDbUser') THEN CREATE ROLE $AppDbUser LOGIN PASSWORD '$appPw'; END IF; END`$`$;"
  foreach ($db in "presales", "presales_test") {
    $exists = & $psql -U postgres -h localhost -w -tAc "SELECT 1 FROM pg_database WHERE datname='$db'"
    if (-not $exists) { & $psql -U postgres -h localhost -w -c "CREATE DATABASE $db OWNER $AppDbUser;" }
    & $psql -U postgres -h localhost -w -d $db -c "CREATE EXTENSION IF NOT EXISTS vector;"
  }
  (Get-Content (Join-Path $backend ".env.example")) `
    -replace '^APP_SECRET_KEY=.*', "APP_SECRET_KEY=$secret" `
    -replace '^DATABASE_URL=.*', "DATABASE_URL=postgresql+psycopg://${AppDbUser}:$appPw@localhost:5432/presales" `
    -replace '^TEST_DATABASE_URL=.*', "TEST_DATABASE_URL=postgresql+psycopg://${AppDbUser}:$appPw@localhost:5432/presales_test" |
    Set-Content $envFile -Encoding ascii
  Write-Host "Wrote backend\.env. Add ANTHROPIC_API_KEY to it."
}

Step "Python environment"
Push-Location $backend
if (-not (Test-Path ".venv")) { python -m venv .venv }
& .\.venv\Scripts\python.exe -m pip install -q --upgrade pip
& .\.venv\Scripts\pip.exe install -q -r requirements.txt

Step "Encryption key for stored API keys"
$envText = [IO.File]::ReadAllText((Join-Path $backend ".env"))
if ($envText -notmatch "(?m)^SECRETS_ENCRYPTION_KEY=\S+") {
  $fk = & .\.venv\Scripts\python.exe -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
  if ($envText -match "(?m)^SECRETS_ENCRYPTION_KEY=") { $envText = $envText -replace "(?m)^SECRETS_ENCRYPTION_KEY=.*$", "SECRETS_ENCRYPTION_KEY=$fk" }
  else { $envText += "`nSECRETS_ENCRYPTION_KEY=$fk`n" }
  [IO.File]::WriteAllText((Join-Path $backend ".env"), $envText)
  Write-Host "Generated SECRETS_ENCRYPTION_KEY. Keep backend\.env backed up: without this key stored API keys cannot be read."
}

Step "Database migrations and seed"
& .\.venv\Scripts\alembic.exe upgrade head
$testUrl = (Select-String -Path .env -Pattern '^TEST_DATABASE_URL=(.*)$').Matches[0].Groups[1].Value
if ($testUrl) { $env:MIGRATE_DATABASE_URL = $testUrl; & .\.venv\Scripts\alembic.exe upgrade head; Remove-Item Env:MIGRATE_DATABASE_URL }
& .\.venv\Scripts\python.exe -m app.seed
Pop-Location

Step "Frontend"
Push-Location $frontend
npm install --no-audit --no-fund
Pop-Location

Step "Done"
Write-Host "Start everything with: powershell -File scripts\start-dev.ps1"
Write-Host "Then open http://localhost:3000 and sign in as admin with the password printed above."
