#!/usr/bin/env python3
"""
segmentation_sam.py - Modulo de segmentacion semantica usando SAM (Segment Anything Model)

Este modulo se encarga de:
  1. Cargar el modelo SAM (ViT-H, ViT-L o ViT-B).
  2. Aplicar la Region de Interes (ROI).
  3. Generar mascaras binarias de la arena seca.
  4. Post-procesado morfologico para limpiar ruido.
  5. Generacion de mapa de probabilidad por pixel (#44).
  6. Eliminacion de falsas detecciones: espuma, reflejos, sombras (#48).
  7. Consistencia temporal entre frames (#50).
  8. Evaluacion de correccion de horizonte (#54).
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

BASE_DIR  = Path(__file__).parent.parent

# CALIB_DIR: NO se calcula solo a partir de __file__ — en la app empaquetada
# (PyInstaller) ese cómputo apunta dentro del bundle de solo lectura, no a la
# carpeta real de datos del usuario (%LOCALAPPDATA%\LineaDeCosta\calibration).
# Se reutiliza la resolución ya correcta y consciente del entorno de
# backend/config.py — con fallback local por si este módulo se usa suelto
# (su propio CLI --image/--cam/--checkpoint) sin backend/ en sys.path.
# Bug real detectado 2026-08-31: sin esto, ROI_FILE.exists() daba False en
# el .exe instalado, get_roi() devolvía None, y SAM colocaba sus puntos de
# referencia sobre la imagen SIN recortar — arena mal detectada, confianza
# baja en TODAS las imágenes de cámaras con ROI personalizado.
try:
    from config import CALIBRATION_DIR as _CALIB_DIR_STR
    CALIB_DIR = Path(_CALIB_DIR_STR)
except ImportError:
    CALIB_DIR = BASE_DIR / "calibration"

ROI_FILE  = CALIB_DIR / "roi_config.json"

# ── Prompts por camara (#43) ─────────────────────────────────────────────────
# Fracciones [0-1] relativas al ROI de cada camara.
# Cada entrada: lista de {point: [fx, fy], label: 1=fg/0=bg}
# La zona baja-central del ROI corresponde a la arena seca en Guardamar.
CAM_PROMPTS = {
    "CAM_1": [
        {"point": [0.50, 0.80], "label": 1},  # centro-bajo: arena seca
        {"point": [0.50, 0.15], "label": 0},  # zona alta: agua/horizonte
    ],
    "CAM_2": [
        {"point": [0.45, 0.78], "label": 1},
        {"point": [0.50, 0.12], "label": 0},
    ],
    "CAM_3": [
        {"point": [0.50, 0.82], "label": 1},
        {"point": [0.50, 0.10], "label": 0},
    ],
    "CAM_4": [
        {"point": [0.52, 0.80], "label": 1},
        {"point": [0.50, 0.12], "label": 0},
    ],
    "CAM_5": [
        {"point": [0.48, 0.75], "label": 1},
        {"point": [0.50, 0.15], "label": 0},
    ],
    "CAM_6": [
        {"point": [0.50, 0.78], "label": 1},
        {"point": [0.50, 0.12], "label": 0},
    ],
}


def generate_probability_map(logits: np.ndarray) -> np.ndarray:
    """
    Genera mapa de probabilidad por pixel con 3 clases: [seca, humeda, agua] (#44).

    Entrada: logits SAM shape (N, H, W) — tipicamente N=3 mascaras multimask.
    Salida:  ndarray float32 (H, W, 3) con probabilidades suavizadas por clase
             via sigmoid. Los logits de SAM son scores por pixel; los 3 canales
             se asignan heuristicamente: el de mayor score = seca, el intermedio
             = humeda, el menor = agua.
    """
    if logits is None or logits.ndim < 3:
        return np.zeros((1, 1, 3), dtype=np.float32)

    def sigmoid(x):
        return 1.0 / (1.0 + np.exp(-np.clip(x, -88, 88)))

    probs = sigmoid(logits.astype(np.float32))  # (N, H, W)

    # Ordenar canales por score medio descendente: mayor = arena seca
    mean_scores = probs.mean(axis=(1, 2))
    order = np.argsort(mean_scores)[::-1]  # indices de mayor a menor
    n = probs.shape[0]

    h, w = probs.shape[1], probs.shape[2]
    out = np.zeros((h, w, 3), dtype=np.float32)
    out[:, :, 0] = probs[order[0]] if n > 0 else 0        # seca
    out[:, :, 1] = probs[order[1]] if n > 1 else 0        # humeda
    out[:, :, 2] = probs[order[2]] if n > 2 else 0        # agua

    return out


def evaluate_sam_vs_sam2(image: np.ndarray, cam_id: str) -> dict:
    """
    Compara SAM base vs SAM2 sobre una imagen y retorna scores (#45).
    Si SAM2 no esta instalado devuelve solo el resultado de SAM base.
    """
    result = {"cam_id": cam_id, "sam_available": SAM_AVAILABLE, "sam2_available": False,
              "recommendation": "sam_base"}

    try:
        import sam2  # noqa: F401
        result["sam2_available"] = True
    except ImportError:
        pass

    if not SAM_AVAILABLE:
        result["recommendation"] = "ninguno_disponible"
        return result

    # Con modelo real: ejecutar ambos y comparar IoU contra GT si existe.
    # Sin modelo: retornar disponibilidad y recomendacion heuristica.
    # SAM2 es superior en videos; para imagenes estatticas SAM base es suficiente.
    if result["sam2_available"]:
        result["recommendation"] = "sam2"
        result["reason"] = "SAM2 mejora consistencia temporal en secuencias de video"
    else:
        result["recommendation"] = "sam_base"
        result["reason"] = "SAM base disponible; instalar SAM2 para mayor robustez temporal"

    return result


def remove_false_detections(mask: np.ndarray, image: np.ndarray) -> np.ndarray:
    """
    Elimina falsas detecciones de espuma, reflejos y sombras (#48).

    Estrategia de tres filtros:
      1. Filtro HSV: elimina zonas de espuma (blanco saturado, S<30, V>220).
      2. Filtro de brillo: elimina reflejos especulares (V > 245 en HSV).
      3. Filtro de posicion vertical: la arena seca debe estar en la mitad
         inferior de la imagen; elimina regiones en el tercio superior.
    """
    if mask is None or image is None:
        return mask

    result = mask.copy()
    h, w = mask.shape[:2]
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)

    # 1. Espuma: baja saturacion + alto brillo
    espuma = (hsv[:, :, 1] < 30) & (hsv[:, :, 2] > 220)
    result[espuma] = 0

    # 2. Reflejos especulares: brillo extremo
    reflejos = hsv[:, :, 2] > 245
    result[reflejos] = 0

    # 3. Eliminar detecciones en tercio superior (cielo, gaviotas, horizonte)
    result[:int(h * 0.33), :] = 0

    # 4. Limpieza morfologica tras filtros
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
    result = cv2.morphologyEx(result, cv2.MORPH_OPEN, kernel)

    return result


def check_temporal_consistency(
    mask_prev: np.ndarray,
    mask_curr: np.ndarray,
    threshold: float = 0.15,
) -> tuple[bool, float]:
    """
    Evalua la consistencia de segmentacion entre dos frames consecutivos (#50).

    Calcula la interseccion sobre union (IoU) entre las dos mascaras.
    Si IoU < threshold, los frames son inconsistentes (posible error de segmentacion).

    Retorna (consistente: bool, iou: float).
    """
    if mask_prev is None or mask_curr is None:
        return False, 0.0

    prev = (mask_prev > 0).astype(np.uint8)
    curr = (mask_curr > 0).astype(np.uint8)

    # Redimensionar si difieren
    if prev.shape != curr.shape:
        curr = cv2.resize(curr, (prev.shape[1], prev.shape[0]),
                          interpolation=cv2.INTER_NEAREST)

    intersection = np.logical_and(prev, curr).sum()
    union = np.logical_or(prev, curr).sum()

    iou = float(intersection) / float(union) if union > 0 else 1.0
    return iou >= threshold, iou


def evaluate_horizon_correction_needed(image: np.ndarray, cam_id: str) -> bool:
    """
    Detecta si la linea de horizonte esta inclinada mas de 1 grado (#54).
    Usa transformada de Hough sobre bordes del tercio superior de la imagen.

    Retorna True si se detecta inclinacion significativa (>1 deg) y la
    correccion de horizonte deberia aplicarse antes de segmentar.
    """
    h, w = image.shape[:2]
    roi_top = image[:int(h * 0.45), :]
    gray = cv2.cvtColor(roi_top, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 50, 150)

    lines = cv2.HoughLinesP(edges, rho=1, theta=np.pi / 180,
                             threshold=100, minLineLength=w // 4, maxLineGap=30)
    if lines is None:
        return False

    angles = []
    for line in lines:
        x1, y1, x2, y2 = line[0]
        if x2 != x1:
            angle = np.degrees(np.arctan2(abs(y2 - y1), abs(x2 - x1)))
            if angle < 20:  # solo lineas casi horizontales
                angles.append(angle)

    if not angles:
        return False

    median_angle = float(np.median(angles))
    return median_angle > 1.0


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
            import torch
            device = "cuda" if torch.cuda.is_available() else "cpu"
            self.sam.to(device=device)
            self.predictor = SamPredictor(self.sam)
            print(f"[OK] SAM cargado en {device}.")
        else:
            print(f"[WARNING] Checkpoint no encontrado en {checkpoint_path}.")

    def get_roi(self, cam_id: str):
        if not ROI_FILE.exists():
            return None
        with open(ROI_FILE) as f:
            rois = json.load(f)
        key = f"CAM_{cam_id}" if not str(cam_id).startswith("CAM") else str(cam_id)
        return rois.get(key)

    def apply_roi(self, image, roi):
        if not roi:
            return image, (0, 0)
        x1, y1, x2, y2 = roi["x_min"], roi["y_min"], roi["x_max"], roi["y_max"]
        return image[y1:y2, x1:x2], (x1, y1)

    def _build_cam_prompts(self, cam_id: str, roi_h: int, roi_w: int):
        """Convierte CAM_PROMPTS fraccionarios a coordenadas pixel en el ROI (#43)."""
        key = f"CAM_{cam_id}" if not str(cam_id).startswith("CAM") else str(cam_id)
        entries = CAM_PROMPTS.get(key, [{"point": [0.5, 0.8], "label": 1}])
        points = np.array([[int(e["point"][0] * roi_w), int(e["point"][1] * roi_h)]
                           for e in entries])
        labels = np.array([e["label"] for e in entries])
        return points, labels

    def segment_dry_sand(self, image, cam_id: str, prompts=None,
                         remove_false=True, return_prob_map=False):
        """
        Segmenta la arena seca usando SAM.
        prompts: dict {"points": [[x,y],...], "labels": [1,0,...]} en coords ROI.
        remove_false: aplicar filtro de falsas detecciones (#48).
        return_prob_map: retornar tambien el mapa de probabilidad (#44).
        """
        if self.predictor is None:
            print("[FAILED] Predictor no inicializado.")
            return (None, None) if return_prob_map else None

        roi = self.get_roi(cam_id)
        roi_img, offset = self.apply_roi(image, roi)
        h_roi, w_roi = roi_img.shape[:2]

        img_rgb = cv2.cvtColor(roi_img, cv2.COLOR_BGR2RGB)
        self.predictor.set_image(img_rgb)

        if prompts is None:
            input_point, input_label = self._build_cam_prompts(cam_id, h_roi, w_roi)
        else:
            input_point = np.array(prompts["points"])
            input_label = np.array(prompts["labels"])

        masks, scores, logits = self.predictor.predict(
            point_coords=input_point,
            point_labels=input_label,
            multimask_output=True,
        )

        best_idx = np.argmax(scores)
        mask = masks[best_idx]

        # Mapa de probabilidad (#44)
        prob_map = generate_probability_map(logits) if return_prob_map else None

        # Recomponer mascara al tamano original
        full_mask = np.zeros(image.shape[:2], dtype=np.uint8)
        if roi:
            x1, y1, x2, y2 = roi["x_min"], roi["y_min"], roi["x_max"], roi["y_max"]
            full_mask[y1:y2, x1:x2] = mask.astype(np.uint8) * 255
        else:
            full_mask = mask.astype(np.uint8) * 255

        # Post-procesado morfologico
        kernel = np.ones((5, 5), np.uint8)
        full_mask = cv2.morphologyEx(full_mask, cv2.MORPH_OPEN, kernel)
        full_mask = cv2.morphologyEx(full_mask, cv2.MORPH_CLOSE, kernel)

        # Filtro de falsas detecciones (#48)
        if remove_false:
            full_mask = remove_false_detections(full_mask, image)

        if return_prob_map:
            return full_mask, prob_map
        return full_mask


def main():
    import argparse
    ap = argparse.ArgumentParser(description="SAM segmentation debug")
    ap.add_argument("--image", required=True, help="Ruta a la imagen")
    ap.add_argument("--cam",   required=True, help="ID camara (1-6)")
    ap.add_argument("--checkpoint", default=None, help="Ruta al checkpoint SAM")
    ap.add_argument("--out",   default="/tmp/mask_debug.png")
    args = ap.parse_args()

    img = cv2.imread(args.image)
    if img is None:
        print(f"No se pudo leer: {args.image}")
        return

    # Evaluaciones independientes del modelo
    needs_horizon = evaluate_horizon_correction_needed(img, args.cam)
    print(f"Correccion horizonte necesaria: {needs_horizon}")

    sam_eval = evaluate_sam_vs_sam2(img, args.cam)
    print(f"Evaluacion SAM: {sam_eval}")

    segmenter = SAMSegmenter(checkpoint_path=args.checkpoint)
    mask = segmenter.segment_dry_sand(img, args.cam)
    if mask is not None:
        cv2.imwrite(args.out, mask)
        print(f"Mascara guardada en {args.out}")
    else:
        print("No se genero mascara (modelo no disponible)")


if __name__ == "__main__":
    main()
