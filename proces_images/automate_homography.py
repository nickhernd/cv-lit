#!/usr/bin/env python3
"""
automate_homography.py — Esquema de automatización para calibración masiva

Este script carga los puntos predeterminados del Excel/CSV para todas las cámaras,
asigna las coordenadas UTM de las boyas correspondientes y genera los
perfiles de calibración (.json y .npy) sin intervención manual.
"""

import os
from calibration_tool import CalibrationTool, DATA_DIR

def main():
    print("=== Pipeline Automatizado de Homografía (Esquema) ===")
    
    # Lista de cámaras a procesar
    cameras = [1, 2, 3, 4, 5, 6]
    
    for cam_idx in cameras:
        print(f"\n[Cámara {cam_idx}]")
        try:
            # 1. Instanciar herramienta
            tool = CalibrationTool(cam_idx)
            
            # 2. Cargar puntos desde el CSV de referencia (el 'Excel')
            # Este método usa el esquema de mapeo interno para 'A' y 'V'
            if tool.load_from_reference_csv():
                # 3. Calcular homografía automáticamente
                if tool.compute_homography():
                    # 4. Guardar resultados
                    tool.save_profile()
                    print(f"  [OK] Calibración completada para Cámara {cam_idx}")
                else:
                    print(f"  [!] Fallo en el cálculo de homografía para Cámara {cam_idx}")
            else:
                print(f"  [!] No se pudieron cargar puntos de referencia para Cámara {cam_idx}")
                
        except Exception as e:
            print(f"  [ERROR] Error procesando Cámara {cam_idx}: {e}")

    print("\nProceso finalizado. Perfiles guardados en la carpeta 'calibration/'.")

if __name__ == "__main__":
    main()
