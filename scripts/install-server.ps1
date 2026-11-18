<#
  Production install on the on-premises Windows server (Section 19.3). Run as Administrator from the repository root,
  after running setup-laptop.ps1 steps (or equivalent) with APP_ENV=production in backend\.env.

    powershell -ExecutionPolicy Bypass -File scripts\install-server.ps1 -Nssm C:\Tools\nssm\nssm.exe

  Creates Windows services that start automatically and restart on failure:
    PresalesApi      FastAPI on 127.0.0.1:8010
    PresalesWorker1..N job workers
    PresalesWeb      Next.js on 0.0.0.0:3000 (the only port opened in the firewall)
#>
param(
  [Parameter(Mandatory = $true)][string]$Nssm,
  [int]$Workers = 2,
  [int]$BackendPort = 8010,
  [int]$WebPort = 3000,
  [string]$LogDir = ""
)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$backend = Join-Path $root "backend"
$frontend = Join-Path $root "frontend"
if (-not $LogDir) { $LogDir = Join-Path $backend "logs" }
New-Item -ItemType Directory -Force $LogDir | Out-Null
$py = Join-Path $backend ".venv\Scripts\python.exe"
$node = (Get-Command node).Source

if ((Select-String -Path (Join-Path $backend ".env") -Pattern '^APP_ENV=production').Count -eq 0) {
  Write-Warning "backend\.env does not set APP_ENV=production"
}

Write-Host "Building frontend"
Push-Location $frontend
$env:BACKEND_URL = "http://127.0.0.1:$BackendPort"
npm ci --no-audit --no-fund
npm run build
Pop-Location

Write-Host "Applying migrations"
Push-Location $backend
& $py -m alembic upgrade head
& $py -m app.seed
Pop-Location

function Install-Svc($name, $exe, $arguments, $dir, $display) {
  if (Get-Service $name -ErrorAction SilentlyContinue) { & $Nssm stop $name | Out-Null; & $Nssm remove $name confirm | Out-Null }
  & $Nssm install $name $exe $arguments
  & $Nssm set $name AppDirectory $dir
  & $Nssm set $name DisplayName $display
  & $Nssm set $name Start SERVICE_AUTO_START
  & $Nssm set $name AppStdout (Join-Path $LogDir "$name.log")
  & $Nssm set $name AppStderr (Join-Path $LogDir "$name.log")
  & $Nssm set $name AppRotateFiles 1
  & $Nssm set $name AppRotateBytes 10485760
  & $Nssm set $name AppExit Default Restart
  & $Nssm start $name
}

Install-Svc "PresalesApi" $py "-m uvicorn app.main:app --host 127.0.0.1 --port $BackendPort --workers 2" $backend "Presales Intelligence API"
for ($i = 1; $i -le $Workers; $i++) { Install-Svc "PresalesWorker$i" $py "worker.py" $backend "Presales Intelligence Worker $i" }
Install-Svc "PresalesWeb" $node "node_modules\next\dist\bin\next start -p $WebPort" $frontend "Presales Intelligence Web"

Write-Host "Opening firewall for the web port on the local network"
if (-not (Get-NetFirewallRule -DisplayName "Presales Intelligence Web" -ErrorAction SilentlyContinue)) {
  New-NetFirewallRule -DisplayName "Presales Intelligence Web" -Direction Inbound -Protocol TCP -LocalPort $WebPort -Profile Domain,Private -Action Allow | Out-Null
}

Start-Sleep -Seconds 5
try { Invoke-RestMethod "http://127.0.0.1:$BackendPort/api/health" | Out-String | Write-Host } catch { Write-Warning "Health check failed: $_" }
Write-Host "Done. Team machines open http://<server-name>:$WebPort . Logs: $LogDir"
