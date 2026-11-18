<#
  Start backend (port 8010), workers and the Next.js dev server (port 3000) in separate windows.
#>
param([int]$Workers = 2, [int]$BackendPort = 8010)
$root = Split-Path -Parent $PSScriptRoot
$backend = Join-Path $root "backend"
$frontend = Join-Path $root "frontend"

Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$backend'; .\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port $BackendPort --reload"
for ($i = 1; $i -le $Workers; $i++) {
  Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$backend'; .\.venv\Scripts\python.exe worker.py"
}
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$frontend'; `$env:BACKEND_URL='http://127.0.0.1:$BackendPort'; npm run dev"
Write-Host "Backend http://127.0.0.1:$BackendPort/api/docs  -  App http://localhost:3000"
