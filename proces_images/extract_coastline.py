#!/usr/bin/env python3
"""
extract_coastline.py — Módulo para extraer la línea de costa desde una máscara binaria.

Flujo:
  1. Recibir máscara binaria (255=arena, 0=resto).
  2. Detectar contornos (cv2.findContours).
  3. Filtrar y seleccionar el contorno de la interfaz arena-mar.
  4. Suavizar y simplificar la polilínea.
"""

import cv2
import numpy as np

def extract_coastline_from_mask(mask, min_length=100, epsilon_factor=0.001):
    """
    Extrae la polilínea de la línea de costa.
    mask: máscara binaria (0-255).
    min_length: longitud mínima del contorno para ser considerado.
    epsilon_factor: factor de simplificación Douglas-Peucker.
    """
    # 1. Encontrar contornos
    # RETR_EXTERNAL para obtener solo los bordes exteriores
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    if not contours:
        return None

    # 2. Filtrar por longitud y seleccionar el principal
    # En una playa, la línea de costa suele ser el contorno más largo que cruza la ROI
    valid_contours = [c for c in contours if cv2.arcLength(c, False) > min_length]
    
    if not valid_contours:
        return None
    
    # Seleccionamos el más largo como candidato a línea de costa
    main_contour = max(valid_contours, key=lambda c: cv2.arcLength(c, False))
    
    # 3. Simplificación de la polilínea (Douglas-Peucker)
    epsilon = epsilon_factor * cv2.arcLength(main_contour, False)
    approx = cv2.approxPolyDP(main_contour, epsilon, False)
    
    # 4. Convertir a lista de puntos (u, v)
    points = approx.reshape(-1, 2).tolist()
    
    return points

def draw_coastline(image, points, color=(0, 255, 0), thickness=2):
    """Dibuja la línea de costa sobre una imagen."""
    if not points:
        return image
    
    pts = np.array(points, dtype=np.int32).reshape((-1, 1, 2))
    cv2.polylines(image, [pts], False, color, thickness, cv2.LINE_AA)
    return image

if __name__ == "__main__":
    # Test rápido con máscara ficticia
    dummy_mask = np.zeros((500, 500), dtype=np.uint8)
    cv2.rectangle(dummy_mask, (100, 100), (400, 400), 255, -1)
    pts = extract_coastline_from_mask(dummy_mask)
    print(f"Puntos extraídos: {len(pts) if pts else 0}")
