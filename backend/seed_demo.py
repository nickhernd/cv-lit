"""Siembra el workspace de la DEMO.

Copia las imágenes de muestra de proces_images/data, importa las varillas del
GCP.csv como catálogo por cámara y deja cada imagen con GCPs del CSV ya marcada
y con su homografía calculada (calibración por imagen).

Se invoca desde start_demo.ps1 con CVLIT_DATA_DIR y CVLIT_CALIBRATION_DIR
apuntando al workspace de demo. Cada ejecución regenera la demo desde cero,
sin tocar nunca los datos reales.
"""
import io
import json
import os
import shutil
import sys
import datetime

# Guardarraíl: sin las variables de entorno del workspace este script operaría
# sobre los datos reales (los sobrescribiría). Abortamos antes de importar nada.
if not os.environ.get("CVLIT_DATA_DIR") or not os.environ.get("CVLIT_CALIBRATION_DIR"):
    print("[ERROR] seed_demo.py requiere CVLIT_DATA_DIR y CVLIT_CALIBRATION_DIR "
          "(usa start_demo.ps1). Abortado para no tocar los datos reales.")
    sys.exit(1)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import cv2
import pandas as pd

from config import BASE_DIR, CAMERAS, DATA_DIR, CALIBRATION_DIR, PROCES_IMAGES_DIR
from main import HomographyRequest, calculate_homography, _annotations_path

REAL_DATA_DIR = os.path.join(PROCES_IMAGES_DIR, "data")
REAL_CALIBRATION_DIR = os.path.join(BASE_DIR, "calibration")
GCP_CSV = os.path.join(REAL_DATA_DIR, "GCP.csv")
THRESHOLD_PX = 30.0

CAM_TAG_TO_ID = {f"CAM{i}": i for i in CAMERAS}


def _num(v) -> float:
    if isinstance(v, str):
        v = v.strip().replace(",", ".")
    return float(v)


def reset_workspace():
    """Borra y recrea el workspace de demo (solo si es realmente un workspace)."""
    for path in (DATA_DIR, CALIBRATION_DIR):
        if "workspace" not in path.lower():
            print(f"[ERROR] {path} no parece un workspace de demo. Abortado.")
            sys.exit(1)
        if os.path.isdir(path):
            shutil.rmtree(path)
        os.makedirs(path, exist_ok=True)


def copy_sample_images():
    for cam_id, info in CAMERAS.items():
        src = os.path.join(REAL_DATA_DIR, info["folder"])
        dst = os.path.join(DATA_DIR, info["folder"])
        os.makedirs(dst, exist_ok=True)
        count = 0
        if os.path.isdir(src):
            for f in os.listdir(src):
                if f.lower().endswith((".jpg", ".jpeg", ".png")):
                    shutil.copy2(os.path.join(src, f), os.path.join(dst, f))
                    count += 1
        print(f"[demo] Cam {cam_id}: {count} imágenes de muestra copiadas")


def copy_calibration_support():
    """Máscaras de alineación, ROIs y hardware: la demo hereda los reales."""
    for name in ("alignment_masks.json", "roi_config.json", "camera_hardware.json"):
        src = os.path.join(REAL_CALIBRATION_DIR, name)
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(CALIBRATION_DIR, name))


def parse_gcp_csv():
    """Devuelve {cam_id: [ {label, utm, pixel, file, color} ]} desde GCP.csv."""
    with open(GCP_CSV, "r", encoding="utf-8-sig", errors="replace") as f:
        text = f.read()
    df = pd.read_csv(io.StringIO(text), sep=None, engine="python", header=1)
    cols = {str(c).strip().upper(): c for c in df.columns}
    by_cam = {}
    for _, row in df.iterrows():
        cam_raw = row.get(cols.get("CAMERA"))
        if pd.isna(cam_raw):
            continue
        cam_tag = str(cam_raw).strip().upper().replace(" ", "").replace("_", "")
        cam_id = CAM_TAG_TO_ID.get(cam_tag)
        if cam_id is None:
            continue
        try:
            utm = [_num(row[cols["X.1"]]), _num(row[cols["Y.1"]])]
            pixel = [_num(row[cols["X"]]), _num(row[cols["Y"]])]
        except (TypeError, ValueError, KeyError):
            continue
        label = f"GCP_{str(row[cols['ID']]).strip()}" if "ID" in cols and not pd.isna(row[cols["ID"]]) else "GCP"
        entry = {
            "label": label,
            "utm": utm,
            "pixel": pixel,
            "file": str(row[cols["FILE"]]).strip() if "FILE" in cols and not pd.isna(row[cols["FILE"]]) else "",
            "color": str(row[cols["COLOR"]]).strip() if "COLOR" in cols and not pd.isna(row[cols["COLOR"]]) else "",
        }
        by_cam.setdefault(cam_id, []).append(entry)
    return by_cam


def write_rods(cam_id, entries):
    rods = [{
        "label": e["label"], "utm": e["utm"], "pixel": e["pixel"],
        "notes": " · ".join(x for x in (e["file"], e["color"]) if x),
    } for e in entries]
    payload = {
        "cam_id": cam_id,
        "source_file": "GCP.csv",
        "imported_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "rods": rods,
    }
    with open(os.path.join(CALIBRATION_DIR, f"cam_{cam_id}_rods.json"), "w") as f:
        json.dump(payload, f, indent=2)


def find_image(cam_id, file_tag):
    """Busca en la carpeta de la cámara una imagen cuyo nombre contenga el tag
    FILE del CSV (p.ej. '20260526_0930' casa con '..._20260526_093000_...')."""
    folder = os.path.join(DATA_DIR, CAMERAS[cam_id]["folder"])
    if not os.path.isdir(folder) or not file_tag:
        return None
    for f in sorted(os.listdir(folder)):
        if file_tag in f and f.lower().endswith((".jpg", ".jpeg", ".png")):
            return f
    return None


def seed_camera(cam_id, entries):
    write_rods(cam_id, entries)

    # Agrupar por imagen (FILE): la calibración es por imagen
    by_file = {}
    for e in entries:
        by_file.setdefault(e["file"], []).append(e)

    calibrated_any = False
    for file_tag, group in by_file.items():
        if len(group) < 4:
            continue
        filename = find_image(cam_id, file_tag)
        if not filename:
            print(f"[demo] Cam {cam_id}: sin imagen para el tag '{file_tag}', se omite")
            continue

        img = cv2.imread(os.path.join(DATA_DIR, CAMERAS[cam_id]["folder"], filename))
        if img is None:
            continue
        h, w = img.shape[:2]

        points = [{
            "pixel": e["pixel"], "utm": e["utm"], "label": e["label"], "type": "calib",
            "rel": [e["pixel"][0] / w * 100, e["pixel"][1] / h * 100],
        } for e in group]

        ann_path = _annotations_path(cam_id, filename)
        os.makedirs(os.path.dirname(ann_path), exist_ok=True)
        with open(ann_path, "w") as f:
            json.dump({"points": points, "roi": None}, f, indent=2)

        # Perfil inicial con la referencia antes de calcular
        profile_path = os.path.join(CALIBRATION_DIR, f"cam_{cam_id}_profile.json")
        if not os.path.exists(profile_path):
            with open(profile_path, "w") as f:
                json.dump({"cam_id": cam_id, "gcps": [], "reference_image": filename}, f, indent=2)

        try:
            res = calculate_homography(cam_id, HomographyRequest(
                image_name=filename, threshold_px=THRESHOLD_PX))
            flagged = sum(1 for r in res["residuals"] if r["above_threshold"])
            print(f"[demo] Cam {cam_id} · {filename}: RMSE {res['rmse_px']:.2f}px / "
                  f"{res['rmse_m']:.3f}m ({len(points)} varillas, {flagged} sobre umbral)")
            calibrated_any = True
        except Exception as e:
            detail = getattr(e, "detail", str(e))
            print(f"[demo] Cam {cam_id} · {filename}: homografía fallida — {detail}")

    if not calibrated_any:
        print(f"[demo] Cam {cam_id}: sin calibración (puntos insuficientes o sin imagen)")


def _order_along_coast(coords):
    """Ordena los puntos según su proyección sobre el eje dominante (PCA):
    funciona con cualquier orientación de la playa, no solo norte-sur."""
    import numpy as np
    arr = np.array(coords, dtype=float)
    centered = arr - arr.mean(axis=0)
    _, _, vt = np.linalg.svd(centered, full_matrices=False)
    t = centered @ vt[0]
    return arr[np.argsort(-t)].tolist()


def _moving_average(pts, window=3):
    """Media móvil centrada para eliminar el ruido métrico de las estacas."""
    import numpy as np
    arr = np.array(pts, dtype=float)
    if len(arr) < window:
        return pts
    pad = window // 2
    out = arr.copy()
    for ax in range(arr.shape[1]):
        padded = np.pad(arr[:, ax], (pad, pad), mode="edge")
        out[:, ax] = np.convolve(padded, np.ones(window) / window, mode="valid")
    return out.tolist()


def _chaikin(pts, iterations=3):
    """Suavizado de esquinas de Chaikin (conserva los extremos)."""
    for _ in range(iterations):
        out = [pts[0]]
        for a, b in zip(pts[:-1], pts[1:]):
            out.append([0.75 * a[0] + 0.25 * b[0], 0.75 * a[1] + 0.25 * b[1]])
            out.append([0.25 * a[0] + 0.75 * b[0], 0.25 * a[1] + 0.75 * b[1]])
        out.append(pts[-1])
        pts = out
    return pts


def _capture_dates(cam_id):
    """Fechas de captura (ISO) de las imágenes de muestra de la cámara."""
    import re
    folder = os.path.join(DATA_DIR, CAMERAS[cam_id]["folder"])
    dates = []
    if os.path.isdir(folder):
        for f in sorted(os.listdir(folder)):
            m = re.match(r"^\d+_(\d{8})_(\d{6})_", f)
            if m:
                dt = datetime.datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M%S")
                dates.append((dt.isoformat(timespec="seconds"), f))
    return dates


# Ajuste fino por cámara de la línea de demo hacia el este (metros): en algunas
# campañas las estacas quedan algo tierra adentro respecto a la orilla visible.
EAST_OFFSET_M = {2: 15.0, 3: 35.0}


def build_demo_coastline(by_cam):
    """Genera líneas de costa de demostración trazadas sobre las varillas
    topografiadas (siguen la orilla), suavizadas, más un histórico temporal por
    cámara (una línea por fecha de captura, con una variación suave en metros)
    para poder demostrar la evolución temporal sin ejecutar la segmentación."""
    import math
    now = datetime.datetime.now().isoformat(timespec="seconds")
    all_features = []
    for cam_id in sorted(by_cam):
        # Solo estacas de orilla (V/A): los puntos FIJO son marcas de control en
        # zonas estables (paseo, edificios) y no describen la línea de costa.
        # Además, una sola campaña (FILE): mezclar varias del mismo tramo zigzaguea.
        entries = [e for e in by_cam[cam_id] if e.get("color") in ("V", "A")] or by_cam[cam_id]
        groups = {}
        for e in entries:
            groups.setdefault(e["file"], []).append(e)
        best = max(groups.values(), key=len)
        if len(best) < 3:
            continue
        coords = _order_along_coast([e["utm"] for e in best])
        east = EAST_OFFSET_M.get(cam_id, 0.0)
        if east:
            coords = [[x + east, y] for x, y in coords]
        base = _chaikin(_moving_average(coords))

        def make_feature(ts, offset_m=0.0, image=None):
            n = len(base)
            # desplazamiento este-oeste con forma de arco (máximo en el centro)
            line = [[x + offset_m * math.sin(math.pi * i / max(n - 1, 1)), y]
                    for i, (x, y) in enumerate(base)]
            props = {
                "ID_Camara": cam_id,
                "Timestamp": ts,
                "EPSG": 25830,
                "Fuente": "varillas topográficas (demo)",
            }
            if image:
                props["Imagen"] = image
            return {"type": "Feature", "properties": props,
                    "geometry": {"type": "LineString", "coordinates": line}}

        # Última línea (para el mapa combinado)
        feature = make_feature(now)
        all_features.append(feature)
        with open(os.path.join(DATA_DIR, f"latest_result_cam{cam_id}.json"), "w") as f:
            json.dump({"type": "FeatureCollection", "features": [feature]}, f)

        # Histórico: una línea por captura de muestra con variación suave (±6 m)
        history = [make_feature(ts, offset_m=6.0 * math.sin(idx * 0.9), image=img)
                   for idx, (ts, img) in enumerate(_capture_dates(cam_id))]
        with open(os.path.join(DATA_DIR, f"coastline_history_cam{cam_id}.json"), "w") as f:
            json.dump({"type": "FeatureCollection", "features": history}, f)

    with open(os.path.join(DATA_DIR, "latest_result.json"), "w") as f:
        json.dump({"type": "FeatureCollection", "features": all_features}, f)
    print(f"[demo] Línea de costa de demostración: {len(all_features)} tramos + histórico temporal")


def main():
    if not os.path.exists(GCP_CSV):
        print(f"[ERROR] No se encontró {GCP_CSV}")
        sys.exit(1)

    print(f"[demo] Workspace: {DATA_DIR}")
    reset_workspace()
    copy_sample_images()
    copy_calibration_support()

    by_cam = parse_gcp_csv()
    print(f"[demo] GCP.csv: varillas para {len(by_cam)} cámaras")
    for cam_id in sorted(by_cam):
        seed_camera(cam_id, by_cam[cam_id])
    build_demo_coastline(by_cam)

    print("[demo] Siembra completada")


if __name__ == "__main__":
    main()
