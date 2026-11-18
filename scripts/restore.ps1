<#
  Restore a backup made by backup.ps1 (Section 19.4). Stop the Presales services first.
    powershell -ExecutionPolicy Bypass -File scripts\restore.ps1 -Source \\nas\backups\presales\20261118-010000 -PostgresPassword <pw>
  The database is dropped and recreated from the dump. Test this at least once before go-live.
#>
param(
  [Parameter(Mandatory = $true)][string]$Source,
  [Parameter(Mandatory = $true)][string]$PostgresPassword,
  [string]$PgBin = "C:\Program Files\PostgreSQL\18\bin",
  [string]$Database = "presales",
  [string]$Owner = "presales_app"
)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$backend = Join-Path $root "backend"
$env:PGPASSWORD = $PostgresPassword
$psql = Join-Path $PgBin "psql.exe"

Write-Host "Recreating database $Database"
& $psql -U postgres -h localhost -w -c "DROP DATABASE IF EXISTS $Database WITH (FORCE);"
& $psql -U postgres -h localhost -w -c "CREATE DATABASE $Database OWNER $Owner;"
& $psql -U postgres -h localhost -w -d $Database -c "CREATE EXTENSION IF NOT EXISTS vector;"
& (Join-Path $PgBin "pg_restore.exe") -U postgres -h localhost -w --no-owner --role=$Owner -d $Database (Join-Path $Source "presales.dump")

$zip = Join-Path $Source "storage.zip"
if (Test-Path $zip) {
  $storage = Join-Path $backend "storage"
  if (Test-Path $storage) { Rename-Item $storage "$storage.before-restore-$(Get-Date -Format yyyyMMddHHmmss)" }
  Expand-Archive $zip -DestinationPath $storage
}
Write-Host "Restored. The backup's configuration is at $(Join-Path $Source 'backend.env') if backend\.env needs replacing."
