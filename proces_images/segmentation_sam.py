#!/usr/bin/env python3
"""
segmentation_sam.py - Modulo de segmentacion semantica usando SAM (Segment Anything Model)

Este modulo se encarga de:
  1. Cargar el modelo SAM (ViT-H, ViT-L o ViT-B).
  2. Aplicar la Region de Interes (ROI).
  3. Generar mascaras binarias de la arena seca.
  4. Post-procesado morfologico para limpiar ruido.
"""

import os
import cv2
import numpy as np
import json
from pathlib import Path

try:
    from segment_anything import sam_model_registry, SamPredictor
    SAM_AVAILABLE = True
except ImportError:
    SAM_AVAILABLE = False

BASE_DIR = Path(__file__).parent.parent
CALIB_DIR = BASE_DIR / "calibration"
ROI_FILE = CALIB_DIR / "roi_config.json"

class SAMSegmenter:
    def __init__(self, model_type="vit_h", checkpoint_path=None):
        self.model_type = model_type
        self.checkpoint_path = checkpoint_path
        self.predictor = None
        self.sam = None
        
        if not SAM_AVAILABLE:
            print("[FAILED] Error: 'segment-anything' no esta instalado.")
            return

        if checkpoint_path and os.path.exists(checkpoint_path):
            print(f"[.] Cargando SAM ({model_type}) desde {checkpoint_path}...")
            self.sam = sam_model_registry[model_type](checkpoint=checkpoint_path)
            # Mover a GPU si esta disponible
            import torch
            device = "cuda" if torch.cuda.is_available() else "cpu"
            self.sam.to(device=device)
            self.predictor = SamPredictor(self.sam)
            print(f"[OK] SAM cargado en {device}.")
        else:
            print(f"[WARNING] Checkpoint no encontrado en {checkpoint_path}. El predictor no estara disponible.")

    def get_roi(self, cam_id: str):
        """Obtiene las coordenadas ROI para una camara."""
        if not ROI_FILE.exists():
            return None
        with open(ROI_FILE) as f:
            rois = json.load(f)
        
        # El ID puede venir como "CAM_1" o 1
        key = f"CAM_{cam_id}" if not str(cam_id).startswith("CAM") else str(cam_id)
        return rois.get(key)

    def apply_roi(self, image, roi):
        """Recorta la imagen segun la ROI."""
        if not roi:
            return image, (0, 0)
        
        x1, y1, x2, y2 = roi["x_min"], roi["y_min"], roi["x_max"], roi["y_max"]
        return image[y1:y2, x1:x2], (x1, y1)

    def segment_dry_sand(self, image, cam_id: str, prompts=None):
        """
        Segmenta la arena seca usando SAM.
        prompts: lista de puntos [(x, y), ...] o boxes [x1, y1, x2, y2], ...]
        """
        if self.predictor is None:
            print("[FAILED] Predictor no inicializado. Carga los pesos del modelo primero.")
            return None

        # 1. Preparar ROI
        roi = self.get_roi(cam_id)
        roi_img, offset = self.apply_roi(image, roi)
        
        # 2. Configurar imagen en SAM
        # SAM espera RGB
        img_rgb = cv2.cvtColor(roi_img, cv2.COLOR_BGR2RGB)
        self.predictor.set_image(img_rgb)

        # 3. Generar prompts automaticos si no se proporcionan
        # En Guardamar, la arena seca suele estar en la parte inferior/central de la ROI
        if prompts is None:
            # Punto semilla heuristico: centro inferior de la ROI
            h, w = roi_img.shape[:2]
            input_point = np.array([w // 2, h - h // 4])
            input_label = np.array([1]) # 1 = foreground
        else:
            input_point = np.array(prompts["points"])
            input_label = np.array(prompts["labels"])

        # 4. Predecir
        masks, scores, logits = self.predictor.predict(
            point_coords=input_point,
            point_labels=input_label,
            multimask_output=True,
        )

        # Seleccionar la mascara con mejor score
        best_idx = np.argmax(scores)
        mask = masks[best_idx]
        
        # 5. Recomponer mascara al tamano original
        full_mask = np.zeros(image.shape[:2], dtype=np.uint8)
        if roi:
            x1, y1, x2, y2 = roi["x_min"], roi["y_min"], roi["x_max"], roi["y_max"]
            full_mask[y1:y2, x1:x2] = mask.astype(np.uint8) * 255
        else:
            full_mask = mask.astype(np.uint8) * 255

        # 6. Post-procesado morfologico
        kernel = np.ones((5, 5), np.uint8)
        full_mask = cv2.morphologyEx(full_mask, cv2.MORPH_OPEN, kernel) # Eliminar ruido
        full_mask = cv2.morphologyEx(full_mask, cv2.MORPH_CLOSE, kernel) # Rellenar huecos

        return full_mask

def main():
    # Ejemplo de uso (mockup si no hay pesos)
    segmenter = SAMSegmenter(checkpoint_path="sam_vit_h_4b8939.pth")
    print("Modulo SAM listo.")

if __name__ == "__main__":
    main()
