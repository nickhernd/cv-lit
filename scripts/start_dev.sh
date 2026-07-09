#!/bin/bash

# --- Configuración ---
# Usamos el venv de la raíz
BACKEND_DIR="backend"
VENV_PATH="./venv"

echo "=== Iniciando entorno de desarrollo CV-LIT ==="

# 0. Verificar/Crear entorno virtual
if [ ! -d "$VENV_PATH" ]; then
    echo "[!] Entorno virtual no encontrado. Creándolo..."
    python3 -m venv "$VENV_PATH"
    echo "[OK] Entorno virtual creado."
fi

# Windows (venv/Scripts/python.exe) vs Linux/Mac (venv/bin/python)
if [ -f "$VENV_PATH/Scripts/python.exe" ]; then
    PYTHON_BIN="$VENV_PATH/Scripts/python.exe"
else
    PYTHON_BIN="$VENV_PATH/bin/python"
fi

# En Windows, Node.js suele no estar en el PATH de Git Bash aunque esté instalado
if ! command -v npm >/dev/null 2>&1 && [ -f "/c/Program Files/nodejs/npm.cmd" ]; then
    export PATH="/c/Program Files/nodejs:$PATH"
fi

# Evita UnicodeEncodeError en consola Windows (cp1252 por defecto)
export PYTHONIOENCODING=utf-8

# Actualizar dependencias de backend si es necesario
echo "[.] Verificando dependencias del Backend..."
$PYTHON_BIN -m pip install -r $BACKEND_DIR/requirements.txt --quiet

# 1. Iniciar Backend
echo "[1/2] Iniciando Backend (FastAPI)..."
cd $BACKEND_DIR
# Usamos la ruta absoluta al python del venv para evitar líos
"../$PYTHON_BIN" -m uvicorn main:app --port 8000 --reload &
BACKEND_PID=$!
cd ..

# 2. Iniciar Frontend
echo "[2/2] Iniciando Frontend (Vite)..."
cd frontend
if [ ! -d "node_modules" ]; then
    echo "[!] node_modules no encontrado. Instalando..."
    npm install
fi
npm run dev &
FRONTEND_PID=$!
cd ..

# Manejo de cierre (Ctrl+C)
trap 'echo -e "\n=== Cerrando servidores..."; kill $BACKEND_PID $FRONTEND_PID; exit' SIGINT SIGTERM

echo ""
echo "[OK] Backend corriendo en: http://localhost:8000"
echo "[OK] Frontend corriendo en: http://localhost:5173"
echo "=== Presiona Ctrl+C para detener ==="
echo ""

wait
