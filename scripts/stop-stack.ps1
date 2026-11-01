# Stops the app and the project-local PostgreSQL cluster started by start-stack.ps1.

$root = Split-Path -Parent $PSScriptRoot
$pgBin = 'D:\PostgreSQL\18\bin'
$dataDir = Join-Path $root '.pgdata'

Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
    Where-Object { $_.CommandLine -like '*uvicorn backend.app.main*' } |
    ForEach-Object {
        Write-Host "Stopping app process $($_.ProcessId)"
        Stop-Process -Id $_.ProcessId -Force
    }

if (Test-Path (Join-Path $dataDir 'postmaster.pid')) {
    Write-Host 'Stopping PostgreSQL cluster ...'
    & (Join-Path $pgBin 'pg_ctl.exe') -D $dataDir -m fast stop
}
