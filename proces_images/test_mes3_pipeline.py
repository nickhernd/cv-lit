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
    Segmentacion adaptativa (Otsu) como fallback.
    Asume que la arena es la zona mas clara de la ROI.
    """
    x1, y1, x2, y2 = roi["x_min"], roi["y_min"], roi["x_max"], roi["y_max"]
    roi_img = image[y1:y2, x1:x2]
    
    # Convertir a escala de grises
    gray = cv2.cvtColor(roi_img, cv2.COLOR_BGR2GRAY)
    
    # Aplicar desenfoque gaussiano para reducir ruido
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    
    # Umbral de Otsu
    _, mask = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    
    # Limpieza morfologica
    kernel = np.ones((5, 5), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
    
    # Recomponer
    full_mask = np.zeros(image.shape[:2], dtype=np.uint8)
    full_mask[y1:y2, x1:x2] = mask
    
    return full_mask

def run_test(cam_id=1):
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    # 1. Cargar imagen de referencia
    # Usamos la config del segmenter para buscar la imagen por defecto
    segmenter = SAMSegmenter(checkpoint_path=str(CHECKPOINT_SAM))
    roi = segmenter.get_roi(cam_id)
    
    if not roi:
        print(f"[FAILED] No se encontro ROI para camara {cam_id}")
        return

    # Buscar una imagen real en las carpetas
    cam_folder = DATA_DIR / f"camera{cam_id}"
    images = list(cam_folder.glob("*.jpg"))
    if not images:
        print(f"[FAILED] No hay imagenes en {cam_folder}")
        return
    
    img_path = images[0]
    print(f"[.] Procesando: {img_path.name}")
    img = cv2.imread(str(img_path))
    
    # 2. Segmentacion
    if segmenter.predictor:
        print("[.] Ejecutando segmentacion SAM...")
        mask = segmenter.segment_dry_sand(img, cam_id)
        method = "SAM"
    else:
        print("[WARNING] SAM no disponible (sin pesos). Usando fallback por color...")
        mask = color_fallback_segmentation(img, roi)
        method = "Color-Fallback"

    # 3. Extraccion de linea de costa
    print("[.] Extrayendo linea de costa...")
    points = extract_coastline_from_mask(mask)
    
    # 4. Visualizacion
    viz = img.copy()
    # Dibujar ROI
    cv2.rectangle(viz, (roi["x_min"], roi["y_min"]), (roi["x_max"], roi["y_max"]), (255, 255, 0), 2)
    # Dibujar Linea
    if points:
        viz = draw_coastline(viz, points, color=(0, 255, 0), thickness=3)
        print(f"[OK] Linea de costa extraida: {len(points)} puntos.")
    else:
        print("[FAILED] No se pudo extraer la linea de costa de la mascara.")

    # Guardar resultados
    out_img_path = OUTPUT_DIR / f"mes3_test_cam{cam_id}.jpg"
    out_mask_path = OUTPUT_DIR / f"mes3_mask_cam{cam_id}.png"
    
    cv2.imwrite(str(out_img_path), viz)
    cv2.imwrite(str(out_mask_path), mask)
    
    print(f"\n[OK] Resultados guardados en:")
    print(f"  - Imagen: {out_img_path}")
    print(f"  - Mascara: {out_mask_path}")
    print(f"Metodo utilizado: {method}")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--cam", type=int, default=1)
    args = parser.parse_args()
    run_test(args.cam)
