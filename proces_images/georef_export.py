#!/usr/bin/env python3
"""
georef_export.py - Georreferenciacion y exportacion a GeoJSON.

Issues implementadas:
  #63 — Cargar calibracion por camara (H matrix, EPSG, RMSE).
  #64 — Proyectar pixeles a UTM EPSG:25830 con homografia.
  #65 — Calcular area seca en m2 desde mascara.
  #66 — Indice de confianza por deteccion.
  #68 — Exportar GeoJSON con atributos estandar.
"""

import json
import math
import numpy as np
from pathlib import Path
from typing import Optional
from datetime import datetime, timezone

BASE_DIR  = Path(__file__).parent.parent
CALIB_DIR = BASE_DIR / "calibration"

# RMSE umbral para considerar calibracion "buena" (~1.5 m @ 4K)
RMSE_GOOD_M = 2.0


def load_calibration(cam_id: int | str) -> dict:
    """
    Carga la matriz de homografia y metadatos de calibracion (#63).

    Retorna dict con:
      "H"          → np.ndarray (3,3) pixel→UTM 25830
      "epsg"       → int (25830)
      "rmse_m"     → float RMSE en metros
      "rmse_val_m" → float RMSE validacion
      "cam_id"     → int
    """
    cam_num = int(str(cam_id).replace("CAM_", "").replace("CAM", ""))
    profile_path = CALIB_DIR / f"cam_{cam_num}_profile.json"
    h_path       = CALIB_DIR / f"cam_{cam_num}_H.npy"

    if not profile_path.exists():
        raise FileNotFoundError(f"Perfil no encontrado: {profile_path}")

    with open(profile_path) as f:
        prof = json.load(f)

    if h_path.exists():
        H = np.load(str(h_path))
    else:
        H = np.array(prof["H"], dtype=np.float64)

    return {
        "H": H,
        "epsg": prof.get("epsg", 25830),
        "rmse_m": prof.get("rmse_m", 9999.0),
        "rmse_val_m": prof.get("rmse_val_m", 9999.0),
        "cam_id": cam_num,
        "cam_name": prof.get("cam_name", f"CAM_{cam_num}"),
    }


def pixels_to_utm(
    points_px: list | np.ndarray,
    H: np.ndarray,
) -> np.ndarray:
    """
    Proyecta puntos pixel a coordenadas UTM EPSG:25830 (#64).

    Aplica la homografia: [X, Y, W]^T = H @ [x, y, 1]^T
    Coordenadas finales: (X/W, Y/W).

    points_px: array-like (N, 2) con pares (col, row).
    Retorna array (N, 2) con pares (Easting, Northing) en metros.
    """
    pts = np.asarray(points_px, dtype=np.float64).reshape(-1, 2)
    ones = np.ones((len(pts), 1), dtype=np.float64)
    hom = np.hstack([pts, ones])          # (N, 3)
    proj = (H @ hom.T).T                  # (N, 3)
    w = proj[:, 2:3]
    utm = proj[:, :2] / w                 # divide por componente homogenea
    return utm


def calculate_dry_area_m2(
    mask: np.ndarray,
    H: np.ndarray,
    sample_step: int = 10,
) -> float:
    """
    Calcula el area de arena seca en m2 a partir de la mascara binaria (#65).

    Estrategia: muestrea una cuadricula de pixeles activos en la mascara,
    los proyecta a UTM y estima el area como suma de celdas.
    Cada celda en UTM ocupa aproximadamente el area de un pixel proyectado.

    sample_step: submuestreo de pixeles (mayor → mas rapido, menos preciso).
    """
    if mask is None:
        return 0.0

    h_img, w_img = mask.shape[:2]
    ys, xs = np.where(mask > 0)
    if len(xs) == 0:
        return 0.0

    # Submuestrear para eficiencia
    step = max(1, sample_step)
    xs_s = xs[::step]
    ys_s = ys[::step]

    # Proyectar esquinas de celda para estimar area de pixel en UTM
    # Tomamos un pixel central representativo del area activa
    cx = float(np.median(xs_s))
    cy = float(np.median(ys_s))

    # Proyectamos cuatro esquinas de un pixel (1x1)
    corners_px = np.array([
        [cx, cy],
        [cx + 1, cy],
        [cx, cy + 1],
        [cx + 1, cy + 1],
    ])
    corners_utm = pixels_to_utm(corners_px, H)

    # Area del cuadrilatero via producto cruzado
    p0, p1, p2, p3 = corners_utm
    d1 = p1 - p0  # vector horizontal
    d2 = p2 - p0  # vector vertical
    pixel_area_m2 = abs(float(np.cross(d1, d2)))

    total_pixels = len(xs)
    return total_pixels * pixel_area_m2


def confidence_index(
    mask: np.ndarray,
    rmse_m: float,
    coastline_points: Optional[list] = None,
    prob_map: Optional[np.ndarray] = None,
) -> float:
    """
    Calcula el indice de confianza de la deteccion en [0, 1] (#66).

    Factores combinados (promedio ponderado):
      1. Calidad de calibracion: exp(-rmse / RMSE_GOOD_M)
      2. Cobertura de mascara: fraccion del frame con arena detectada
      3. Media de probabilidad SAM (si prob_map disponible)
      4. Confianza de puntos de costa (si coastline_points incluye .confidence)

    Pesos reajustados en 2026-08-31 tras diagnosticar en vivo, con varias
    cámaras recién recalibradas con datos reales, un doble penalizado
    estructural: la calidad de calibración (factor 1) es una CONSTANTE por
    cámara — ya se decide aparte, al calibrar, si el RMSE pasa el umbral
    RMSE_GOOD_M — pero con peso 3 (el mayor de los cuatro) y una caída
    exponencial dura, cualquier cámara con un RMSE real "aceptable pero no
    excelente" (p.ej. 1.5-2.0 m, perfectamente dentro de tolerancia) arrastra
    la confianza de TODAS sus imágenes hacia abajo, sin que la imagen en sí
    tenga ningún problema. La probabilidad media de SAM (factor 3) resultó
    igual de poco fiable por otro motivo: se promedia sobre TODA la zona de
    interés, que en cualquier foto de costa incluye mar/agua en cantidad —
    píxeles correctamente "no arena" que diluyen la media aunque la playa se
    detecte perfectamente. La cobertura de máscara (factor 2) fue, con
    diferencia, la señal más fiable de las tres en los casos reales
    comprobados — de ahí el peso subido. Casos verificados con datos reales:
    3 cámaras con calibración válida (RMSE 1.36-1.98 m) que antes se
    rechazaban por baja confianza pasan a aceptarse, sin que las máscaras
    realmente vacías (falla otro filtro aparte, mask_area_min_ratio) ni la
    homografía mal condicionada (filtro area_no_fiable, también aparte) se
    vean afectadas — ninguna de las dos depende de confidence_index().
    """
    scores = []
    weights = []

    # 1. Calidad de calibracion (peso 1 — antes 3, ver nota arriba)
    calib_score = math.exp(-rmse_m / RMSE_GOOD_M)
    scores.append(calib_score)
    weights.append(1.0)

    # 2. Cobertura de mascara (peso 2 — antes 1, ver nota arriba) — esperamos >5% y <70% de frame
    if mask is not None:
        total = mask.size
        active = int(np.sum(mask > 0))
        frac = active / total
        # Score maximo en ~15-40% de cobertura
        cov_score = min(1.0, 2.0 * min(frac, 0.5 - frac) / 0.35) if 0 < frac < 0.5 else 0.1
        scores.append(max(0.0, cov_score))
        weights.append(2.0)

    # 3. Media de probabilidad SAM (peso 1 — antes 2, ver nota arriba)
    if prob_map is not None and prob_map.ndim == 3:
        mean_prob = float(np.mean(prob_map[:, :, 0]))  # canal seca
        scores.append(np.clip(mean_prob, 0.0, 1.0))
        weights.append(1.0)

    # 4. Confianza media de puntos de costa (peso 2)
    if coastline_points:
        conf_vals = [p["confidence"] for p in coastline_points
                     if isinstance(p, dict) and "confidence" in p]
        if conf_vals:
            scores.append(float(np.mean(conf_vals)))
            weights.append(2.0)

    if not scores:
        return 0.0

    total_w = sum(weights)
    return round(sum(s * w for s, w in zip(scores, weights)) / total_w, 4)


def build_geojson_feature(
    coastline_points: list,
    cam_id: int | str,
    timestamp: str,
    H: np.ndarray,
    mask: np.ndarray,
    rmse_m: float,
    prob_map: Optional[np.ndarray] = None,
) -> dict:
    """
    Construye un GeoJSON Feature con la linea de costa y atributos (#68).

    Esquema de propiedades:
      ID_Camara     — identificador de camara (str)
      Timestamp     — ISO 8601 UTC
      Confianza_IA  — float [0,1]
      Area_Seca_m2  — float metros cuadrados
      RMSE_m        — float error de calibracion en metros
      n_puntos      — int numero de vertices en la polilinia
    """
    cam_str = f"CAM_{int(str(cam_id).replace('CAM_', '').replace('CAM', ''))}"

    # Normalizar puntos: admite [x,y] o {"point": [x,y], ...}
    def to_xy(p):
        return p["point"] if isinstance(p, dict) else p

    raw_pts = [to_xy(p) for p in coastline_points]

    # Proyectar pixeles a UTM (#64)
    utm_pts = pixels_to_utm(raw_pts, H)
    coordinates = [[round(float(e), 3), round(float(n), 3)]
                   for e, n in utm_pts]

    area_m2 = calculate_dry_area_m2(mask, H)
    conf    = confidence_index(mask, rmse_m, coastline_points, prob_map)

    return {
        "type": "Feature",
        "geometry": {
            "type": "LineString",
            "coordinates": coordinates,
        },
        "properties": {
            "ID_Camara":    cam_str,
            "Timestamp":    timestamp,
            "Confianza_IA": conf,
            "Area_Seca_m2": round(area_m2, 2),
            "RMSE_m":       round(rmse_m, 4),
            "n_puntos":     len(coordinates),
            "crs":          "EPSG:25830",
        },
    }


def export_geojson(
    features: list,
    output_path: str | Path,
    indent: int = 2,
) -> Path:
    """
    Exporta lista de features GeoJSON a fichero (#68).

    La coleccion incluye metadatos de creacion en las propiedades globales.
    """
    collection = {
        "type": "FeatureCollection",
        "crs": {
            "type": "name",
            "properties": {"name": "urn:ogc:def:crs:EPSG::25830"},
        },
        "properties": {
            "project": "CV-LIT Guardamar",
            "created": datetime.now(timezone.utc).isoformat(),
            "n_features": len(features),
        },
        "features": features,
    }

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(collection, f, indent=indent, ensure_ascii=False)

    return out


def validate_units(utm_coords: list) -> bool:
    """
    Valida que las coordenadas son plausibles para EPSG:25830 (UTM zona 30N, peninsula iberica).

    Rango aproximado: Easting 100000-900000, Northing 3900000-4900000.
    """
    if not utm_coords:
        return False

    for coord in utm_coords:
        e, n = coord[0], coord[1]
        if not (100_000 <= e <= 900_000):
            return False
        if not (3_900_000 <= n <= 4_900_000):
            return False

    return True


if __name__ == "__main__":
    import argparse, sys
    ap = argparse.ArgumentParser(description="Georreferencia y exporta linea de costa")
    ap.add_argument("--cam",        required=True,              help="ID camara (1-6)")
    ap.add_argument("--mask",       required=True,              help="Mascara binaria PNG")
    ap.add_argument("--coastline",  required=True,              help="JSON con lista de puntos [x,y]")
    ap.add_argument("--timestamp",  default=None,               help="ISO8601 (default: ahora)")
    ap.add_argument("--out",        default="/tmp/coast.geojson")
    args = ap.parse_args()

    import cv2
    mask = cv2.imread(args.mask, cv2.IMREAD_GRAYSCALE)
    if mask is None:
        sys.exit(f"No se pudo leer mascara: {args.mask}")

    with open(args.coastline) as f:
        points = json.load(f)

    ts = args.timestamp or datetime.now(timezone.utc).isoformat()

    try:
        calib = load_calibration(args.cam)
    except FileNotFoundError as e:
        sys.exit(str(e))

    feature = build_geojson_feature(
        coastline_points=points,
        cam_id=args.cam,
        timestamp=ts,
        H=calib["H"],
        mask=mask,
        rmse_m=calib["rmse_m"],
    )

    valid = validate_units(feature["geometry"]["coordinates"])
    print(f"Coordenadas UTM validas: {valid}")
    print(f"Area seca: {feature['properties']['Area_Seca_m2']} m2")
    print(f"Confianza: {feature['properties']['Confianza_IA']}")

    out = export_geojson([feature], args.out)
    print(f"GeoJSON exportado: {out}")
