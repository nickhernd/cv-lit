"""
align_images.py
===============
Alinea una secuencia de imágenes de cámara fija respecto a una referencia.
Usa SIFT + FLANN + RANSAC para calcular la homografía entre cada imagen y la referencia.

Uso:
    python align_images.py --input /ruta/imagenes --output /ruta/salida
    python align_images.py --input /ruta/imagenes --output /ruta/salida --ref imagen.jpg

Outputs:
    /output/aligned/     → Imágenes alineadas
    /output/homographies.csv  → Parámetros H y métricas de calidad por imagen
"""

import cv2
import numpy as np
import pandas as pd
from pathlib import Path
from datetime import datetime
import argparse
import re
import sys
import json

# ── Configuración ──────────────────────────────────────────
MIN_INLIERS   = 50     # Mínimo de inliers RANSAC para aceptar la alineación
RANSAC_THRESH = 5.0    # Umbral de reproyección RANSAC (píxeles)
SIFT_FEATURES = 3000   # Número de keypoints SIFT
LOWE_RATIO    = 0.75   # Ratio test de Lowe
# ───────────────────────────────────────────────────────────

# ── Corrección de iluminación ───────────────────────────────────────────────
# SIFT es sensible a la iluminación: sol directo, reflejos en el agua o cielo
# sobreexpuesto generan keypoints en zonas dinámicas (espuma, gaviotas, sombras)
# que producen matches falsos y sesgan la homografía (pocos inliers reales).
#
# Solución en dos pasos aplicados ANTES de detectAndCompute:
#   1. _check_lighting  → descarta imágenes con iluminación extrema (sobre/sub
#                         exposición o contraste nulo) antes de entrar en SIFT.
#   2. _CLAHE.apply     → ecualización de histograma adaptativa local (bloques
#                         8×8 px). Normaliza el contraste entre imágenes de
#                         distintas horas/condiciones sin alterar la geometría,
#                         haciendo que una imagen a mediodía y otra con nubes
#                         produzcan keypoints equivalentes en las mismas zonas.
# ────────────────────────────────────────────────────────────────────────────
_CLAHE = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))

def _check_lighting(gray: np.ndarray) -> tuple[bool, str]:
    """Detecta condiciones de iluminación que degradan SIFT."""
    mean = float(np.mean(gray))
    std  = float(np.std(gray))
    if mean > 200:
        return False, "overexposed"   # sol directo / reflejos saturados
    if mean < 30:
        return False, "underexposed"  # amanecer / anochecer / imagen oscura
    if std < 18:
        return False, "low_contrast"  # niebla / calima / imagen lavada
    return True, ""

MASKS_PATH = Path(__file__).parent.parent / "calibration" / "alignment_masks.json"

def build_mask_for_cam(cam_id: int, h: int, w: int):
    """Carga alignment_masks.json y genera máscara binaria para SIFT. None = sin restricción."""
    if not MASKS_PATH.exists():
        return None
    with open(MASKS_PATH) as f:
        cfg = json.load(f)
    key = f"CAM_{cam_id}"
    if key not in cfg:
        return None
    canvas = np.zeros((h, w), dtype=np.uint8)
    for r in cfg[key].get("regions", []):
        x0, y0 = int(r["x0"] * w), int(r["y0"] * h)
        x1, y1 = int(r["x1"] * w), int(r["y1"] * h)
        cv2.rectangle(canvas, (x0, y0), (x1, y1), 255, -1)
    return canvas


def parse_filename(path: Path) -> datetime:
    """Extrae datetime del nombre de archivo. Formato: UNIX_YYYYMMDD_HHMMSS_*.jpg"""
    m = re.match(r"\d+_(\d{8})_(\d{6})_", path.stem)
    if m:
        return datetime.strptime(f"{m.group(1)}_{m.group(2)}", "%Y%m%d_%H%M%S")
    m2 = re.search(r"(\d{8})", path.stem)
    if m2:
        return datetime.strptime(m2.group(1), "%Y%m%d")
    return datetime.fromtimestamp(path.stat().st_mtime)


def load_sequence(input_dir: Path) -> list[Path]:
    paths = []
    for ext in ["*.jpg", "*.jpeg", "*.JPG", "*.JPEG"]:
        paths.extend(input_dir.glob(ext))
    paths.sort(key=lambda p: parse_filename(p))
    print(f"  {len(paths)} imágenes encontradas")
    return paths


def align(img: np.ndarray, ref_gray: np.ndarray, ref_kp, ref_des,
          ref_img: np.ndarray = None, feat_mask: np.ndarray = None) -> tuple[np.ndarray, dict]:
    """Alinea img respecto a la referencia. Retorna (imagen_alineada, info)."""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # Paso 1: filtro de iluminación — descarta imágenes con luz extrema antes de SIFT
    ok, light_reason = _check_lighting(gray)
    if not ok:
        return img.copy(), {"status": "bad_lighting", "inliers": 0, "viz": None, "fail_reason": light_reason}

    # Paso 2: normalización de contraste local — iguala condiciones entre tomas
    gray = _CLAHE.apply(gray)

    sift = cv2.SIFT_create(nfeatures=SIFT_FEATURES)

    # Paso 3: máscara de zonas estables — restringe SIFT a regiones sin objetos
    # dinámicos (gaviotas, olas, personas). Definida en calibration/alignment_masks.json
    # con coordenadas fraccionarias [0.0-1.0] independientes de la resolución.
    mask_use = None
    if feat_mask is not None:
        mask_use = cv2.resize(feat_mask, (gray.shape[1], gray.shape[0]),
                              interpolation=cv2.INTER_NEAREST)
    kp, des = sift.detectAndCompute(gray, mask_use)

    if des is None or len(kp) < 10:
        return img.copy(), {"status": "no_features", "inliers": 0, "viz": None}

    flann = cv2.FlannBasedMatcher({"algorithm": 1, "trees": 5}, {"checks": 50})
    matches = flann.knnMatch(ref_des, des, k=2)
    good = [m for m, n in matches if m.distance < LOWE_RATIO * n.distance]

    if len(good) < MIN_INLIERS:
        return img.copy(), {"status": "low_matches", "inliers": len(good), "viz": None}

    src = np.float32([ref_kp[m.queryIdx].pt for m in good]).reshape(-1, 1, 2)
    dst = np.float32([kp[m.trainIdx].pt for m in good]).reshape(-1, 1, 2)

    H, mask = cv2.findHomography(dst, src, cv2.RANSAC, RANSAC_THRESH)
    inliers = int(mask.ravel().sum()) if mask is not None else 0

    if H is None or inliers < MIN_INLIERS:
        return img.copy(), {"status": "ransac_failed", "inliers": inliers, "viz": None}

    h, w = ref_gray.shape
    aligned = cv2.warpPerspective(img, H, (w, h))
    
    # --- Generar Visualización de Diagnóstico ---
    # 1. Blend (Overlay) solicitado por el usuario
    # Redimensionamos a algo manejable pero visible (ej: 800x450)
    v_size = (800, 450)
    ref_res = cv2.resize(ref_img, v_size)
    ali_res = cv2.resize(aligned, v_size)
    blend = cv2.addWeighted(ref_res, 0.5, ali_res, 0.5, 0)
    
    # 2. Dibujar Matches (Inliers)
    # Solo mostramos una selección para no saturar
    matches_mask = mask.ravel().tolist()
    viz_matches = cv2.drawMatches(ref_img, ref_kp, img, kp, good, None,
                                  matchColor=(0, 255, 0),
                                  singlePointColor=(0, 0, 255),
                                  matchesMask=matches_mask,
                                  flags=cv2.DrawMatchesFlags_NOT_DRAW_SINGLE_POINTS)
    viz_matches = cv2.resize(viz_matches, (1600, 450))
    
    # Combinar ambos en una tira de diagnóstico
    diagnostics = np.hstack([cv2.resize(blend, (800, 450)), viz_matches[:450, :800]])
    
    return aligned, {"status": "ok", "inliers": inliers, "H": H, "viz": diagnostics}


def run(input_dir: Path, output_dir: Path, ref_path: Path | None):
    print("\n── Coastal Alignment Pipeline · Tech4D Lab ──\n")

    out_aligned = output_dir / "aligned"
    out_diag    = output_dir / "diagnostics"
    out_aligned.mkdir(parents=True, exist_ok=True)
    out_diag.mkdir(parents=True, exist_ok=True)

    paths = load_sequence(input_dir)
    if not paths:
        sys.exit("No se encontraron imágenes.")

    # Referencia
    ref_file = ref_path or paths[0]
    ref_img  = cv2.imread(str(ref_file))
    ref_gray = cv2.cvtColor(ref_img, cv2.COLOR_BGR2GRAY)
    ref_gray = _CLAHE.apply(ref_gray)
    h_ref, w_ref = ref_gray.shape

    # Máscara de zonas estables (si --cam está disponible)
    feat_mask = build_mask_for_cam(args.cam, h_ref, w_ref) if hasattr(args, 'cam') and args.cam else None
    if feat_mask is not None:
        print(f"  Máscara de alineación activa para CAM {args.cam}")

    sift = cv2.SIFT_create(nfeatures=SIFT_FEATURES)
    ref_kp, ref_des = sift.detectAndCompute(ref_gray, feat_mask)
    print(f"  Referencia: {ref_file.name}  ({len(ref_kp)} keypoints)\n")

    records = []
    for i, p in enumerate(paths):
        img = cv2.imread(str(p))
        if img is None:
            print(f"  [{i+1:03d}] {p.name} → ERROR lectura")
            continue

        dt = parse_filename(p)

        if p == ref_file:
            aligned = img.copy()
            info = {"status": "reference", "inliers": len(ref_kp), "viz": None}
            H_flat = np.eye(3).flatten().tolist()
        else:
            aligned, info = align(img, ref_gray, ref_kp, ref_des, ref_img=ref_img, feat_mask=feat_mask)
            H_flat = info["H"].flatten().tolist() if info.get("H") is not None else [None]*9

        cv2.imwrite(str(out_aligned / p.name), aligned)
        if info.get("viz") is not None:
            cv2.imwrite(str(out_diag / f"diag_{p.name}"), info["viz"])

        status_icon = "[OK]" if info["status"] in ("ok", "reference") else "[WARNING]"
        extra = f"  [{info.get('fail_reason','')}]" if info["status"] == "bad_lighting" else ""
        print(f"  [{i+1:03d}] {p.name}  {status_icon}  {info['status']}  ({info['inliers']} inliers){extra}")

        records.append({
            "datetime":  dt.isoformat(),
            "filename":  p.name,
            "status":    info["status"],
            "inliers":   info["inliers"],
            **{f"H{r}{c}": H_flat[r*3+c] for r in range(3) for c in range(3)},
        })

    df = pd.DataFrame(records)
    csv_path = output_dir / "homographies.csv"
    df.to_csv(csv_path, index=False)

    ok = (df["status"].isin(["ok", "reference"])).sum()
    print(f"\n  Procesadas: {len(df)}  |  OK: {ok}  |  CSV: {csv_path}\n")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Align beach camera images to a reference.")
    ap.add_argument("--input",  "-i", required=True, type=Path)
    ap.add_argument("--output", "-o", required=True, type=Path)
    ap.add_argument("--ref",    "-r", default=None,  type=Path)
    ap.add_argument("--cam",    "-c", default=None,  type=int,
                    help="ID de cámara (1-6) para aplicar máscara de zonas estables")
    args = ap.parse_args()
    run(args.input, args.output, args.ref)
