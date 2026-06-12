#!/usr/bin/env python3
"""
verify_setup.py - Script de diagnostico integral del proyecto cv-lit.
Verifica el estado de los Meses 1 y 2.
"""

import os
import json
import sys
from pathlib import Path

# Anadir directorios al path para importar modulos locales
BASE_DIR = Path(__file__).parent
sys.path.append(str(BASE_DIR / "acces_api"))

try:
    from obscape_api import ObscapeClient
    API_AVAILABLE = True
except ImportError:
    API_AVAILABLE = False

def check_mes_1():
    print("\n[MES 1] Verificando Preparacion de Datos e API...")
    if not API_AVAILABLE:
        print("  [FAILED] No se pudo importar ObscapeClient. Revisa acces_api/obscape_api.py")
        return False
    
    client = ObscapeClient()
    print("  [.] Conectando con API Obscape...")
    try:
        stations = client.list_stations(cameras_only=True)
        if stations:
            print(f"  [OK] Conexion API exitosa. {len(stations)} camaras encontradas.")
            for s in stations:
                print(f"      - {s['name']} (ID: {s['id']})")
        else:
            print("  [WARNING] Conexion API OK pero no se encontraron camaras. ¿Credenciales correctas?")
    except Exception as e:
        print(f"  [FAILED] Error de conexion API: {e}")

    # Verificar directorios
    log_file = BASE_DIR / "data" / "logs" / "download_history.csv"
    if log_file.exists():
        print(f"  [OK] Log de descargas encontrado: {log_file}")
    else:
        print("  [ ] No se ha iniciado el log de descargas aun.")

    return True

def check_mes_2():
    print("\n[MES 2] Verificando Calibracion Geometrica...")
    calib_dir = BASE_DIR / "calibration"
    roi_file = calib_dir / "roi_config.json"
    
    # ROI
    if roi_file.exists():
        with open(roi_file) as f:
            rois = json.load(f)
        print(f"  [OK] Configuracion ROI encontrada con {len(rois)} camaras.")
    else:
        print("  [FAILED] No se encuentra calibration/roi_config.json")

    # Perfiles
    profiles = list(calib_dir.glob("cam_*_profile.json"))
    print(f"  [.] Encontrados {len(profiles)} perfiles de calibracion.")
    for p in profiles:
        with open(p) as f:
            data = json.load(f)
            has_H = data.get("H") is not None
            status = "CALIBRADO" if has_H else "PENDIENTE (sin H)"
            print(f"      - {p.name}: {status}")

    # Datos GCP
    gcp_csv = BASE_DIR / "proces_images" / "data" / "GCP.csv"
    if gcp_csv.exists():
        print(f"  [OK] Archivo de referencia GCP encontrado: {gcp_csv}")
        # Verificar si tiene datos UTM
        with open(gcp_csv) as f:
            content = f.read()
            if "CAM" in content and content.count(",") > 5: # check if it has more than headers
                print("      (Contiene coordenadas de pixel, UTMs parecen pendientes)")
    else:
        print("  [WARNING] No se encuentra proces_images/data/GCP.csv")

    return True

def main():
    print("="*50)
    print("DIAGNOSTICO DEL PROYECTO CV-LIT")
    print("="*50)
    
    m1 = check_mes_1()
    m2 = check_mes_2()
    
    print("\n" + "="*50)
    print("RESUMEN DE ESTADO")
    print("  MES 1 (API/Datos)    :", "COMPLETADO" if m1 else "PENDIENTE")
    print("  MES 2 (Calibracion)  :", "HERRAMIENTAS LISTAS / ESPERANDO DATOS")
    print("="*50)

if __name__ == "__main__":
    main()
