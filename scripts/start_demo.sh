#!/bin/bash

# --- Configuración ---
# Usamos el venv de la raíz
BACKEND_DIR="backend"
VENV_PATH="./venv"
PYTHON_BIN="$VENV_PATH/bin/python"

echo "=== Iniciando MODO DEMO CV-LIT (Datos Simulados) ==="

# 0. Verificar/Crear entorno virtual
if [ ! -d "$VENV_PATH" ]; then
    echo "[!] Entorno virtual no encontrado. Creándolo..."
    python3 -m venv "$VENV_PATH"
    echo "[OK] Entorno virtual creado."
fi

# Actualizar dependencias de backend si es necesario
echo "[.] Verificando dependencias del Backend..."
$PYTHON_BIN -m pip install -r $BACKEND_DIR/requirements.txt --quiet

# 1. Iniciar Backend en Modo Demo
echo "[1/2] Iniciando Backend en MODO DEMO..."
cd $BACKEND_DIR
# Pasamos la variable de entorno APP_MODE=demo
# Usamos la ruta absoluta al python del venv
APP_MODE=demo "../$PYTHON_BIN" -m uvicorn main:app --port 8000 --reload &
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
echo "[OK] Backend DEMO corriendo en: http://localhost:8000"
echo "[OK] Frontend corriendo en: http://localhost:5173"
echo "=== Presiona Ctrl+C para detener ==="
echo ""

wait
