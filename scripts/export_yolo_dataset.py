"""Exporta las polilíneas de entrenamiento (línea húmeda) de todas las cámaras
a un dataset de segmentación en formato YOLO (ultralytics), listo para
`yolo segment train` o `scripts/train_yolo_segmentation.py`.

Por qué una FRANJA y no la línea tal cual: YOLO-seg se entrena con polígonos
(regiones cerradas), no con líneas abiertas. Cada polilínea marcada a mano se
"engorda" con un ancho fijo (--line-width-px) usando shapely, formando un
corredor alrededor de la línea húmeda real — el modelo aprende a detectar esa
franja, y luego se puede adelgazar de vuelta a una línea (mismo principio que
extract_coastline_from_mask() ya usa en el resto del pipeline, solo que al
revés: aquí partimos de la línea para construir la máscara, no de la máscara
para extraer la línea).

Fuente de los datos: exactamente las mismas anotaciones que gestiona la
sección "Entrenamiento" de la app (polilíneas guardadas a mano + las
correcciones manuales de "Editar línea manualmente" en Resultados, que
escriben en el mismo almacén) — se reutiliza la lógica real del backend
(list_training_images, _training_polyline_path...) importándola de
backend/main.py, en vez de reimplementarla aparte y arriesgarse a que las dos
copias diverjan con el tiempo.

Uso:
    python scripts/export_yolo_dataset.py --out training_dataset/linea_humeda
    python scripts/export_yolo_dataset.py --out training_dataset/linea_humeda --line-width-px 40 --val-split 0.2

Salida:
    <out>/images/train/*.jpg   <out>/images/val/*.jpg
    <out>/labels/train/*.txt   <out>/labels/val/*.txt   (formato YOLO-seg)
    <out>/data.yaml                                      (config de dataset para ultralytics)
"""
import argparse
import json
import os
import random
import shutil
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend"))

import cv2  # noqa: E402
from shapely.geometry import LineString  # noqa: E402

from config import CAMERAS, DATA_DIR  # noqa: E402
from main import (  # noqa: E402
    _training_polyline_path,
    _resolve_training_image_path,
    list_training_images,
)

CLASS_ID = 0
CLASS_NAME = "linea_humeda"


def _polyline_to_yolo_polygon(points, img_w, img_h, line_width_px, cap_style, join_style):
    """Convierte una polilínea [[x,y],...] en píxeles a un polígono YOLO-seg
    normalizado (lista plana [x1,y1,x2,y2,...] en [0,1]) — la línea engordada
    a una franja de ancho line_width_px. None si la línea es degenerada
    (menos de 2 puntos distintos) o el resultado sale vacío."""
    line = LineString(points)
    if line.length == 0:
        return None
    corridor = line.buffer(line_width_px / 2, cap_style=cap_style, join_style=join_style)
    if corridor.is_empty:
        return None
    geom = corridor
    if geom.geom_type == "MultiPolygon":
        # Caso degenerado (p.ej. línea con auto-intersección) — nos quedamos
        # con el trozo de mayor área, el corredor "real".
        geom = max(geom.geoms, key=lambda g: g.area)
    coords = list(geom.exterior.coords)
    norm = []
    for x, y in coords:
        norm.append(min(max(x / img_w, 0.0), 1.0))
        norm.append(min(max(y / img_h, 0.0), 1.0))
    return norm


def collect_samples(line_width_px, cap_style, join_style):
    """Recorre las 6 cámaras y devuelve [{cam_id, filename, src_path, polygon}]
    — una entrada por imagen anotada (no excluida) con polilínea guardada."""
    samples = []
    skipped_excluded = 0
    skipped_no_image = 0
    skipped_degenerate = 0
    for cam_id in CAMERAS:
        for img in list_training_images(cam_id):
            if not img["annotated"] or img.get("excluded"):
                if img.get("excluded"):
                    skipped_excluded += 1
                continue
            filename = img["filename"]
            poly_path = _training_polyline_path(cam_id, filename)
            if not os.path.exists(poly_path):
                continue
            with open(poly_path, "r") as f:
                points = json.load(f).get("points", [])
            if len(points) < 2:
                skipped_degenerate += 1
                continue
            src_path = _resolve_training_image_path(cam_id, filename)
            if not src_path:
                skipped_no_image += 1
                continue
            img_bgr = cv2.imread(src_path)
            if img_bgr is None:
                skipped_no_image += 1
                continue
            h, w = img_bgr.shape[:2]
            polygon = _polyline_to_yolo_polygon(points, w, h, line_width_px, cap_style, join_style)
            if polygon is None:
                skipped_degenerate += 1
                continue
            samples.append({"cam_id": cam_id, "filename": filename, "src_path": src_path, "polygon": polygon})
    return samples, {
        "excluded": skipped_excluded,
        "sin_imagen": skipped_no_image,
        "degeneradas": skipped_degenerate,
    }


def write_dataset(samples, out_dir, val_split, seed):
    random.Random(seed).shuffle(samples)
    n_val = round(len(samples) * val_split) if len(samples) > 1 else 0
    splits = {"val": samples[:n_val], "train": samples[n_val:]}

    for split, split_samples in splits.items():
        img_dir = os.path.join(out_dir, "images", split)
        lbl_dir = os.path.join(out_dir, "labels", split)
        os.makedirs(img_dir, exist_ok=True)
        os.makedirs(lbl_dir, exist_ok=True)
        for s in split_samples:
            base = f"cam{s['cam_id']}_{os.path.splitext(s['filename'])[0]}"
            ext = os.path.splitext(s["filename"])[1] or ".jpg"
            dst_img = os.path.join(img_dir, base + ext)
            shutil.copy2(s["src_path"], dst_img)
            with open(os.path.join(lbl_dir, base + ".txt"), "w") as f:
                f.write(str(CLASS_ID) + " " + " ".join(f"{v:.6f}" for v in s["polygon"]) + "\n")

    data_yaml = os.path.join(out_dir, "data.yaml")
    abs_out = os.path.abspath(out_dir).replace("\\", "/")
    with open(data_yaml, "w") as f:
        f.write(f"path: {abs_out}\ntrain: images/train\nval: images/val\nnames:\n  0: {CLASS_NAME}\n")

    return {"train": len(splits["train"]), "val": len(splits["val"])}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default="training_dataset/linea_humeda", help="Carpeta de salida del dataset")
    ap.add_argument("--line-width-px", type=float, default=60.0,
                    help="Ancho (px) de la franja alrededor de la línea húmeda marcada (por defecto 60px)")
    ap.add_argument("--cap-style", choices=["flat", "round", "square"], default="flat",
                    help="Cómo se cierra el corredor en los extremos de la línea (por defecto flat)")
    ap.add_argument("--join-style", choices=["round", "mitre", "bevel"], default="round",
                    help="Cómo se suavizan los ángulos entre segmentos de la línea (por defecto round)")
    ap.add_argument("--val-split", type=float, default=0.2, help="Fracción de imágenes para validación (0-1)")
    ap.add_argument("--seed", type=int, default=42, help="Semilla del barajado train/val, para reproducibilidad")
    args = ap.parse_args()

    cap_map = {"flat": "flat", "round": "round", "square": "square"}
    samples, skipped = collect_samples(args.line_width_px, cap_map[args.cap_style], args.join_style)

    if not samples:
        print("[export_yolo_dataset] No hay ninguna polilínea de entrenamiento guardada todavía "
              "(sección 'Entrenamiento' de la app) — nada que exportar.")
        if any(skipped.values()):
            print(f"[export_yolo_dataset] Descartadas: {skipped}")
        sys.exit(1)

    counts = write_dataset(samples, args.out, args.val_split, args.seed)
    print(f"[export_yolo_dataset] Dataset escrito en {os.path.abspath(args.out)}")
    print(f"[export_yolo_dataset] {counts['train']} imagen(es) de entrenamiento, {counts['val']} de validación")
    if any(skipped.values()):
        print(f"[export_yolo_dataset] Descartadas: {skipped}")


if __name__ == "__main__":
    main()
