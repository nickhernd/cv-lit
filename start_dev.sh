#!/bin/bash

# --- Configuración ---
BACKEND_CMD="backend/venv/bin/uvicorn backend.main:app --port 8000 --reload"
FRONTEND_CMD="npm run dev"

echo "=== Iniciando entorno de desarrollo ==="

# Iniciar Backend
echo "[1/2] Iniciando Backend (FastAPI)..."
$BACKEND_CMD &
BACKEND_PID=$!

# Iniciar Frontend
echo "[2/2] Iniciando Frontend (Vite)..."
cd frontend
$FRONTEND_CMD &
FRONTEND_PID=$!
cd ..

# Manejo de cierre (Ctrl+C)
trap 'echo -e "\n=== Cerrando servidores..."; kill $BACKEND_PID $FRONTEND_PID; exit' SIGINT SIGTERM

echo "=== Servidores corriendo (Ctrl+C para detener) ==="
wait
