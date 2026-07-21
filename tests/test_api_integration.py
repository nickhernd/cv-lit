"""Tests de integración contra un backend REAL en ejecución (no mockean nada).
Requieren `uvicorn main:app` levantado en localhost:8000 con datos de cámara
disponibles (p.ej. start_dev.ps1 con un workspace ya sembrado). Si el servidor
no responde, se saltan en vez de fallar — así no rompen un `pytest` que no
tiene forma de levantar el backend (CI sin workspace real, por ejemplo).
"""

import requests
import pytest

BASE_URL = "http://localhost:8000/api"


def _server_up() -> bool:
    try:
        requests.get(f"{BASE_URL}/dashboard", timeout=2)
        return True
    except requests.exceptions.ConnectionError:
        return False


pytestmark = pytest.mark.skipif(
    not _server_up(),
    reason="Backend no disponible en localhost:8000 — arranca start_dev.ps1 primero",
)


def test_dashboard():
    res = requests.get(f"{BASE_URL}/dashboard")
    assert res.status_code == 200
    data = res.json()
    assert "cameras" in data


def test_cameras_list():
    res = requests.get(f"{BASE_URL}/cameras/1/images")
    assert res.status_code == 200
    assert isinstance(res.json(), list)


def test_analyze_roi():
    res = requests.post(f"{BASE_URL}/cameras/1/analyze-roi")
    assert res.status_code == 200
    data = res.json()
    assert "dry_area_m2" in data


if __name__ == "__main__":
    print("=== INICIANDO TESTS DE INTEGRACION API ===")
    if not _server_up():
        print("[SKIP] Backend no disponible en localhost:8000")
    else:
        test_dashboard()
        print("    [OK] Dashboard")
        test_cameras_list()
        print("    [OK] Listado de imagenes")
        test_analyze_roi()
        print("    [OK] Analisis ROI")
        print("\n=== TODOS LOS TESTS PASARON CORRECTAMENTE ===")
