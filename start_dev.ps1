# CV-LIT — arranque de DESARROLLO
# Workspace completamente VACÍO: sin imágenes, sin varillas, sin calibraciones.
# Los datos reales (proces_images/data, calibration/) no se muestran ni se tocan.
$ErrorActionPreference = "Stop"
$root = $PSScriptRoot

$env:CVLIT_DATA_DIR        = Join-Path $root "workspace\dev\data"
$env:CVLIT_CALIBRATION_DIR = Join-Path $root "workspace\dev\calibration"
$env:APP_MODE              = "real"

New-Item -ItemType Directory -Force $env:CVLIT_DATA_DIR        | Out-Null
New-Item -ItemType Directory -Force $env:CVLIT_CALIBRATION_DIR | Out-Null

Write-Host "== CV-LIT DEV ==" -ForegroundColor Cyan
Write-Host "Workspace vacio: $env:CVLIT_DATA_DIR"

Start-Process -WorkingDirectory (Join-Path $root "backend") `
    -FilePath (Join-Path $root "venv\Scripts\python.exe") `
    -ArgumentList "-m","uvicorn","main:app","--port","8000","--reload"
Start-Process -WorkingDirectory (Join-Path $root "frontend") `
    -FilePath "cmd.exe" -ArgumentList "/k","npm run dev"

Write-Host "Backend:  http://localhost:8000"
Write-Host "Frontend: http://localhost:5173"
