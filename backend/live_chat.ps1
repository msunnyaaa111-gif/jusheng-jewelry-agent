$ErrorActionPreference = "Stop"

chcp 65001 | Out-Null
[Console]::InputEncoding = [System.Text.UTF8Encoding]::new()
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
$OutputEncoding = [Console]::OutputEncoding

$python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
$script = Join-Path $PSScriptRoot "live_chat.py"

if (-not (Test-Path $python)) {
    Write-Host "Python venv not found: $python" -ForegroundColor Red
    exit 1
}

& $python $script
