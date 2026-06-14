#!/usr/bin/env python3
"""
test_mes3_pipeline.py - Script de prueba integral para el prototipo del Mes 3.

Ejecuta: ROI -> Segmentacion (SAM o Fallback) -> Extraccion de Linea.
"""

import os
import cv2
import numpy as np
import json
from pathlib import Path
from segmentation_sam import SAMSegmenter
from extract_coastline import extract_coastline_from_mask, draw_coastline

# Configuracion
BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "proces_images" / "data"
OUTPUT_DIR = BASE_DIR / "proces_images" / "output"
CHECKPOINT_SAM = BASE_DIR / "sam_vit_h_4b8939.pth"

def color_fallback_segmentation(image, roi):
    """
    Segmentacion avanzada: Detecta arena y RESTA la espuma blanca.
    """
    x1, y1, x2, y2 = roi["x_min"], roi["y_min"], roi["x_max"], roi["y_max"]
    roi_img = image[y1:y2, x1:x2]
    hsv = cv2.cvtColor(roi_img, cv2.COLOR_BGR2HSV)
    
    # 1. Detectar Arena (Tonos marrones/amarillos con saturación)
    lower_sand = np.array([10, 40, 80])
    upper_sand = np.array([30, 255, 230]) # Bajamos el valor maximo para evitar blancos
    mask_sand = cv2.inRange(hsv, lower_sand, upper_sand)
    
    # 2. Detectar Espuma Blanca (Brillo alto, poca saturación)
    lower_foam = np.array([0, 0, 220])
    upper_foam = np.array([180, 50, 255])
    mask_foam = cv2.inRange(hsv, lower_foam, upper_foam)
    
    # 3. RESTAR: Arena - Espuma
    mask = cv2.subtract(mask_sand, mask_foam)
    
    # 4. Limpieza agresiva
    kernel = np.ones((11, 11), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel) # Borrar puntos sueltos
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel) # Unir la playa
    
    # Recomponer
    full_mask = np.zeros(image.shape[:2], dtype=np.uint8)
    full_mask[y1:y2, x1:x2] = mask
    
    return full_mask

def run_test(cam_id=1, process_all=False):
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    cam_folder = DATA_DIR / f"camera{cam_id}"
    images = sorted(list(cam_folder.glob("*.jpg")))
    if not images: return
    
    first_img = cv2.imread(str(images[0]))
    h, w = first_img.shape[:2]
    roi = {"x_min": int(w*0.05), "y_min": int(h*0.45), "x_max": int(w*0.95), "y_max": int(h*0.95)}
    
    to_process = images if process_all else [images[0]]
    prev_mask = None
    
    print(f"[.] Iniciando Deteccion Dinamica para {len(to_process)} frames...")
    
    for idx, img_path in enumerate(to_process):
        img = cv2.imread(str(img_path))
        current_mask = color_fallback_segmentation(img, roi)
        
        # SUAVIZADO TEMPORAL (Media Movil)
        # Mezclamos la mascara actual con la anterior para un movimiento fluido
        if prev_mask is not None:
            # 70% peso a la actual, 30% a la anterior (evita saltos bruscos)
            smoothed_mask = cv2.addWeighted(current_mask, 0.7, prev_mask, 0.3, 0)
            # Volver a binarizar tras la mezcla
            _, smoothed_mask = cv2.threshold(smoothed_mask, 127, 255, cv2.THRESH_BINARY)
        else:
            smoothed_mask = current_mask
            
        prev_mask = smoothed_mask
        
        # Extraer puntos de la mascara suavizada
        points = extract_coastline_from_mask(smoothed_mask)
        
        # Visualizacion
        viz = img.copy()
        cv2.rectangle(viz, (roi["x_min"], roi["y_min"]), (roi["x_max"], roi["y_max"]), (255, 255, 0), 4)
        
        if points:
            viz = draw_coastline(viz, points, color=(0, 0, 255), thickness=12)
            cv2.putText(viz, "DETECCION DINAMICA - SUAVIZADA", (100, 250), 
                        cv2.FONT_HERSHEY_SIMPLEX, 3.0, (255, 255, 0), 8)
        
        out_name = f"frame_{idx:03d}.jpg" if process_all else f"mes3_test_cam{cam_id}.jpg"
        cv2.imwrite(str(OUTPUT_DIR / out_name), viz)
        cv2.imwrite(str(OUTPUT_DIR / f"mask_frame_{idx:03d}.png"), smoothed_mask)
        print(f"  [OK] Frame {idx+1} procesado.")
    
    print(f"\n[OK] Analisis dinamico finalizado.")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--cam", type=int, default=1)
    parser.add_argument("--all", action="store_true")
    args = parser.parse_args()
    run_test(args.cam, args.all)
