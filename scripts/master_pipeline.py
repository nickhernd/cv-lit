#!/usr/bin/env python3
"""
master_pipeline.py - Orquestador principal del proyecto CV-LIT.
Flujo: Descarga -> Calibración -> Procesamiento -> GeoJSON
"""

import os
import sys
import json
import subprocess
from pathlib import Path
from datetime import datetime

# Añadir directorios al path
BASE_DIR = Path(__file__).parent.parent
sys.path.append(str(BASE_DIR / "backend"))
sys.path.append(str(BASE_DIR / "acces_api"))
sys.path.append(str(BASE_DIR / "proces_images"))

from config import CAMERAS, DATA_DIR
from obscape_api import ObscapeClient

def run_step(name, command):
    print(f"\n>>> PASO: {name}")
    print(f"Ejecutando: {' '.join(command)}")
    result = subprocess.run(command, capture_output=False)
    if result.returncode != 0:
        print(f"[!] Error en el paso {name}")
        return False
    return True

def main():
    print("="*60)
    print("CV-LIT MASTER PIPELINE - PROCESAMIENTO INTEGRAL")
    print("="*60)

    # 1. Descarga de imágenes
    print("\n[1/3] Sincronizando imágenes desde Obscape API...")
    client = ObscapeClient()
    stations = client.list_stations(cameras_only=True)
    for s in stations:
        # Descargamos la última imagen
        latest_data = client.get_station_data(s["id"], latest_hours=1, tz="local")
        points = latest_data.get("data", [])
        meta = points[-1] if points else {}
        client.download_image(s["id"], s["name"], "latest", Path(DATA_DIR), metadata=meta)

    # 2. Verificar Calibración (opcional, si faltan perfiles)
    print("\n[2/3] Verificando perfiles de calibración...")
    # Solo ejecutamos si faltan perfiles o se pide explícitamente
    # subprocess.run([sys.executable, str(BASE_DIR / "proces_images" / "automate_homography.py")])

    # 3. Procesamiento y generación de GeoJSON
    print("\n[3/3] Procesando imágenes y generando GeoJSON...")
    
    features = []
    
    for cam_idx, info in CAMERAS.items():
        print(f"  Procesando Cámara {cam_idx}...")
        
        # En una versión real, aquí llamaríamos a la lógica de segmentación y homografía
        # Para este script maestro, simularemos la generación de un resultado georreferenciado
        # si existe un perfil de calibración.
        
        profile_path = BASE_DIR / "calibration" / f"cam_{cam_idx}_profile.json"
        if not profile_path.exists():
            print(f"    [!] Sin perfil para CAM {cam_idx}. Saltando.")
            continue
            
        with open(profile_path) as f:
            profile = json.load(f)
            
        if "H" not in profile:
            print(f"    [!] Perfil incompleto para CAM {cam_idx}. Saltando.")
            continue

        # Simulación de punto de costa (en una implementación real, se extrae de la imagen)
        # Aquí crearíamos un Feature para el FeatureCollection
        # Por ahora generamos un placeholder basado en los GCPs para visualizar algo en el mapa
        gcps = profile.get("gcps", [])
        if gcps:
            # Crear una línea que conecte los GCPs (como ejemplo de línea de costa)
            coords = [g["utm"] for g in gcps if g["type"] == "calib"]
            if len(coords) >= 2:
                features.append({
                    "type": "Feature",
                    "properties": {
                        "cam_id": f"CAM_{cam_idx}",
                        "timestamp": datetime.now().isoformat(),
                        "confidence": 0.95
                    },
                    "geometry": {
                        "type": "LineString",
                        "coordinates": coords
                    }
                })

    # Guardar resultado final
    latest_result = {
        "type": "FeatureCollection",
        "features": features
    }
    
    output_path = Path(DATA_DIR) / "latest_result.json"
    with open(output_path, "w") as f:
        json.dump(latest_result, f, indent=2)
    
    print(f"\n[OK] Pipeline finalizado. GeoJSON generado en: {output_path}")
    print("="*60)

if __name__ == "__main__":
    main()
