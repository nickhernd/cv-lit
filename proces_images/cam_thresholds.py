"""
cam_thresholds.py — Umbrales de segmentación ajustados por cámara (#80).

Tras validación visual de las 6 cámaras de Guardamar:
- confidence_min: umbral mínimo SAM para aceptar la máscara (0–1)
- mask_area_min_ratio: fracción mínima de la imagen que debe ser arena seca
  (evita máscaras vacías por fallo de segmentación)
- mask_area_max_ratio: fracción máxima de la imagen que puede ser arena seca
  (evita que se segmente todo el frame por error)

CAM_6 tiene umbrales más estrictos porque su ángulo da más cielo visible.
CAM_3 y CAM_4 tienen ratios de área más permisivos (playa más ancha visible).
"""

CAM_THRESHOLDS: dict[int, dict] = {
    1: {"confidence_min": 0.45, "mask_area_min_ratio": 0.05, "mask_area_max_ratio": 0.70},
    2: {"confidence_min": 0.45, "mask_area_min_ratio": 0.05, "mask_area_max_ratio": 0.70},
    3: {"confidence_min": 0.40, "mask_area_min_ratio": 0.05, "mask_area_max_ratio": 0.75},
    4: {"confidence_min": 0.40, "mask_area_min_ratio": 0.05, "mask_area_max_ratio": 0.75},
    5: {"confidence_min": 0.45, "mask_area_min_ratio": 0.05, "mask_area_max_ratio": 0.70},
    6: {"confidence_min": 0.50, "mask_area_min_ratio": 0.08, "mask_area_max_ratio": 0.65},
}

_DEFAULT = {"confidence_min": 0.45, "mask_area_min_ratio": 0.05, "mask_area_max_ratio": 0.70}


def get_threshold(cam_id: int) -> dict:
    """Retorna los umbrales de segmentación para la cámara dada."""
    return CAM_THRESHOLDS.get(int(cam_id), _DEFAULT)


def validate_mask(mask, cam_id: int, image_shape: tuple) -> tuple[bool, str]:
    """
    Valida que la máscara cumple los criterios de área para la cámara dada.
    Retorna (válida: bool, motivo: str).
    """
    import numpy as np
    t = get_threshold(cam_id)
    total_px = image_shape[0] * image_shape[1]
    mask_px  = int(np.sum(mask > 0))
    ratio    = mask_px / total_px if total_px > 0 else 0.0

    if ratio < t["mask_area_min_ratio"]:
        return False, f"mascara_vacia:ratio={ratio:.3f}<{t['mask_area_min_ratio']}"
    if ratio > t["mask_area_max_ratio"]:
        return False, f"mascara_saturada:ratio={ratio:.3f}>{t['mask_area_max_ratio']}"
    return True, ""
