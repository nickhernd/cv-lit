#!/bin/bash

# --- Configuración ---
# Usamos el venv de la raíz
BACKEND_DIR="backend"
VENV_PATH="./venv"
PYTHON_BIN="$VENV_PATH/bin/python"

echo "=== Iniciando entorno de desarrollo CV-LIT ==="

# 1. Iniciar Backend
echo "[1/2] Iniciando Backend (FastAPI)..."
# Ejecutamos desde la carpeta backend para que las rutas relativas funcionen bien
cd $BACKEND_DIR
../$PYTHON_BIN -m uvicorn main:app --port 8000 --reload &
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
echo "✔ Backend corriendo en: http://localhost:8000"
echo "✔ Frontend corriendo en: http://localhost:5173"
echo "=== Presiona Ctrl+C para detener ==="
echo ""

wait
