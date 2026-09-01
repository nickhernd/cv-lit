#!/usr/bin/env python3
"""
extract_coastline.py - Extraccion y suavizado de la linea de costa desde mascara binaria.

Issues implementadas:
  #56 — Seleccionar borde principal: contorno con mayor span horizontal.
  #57 — Descartar bordes secundarios por longitud, continuidad y posicion.
  #58 — Suavizar polilinia con Savitzky-Golay antes de proyectar.
  #61 — Manejar zonas de baja confianza en bordes del area visible.
"""

import cv2
import numpy as np
from typing import Optional

try:
    from scipy.signal import savgol_filter
    SCIPY_AVAILABLE = True
except ImportError:
    SCIPY_AVAILABLE = False


def filter_secondary_contours(
    contours,
    min_length: float = 500,
    min_horizontal_span_ratio: float = 0.3,
    image_width: int = 4608,
    roi_lower_half_only: bool = True,
    image_height: int = 2682,
) -> list:
    """
    Filtra contornos secundarios, conservando solo los candidatos validos (#57).

    Criterios de descarte:
      - Longitud de arco < min_length.
      - Span horizontal (xmax-xmin) < min_horizontal_span_ratio * image_width.
      - Si roi_lower_half_only: centroide en la mitad superior → descartar.
    """
    valid = []
    min_span = min_horizontal_span_ratio * image_width
    half_h = image_height * 0.5

    for c in contours:
        arc = cv2.arcLength(c, False)
        if arc < min_length:
            continue

        x, y, cw, ch = cv2.boundingRect(c)
        if cw < min_span:
            continue

        if roi_lower_half_only:
            M = cv2.moments(c)
            if M["m00"] > 0:
                cy = M["m01"] / M["m00"]
                if cy < half_h:
                    continue

        valid.append(c)

    return valid


def smooth_polyline(
    points: list,
    method: str = "savgol",
    window: int = 21,
    polyorder: int = 3,
) -> list:
    """
    Suaviza la polilinia de la linea de costa (#58).

    method='savgol': Savitzky-Golay (preserva picos, no introduce lag).
    method='approx': fallback con cv2.approxPolyDP si scipy no disponible.
    """
    if not points or len(points) < 4:
        return points

    pts = np.array(points, dtype=np.float32)

    if method == "savgol" and SCIPY_AVAILABLE:
        # Asegurar que window es impar y <= len(points)
        win = min(window, len(pts))
        if win % 2 == 0:
            win -= 1
        if win < polyorder + 2:
            win = polyorder + 2
            if win % 2 == 0:
                win += 1

        try:
            xs = savgol_filter(pts[:, 0], win, polyorder)
            ys = savgol_filter(pts[:, 1], win, polyorder)
            return list(zip(xs.tolist(), ys.tolist()))
        except Exception:
            pass  # fallback

    # Fallback: approxPolyDP
    arr = pts.reshape(-1, 1, 2).astype(np.float32)
    epsilon = 0.001 * cv2.arcLength(arr, False)
    approx = cv2.approxPolyDP(arr, epsilon, False)
    return approx.reshape(-1, 2).tolist()


def apply_confidence_zones(
    points: list,
    confidence_map: Optional[np.ndarray],
    threshold: float = 0.5,
) -> list:
    """
    Marca segmentos de la linea de costa con baja confianza (#61).

    Cada punto de la polilinia se evalua contra el mapa de confianza
    (canal 0 del probability_map = probabilidad de arena seca).
    Retorna lista de dicts: {"point": [x, y], "low_confidence": bool, "confidence": float}.
    """
    if not points:
        return []

    result = []
    for pt in points:
        x, y = int(pt[0]), int(pt[1])
        conf = 1.0
        if confidence_map is not None:
            h, w = confidence_map.shape[:2]
            if 0 <= y < h and 0 <= x < w:
                # Canal 0 = probabilidad arena seca
                val = confidence_map[y, x]
                conf = float(val[0]) if confidence_map.ndim == 3 else float(val)

        result.append({
            "point": [x, y],
            "low_confidence": conf < threshold,
            "confidence": round(conf, 4),
        })

    return result


def extract_coastline_from_mask(
    mask: np.ndarray,
    min_length: float = 500,
    smooth: bool = True,
    confidence_map: Optional[np.ndarray] = None,
) -> Optional[list]:
    """
    Extrae la linea de costa desde la mascara binaria (#56, #57, #58, #61).

    Criterio de seleccion del borde principal: contorno con mayor span
    horizontal (xmax - xmin), que corresponde al limite arena/agua que
    cruza la imagen de lado a lado.

    Retorna lista de puntos [x, y] (o dicts si confidence_map se provee).
    """
    mask = mask.copy()
    h, w = mask.shape

    # Ignorar tercio superior (cielo/horizonte) y bordes laterales
    mask[:int(h * 0.4), :] = 0
    margin = int(w * 0.03)
    mask[:, :margin] = 0
    mask[:, w - margin:] = 0

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None

    # Filtrar contornos secundarios (#57)
    valid = filter_secondary_contours(
        contours,
        min_length=min_length,
        image_width=w,
        image_height=h,
    )
    if not valid:
        # Relajar filtro: solo longitud minima
        valid = [c for c in contours if cv2.arcLength(c, False) > min_length * 0.5]
    if not valid:
        return None

    # Seleccionar borde principal: mayor span horizontal (#56)
    def horizontal_span(c):
        x, _, cw, _ = cv2.boundingRect(c)
        return cw

    main_contour = max(valid, key=horizontal_span)
    points = main_contour.reshape(-1, 2).tolist()

    # Suavizar (#58)
    if smooth:
        points = smooth_polyline(points)

    # Aplicar zonas de confianza (#61)
    if confidence_map is not None:
        return apply_confidence_zones(points, confidence_map)

    return points


def draw_coastline(image: np.ndarray, points: list,
                   color=(0, 0, 255), thickness: int = 6) -> np.ndarray:
    """Dibuja la linea de costa. Soporta lista de puntos o lista de dicts con confianza."""
    if not points:
        return image

    # Normalizar: admite tanto [x,y] como {"point": [x,y], ...}
    def to_xy(p):
        return p["point"] if isinstance(p, dict) else p

    raw_pts = [to_xy(p) for p in points]
    pts = np.array(raw_pts, dtype=np.int32).reshape((-1, 1, 2))
    cv2.polylines(image, [pts], False, color, thickness, cv2.LINE_AA)

    # Marcar zonas de baja confianza en amarillo
    low_conf = [p for p in points if isinstance(p, dict) and p.get("low_confidence")]
    for p in low_conf:
        x, y = int(p["point"][0]), int(p["point"][1])
        cv2.circle(image, (x, y), 12, (0, 255, 255), -1)

    return image


if __name__ == "__main__":
    import argparse, os, sys, tempfile
    # Bug real detectado 2026-08-31 (mismo que en segmentation_sam.py): "/tmp/"
    # como valor por defecto no existe en Windows, único SO objetivo de este
    # proyecto — este CLI de depuración fallaba al guardar el resultado si se
    # ejecutaba sin pasar --out explícito.
    default_out = os.path.join(tempfile.gettempdir(), "coastline_debug.jpg")
    ap = argparse.ArgumentParser(description="Extrae linea de costa de una mascara binaria")
    ap.add_argument("--mask",  required=True, help="Mascara binaria PNG")
    ap.add_argument("--image", default=None,  help="Imagen original para visualizacion")
    ap.add_argument("--out",   default=default_out)
    args = ap.parse_args()

    mask = cv2.imread(args.mask, cv2.IMREAD_GRAYSCALE)
    if mask is None:
        sys.exit(f"No se pudo leer: {args.mask}")

    points = extract_coastline_from_mask(mask)
    if points is None:
        print("No se detecto linea de costa.")
        sys.exit(0)

    print(f"Linea de costa: {len(points)} puntos")

    base = cv2.imread(args.image) if args.image else cv2.cvtColor(mask, cv2.COLOR_GRAY2BGR)
    result = draw_coastline(base, points)
    cv2.imwrite(args.out, result)
    print(f"Guardado en {args.out}")
