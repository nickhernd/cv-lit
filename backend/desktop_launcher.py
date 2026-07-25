"""Lanzador de escritorio: arranca el backend (FastAPI/uvicorn) en un hilo en
segundo plano y abre una ventana nativa (pywebview) apuntando a él — así la
app se usa como un programa normal, sin terminal ni navegador aparte.

Con `frontend/dist/` construido (`npm run build`), `main.py` ya sirve el
frontend en el mismo proceso (ver el mount de StaticFiles al final de
main.py), así que esta ventana apunta directamente a http://127.0.0.1:8000/.
"""
import os
import socket
import sys
import threading
import time

import uvicorn
import webview

import main as backend_main

HOST = "127.0.0.1"
PORT = 8000
WINDOW_TITLE = "Línea de Costa — Guardamar del Segura"


def _port_open(host: str, port: int, timeout: float = 0.5) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _run_server() -> None:
    uvicorn.run(backend_main.app, host=HOST, port=PORT, log_level="warning")


def main() -> None:
    threading.Thread(target=_run_server, daemon=True).start()

    # Esperar a que el backend esté escuchando de verdad antes de abrir la
    # ventana, en vez de una espera fija: arranca antes en máquinas rápidas
    # y no se rompe en máquinas lentas (p.ej. si tarda en cargar SAM).
    for _ in range(300):  # hasta 30s
        if _port_open(HOST, PORT):
            break
        time.sleep(0.1)

    webview.create_window(
        WINDOW_TITLE,
        f"http://{HOST}:{PORT}/",
        width=1440,
        height=860,
        min_size=(1024, 700),
    )
    webview.start()


if __name__ == "__main__":
    main()
