import requests
import json

BASE_URL = "http://localhost:8000/api"

def test_dashboard():
    print("[.] Probando endpoint Dashboard...")
    res = requests.get(f"{BASE_URL}/dashboard")
    assert res.status_code == 200
    data = res.json()
    assert "cameras" in data
    print(f"    [OK] Encontradas {len(data['cameras'])} camaras.")

def test_cameras_list():
    print("[.] Probando listado de imagenes...")
    res = requests.get(f"{BASE_URL}/cameras/1/images")
    assert res.status_code == 200
    data = res.json()
    print(f"    [OK] Encontradas {len(data)} imagenes para CAM 1.")

def test_analyze_roi():
    print("[.] Probando analisis ROI (esto puede tardar unos segundos)...")
    res = requests.post(f"{BASE_URL}/cameras/1/analyze-roi")
    assert res.status_code == 200
    data = res.json()
    assert "dry_area_m2" in data
    print(f"    [OK] Area detectada: {data['dry_area_m2']} m2 (Confianza: {data['confidence']})")

if __name__ == "__main__":
    print("=== INICIANDO TESTS DE INTEGRACION API ===")
    try:
        test_dashboard()
        test_cameras_list()
        test_analyze_roi()
        print("\n=== TODOS LOS TESTS PASARON CORRECTAMENTE ===")
    except Exception as e:
        print(f"\n[FAILED] Error en los tests: {e}")
