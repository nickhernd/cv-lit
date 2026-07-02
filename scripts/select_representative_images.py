#!/usr/bin/env python3
"""
select_representative_images.py - Seleccion de imagenes representativas por camara y hora.

Issues implementadas:
  #38 — Clasificar imagenes por hora del dia y nivel de brillo.
  #39 — Seleccionar al menos 20 imagenes representativas por camara.
  #40 — Exportar JSON con rutas seleccionadas para calibracion manual.

Nomenclatura esperada: {timestamp}_{YYYYMMDD}_{HHMMSS}_{ID}.jpg
"""

import cv2
import json
import re
import numpy as np
from pathlib import Path
from collections import defaultdict

BASE_DIR  = Path(__file__).parent.parent
DATA_DIR  = BASE_DIR / "proces_images" / "data"
CALIB_DIR = BASE_DIR / "calibration"

# Directorios de imagenes por camara
CAM_DIRS = {
    1: [DATA_DIR / "camera1"],
    2: [DATA_DIR / "camera2"],
    3: [DATA_DIR / "camera3"],
    4: [DATA_DIR / "camera4"],
    5: [DATA_DIR / "camera5"],
    6: [DATA_DIR / "camera6"],
}

# Franjas horarias de interes (hora local, 0-23)
HOUR_SLOTS = [7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20]
IMAGES_PER_CAM = 20   # minimo de imagenes a seleccionar por camara


_FNAME_RE = re.compile(r"(\d{10})_(\d{8})_(\d{6})_")


def parse_filename(path: Path) -> dict | None:
    """Extrae metadatos del nombre de fichero."""
    m = _FNAME_RE.match(path.name)
    if not m:
        return None
    ts_unix, date_str, time_str = m.group(1), m.group(2), m.group(3)
    hour = int(time_str[:2])
    return {
        "path":      str(path),
        "timestamp": int(ts_unix),
        "date":      date_str,
        "hour":      hour,
    }


def measure_brightness(path: Path) -> float:
    """Lee la imagen y devuelve la luminancia media (0-255)."""
    img = cv2.imread(str(path))
    if img is None:
        return -1.0
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    return float(np.mean(gray))


def classify_images(cam_dirs: list[Path]) -> list[dict]:
    """
    Clasifica todas las imagenes de una camara por hora y brillo (#38).

    Retorna lista de dicts con: path, timestamp, date, hour, brightness,
    brightness_class (dark/ok/bright).
    """
    images = []
    for d in cam_dirs:
        if not d.exists():
            continue
        for f in sorted(d.glob("*.jpg")):
            meta = parse_filename(f)
            if meta is None:
                continue
            brightness = measure_brightness(f)
            if brightness < 0:
                continue

            if brightness < 50:
                b_class = "dark"
            elif brightness > 200:
                b_class = "bright"
            else:
                b_class = "ok"

            meta["brightness"] = round(brightness, 2)
            meta["brightness_class"] = b_class
            images.append(meta)

    return images


def select_representative(images: list[dict], n_min: int = IMAGES_PER_CAM) -> list[dict]:
    """
    Selecciona imagenes representativas (#39).

    Estrategia:
      1. Por cada franja horaria, seleccionar la imagen con brillo mas cercano
         a la mediana del slot (evita outliers de luz).
      2. Si no se alcanza n_min, rellenar con las imagenes "ok" restantes
         ordenadas por brillo.
      3. Marcar las rechazadas (bad_lighting) para referencia.
    """
    # Agrupar por hora
    by_hour: dict[int, list[dict]] = defaultdict(list)
    for img in images:
        if img["brightness_class"] == "ok" and img["hour"] in HOUR_SLOTS:
            by_hour[img["hour"]].append(img)

    selected = []

    # Paso 1: un representante por hora
    for h in HOUR_SLOTS:
        slot = by_hour.get(h, [])
        if not slot:
            continue
        brightnesses = [s["brightness"] for s in slot]
        median_b = float(np.median(brightnesses))
        best = min(slot, key=lambda s: abs(s["brightness"] - median_b))
        best = dict(best)
        best["selection_reason"] = f"median_of_slot_{h:02d}h"
        selected.append(best)

    # Paso 2: rellenar hasta n_min
    already = {s["path"] for s in selected}
    ok_remaining = sorted(
        [img for img in images if img["path"] not in already and img["brightness_class"] == "ok"],
        key=lambda x: x["brightness"],
    )
    while len(selected) < n_min and ok_remaining:
        img = ok_remaining.pop(len(ok_remaining) // 2)  # tomar el del centro (mediana)
        img = dict(img)
        img["selection_reason"] = "fill_to_minimum"
        selected.append(img)

    return selected


def export_selection(
    selection_by_cam: dict[str, list[dict]],
    output_path: Path,
) -> None:
    """Exporta el JSON de seleccion (#40)."""
    summary = {
        "description": "Imagenes representativas seleccionadas para calibracion manual",
        "min_per_cam": IMAGES_PER_CAM,
        "cameras": {},
    }
    for cam_key, images in selection_by_cam.items():
        summary["cameras"][cam_key] = {
            "count": len(images),
            "images": images,
        }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    print(f"[OK] Exportado: {output_path}")


def main():
    import argparse
    ap = argparse.ArgumentParser(
        description="Selecciona imagenes representativas por camara para calibracion"
    )
    ap.add_argument("--cam",    default=None, type=int,
                    help="Procesar solo esta camara (1-6). Default: todas.")
    ap.add_argument("--n",      default=IMAGES_PER_CAM, type=int,
                    help=f"Minimo de imagenes por camara (default: {IMAGES_PER_CAM})")
    ap.add_argument("--out",    default=str(CALIB_DIR / "representative_images.json"),
                    help="Ruta de salida del JSON")
    ap.add_argument("--no-brightness", action="store_true",
                    help="Omitir lectura de brillo (mas rapido, no filtra por luz)")
    args = ap.parse_args()

    cams = [args.cam] if args.cam else list(CAM_DIRS.keys())
    selection_by_cam: dict[str, list[dict]] = {}

    for cam_id in cams:
        cam_key = f"CAM_{cam_id}"
        dirs = CAM_DIRS.get(cam_id, [])
        print(f"[.] {cam_key}: clasificando imagenes en {[str(d) for d in dirs]} ...")

        if args.no_brightness:
            images = []
            for d in dirs:
                if not d.exists():
                    print(f"    [WARNING] Directorio no existe: {d}")
                    continue
                for f in sorted(d.glob("*.jpg")):
                    meta = parse_filename(f)
                    if meta:
                        meta["brightness"] = -1.0
                        meta["brightness_class"] = "ok"
                        images.append(meta)
        else:
            images = classify_images(dirs)

        if not images:
            print(f"    [WARNING] Sin imagenes encontradas para {cam_key}")
            selection_by_cam[cam_key] = []
            continue

        selected = select_representative(images, n_min=args.n)
        selection_by_cam[cam_key] = selected
        print(f"    [OK] {len(selected)} imagenes seleccionadas de {len(images)} totales")

    export_selection(selection_by_cam, Path(args.out))


if __name__ == "__main__":
    main()
