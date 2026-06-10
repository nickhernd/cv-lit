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


# ── Configuración ──────────────────────────────────────────
MIN_INLIERS   = 50     # Mínimo de inliers RANSAC para aceptar la alineación
RANSAC_THRESH = 5.0    # Umbral de reproyección RANSAC (píxeles)
SIFT_FEATURES = 3000   # Número de keypoints SIFT
LOWE_RATIO    = 0.75   # Ratio test de Lowe
# ───────────────────────────────────────────────────────────


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


def align(img: np.ndarray, ref_gray: np.ndarray, ref_kp, ref_des) -> tuple[np.ndarray, dict]:
    """Alinea img respecto a la referencia. Retorna (imagen_alineada, info)."""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    sift = cv2.SIFT_create(nfeatures=SIFT_FEATURES)
    kp, des = sift.detectAndCompute(gray, None)

    if des is None or len(kp) < 10:
        return img.copy(), {"status": "no_features", "inliers": 0}

    flann = cv2.FlannBasedMatcher({"algorithm": 1, "trees": 5}, {"checks": 50})
    matches = flann.knnMatch(ref_des, des, k=2)
    good = [m for m, n in matches if m.distance < LOWE_RATIO * n.distance]

    if len(good) < MIN_INLIERS:
        return img.copy(), {"status": "low_matches", "inliers": len(good)}

    src = np.float32([ref_kp[m.queryIdx].pt for m in good]).reshape(-1, 1, 2)
    dst = np.float32([kp[m.trainIdx].pt for m in good]).reshape(-1, 1, 2)

    H, mask = cv2.findHomography(dst, src, cv2.RANSAC, RANSAC_THRESH)
    inliers = int(mask.ravel().sum()) if mask is not None else 0

    if H is None or inliers < MIN_INLIERS:
        return img.copy(), {"status": "ransac_failed", "inliers": inliers}

    h, w = ref_gray.shape
    aligned = cv2.warpPerspective(img, H, (w, h))
    return aligned, {"status": "ok", "inliers": inliers, "H": H}


def run(input_dir: Path, output_dir: Path, ref_path: Path | None):
    print("\n── Coastal Alignment Pipeline · Tech4D Lab ──\n")

    out_aligned = output_dir / "aligned"
    out_aligned.mkdir(parents=True, exist_ok=True)

    paths = load_sequence(input_dir)
    if not paths:
        sys.exit("No se encontraron imágenes.")

    # Referencia
    ref_file = ref_path or paths[0]
    ref_img  = cv2.imread(str(ref_file))
    ref_gray = cv2.cvtColor(ref_img, cv2.COLOR_BGR2GRAY)
    sift = cv2.SIFT_create(nfeatures=SIFT_FEATURES)
    ref_kp, ref_des = sift.detectAndCompute(ref_gray, None)
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
            info = {"status": "reference", "inliers": len(ref_kp)}
            H_flat = np.eye(3).flatten().tolist()
        else:
            aligned, info = align(img, ref_gray, ref_kp, ref_des)
            H_flat = info["H"].flatten().tolist() if info.get("H") is not None else [None]*9

        cv2.imwrite(str(out_aligned / p.name), aligned)

        status_icon = "✓" if info["status"] in ("ok", "reference") else "⚠"
        print(f"  [{i+1:03d}] {p.name}  {status_icon}  {info['status']}  ({info['inliers']} inliers)")

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
    args = ap.parse_args()
    run(args.input, args.output, args.ref)
