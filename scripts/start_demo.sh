#!/bin/bash

# --- Configuración ---
# Usamos el venv de la raíz
BACKEND_DIR="backend"
VENV_PATH="./venv"
PYTHON_BIN="$VENV_PATH/bin/python"

echo "=== Iniciando MODO DEMO CV-LIT (Datos Simulados) ==="

# 1. Iniciar Backend en Modo Demo
echo "[1/2] Iniciando Backend en MODO DEMO..."
cd $BACKEND_DIR
# Pasamos la variable de entorno APP_MODE=demo
APP_MODE=demo ../$PYTHON_BIN -m uvicorn main:app --port 8000 --reload &
BACKEND_PID=$!
cd ..

# 2. Iniciar Frontend
echo "[2/2] Iniciando Frontend (Vite)..."
cd frontend
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
