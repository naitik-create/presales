<#
  Backup (Section 19.4): PostgreSQL dump, uploaded and generated files, and configuration.
  Store the target on a different disk or machine. Schedule daily with Task Scheduler:
    schtasks /Create /SC DAILY /ST 01:00 /TN PresalesBackup /TR "powershell -ExecutionPolicy Bypass -File D:\Presales\scripts\backup.ps1 -Target \\nas\backups\presales"
#>
param(
  [Parameter(Mandatory = $true)][string]$Target,
  [string]$PgBin = "C:\Program Files\PostgreSQL\18\bin",
  [int]$KeepDays = 30
)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$backend = Join-Path $root "backend"
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$dest = Join-Path $Target $stamp
New-Item -ItemType Directory -Force $dest | Out-Null

$url = (Select-String -Path (Join-Path $backend ".env") -Pattern '^DATABASE_URL=(.*)$').Matches[0].Groups[1].Value
$pgUrl = $url -replace '^postgresql\+psycopg://', 'postgresql://'
& (Join-Path $PgBin "pg_dump.exe") --format=custom --file (Join-Path $dest "presales.dump") $pgUrl
if ($LASTEXITCODE -ne 0) { throw "pg_dump failed" }

$storage = Join-Path $backend "storage"
if (Test-Path $storage) { Compress-Archive -Path "$storage\*" -DestinationPath (Join-Path $dest "storage.zip") -CompressionLevel Optimal }
Copy-Item (Join-Path $backend ".env") (Join-Path $dest "backend.env")

Get-ChildItem $Target -Directory | Where-Object { $_.CreationTime -lt (Get-Date).AddDays(-$KeepDays) } | Remove-Item -Recurse -Force
Write-Host "Backup written to $dest"
