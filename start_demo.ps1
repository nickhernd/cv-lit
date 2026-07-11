# CV-LIT — arranque de DEMO
# Siembra un workspace aislado con las imágenes de muestra y las varillas del
# GCP.csv ya importadas y calibradas por imagen, y arranca backend + frontend.
# Cada arranque regenera la demo desde cero. Los datos reales no se tocan.
$ErrorActionPreference = "Stop"
$root = $PSScriptRoot

$env:CVLIT_DATA_DIR        = Join-Path $root "workspace\demo\data"
$env:CVLIT_CALIBRATION_DIR = Join-Path $root "workspace\demo\calibration"
$env:APP_MODE              = "real"

Write-Host "== CV-LIT DEMO ==" -ForegroundColor Cyan
Write-Host "Sembrando workspace de demo..."
& (Join-Path $root "venv\Scripts\python.exe") (Join-Path $root "backend\seed_demo.py")
if ($LASTEXITCODE -ne 0) {
    Write-Error "La siembra de la demo fallo (revisa la salida anterior)."
    exit 1
}

Start-Process -WorkingDirectory (Join-Path $root "backend") `
    -FilePath (Join-Path $root "venv\Scripts\python.exe") `
    -ArgumentList "-m","uvicorn","main:app","--port","8000"
Start-Process -WorkingDirectory (Join-Path $root "frontend") `
    -FilePath "cmd.exe" -ArgumentList "/k","npm run dev"

Write-Host "Backend:  http://localhost:8000"
Write-Host "Frontend: http://localhost:5173"
