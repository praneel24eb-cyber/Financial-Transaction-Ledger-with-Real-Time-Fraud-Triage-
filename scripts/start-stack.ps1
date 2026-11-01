# Starts the local stack used on this machine:
#   1. Project-local PostgreSQL 18 cluster (trust auth, port 5433, data dir .pgdata)
#   2. FastAPI app (uvicorn) on http://127.0.0.1:8000
#
# Redis and MongoDB are not installed here; the app automatically falls back to its
# in-memory counters / evidence store (see backend/app/repositories/*_repo.py).

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$pgBin = 'D:\PostgreSQL\18\bin'
$dataDir = Join-Path $root '.pgdata'
$port = 5433

function Test-Port([int]$p) {
    (Test-NetConnection -ComputerName 127.0.0.1 -Port $p -InformationLevel Quiet -WarningAction SilentlyContinue)
}

if (-not (Test-Port $port)) {
    Write-Host "Starting PostgreSQL cluster on port $port ..."
    Start-Process -FilePath (Join-Path $pgBin 'pg_ctl.exe') `
        -ArgumentList @('-D', $dataDir, '-l', (Join-Path $dataDir 'server.log'), '-o', '"-p 5433"', 'start') `
        -WindowStyle Hidden | Out-Null
    for ($i = 0; $i -lt 30 -and -not (Test-Port $port); $i++) { Start-Sleep -Milliseconds 500 }
    if (-not (Test-Port $port)) { throw "PostgreSQL did not start. See $dataDir\server.log" }
}

Write-Host "Starting FastAPI on http://127.0.0.1:8000 ..."
Set-Location $root
& (Join-Path $root '.venv\Scripts\python.exe') -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
