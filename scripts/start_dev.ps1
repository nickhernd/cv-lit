# start_dev.ps1 - Levanta backend (FastAPI) y frontend (Vite) en Windows/PowerShell
# Uso: .\scripts\start_dev.ps1

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

Write-Host "=== Iniciando entorno de desarrollo CV-LIT ==="

# 0. Verificar/Crear entorno virtual
$venvPath   = Join-Path $root "venv"
$venvPython = Join-Path $venvPath "Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    Write-Host "[!] Entorno virtual no encontrado. Creandolo..."
    python -m venv $venvPath
    Write-Host "[OK] Entorno virtual creado."
}

# Node.js puede no estar aun en el PATH de esta sesion si se instalo hace poco
if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
    $nodeDir = "C:\Program Files\nodejs"
    if (Test-Path (Join-Path $nodeDir "npm.cmd")) {
        $env:PATH = "$nodeDir;$env:PATH"
    }
}

# Evita UnicodeEncodeError en consola Windows (cp1252 por defecto)
$env:PYTHONIOENCODING = "utf-8"

# Actualizar dependencias de backend si es necesario
Write-Host "[.] Verificando dependencias del Backend..."
& $venvPython -m pip install -r (Join-Path $root "backend\requirements.txt") --quiet

# 1. Iniciar Backend
Write-Host "[1/2] Iniciando Backend (FastAPI)..."
$backend = Start-Process -FilePath $venvPython `
    -ArgumentList "-m", "uvicorn", "main:app", "--port", "8000", "--reload" `
    -WorkingDirectory (Join-Path $root "backend") `
    -NoNewWindow -PassThru

# 2. Iniciar Frontend
$frontendDir = Join-Path $root "frontend"
if (-not (Test-Path (Join-Path $frontendDir "node_modules"))) {
    Write-Host "[!] node_modules no encontrado. Instalando..."
    Start-Process -FilePath "npm.cmd" -ArgumentList "install" -WorkingDirectory $frontendDir -NoNewWindow -Wait
}
Write-Host "[2/2] Iniciando Frontend (Vite)..."
$frontend = Start-Process -FilePath "npm.cmd" -ArgumentList "run", "dev" `
    -WorkingDirectory $frontendDir -NoNewWindow -PassThru

Write-Host ""
Write-Host "[OK] Backend corriendo en:  http://localhost:8000"
Write-Host "[OK] Frontend corriendo en: http://localhost:5173"
Write-Host "=== Presiona Ctrl+C para detener ==="
Write-Host ""

try {
    Wait-Process -Id $backend.Id, $frontend.Id
}
finally {
    Write-Host "`n=== Cerrando servidores... ==="
    # uvicorn --reload y "npm run dev" lanzan procesos hijos (reloader/vite) que
    # sobreviven al padre si solo se mata este; se buscan y cierran explicitamente.
    $childIds = Get-CimInstance Win32_Process `
        -Filter "ParentProcessId=$($backend.Id) OR ParentProcessId=$($frontend.Id)" `
        -ErrorAction SilentlyContinue |
        Select-Object -ExpandProperty ProcessId
    foreach ($procId in $childIds) {
        Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
    }
    Stop-Process -Id $backend.Id -Force -ErrorAction SilentlyContinue
    Stop-Process -Id $frontend.Id -Force -ErrorAction SilentlyContinue
}
