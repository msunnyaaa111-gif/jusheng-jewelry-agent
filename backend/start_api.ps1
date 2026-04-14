$ErrorActionPreference = "Stop"

$python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    Write-Host "Python venv not found: $python" -ForegroundColor Red
    exit 1
}

Set-Location $PSScriptRoot
& $python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
