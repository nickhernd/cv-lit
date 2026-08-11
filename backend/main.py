from fastapi import FastAPI, HTTPException, UploadFile, File, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import os
import io
import csv
import re
import json
import glob
import numpy as np
import cv2
import pandas as pd
from typing import List, Optional
import shutil
import sys
import datetime

from config import CAMERAS, DATA_DIR, CALIBRATION_DIR, _safe_filename
from batch_alignment import router as batch_router
from auto_mode import router as auto_router


def _safe_print(*args, **kwargs):
    """print() normal, pero tolerante a sys.stdout is None — en el build de
    escritorio empaquetado con PyInstaller (console=False, ver
    desktop_launcher.spec) no hay consola adjunta y sys.stdout puede ser
    None; un print() de arranque normal ahí lanzaría AttributeError y
    tumbaría la app antes de mostrar la ventana."""
    if sys.stdout is None:
        return
    try:
        print(*args, **kwargs)
    except OSError:
        pass

# Configurar path para modulos de procesamiento. Congelada (PyInstaller,
# onedir), "la ubicación de este archivo" no es una ruta real en disco —
# BASE_DIR pasa a ser la carpeta de instalación (sys._MEIPASS), que es donde
# viven el frontend construido y el checkpoint SAM opcional (ver más abajo).
FROZEN = getattr(sys, "frozen", False)
if FROZEN:
    BASE_DIR = sys._MEIPASS
else:
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROCES_DIR = os.path.join(BASE_DIR, "proces_images")
if PROCES_DIR not in sys.path:
    sys.path.append(PROCES_DIR)

# DEBUG (INIT): bloque de arranque — intenta importar los módulos reales de procesamiento
# (proces_images/). Si algo falla (p.ej. dependencias de SAM no instaladas), define
# versiones "stub" mínimas para que el servidor arranque igualmente en modo degradado.
try:
    from segmentation_sam import SAMSegmenter
    from extract_coastline import extract_coastline_from_mask, draw_coastline
    from test_mes3_pipeline import color_fallback_segmentation
    from cam_thresholds import get_threshold, validate_mask
    from georef_export import confidence_index, RMSE_GOOD_M
except ImportError:
    _safe_print("[WARNING] No se pudieron importar los modulos de procesamiento.")
    def get_threshold(cam_id): return {"confidence_min": 0.45, "mask_area_min_ratio": 0.05, "mask_area_max_ratio": 0.70}
    def validate_mask(mask, cam_id, shape): return True, ""
    def confidence_index(mask, rmse_m, coastline_points=None, prob_map=None): return 0.0
    RMSE_GOOD_M = 2.0

# DEBUG (INIT): umbral global de confianza para aceptar/rechazar un análisis de línea de costa.
# Sobreescribible con la variable de entorno CONFIDENCE_THRESHOLD; se usa como fallback,
# el umbral real por cámara viene de get_threshold() (#80/#79 en analyze_roi).
CONFIDENCE_THRESHOLD = float(os.getenv("CONFIDENCE_THRESHOLD", "0.45"))

# DEBUG (INIT): punto de entrada de la app FastAPI. Al importar este módulo (uvicorn
# backend.main:app) se ejecuta TODO el código a nivel de módulo de este archivo,
# de arriba a abajo — este es el verdadero "inicio" del backend.
app = FastAPI(title="CV-Lit API")
# DEBUG (INIT): registra las rutas de batch_alignment.py (prefijo /api/batch) y
# auto_mode.py (prefijo /api/automode) sobre esta app.
app.include_router(batch_router)
app.include_router(auto_router)

# DEBUG (INIT): modo de ejecución global — "real" (pipeline completo con SAM/GCPs) vs
# "demo" (datos simulados, sin cargar modelos pesados). Se lee UNA vez al arrancar
# y condiciona el comportamiento de get_segmenter(), get_dashboard() y calculate_homography().
APP_MODE = os.getenv("APP_MODE", "real").lower()
_safe_print(f"[INFO] Iniciando en MODO: {APP_MODE.upper()}")

# Log persistente (JSONL, una línea por entrada) — antes system_logs vivía
# solo en memoria y se perdía en cada reinicio del backend (`uvicorn --reload`
# lo hace constantemente en desarrollo). Un fichero por workspace (vive en
# DATA_DIR, así que dev/demo/real no se mezclan entre sí).
LOG_FILE = os.path.join(DATA_DIR, "system_logs.jsonl")

def _load_persisted_logs(limit: int = 50):
    if not os.path.exists(LOG_FILE):
        return []
    try:
        with open(LOG_FILE, "r") as f:
            lines = f.readlines()[-limit:]
        return [json.loads(l) for l in lines if l.strip()]
    except (OSError, json.JSONDecodeError):
        return []

# Buffer en memoria para servir GET /api/logs sin releer el fichero en cada
# petición — se rehidrata desde LOG_FILE al arrancar para no perder el
# historial reciente entre reinicios.
system_logs = _load_persisted_logs() or [
    {"time": datetime.datetime.now().strftime("%H:%M:%S"), "msg": "Sistema iniciado correctamente", "type": "info"},
]

# DEBUG: helper de logging usado por casi todos los endpoints para dejar
# trazabilidad de lo que hace el backend en tiempo real (lo consume el frontend
# vía /api/logs). Escribe tanto en memoria (rápido, lo que se sirve) como en
# disco (persiste entre reinicios).
LOG_FILE_MAX_BYTES = 2_000_000  # ~2MB (miles de entradas) antes de rotar
LOG_FILE_KEEP_LINES = 5000

def add_log(msg: str, log_type: str = "info"):
    now = datetime.datetime.now()
    entry = {"time": now.strftime("%H:%M:%S"), "date": now.strftime("%Y-%m-%d"), "msg": msg, "type": log_type}
    system_logs.append(entry)
    if len(system_logs) > 50: system_logs.pop(0)
    try:
        # Rotación simple: sin esto el .jsonl crece para siempre en un
        # servicio de larga duración. Comprobar el tamaño es barato (una
        # llamada al SO), así que se hace en cada escritura sin problema.
        if os.path.exists(LOG_FILE) and os.path.getsize(LOG_FILE) > LOG_FILE_MAX_BYTES:
            with open(LOG_FILE, "r") as f:
                kept = f.readlines()[-LOG_FILE_KEEP_LINES:]
            with open(LOG_FILE, "w") as f:
                f.writelines(kept)
        with open(LOG_FILE, "a") as f:
            f.write(json.dumps(entry) + "\n")
    except OSError:
        pass

# DEBUG (INIT): instancia global del segmentador SAM, con lazy loading (None = aún no cargado).
segmenter = None

# DEBUG (INIT): carga el modelo SAM (pesado, requiere checkpoint .pth) la primera vez que se
# necesita, no al arrancar el servidor. Devuelve None en modo demo, False si falló la
# carga (para no reintentar en cada request), o la instancia ya cargada. Se llama desde
# analyze_roi().
def get_segmenter():
    global segmenter
    if segmenter is not None:
        return segmenter

    if APP_MODE == "demo":
        return None

    CHECKPOINT_SAM = os.path.join(BASE_DIR, "sam_vit_h_4b8939.pth")
    add_log(f"Cargando segmentador SAM desde {os.path.basename(CHECKPOINT_SAM)}", "info")
    try:
        from segmentation_sam import SAMSegmenter
        segmenter = SAMSegmenter(checkpoint_path=CHECKPOINT_SAM)
        add_log("SAM Segmenter cargado con éxito", "success")
    except Exception as e:
        add_log(f"Fallo al inicializar SAM: {str(e)}", "error")
        segmenter = False
    return segmenter

# DEBUG (INIT): habilita CORS abierto ("*") para que el frontend (Vite, otro origen/puerto)
# pueda llamar a esta API sin bloqueos del navegador. allow_credentials=False
# a propósito: esta API no usa cookies/sesión (auth es la cabecera X-API-Key,
# ver más abajo), y combinar origins="*" con credentials=True es una
# configuración CORS insegura (permite peticiones credenciales desde
# cualquier origen).
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Autenticación por API key — OPCIONAL y desactivada por defecto (si
# CVLIT_API_KEY no está definida, la app se comporta exactamente igual que
# antes: sin auth, pensada para desarrollo/demo en local). En cuanto se
# arranque el backend en una red donde no todos los que puedan alcanzar el
# puerto sean de confianza, basta con definir CVLIT_API_KEY y exigir la
# cabecera `X-API-Key` en cada petición (el proxy/frontend que se despliegue
# delante es quien debe inyectarla).
CVLIT_API_KEY = os.environ.get("CVLIT_API_KEY")

@app.middleware("http")
async def require_api_key(request: Request, call_next):
    if CVLIT_API_KEY and request.url.path.startswith("/api/"):
        if request.headers.get("X-API-Key") != CVLIT_API_KEY:
            return JSONResponse(status_code=401, content={"detail": "API key ausente o inválida (cabecera X-API-Key)"})
    return await call_next(request)

class GCP(BaseModel):
    pixel: List[float]
    utm: List[float]
    label: str
    type: str = "calib"
    rel: Optional[List[float]] = None

class CalibrationProfile(BaseModel):
    cam_id: int
    gcps: List[GCP]
    reference_image: Optional[str] = None

class HomographyRequest(BaseModel):
    """Parámetros del cálculo de homografía por imagen."""
    image_name: Optional[str] = None      # si falta, se usa la referencia del perfil
    # Umbral de error de reproyección (px) para marcar una varilla individual
    # como "sobre umbral" en la tabla de Validación — es una AYUDA para
    # detectar de un vistazo qué varilla concreta podría estar mal marcada
    # (un misclick, o una varilla-catálogo equivocada), no el criterio real
    # de aceptación de la calibración (eso es rmse_m frente a RMSE_GOOD_M, ver
    # calculate_homography). Con fotos de ~4-5k px de ancho y sin corrección
    # de distorsión de lente, exigir <1px por varilla marcada a mano es
    # prácticamente imposible de cumplir aunque la calibración sea correcta.
    threshold_px: float = 5.0
    excluded: List[int] = []              # índices de varillas a excluir del cálculo

# Las imágenes de cámara llevan el timestamp de captura en el nombre:
# <epoch>_<YYYYMMDD>_<HHMMSS>_<serial>.jpg
FILENAME_TS_RE = re.compile(r"^(\d+)_(\d{8})_(\d{6})_")

def _parse_capture_ts(filename: str) -> Optional[str]:
    m = FILENAME_TS_RE.match(filename)
    if not m:
        return None
    try:
        dt = datetime.datetime.strptime(m.group(2) + m.group(3), "%Y%m%d%H%M%S")
        return dt.isoformat(timespec="seconds")
    except ValueError:
        return None

def _annotations_path(cam_id: int, filename: str) -> str:
    base = _safe_filename(filename).rsplit(".", 1)[0] + ".json"
    return os.path.join(DATA_DIR, f"CAM_{cam_id}", "json", base)

# Resuelve qué fichero de imagen usar para marcar/analizar una captura: la
# versión alineada (calculada por el módulo de Alineación, batch_alignment.py,
# y confirmada en /commit) si existe, o la captura original si no se ha
# alineado nunca. Se usa en TODOS los sitios que leen la imagen para marcación
# u homografía (get_camera_image, calculate_homography, analyze_roi) para que
# la Marcación (dónde se hace click) y el Análisis (qué imagen se segmenta)
# operen siempre sobre EXACTAMENTE la misma rejilla de píxeles.
def _resolve_camera_image_path(cam_id: int, filename: str) -> str:
    folder = os.path.join(DATA_DIR, CAMERAS[cam_id]["folder"])
    aligned_path = os.path.join(folder, "aligned", filename)
    if os.path.exists(aligned_path):
        return aligned_path
    return os.path.join(folder, filename)

def _alignment_sidecar_path(cam_id: int, filename: str) -> str:
    return os.path.join(DATA_DIR, CAMERAS[cam_id]["folder"], "aligned", f"{filename}.align.json")

def _load_alignment_info(cam_id: int, filename: str) -> Optional[dict]:
    """Info de alineación de esta imagen (H respecto a su captura original,
    inliers, etc.), o None si nunca se alineó (se usa tal cual se capturó)."""
    path = _alignment_sidecar_path(cam_id, filename)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None

IMAGE_EXTS = (".jpg", ".jpeg", ".png")

def _latest_image_filename(cam_id: int) -> Optional[str]:
    """Imagen más reciente disponible de una cámara. Sustituye al antiguo
    fallback a CAMERAS[cam_id]['file'] (un nombre de archivo fijo en
    config.py): ese nombre había que mantenerlo a mano y en cuanto las
    imágenes reales de la carpeta cambiaban (se resembraba el workspace, se
    subían fotos nuevas...) dejaba de existir y el endpoint fallaba con 404
    aunque la cámara sí tuviera imágenes. Esto se recalcula del disco real."""
    folder = os.path.join(DATA_DIR, CAMERAS[cam_id]["folder"])
    if not os.path.isdir(folder):
        return None
    candidates = [f for f in os.listdir(folder) if f.lower().endswith(IMAGE_EXTS)]
    if not candidates:
        return None
    candidates.sort(key=lambda f: os.path.getmtime(os.path.join(folder, f)), reverse=True)
    return candidates[0]

def _smooth_polyline(pts: np.ndarray, window: int = 9) -> np.ndarray:
    """Suaviza una polilínea con media móvil centrada (conserva la longitud).
    La línea de costa extraída píxel a píxel sale dentada; esto la deja continua."""
    if len(pts) < window or window < 3:
        return pts
    kernel = np.ones(window) / window
    smoothed = pts.astype(np.float64).copy()
    pad = window // 2
    for axis in range(pts.shape[1]):
        padded = np.pad(pts[:, axis].astype(np.float64), (pad, pad), mode="edge")
        smoothed[:, axis] = np.convolve(padded, kernel, mode="valid")
    return smoothed

def _history_path(cam_id: int) -> str:
    return os.path.join(DATA_DIR, f"coastline_history_cam{cam_id}.json")

def _append_history(cam_id: int, feature: dict, max_entries: int = 500):
    """Acumula cada línea de costa aceptada en el histórico de la cámara,
    ordenado por timestamp de captura (para la visualización temporal)."""
    path = _history_path(cam_id)
    history = {"type": "FeatureCollection", "features": []}
    if os.path.exists(path):
        try:
            with open(path, "r") as f:
                history = json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    ts = feature["properties"].get("Timestamp")
    # Re-analizar la misma captura sustituye su entrada en vez de duplicarla
    history["features"] = [f for f in history.get("features", [])
                           if f.get("properties", {}).get("Timestamp") != ts]
    history["features"].append(feature)
    history["features"].sort(key=lambda f: f.get("properties", {}).get("Timestamp", ""))
    history["features"] = history["features"][-max_entries:]
    with open(path, "w") as f:
        json.dump(history, f)

# Umbrales para la alerta de degradación de RMSE (#robustez): una calibración
# puede salir con buen RMSE en sus propios puntos y aun así ser peor que la
# anterior — sin guardar un histórico no hay forma de saber si una cámara se
# está "desafinando" con el tiempo hasta que ya da problemas en analyze_roi.
RMSE_DEGRADATION_ABS_M = 0.15   # empeora al menos 15 cm frente a la anterior...
RMSE_DEGRADATION_REL = 0.30    # ...o un 30% relativo, lo que sea mayor umbral

def _rmse_history_path(cam_id: int) -> str:
    return os.path.join(CALIBRATION_DIR, f"cam_{cam_id}_rmse_log.json")

def _check_rmse_trend(cam_id: int, rmse_m: float, max_entries: int = 20):
    """Compara el RMSE de esta calibración con la anterior de la MISMA cámara
    y deja un aviso en el log si ha empeorado significativamente. Acumula un
    histórico corto (no el detalle de residuos, solo fecha+valor) para poder
    comparar en la siguiente calibración."""
    path = _rmse_history_path(cam_id)
    entries = []
    if os.path.exists(path):
        try:
            with open(path, "r") as f:
                entries = json.load(f)
        except (json.JSONDecodeError, OSError):
            entries = []

    if entries:
        prev_rmse = entries[-1]["rmse_m"]
        delta = rmse_m - prev_rmse
        if delta > max(RMSE_DEGRADATION_ABS_M, prev_rmse * RMSE_DEGRADATION_REL):
            add_log(
                f"Cam {cam_id}: el RMSE ha empeorado respecto a la calibración anterior "
                f"({prev_rmse:.3f} m → {rmse_m:.3f} m) — revisar varillas/GCPs",
                "warning",
            )

    entries.append({"date": datetime.datetime.now().isoformat(timespec="seconds"), "rmse_m": round(rmse_m, 4)})
    with open(path, "w") as f:
        json.dump(entries[-max_entries:], f, indent=2)

# DEBUG: expone el buffer system_logs para que el frontend muestre el log de actividad en vivo.
@app.get("/api/logs")
def get_logs():
    return system_logs

# Serie temporal real del área seca para el gráfico "Tendencia Histórica" del
# Dashboard: agrega Area_Seca_m2 de coastline_history_cam{id}.json (el histórico
# que _append_history() va acumulando en cada analyze-roi) de TODAS las cámaras,
# promediando por día natural. Si un día tiene varias capturas (de una o varias
# cámaras) se muestra la media del día, no cada captura suelta.
@app.get("/api/historical-data")
def get_historical_data(cam_id: Optional[int] = None):
    by_date = {}
    if cam_id is not None:
        paths = [os.path.join(DATA_DIR, f"coastline_history_cam{cam_id}.json")]
    else:
        paths = glob.glob(os.path.join(DATA_DIR, "coastline_history_cam*.json"))
    for path in paths:
        try:
            with open(path, "r") as f:
                history = json.load(f)
        except (json.JSONDecodeError, OSError):
            continue
        for feature in history.get("features", []):
            props = feature.get("properties", {})
            ts = props.get("Timestamp")
            area = props.get("Area_Seca_m2")
            if not ts or area is None:
                continue
            date = str(ts)[:10]  # YYYY-MM-DD
            by_date.setdefault(date, []).append(area)
    return [
        {"date": date, "area": round(sum(areas) / len(areas), 2)}
        for date, areas in sorted(by_date.items())
    ]

# Informe completo: una fila por análisis aceptado, con cámara, imagen, área
# seca y confianza — a diferencia de /api/historical-data (que solo da la
# media diaria global para el gráfico), esto es el detalle exportable para
# analizar fuera de la app. format=csv devuelve un fichero descargable.
@app.get("/api/report")
def get_report(format: str = "json"):
    rows = []
    for cam_idx, info in sorted(CAMERAS.items()):
        path = _history_path(cam_idx)
        if not os.path.exists(path):
            continue
        try:
            with open(path, "r") as f:
                history = json.load(f)
        except (json.JSONDecodeError, OSError):
            continue
        for feature in history.get("features", []):
            p = feature.get("properties", {})
            rows.append({
                "camara_idx": cam_idx,
                "camara_nombre": info["name"],
                "timestamp": p.get("Timestamp"),
                "imagen": p.get("Imagen"),
                "area_seca_m2": p.get("Area_Seca_m2"),
                "confianza_ia": p.get("Confianza_IA"),
                "epsg": p.get("EPSG"),
            })
    rows.sort(key=lambda r: (r["timestamp"] or "", r["camara_idx"]))

    if format == "csv":
        buf = io.StringIO()
        fieldnames = ["camara_idx", "camara_nombre", "timestamp", "imagen", "area_seca_m2", "confianza_ia", "epsg"]
        writer = csv.DictWriter(buf, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
        return Response(
            content=buf.getvalue(),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=cv-lit_informe_completo.csv"},
        )
    return rows

# DEBUG: guarda qué imagen se usa como referencia/base para alinear el resto de
# capturas de una cámara. Escribe en calibration/cam_{id}_profile.json.
@app.post("/api/cameras/{cam_id}/set-reference")
def set_reference_image(cam_id: int, filename: str):
    if cam_id not in CAMERAS:
        raise HTTPException(status_code=404, detail="Cámara no encontrada")
    filename = _safe_filename(filename)
    profile_path = os.path.join(CALIBRATION_DIR, f"cam_{cam_id}_profile.json")
    if os.path.exists(profile_path):
        with open(profile_path, "r") as f:
            data = json.load(f)
    else:
        data = {"cam_id": cam_id, "gcps": []}
    
    data["reference_image"] = filename
    with open(profile_path, "w") as f:
        json.dump(data, f, indent=2)
    
    add_log(f"Imagen {filename} establecida como referencia para Cam {cam_id}", "info")
    return {"status": "success", "reference_image": filename}

# DEBUG: lee las anotaciones manuales (puntos/ROI) de una imagen desde
# data/CAM_{id}/json/{filename}.json. Usado por el editor de anotaciones del frontend.
@app.get("/api/cameras/{cam_id}/images/{filename}/annotations")
def get_image_annotations(cam_id: int, filename: str):
    if cam_id not in CAMERAS:
        raise HTTPException(status_code=404, detail="Cámara no encontrada")
    json_path = _annotations_path(cam_id, filename)
    if os.path.exists(json_path):
        with open(json_path, "r") as f:
            return json.load(f)
    return {"points": [], "roi": None}

# DEBUG: contraparte de escritura de get_image_annotations — persiste las
# anotaciones editadas en el frontend a disco. Hace merge sobre el JSON existente
# para no borrar claves que el frontend no envía (p.ej. "calibration").
@app.post("/api/cameras/{cam_id}/images/{filename}/annotations")
def save_image_annotations(cam_id: int, filename: str, data: dict):
    if cam_id not in CAMERAS:
        raise HTTPException(status_code=404, detail="Cámara no encontrada")
    target_dir = os.path.join(DATA_DIR, f"CAM_{cam_id}", "json")
    os.makedirs(target_dir, exist_ok=True)
    json_path = _annotations_path(cam_id, filename)
    existing = {}
    if os.path.exists(json_path):
        try:
            with open(json_path, "r") as f:
                existing = json.load(f)
        except (json.JSONDecodeError, OSError):
            existing = {}
    existing.update(data)
    with open(json_path, "w") as f:
        json.dump(existing, f, indent=2)
    return {"status": "success"}

# DEBUG: resumen para la pantalla principal (cuántas cámaras calibradas, nº de
# imágenes por cámara, etc). En modo demo devuelve datos fijos simulados; en modo
# real recorre CALIBRATION_DIR/DATA_DIR comprobando qué perfiles existen.
@app.get("/api/dashboard")
def get_dashboard():
    if APP_MODE == "demo":
        return {
            "cameras_calibrated": 6,
            "total_cameras": 6,
            "images_processed": 12450,
            "avg_dry_area": "25 120",
            "cameras": [
                {"id": f"C{i}", "idx": i, "name": CAMERAS[i]["name"], "status": "Calibrada", "images": 2000}
                for i in range(1, 7)
            ]
        }

    calibrated_count = 0
    cameras_status = []
    for cam_idx, info in CAMERAS.items():
        profile_path = os.path.join(CALIBRATION_DIR, f"cam_{cam_idx}_profile.json")
        # Calibrada = tiene homografía calculada, no basta con que exista el perfil
        # (el perfil se crea ya al fijar la imagen de referencia).
        is_calibrated = False
        if os.path.exists(profile_path):
            try:
                with open(profile_path, "r") as f:
                    is_calibrated = bool(json.load(f).get("H"))
            except (json.JSONDecodeError, OSError):
                is_calibrated = False
        if is_calibrated: calibrated_count += 1
        
        cam_folder = os.path.join(DATA_DIR, info["folder"])
        images_count = 0
        if os.path.exists(cam_folder):
            images_count = len([f for f in os.listdir(cam_folder) if f.endswith(('.jpg', '.png'))])

        cameras_status.append({
            "id": f"C{cam_idx}", "idx": cam_idx, "name": info["name"],
            "status": "Calibrada" if is_calibrated else "Sin calibrar",
            "images": images_count
        })

    return {
        "cameras_calibrated": calibrated_count,
        "total_cameras": len(CAMERAS),
        "images_processed": 506,
        "avg_dry_area": "23 480",
        "cameras": cameras_status
    }

HARDWARE_PATH = os.path.join(CALIBRATION_DIR, "camera_hardware.json")

def _load_hardware():
    if os.path.exists(HARDWARE_PATH):
        with open(HARDWARE_PATH, "r") as f: return json.load(f)
    return {}

def _save_hardware(data):
    with open(HARDWARE_PATH, "w") as f: json.dump(data, f, indent=2)

def _load_roi_config():
    roi_path = os.path.join(CALIBRATION_DIR, "roi_config.json")
    if os.path.exists(roi_path):
        with open(roi_path, "r") as f: return json.load(f)
    return {}

def _save_roi_config(data):
    roi_path = os.path.join(CALIBRATION_DIR, "roi_config.json")
    with open(roi_path, "w") as f: json.dump(data, f, indent=2)

class CameraHardwareUpdate(BaseModel):
    utm_x: Optional[float] = None
    utm_y: Optional[float] = None
    height_m: Optional[float] = None
    azimuth_deg: Optional[float] = None

class ROIUpdate(BaseModel):
    x_min: int
    y_min: int
    x_max: int
    y_max: int
    description: Optional[str] = ""

@app.get("/api/cameras")
def list_cameras():
    """Resumen de hardware + estado de calibración por cámara (pantalla 'Sistema > Cámaras')."""
    roi_config = _load_roi_config()
    hardware = _load_hardware()

    result = []
    for cam_idx, info in CAMERAS.items():
        profile_path = os.path.join(CALIBRATION_DIR, f"cam_{cam_idx}_profile.json")
        profile = {}
        if os.path.exists(profile_path):
            with open(profile_path, "r") as f: profile = json.load(f)

        cam_folder = os.path.join(DATA_DIR, info["folder"])
        images_count = 0
        last_modified = None
        if os.path.exists(cam_folder):
            files = [f for f in os.listdir(cam_folder) if f.lower().endswith(('.jpg', '.jpeg', '.png'))]
            images_count = len(files)
            if files:
                last_modified = max(os.path.getmtime(os.path.join(cam_folder, f)) for f in files)

        cam_hardware = hardware.get(str(cam_idx), {})
        result.append({
            "idx": cam_idx,
            "id": f"C{cam_idx}",
            "name": info["name"],
            "serial": info["serial"],
            "calibrated": bool(profile.get("H")),
            "rmse_m": profile.get("rmse_m"),
            "rmse_px": profile.get("rmse_px"),
            "mae_m": profile.get("mae_m"),
            "mae_px": profile.get("mae_px"),
            "calibrated_image": profile.get("calibrated_image"),
            "gcps_count": profile.get("gcps_count"),
            "inliers_count": profile.get("inliers_count"),
            "last_calibration_date": profile.get("date"),
            "images_count": images_count,
            "last_image_ts": last_modified,
            "roi": roi_config.get(f"CAM_{cam_idx}"),
            "utm_x": cam_hardware.get("utm_x"),
            "utm_y": cam_hardware.get("utm_y"),
            "height_m": cam_hardware.get("height_m"),
            "azimuth_deg": cam_hardware.get("azimuth_deg"),
        })
    return result

@app.put("/api/cameras/{cam_id}/hardware")
def update_camera_hardware(cam_id: int, payload: CameraHardwareUpdate):
    if cam_id not in CAMERAS: raise HTTPException(status_code=404, detail="Cámara no encontrada")
    data = _load_hardware()
    data[str(cam_id)] = payload.dict(exclude_none=True)
    _save_hardware(data)
    add_log(f"Actualizada información de hardware de Cam {cam_id}", "info")
    return data[str(cam_id)]

@app.put("/api/cameras/{cam_id}/roi")
def update_camera_roi(cam_id: int, payload: ROIUpdate):
    if cam_id not in CAMERAS: raise HTTPException(status_code=404, detail="Cámara no encontrada")
    roi = _load_roi_config()
    roi[f"CAM_{cam_id}"] = payload.dict()
    _save_roi_config(roi)
    add_log(f"Actualizada ROI de Cam {cam_id}", "info")
    return roi[f"CAM_{cam_id}"]

# DEBUG: sirve el archivo de imagen de una cámara (la indicada en `file`, o la
# imagen por defecto de config.CAMERAS si no se especifica).
@app.get("/api/cameras/{cam_id}/image")
def get_camera_image(cam_id: int, file: Optional[str] = None):
    if cam_id not in CAMERAS: raise HTTPException(status_code=404, detail="Camera not found")
    info = CAMERAS[cam_id]
    target = _safe_filename(file) if file else _latest_image_filename(cam_id)
    if not target: raise HTTPException(status_code=404, detail="Esta cámara no tiene imágenes todavía")
    img_path = _resolve_camera_image_path(cam_id, target)
    if not os.path.exists(img_path): raise HTTPException(status_code=404, detail="Image not found")
    return FileResponse(img_path)

# DEBUG: info de alineación de una imagen concreta (H respecto a su captura
# original, inliers, referencia usada). Lo consume el frontend antes de
# guardar puntos importados de un CSV de campo, para saber si hay que
# transformar el píxel "crudo" del CSV al espacio de la imagen alineada.
@app.get("/api/cameras/{cam_id}/images/{filename}/alignment")
def get_image_alignment(cam_id: int, filename: str):
    if cam_id not in CAMERAS: raise HTTPException(status_code=404, detail="Cámara no encontrada")
    info = _load_alignment_info(cam_id, _safe_filename(filename))
    return info or {"aligned": False}

# DEBUG: devuelve el perfil de calibración (GCPs, homografía, estado) de una
# cámara desde calibration/cam_{id}_profile.json, o "uncalibrated" si no existe.
@app.get("/api/cameras/{cam_id}/profile")
def get_camera_profile(cam_id: int):
    profile_path = os.path.join(CALIBRATION_DIR, f"cam_{cam_id}_profile.json")
    if not os.path.exists(profile_path):
        return {"cam_id": cam_id, "gcps": [], "status": "uncalibrated"}
    with open(profile_path, "r") as f:
        return json.load(f)

# Calcula la homografía píxel->UTM DE UNA IMAGEN a partir de las varillas marcadas
# en sus anotaciones (la calibración es por imagen, no por cámara). Devuelve el
# residuo de reproyección por varilla (px y m) para que la UI pueda marcar las que
# superan el umbral, y admite excluir índices concretos y recalcular sin ellos.
# El perfil de cámara guarda la ÚLTIMA calibración válida (la que consume analyze-roi).
@app.post("/api/cameras/{cam_id}/calculate-homography")
def calculate_homography(cam_id: int, payload: Optional[HomographyRequest] = None):
    if cam_id not in CAMERAS:
        raise HTTPException(status_code=404, detail="Cámara no encontrada")
    payload = payload or HomographyRequest()
    add_log(f"Iniciando cálculo homografía para Cam {cam_id}", "info")

    profile_path = os.path.join(CALIBRATION_DIR, f"cam_{cam_id}_profile.json")
    profile = {"cam_id": cam_id, "gcps": []}
    if os.path.exists(profile_path):
        with open(profile_path, "r") as f:
            profile = json.load(f)

    image_name = payload.image_name or profile.get("reference_image")
    if not image_name:
        raise HTTPException(status_code=400, detail="No hay imagen seleccionada ni referencia definida")
    image_name = _safe_filename(image_name)

    # DEBUG (ORIGEN DATOS): los puntos de calibración salen del JSON de anotaciones
    # de ESTA imagen (proces_images/data/CAM_{id}/json/{imagen}.json). Cada punto trae:
    #   - "pixel": [x, y] donde el usuario hizo CLIC en la foto (paso 4 Marcación)
    #   - "utm":   [X, Y] coordenada real de la varilla, del catálogo importado de
    #              GCP.csv (cam_{id}_rods.json) o tecleada a mano en el editor.
    ann_path = _annotations_path(cam_id, image_name)
    ann_data = {"points": [], "roi": None}
    if os.path.exists(ann_path):
        with open(ann_path, "r") as f:
            ann_data = json.load(f)
    points = ann_data.get("points") or []
    if not points:
        # Compatibilidad con perfiles antiguos que guardaban los GCPs a nivel de cámara
        points = [g for g in profile.get("gcps", []) if g.get("type") == "calib"]

    # Varillas "pendientes de confirmar": llegaron de un CSV importado con un píxel
    # aproximado (reproyectado, si la imagen está alineada) y todavía no las ha
    # revisado el usuario con la lupa del paso 5. No entran en el ajuste de la
    # homografía hasta que se confirman — así un punto mal ubicado no puede colar
    # error silenciosamente en la calibración.
    pending = {i for i, p in enumerate(points) if p.get("confirmed") is False}
    user_excluded = set(payload.excluded)
    excluded = user_excluded | pending
    included_idx = [i for i in range(len(points)) if i not in excluded]
    if len(included_idx) < 4:
        faltan_confirmar = len(pending - user_excluded)
        faltan_excluidas = len(user_excluded - pending)
        detail = f"Se necesitan al menos 4 varillas activas y confirmadas (hay {len(included_idx)})"
        motivos = []
        if faltan_confirmar:
            motivos.append(f"{faltan_confirmar} pendiente(s) de confirmar en Marcación")
        if faltan_excluidas:
            motivos.append(f"{faltan_excluidas} excluida(s) manualmente")
        if motivos:
            detail += " — " + ", ".join(motivos)
        raise HTTPException(status_code=400, detail=detail)

    if APP_MODE == "demo":
        residuals = [{
            "idx": i, "label": p.get("label", f"P{i+1}"),
            "error_px": round(float(np.random.uniform(0.2, 1.4)), 3),
            "error_m": round(float(np.random.uniform(0.05, 0.4)), 3),
            "inlier": True, "excluded": i in excluded, "pending": False, "above_threshold": False,
        } for i, p in enumerate(points)]
        add_log(f"Homografía Cam {cam_id} simulada (Demo)", "success")
        return {"status": "success", "image": image_name, "rmse_px": 0.62, "rmse_m": 0.12,
                "mae_px": 0.45, "mae_m": 0.09, "rmse_good_m": RMSE_GOOD_M, "geometry_warning": None,
                "threshold_px": payload.threshold_px, "gcps_used": len(included_idx),
                "excluded": sorted(excluded), "residuals": residuals}

    pts_px = np.array([points[i]["pixel"] for i in included_idx], dtype=np.float32)
    pts_utm = np.array([points[i]["utm"] for i in included_idx], dtype=np.float32)
    # DEBUG (ROTACION+TRASLACION): AQUÍ se calcula la matriz H (3x3) píxel→UTM de
    # la calibración. H contiene, mezcladas en una sola homografía plana, la
    # rotación, la traslación, la escala y la perspectiva que llevan un punto de
    # la foto al plano de la playa en metros (EPSG:25830). RANSAC (umbral 3 m en
    # el dominio UTM) descarta correspondencias atípicas al estimarla.
    H, ransac_mask = cv2.findHomography(pts_px, pts_utm, cv2.RANSAC, 3.0)
    if H is None:
        raise HTTPException(status_code=500, detail="No se pudo estimar la homografía (puntos degenerados o colineales)")
    # DEBUG (ROTACION+TRASLACION): H⁻¹ es la transformación inversa UTM→píxel,
    # necesaria para poder expresar el error de reproyección en píxeles.
    try:
        H_inv = np.linalg.inv(H)
    except np.linalg.LinAlgError:
        raise HTTPException(status_code=500, detail="Homografía singular, revisa las coordenadas de las varillas")

    inlier_by_idx = {}
    if ransac_mask is not None:
        flat = ransac_mask.ravel()
        for pos, i in enumerate(included_idx):
            inlier_by_idx[i] = bool(flat[pos])

    # Aviso de geometría inestable: si RANSAC no encuentra un subconjunto de
    # varillas mutuamente consistente, la H calculada no es de fiar aunque
    # técnicamente se haya podido invertir — es la causa real detrás de los
    # RMSE disparados (decenas de metros) que si no, quedan sin explicar.
    # Motivo típico: una varilla con la UTM o el píxel mal introducidos, o
    # que las varillas marcadas están casi todas alineadas en una única
    # línea/transecto (geométricamente insuficiente para fijar los 8 grados
    # de libertad de una homografía, aunque el cálculo en sí no falle).
    MIN_INLIER_FRACTION = 0.6  # por debajo de esto, la H no se considera fiable
    inlier_count = sum(inlier_by_idx.values())
    inlier_fraction = (inlier_count / len(included_idx)) if included_idx else 1.0
    geometry_warning = None
    if inlier_fraction < MIN_INLIER_FRACTION:
        geometry_warning = (
            f"RANSAC solo encontró {inlier_count} de {len(included_idx)} varillas "
            "mutuamente consistentes — este RMSE probablemente no refleja la calidad "
            "real de la calibración. Revisa si alguna varilla tiene la UTM o el píxel "
            "mal introducidos, y si las varillas marcadas están casi todas en una sola "
            "línea, añade alguna repartida en otra zona/profundidad de la imagen."
        )

    # DEBUG (ERROR POR VARILLA): AQUÍ se calcula el error de reproyección de CADA
    # varilla por separado: E_i = ||x_i - x̂_i|| (distancia euclídea entre lo
    # medido y lo que predice la homografía), en ambos dominios:
    #  - error_m : distancia entre el UTM medido (GCP.csv) y la proyección con H
    #              del píxel donde se marcó la varilla
    #  - error_px: distancia entre el píxel marcado y la retro-proyección con H⁻¹
    #              del UTM medido
    # Estos valores llenan la tabla del paso Cálculo y deciden qué filas
    # se marcan en rojo (error_px > threshold_px). El error POR IMAGEN es el RMSE
    # de estos residuos, que se guarda en el JSON de anotaciones de la imagen.
    residuals = []
    err_px_included, err_m_included = [], []
    for i, p in enumerate(points):
        px = np.array(p["pixel"], dtype=np.float64)
        utm = np.array(p["utm"], dtype=np.float64)
        proj_utm = cv2.perspectiveTransform(px.reshape(1, 1, 2), H).reshape(2)
        back_px = cv2.perspectiveTransform(utm.reshape(1, 1, 2), H_inv).reshape(2)
        err_m = float(np.linalg.norm(proj_utm - utm))
        err_px = float(np.linalg.norm(back_px - px))
        is_excluded_from_fit = i in excluded  # user_excluded ∪ pending
        is_user_excluded = i in user_excluded
        is_pending = i in pending
        if not is_excluded_from_fit:
            err_px_included.append(err_px)
            err_m_included.append(err_m)
        residuals.append({
            "idx": i,
            "label": p.get("label", f"P{i+1}"),
            "error_px": round(err_px, 3),
            "error_m": round(err_m, 4),
            "inlier": inlier_by_idx.get(i, True) if not is_excluded_from_fit else None,
            "excluded": is_user_excluded,
            "pending": is_pending,
            "above_threshold": (not is_excluded_from_fit) and err_px > payload.threshold_px,
        })

    # DEBUG (RMSE/MAE): AQUÍ se calculan las métricas de la calibración de esta
    # imagen, SOLO sobre las varillas activas (las excluidas por el usuario no
    # cuentan). RMSE penaliza más los errores grandes (útil para detectar
    # varillas mal marcadas); MAE es la distancia media sin elevar al
    # cuadrado (issue #71 — ver docs/chapters/cap10_validacion.tex, que da
    # esta misma fórmula: MAE = (1/N) Σ dᵢ). Como err_px/err_m ya son normas
    # euclídeas (siempre ≥ 0), MAE es directamente su media, sin abs().
    # Se persisten en: el JSON de la imagen (calibration.rmse_*/mae_*), el
    # perfil de cámara (cam_{id}_profile.json, que muestra la tabla del paso 1)
    # y la respuesta de este endpoint.
    rmse_px = float(np.sqrt(np.mean(np.square(err_px_included))))
    rmse_m = float(np.sqrt(np.mean(np.square(err_m_included))))
    mae_px = float(np.mean(err_px_included))
    mae_m = float(np.mean(err_m_included))
    now_iso = datetime.datetime.now().isoformat(timespec="seconds")

    calibration = {
        "H": H.tolist(),
        "image": image_name,
        "rmse_px": round(rmse_px, 4),
        "rmse_m": round(rmse_m, 4),
        "mae_px": round(mae_px, 4),
        "mae_m": round(mae_m, 4),
        # Umbral de RMSE en metros que el resto del sistema ya usa para
        # considerar "buena" una calibración (ver georef_export.RMSE_GOOD_M,
        # el mismo factor que pondera confidence_index() en analyze_roi). El
        # frontend lo usa para decidir el estado Óptimo/Revisar del paso de
        # Validación — no el umbral en píxeles por varilla, que es solo una
        # ayuda para detectar varillas mal marcadas, no el criterio real de
        # aceptación (ver comentario junto a threshold_px en HomographyRequest).
        "rmse_good_m": RMSE_GOOD_M,
        "geometry_warning": geometry_warning,
        "threshold_px": payload.threshold_px,
        "gcps_used": len(included_idx),
        "excluded": sorted(excluded),
        "residuals": residuals,
        "date": now_iso,
    }

    # Persistir la calibración junto a las anotaciones de la imagen (por imagen)
    os.makedirs(os.path.dirname(ann_path), exist_ok=True)
    if not ann_data.get("points"):
        ann_data["points"] = points
    ann_data["calibration"] = calibration
    with open(ann_path, "w") as f:
        json.dump(ann_data, f, indent=2)

    # Actualizar el perfil de cámara con la última calibración válida
    inliers_count = sum(1 for r in residuals if r["inlier"])
    profile.update({
        "cam_id": cam_id,
        "H": H.tolist(),
        "rmse_m": round(rmse_m, 4),
        "rmse_px": round(rmse_px, 4),
        "mae_m": round(mae_m, 4),
        "mae_px": round(mae_px, 4),
        "gcps_count": len(included_idx),
        "inliers_count": inliers_count,
        "status": "calibrated",
        "date": now_iso,
        "calibrated_image": image_name,
    })
    with open(profile_path, "w") as f:
        json.dump(profile, f, indent=2)

    _check_rmse_trend(cam_id, rmse_m)

    # analyze_roi carga la homografía desde el .npy — mantenerlo sincronizado
    np.save(os.path.join(CALIBRATION_DIR, f"cam_{cam_id}_H.npy"), H)

    flagged = sum(1 for r in residuals if r["above_threshold"])
    msg = f"Homografía Cam {cam_id} ({image_name}) calculada. RMSE: {rmse_px:.2f}px / {rmse_m:.3f}m"
    if flagged:
        msg += f" — {flagged} varilla(s) sobre umbral de {payload.threshold_px}px"
    if geometry_warning:
        msg += " — ⚠ geometría de varillas inestable, ver detalle en Validación"
    add_log(msg, "success" if not flagged and not geometry_warning else "warning")
    return {"status": "success", **calibration}

# DEBUG: endpoint núcleo del pipeline de análisis. Carga imagen + homografía,
# segmenta arena seca (SAM -> color_fallback -> Otsu, en cascada), valida la
# máscara y la confianza, extrae la línea de costa en píxeles, la proyecta a
# UTM con la homografía y guarda el GeoJSON + preview resultantes en DATA_DIR.
@app.post("/api/cameras/{cam_id}/analyze-roi")
def analyze_roi(cam_id: int, filename: Optional[str] = None):
    if cam_id not in CAMERAS:
        raise HTTPException(status_code=404, detail="Cámara no encontrada")
    add_log(f"Iniciando segmentación y georreferenciación para Cam {cam_id}", "info")

    # 1. Cargar imagen
    info = CAMERAS[cam_id]
    target_file = _safe_filename(filename) if filename else _latest_image_filename(cam_id)
    if not target_file:
        raise HTTPException(status_code=404, detail="Esta cámara no tiene imágenes todavía")
    img_path = _resolve_camera_image_path(cam_id, target_file)
    img = cv2.imread(img_path)
    if img is None: raise HTTPException(status_code=404, detail="Image file not found")
    
    # 2. Cargar Matriz H (.npy generado al calibrar; si no existe, usar la del perfil JSON)
    h_path = os.path.join(CALIBRATION_DIR, f"cam_{cam_id}_H.npy")
    H = None
    if os.path.exists(h_path):
        H = np.load(h_path)
    else:
        profile_path = os.path.join(CALIBRATION_DIR, f"cam_{cam_id}_profile.json")
        if os.path.exists(profile_path):
            with open(profile_path, "r") as f:
                profile_h = json.load(f).get("H")
            if profile_h:
                H = np.array(profile_h, dtype=np.float64)
    if H is None:
        add_log(f"Falta calibración para Cam {cam_id}", "error")
        raise HTTPException(status_code=400, detail="Camera not calibrated")

    # rmse_m de la última calibración: alimenta el factor de "calidad de
    # calibración" de confidence_index() (peso 3 del índice, ver georef_export.py).
    profile_path = os.path.join(CALIBRATION_DIR, f"cam_{cam_id}_profile.json")
    rmse_m = None
    if os.path.exists(profile_path):
        with open(profile_path, "r") as f:
            rmse_m = json.load(f).get("rmse_m")
    if rmse_m is None:
        rmse_m = RMSE_GOOD_M  # sin RMSE registrado: ni penaliza ni premia el índice

    # 3. Segmentación con estrategia de tres niveles (#81):
    #    Nivel 1 → SAM (requiere GPU + checkpoint)
    #    Nivel 2 → color_fallback (HSV heurístico, siempre disponible)
    #    Nivel 3 → Otsu sobre canal V (último recurso si los anteriores fallan)
    h_orig, w_orig = img.shape[:2]
    roi = {"x_min": 0, "y_min": int(h_orig * 0.4), "x_max": w_orig, "y_max": h_orig}
    prob_map = None

    s = get_segmenter()
    if s and s is not False:
        add_log(f"Cam {cam_id}: segmentación con SAM", "info")
        try:
            mask, prob_map = s.segment_dry_sand(img, str(cam_id), return_prob_map=True)
        except Exception as e:
            add_log(f"Cam {cam_id}: SAM falló ({e}), usando color_fallback", "warning")
            mask = None
    else:
        add_log(f"Cam {cam_id}: SAM no disponible, usando color_fallback", "warning")
        mask = None

    if mask is None or (hasattr(mask, 'sum') and mask.sum() == 0):
        mask = color_fallback_segmentation(img, roi)
        add_log(f"Cam {cam_id}: color_fallback aplicado", "info")

    # Fallback Otsu si color_fallback también devuelve máscara vacía
    if mask is None or (hasattr(mask, 'sum') and mask.sum() == 0):
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        _, mask = cv2.threshold(hsv[:, :, 2], 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        mask[:int(h_orig * 0.4), :] = 0  # excluir cielo/horizonte
        add_log(f"Cam {cam_id}: Otsu como fallback de segmentación", "warning")

    # Validar área de la máscara con umbrales por cámara (#80)
    mask_valid, mask_reason = validate_mask(mask, cam_id, img.shape[:2])
    if not mask_valid:
        add_log(f"Cam {cam_id}: máscara inválida — {mask_reason}", "error")
        return {
            "dry_area_m2": 0, "confidence": 0.0,
            "timestamp": str(datetime.datetime.now()),
            "rejected": True, "reject_reason": mask_reason,
        }

    # 4. Calcular confianza real (#79)
    if prob_map is not None:
        conf = float(confidence_index(mask, rmse_m, prob_map=prob_map))
    else:
        # Proxy sin prob_map: normalizar número de puntos de costa detectados
        n_px = int(mask.sum() > 0) and len(extract_coastline_from_mask(mask) or [])
        conf = min(1.0, n_px / 500.0)

    # Auto-rechazo por baja confianza (#79)
    thr = get_threshold(cam_id)
    conf_min = thr["confidence_min"]
    if conf < conf_min:
        add_log(f"Cam {cam_id}: rechazada por baja confianza ({conf:.2f} < {conf_min})", "error")
        return {
            "dry_area_m2": 0, "confidence": round(conf, 4),
            "timestamp": str(datetime.datetime.now()),
            "rejected": True, "reject_reason": f"low_confidence:{conf:.2f}",
        }

    # 5. Extraer línea de costa (píxeles)
    points_px = extract_coastline_from_mask(mask)

    if not points_px:
        add_log(f"No se detectó línea en Cam {cam_id}", "warning")
        return {
            "dry_area_m2": 0, "confidence": round(conf, 4),
            "timestamp": str(datetime.datetime.now()),
            "rejected": False,
        }

    # 6. Proyectar a UTM y suavizar (la extracción píxel a píxel sale dentada)
    # DEBUG (ROTACION+TRASLACION): AQUÍ se APLICA la homografía de calibración —
    # perspectiveTransform rota/traslada/escala cada punto de la línea de costa
    # detectada (en píxeles) al plano UTM en metros. La matriz H viene de
    # calculate_homography() (cam_{id}_H.npy / perfil), que a su vez salió de las
    # varillas marcadas por el usuario + coordenadas del GCP.csv.
    pts_array = np.array(points_px, dtype=np.float32).reshape(-1, 1, 2)
    pts_utm = cv2.perspectiveTransform(pts_array, H).reshape(-1, 2)
    pts_utm = _smooth_polyline(pts_utm)

    # 7. Calcular área seca en m²: proyectar el CONTORNO de la máscara a UTM con
    # la homografía y aplicar la fórmula shoelace — no un factor fijo de m²/píxel,
    # que ignora la perspectiva oblicua (un píxel cerca de la cámara cubre mucho
    # menos terreno real que uno cerca del horizonte, y varía con la resolución
    # de la foto de origen).
    contours, _ = cv2.findContours(mask.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    area_m2 = 0.0
    if contours:
        largest_px = max(contours, key=cv2.contourArea).astype(np.float32)
        largest_utm = cv2.perspectiveTransform(largest_px, H).reshape(-1, 2).astype(np.float64)
        # Recentrar en el origen ANTES del shoelace: las UTM absolutas rondan
        # las 7 cifras (ej. x≈706644) mientras el polígono mide decenas/cientos
        # de metros — hacer x*y con esas magnitudes directamente satura la
        # precisión de punto flotante y el área sale exactamente 0 por
        # cancelación catastrófica, incluso en float64.
        largest_utm -= largest_utm.mean(axis=0)
        x, y = largest_utm[:, 0], largest_utm[:, 1]
        area_m2 = float(abs(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1))) / 2.0)

    # Salvaguarda: una homografía ajustada con pocas varillas (mínimo 4) puede
    # tener buen RMSE EN esos puntos y aun así extrapolar muy mal fuera de su
    # zona de calibración — si la máscara de arena seca se extiende más allá
    # de esa zona, el área proyectada se dispara varios órdenes de magnitud
    # (se ha visto un caso real: 15 millones de m² con solo 5 GCPs). Mejor
    # rechazar con un motivo claro que mostrar una cifra fabricada.
    MAX_PLAUSIBLE_AREA_M2 = 50_000  # ~5 ha: por encima del mayor tramo real observado (~1.9 ha)
    if area_m2 > MAX_PLAUSIBLE_AREA_M2:
        add_log(f"Cam {cam_id}: área calculada no fiable ({area_m2:,.0f} m² — homografía mal condicionada fuera de las varillas de calibración)", "error")
        return {
            "dry_area_m2": 0, "confidence": round(conf, 4),
            "timestamp": str(datetime.datetime.now()),
            "rejected": True, "reject_reason": f"area_no_fiable:{area_m2:.0f}m2 — recalibrar con más varillas",
        }

    # El timestamp de la feature es el de CAPTURA de la imagen (del nombre de
    # archivo), no el de procesado — es lo que da sentido a la línea temporal.
    processed_at = datetime.datetime.now().isoformat()
    timestamp = _parse_capture_ts(target_file) or processed_at

    # 8. Generar GeoJSON con atributos estándar del proyecto (EPSG:25830)
    feature = {
        "type": "Feature",
        "properties": {
            "ID_Camara":    cam_id,
            "Timestamp":    timestamp,
            "Procesado":    processed_at,
            "Imagen":       target_file,
            "Confianza_IA": round(conf, 4),
            "Area_Seca_m2": round(area_m2, 2),
            "EPSG":         25830,
        },
        "geometry": {
            "type": "LineString",
            "coordinates": pts_utm.tolist(),
        },
    }
    fc = {"type": "FeatureCollection", "features": [feature]}

    # Guardar resultado por cámara (#87) + histórico temporal — /api/geojson agrega
    # estos ficheros en caliente para el mapa global, así que no hace falta un
    # "latest_result.json" compartido aparte.
    with open(os.path.join(DATA_DIR, f"latest_result_cam{cam_id}.json"), "w") as f:
        json.dump(fc, f)
    _append_history(cam_id, feature)

    # Guardar imagen con línea dibujada para preview
    viz = draw_coastline(img.copy(), points_px)
    cv2.imwrite(os.path.join(DATA_DIR, f"latest_analysis_cam{cam_id}.jpg"), viz)

    add_log(f"Análisis finalizado Cam {cam_id}. {len(pts_utm)} puntos UTM. Conf={conf:.2f}", "success")
    return {
        "dry_area_m2":  round(area_m2, 2),
        "confidence":   round(conf, 4),
        "timestamp":    timestamp,
        "points_utm":   len(pts_utm),
        "rejected":     False,
    }

# ── Alineación con preview blend 50/50 ────────────────────────────────────────
# DEBUG: alinea una imagen 'target' contra una referencia con SIFT+FLANN+RANSAC y
# devuelve un PNG con un blend 50/50 en blanco y negro para inspección visual rápida.
# SÍ está en uso: lo llama Calibration.vue como vista previa rápida de alineación
# antes de lanzar una Alineación masiva completa. No usa las máscaras de zonas
# estables de alignment_masks.json (a diferencia de batch_alignment.py) porque aquí
# la referencia puede ser una imagen subida ad-hoc, no la de una cámara calibrada.
@app.post("/api/cameras/{cam_id}/align-preview")
async def align_preview(
    cam_id: int,
    target: UploadFile = File(...),
    reference: Optional[UploadFile] = File(None),
):
    """
    Alinea 'target' respecto a la imagen de referencia del perfil (o a 'reference' si se sube).
    Devuelve un PNG con el blend 50/50 en B&W para diagnóstico visual.
    """
    # ── 1. Cargar referencia ──────────────────────────────────────────────────
    if reference is not None:
        ref_data = await reference.read()
        ref_arr  = np.frombuffer(ref_data, np.uint8)
        ref_img  = cv2.imdecode(ref_arr, cv2.IMREAD_COLOR)
    else:
        # Leer desde perfil guardado en disco
        profile_path = os.path.join(CALIBRATION_DIR, f"cam_{cam_id}_profile.json")
        if not os.path.exists(profile_path):
            raise HTTPException(400, "No hay perfil para esta cámara. Establece una referencia primero.")
        with open(profile_path) as f:
            profile = json.load(f)
        ref_filename = profile.get("reference_image")
        if not ref_filename:
            raise HTTPException(400, "No hay imagen de referencia establecida en el perfil.")
        ref_path = os.path.join(DATA_DIR, CAMERAS[cam_id]["folder"], _safe_filename(ref_filename))
        ref_img  = cv2.imread(ref_path)

    if ref_img is None:
        raise HTTPException(500, "No se pudo leer la imagen de referencia.")

    # ── 2. Cargar imagen a alinear ────────────────────────────────────────────
    tgt_data = await target.read()
    tgt_arr  = np.frombuffer(tgt_data, np.uint8)
    tgt_img  = cv2.imdecode(tgt_arr, cv2.IMREAD_COLOR)
    if tgt_img is None:
        raise HTTPException(400, "No se pudo leer la imagen target.")

    # ── 3. Alinear con SIFT+FLANN (más robusto que ORB para vistas costeras) ──
    MIN_INLIERS   = 30
    RANSAC_THRESH = 5.0
    SIFT_FEATURES = 3000
    LOWE_RATIO    = 0.75

    ref_gray = cv2.cvtColor(ref_img, cv2.COLOR_BGR2GRAY)
    tgt_gray = cv2.cvtColor(tgt_img, cv2.COLOR_BGR2GRAY)

    # NOTA: este endpoint no aplica las máscaras de calibration/alignment_masks.json
    # (a diferencia de backend/batch_alignment.py y scripts/debug_*.py, que sí las usan).
    # No parece estar en uso desde la interfaz actual (BatchAlignment.vue sustituyó a
    # este flujo de preview individual); la edición de máscaras desde la UI ya está
    # implementada para el pipeline real en GET/PUT /api/batch/masks/{cam_id}, editable
    # al elegir la imagen base en el paso "Alineación". Si se retoma este endpoint,
    # debería usar _build_mask() de batch_alignment.py igual que el resto.
    sift = cv2.SIFT_create(nfeatures=SIFT_FEATURES)
    ref_kp, ref_des = sift.detectAndCompute(ref_gray, None)
    tgt_kp, tgt_des = sift.detectAndCompute(tgt_gray, None)

    if tgt_des is None or len(tgt_kp) < 10:
        raise HTTPException(422, "La imagen target tiene muy pocas features detectables.")

    flann   = cv2.FlannBasedMatcher({"algorithm": 1, "trees": 5}, {"checks": 50})
    matches = flann.knnMatch(ref_des, tgt_des, k=2)
    good    = [m for m, n in matches if m.distance < LOWE_RATIO * n.distance]

    if len(good) < MIN_INLIERS:
        raise HTTPException(422, f"Pocos matches ({len(good)}). Imágenes demasiado distintas.")

    src = np.float32([ref_kp[m.queryIdx].pt for m in good]).reshape(-1, 1, 2)
    dst = np.float32([tgt_kp[m.trainIdx].pt for m in good]).reshape(-1, 1, 2)

    # DEBUG (ROTACION+TRASLACION): igual que en batch_alignment._try_align() —
    # H imagen→referencia a partir de matches SIFT, y warpPerspective la aplica.
    H, mask = cv2.findHomography(dst, src, cv2.RANSAC, RANSAC_THRESH)
    inliers  = int(mask.ravel().sum()) if mask is not None else 0

    if H is None or inliers < MIN_INLIERS:
        raise HTTPException(422, f"RANSAC fallido ({inliers} inliers). No se puede alinear.")

    h, w    = ref_gray.shape
    aligned = cv2.warpPerspective(tgt_img, H, (w, h))

    add_log(f"Alineación Cam {cam_id}: {inliers} inliers RANSAC", "info")

    # ── 4. Blend 50/50 en escala de grises ───────────────────────────────────
    ref_bw     = cv2.cvtColor(ref_img, cv2.COLOR_BGR2GRAY)
    aligned_bw = cv2.cvtColor(aligned,  cv2.COLOR_BGR2GRAY)
    aligned_bw = cv2.resize(aligned_bw, (w, h))  # garantizar mismo tamaño

    blend = cv2.addWeighted(ref_bw, 0.5, aligned_bw, 0.5, 0)

    # ── 5. Devolver PNG ───────────────────────────────────────────────────────
    import io
    from fastapi.responses import StreamingResponse
    _, buf = cv2.imencode(".png", blend)
    return StreamingResponse(io.BytesIO(buf.tobytes()), media_type="image/png")

# Devuelve el GeoJSON global (TODAS las cámaras combinadas), agregando en caliente
# el último resultado de CADA cámara (latest_result_cam{id}.json) — antes leía un
# único latest_result.json que analyze_roi() sobrescribe en cada llamada, así que
# solo mostraba la cámara analizada más recientemente, nunca las 6 a la vez.
@app.get("/api/geojson")
def get_geojson():
    features = []
    for cam_idx in sorted(CAMERAS.keys()):
        cam_path = os.path.join(DATA_DIR, f"latest_result_cam{cam_idx}.json")
        if os.path.exists(cam_path):
            with open(cam_path, "r") as f:
                fc = json.load(f)
            features.extend(fc.get("features", []))
    return {"type": "FeatureCollection", "features": features}


# Variante de get_geojson() por cámara individual.
@app.get("/api/cameras/{cam_id}/geojson")
def get_camera_geojson(cam_id: int):
    """Devuelve el último GeoJSON generado para esta cámara (#87)."""
    if cam_id not in CAMERAS:
        raise HTTPException(404, "Cámara no encontrada")
    cam_path = os.path.join(DATA_DIR, f"latest_result_cam{cam_id}.json")
    if os.path.exists(cam_path):
        with open(cam_path) as f:
            return json.load(f)
    return {"type": "FeatureCollection", "features": []}

# Histórico de líneas de costa de una cámara, ordenado por timestamp de captura.
# Lo consume el modo "Evolución temporal" del Mapa GeoJSON.
@app.get("/api/cameras/{cam_id}/coastline-history")
def get_coastline_history(cam_id: int):
    if cam_id not in CAMERAS:
        raise HTTPException(404, "Cámara no encontrada")
    path = _history_path(cam_id)
    if os.path.exists(path):
        with open(path, "r") as f:
            return json.load(f)
    return {"type": "FeatureCollection", "features": []}

# DEBUG: sirve la imagen con la línea de costa dibujada (generada por analyze_roi
# vía draw_coastline); si no existe aún, cae a la imagen original de la cámara.
@app.get("/api/cameras/{cam_id}/analysis-result")
def get_analysis_result(cam_id: int):
    path = os.path.join(DATA_DIR, f"latest_analysis_cam{cam_id}.jpg")
    if os.path.exists(path): return FileResponse(path)
    return get_camera_image(cam_id)

# Límite de tamaño por fichero subido (imagen o CSV) — evita que un cliente
# agote el disco con un solo POST; generoso para fotos 4K sin comprimir.
MAX_UPLOAD_BYTES = 25 * 1024 * 1024

# DEBUG: sube uno o varios archivos de imagen a la carpeta de una cámara
# (DATA_DIR/{folder}), creando el directorio si no existe.
@app.post("/api/cameras/{cam_id}/upload-images")
async def upload_images(cam_id: int, files: List[UploadFile] = File(...)):
    if cam_id not in CAMERAS:
        raise HTTPException(status_code=404, detail="Cámara no encontrada")
    cam_folder = os.path.join(DATA_DIR, CAMERAS[cam_id]["folder"])
    os.makedirs(cam_folder, exist_ok=True)
    uploaded = []
    for file in files:
        safe_name = _safe_filename(file.filename)
        if not safe_name.lower().endswith(IMAGE_EXTS):
            raise HTTPException(status_code=400, detail=f"Tipo de archivo no permitido: {safe_name}")
        contents = await file.read()
        if len(contents) > MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail=f"Archivo demasiado grande: {safe_name}")
        file_path = os.path.join(cam_folder, safe_name)
        with open(file_path, "wb") as buffer:
            buffer.write(contents)
        uploaded.append(safe_name)
    add_log(f"Subidas {len(uploaded)} imágenes a Cam {cam_id}", "info")
    return {"status": "success", "uploaded": uploaded, "count": len(uploaded)}

# DEBUG: lista los archivos de imagen (jpg/png) de la carpeta de una cámara con
# tamaño y fecha de modificación; usado por el explorador de imágenes del frontend.
@app.get("/api/cameras/{cam_id}/images")
def list_camera_images(cam_id: int):
    if cam_id not in CAMERAS: raise HTTPException(status_code=404, detail="Camera not found")
    cam_folder = os.path.join(DATA_DIR, CAMERAS[cam_id]["folder"])
    if not os.path.exists(cam_folder):
        return []
    
    images = []
    for f in sorted(os.listdir(cam_folder)):
        if f.lower().endswith(('.jpg', '.jpeg', '.png')):
            ann_path = _annotations_path(cam_id, f)
            annotated = False
            calibrated = False
            if os.path.exists(ann_path):
                try:
                    with open(ann_path, "r") as af:
                        ann = json.load(af)
                    annotated = bool(ann.get("points"))
                    calibrated = bool(ann.get("calibration"))
                except (json.JSONDecodeError, OSError):
                    pass
            align_info = _load_alignment_info(cam_id, f)
            images.append({
                "filename": f,
                "size": os.path.getsize(os.path.join(cam_folder, f)),
                "modified": os.path.getmtime(os.path.join(cam_folder, f)),
                "captured_at": _parse_capture_ts(f),
                "annotated": annotated,
                "calibrated": calibrated,
                "aligned": bool(align_info),
                "align_inliers": align_info.get("inliers") if align_info else None,
            })
    return images

# DEBUG: elimina físicamente un archivo de imagen de la carpeta de una cámara. Acción
# destructiva e irreversible sobre disco — no hay papelera ni confirmación server-side.
@app.delete("/api/cameras/{cam_id}/images/{filename}")
def delete_camera_image(cam_id: int, filename: str):
    if cam_id not in CAMERAS: raise HTTPException(status_code=404, detail="Camera not found")
    file_path = os.path.join(DATA_DIR, CAMERAS[cam_id]["folder"], _safe_filename(filename))
    if os.path.exists(file_path):
        try:
            os.remove(file_path)
            add_log(f"Imagen {filename} eliminada de Cam {cam_id}", "info")
            return {"status": "success"}
        except Exception as e:
            add_log(f"Error al eliminar {filename} de Cam {cam_id}: {e}", "error")
            raise HTTPException(status_code=500, detail="No se pudo eliminar el archivo")
    raise HTTPException(status_code=404, detail="File not found")

# ── Catálogo de varillas (coordenadas UTM topografiadas en campo) ─────────────
# El CSV es flexible en cabeceras (español/inglés, con o sin unidades) y en
# separador (coma o punto y coma, con decimales con coma al estilo español).
RODS_LABEL_COLS = ("id", "label", "nombre", "varilla", "punto", "name", "codigo", "código")
RODS_X_COLS = ("x", "utm_x", "este", "easting", "x_m", "x(m)", "x (m)", "coord_x")
RODS_Y_COLS = ("y", "utm_y", "norte", "northing", "y_m", "y(m)", "y (m)", "coord_y")
RODS_Z_COLS = ("z", "cota", "altura", "elevation", "z_m", "z(m)", "z (m)")
RODS_NOTES_COLS = ("notas", "notes", "descripcion", "descripción", "obs", "observaciones")

def _find_col(columns: dict, candidates: tuple):
    for cand in candidates:
        if cand in columns:
            return columns[cand]
    return None

def _rods_path(cam_id: int) -> str:
    return os.path.join(CALIBRATION_DIR, f"cam_{cam_id}_rods.json")

# El campo FILE del CSV de campo identifica la sesión de disparo como
# "YYYYMMDD_HHMM" (sin segundos ni serial). Empareja esa etiqueta con el
# nombre de archivo real "<epoch>_<YYYYMMDD>_<HHMMSS>_<serial>.jpg" comparando
# fecha y HHMM — cada sesión de campo generaba sus propias varillas, distintas
# de las de otra imagen, así que no hay catálogo compartido que valga para todas.
FILE_TAG_RE = re.compile(r"^(\d{8})_(\d{4})$")

def _match_image_for_file_tag(cam_id: int, file_tag: str) -> Optional[dict]:
    m = FILE_TAG_RE.match(str(file_tag).strip())
    if not m:
        return None
    date_str, hhmm = m.group(1), m.group(2)
    cam_folder = os.path.join(DATA_DIR, CAMERAS[cam_id]["folder"])
    if not os.path.exists(cam_folder):
        return None
    for f in sorted(os.listdir(cam_folder)):
        fm = FILENAME_TS_RE.match(f)
        if fm and fm.group(2) == date_str and fm.group(3)[:4] == hhmm:
            return {"filename": f, "captured_at": _parse_capture_ts(f)}
    return None

@app.post("/api/cameras/{cam_id}/import-rods")
async def import_rods(cam_id: int, file: UploadFile = File(...)):
    if cam_id not in CAMERAS:
        raise HTTPException(status_code=404, detail="Cámara no encontrada")
    if not _safe_filename(file.filename).lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Solo se admiten archivos .csv")
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="El archivo está vacío")
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Archivo demasiado grande")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("latin-1")

    def _num(v) -> float:
        if isinstance(v, str):
            v = v.strip().replace(",", ".")
        return float(v)

    rods, skipped = [], 0
    first_line = text.splitlines()[0].upper() if text.splitlines() else ""

    if first_line.startswith(",") and "UTM" in first_line:
        # Formato de levantamiento GCP del proyecto: doble cabecera (fila de grupos
        # IMG/UTM + fila de nombres), columnas X/Y duplicadas (píxel y UTM),
        # decimales con coma y filas de varias cámaras mezcladas (columna CAMERA).
        # La columna FILE liga cada fila a la sesión de disparo en la que se
        # topografió: las varillas de una imagen NO son las de otra, así que
        # agrupamos por FILE y las repartimos entre las imágenes reales.
        try:
            df = pd.read_csv(io.StringIO(text), sep=None, engine="python", header=1)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"No se pudo leer el CSV: {e}")
        cols = {str(c).strip().upper(): c for c in df.columns}
        # pandas renombra los duplicados: X (píxel) y X.1 (UTM)
        utm_x, utm_y = cols.get("X.1"), cols.get("Y.1")
        px_x, px_y = cols.get("X"), cols.get("Y")
        id_col, cam_col = cols.get("ID"), cols.get("CAMERA")
        file_col, color_col = cols.get("FILE"), cols.get("COLOR")
        if utm_x is None or utm_y is None:
            raise HTTPException(status_code=400, detail="Formato GCP no reconocido: faltan columnas UTM X/Y")
        cam_tag = f"CAM{cam_id}"
        groups = {}          # file_tag (o "" si no hay columna FILE) -> [puntos]
        for _, row in df.iterrows():
            if cam_col is not None:
                cam_val = str(row[cam_col]).strip().upper().replace(" ", "").replace("_", "")
                if cam_val != cam_tag:
                    continue
            try:
                x, y = _num(row[utm_x]), _num(row[utm_y])
            except (TypeError, ValueError):
                skipped += 1
                continue
            label = f"GCP_{str(row[id_col]).strip()}" if id_col is not None and not pd.isna(row[id_col]) else f"VARILLA_{len(rods) + 1}"
            point = {"label": label, "utm": [x, y]}
            if px_x is not None and px_y is not None and not pd.isna(row[px_x]) and not pd.isna(row[px_y]):
                try:
                    point["pixel"] = [_num(row[px_x]), _num(row[px_y])]
                except (TypeError, ValueError):
                    pass
            if color_col is not None and not pd.isna(row[color_col]):
                point["notes"] = str(row[color_col]).strip()
            file_tag = str(row[file_col]).strip() if file_col is not None and not pd.isna(row[file_col]) else ""
            groups.setdefault(file_tag, []).append(point)
            rods.append(point)

        if file_col is not None:
            matched, unmatched = [], []
            for file_tag, points in groups.items():
                match = _match_image_for_file_tag(cam_id, file_tag) if file_tag else None
                if match:
                    matched.append({**match, "file_tag": file_tag, "points": points})
                else:
                    unmatched.append({"file_tag": file_tag, "points": points})
            if not rods:
                raise HTTPException(status_code=400, detail="El CSV no contiene ninguna fila con coordenadas válidas")
            msg = f"CSV de campo leído: {len(rods)} varillas en {len(matched)} imagen(es) emparejada(s)"
            if unmatched:
                msg += f", {len(unmatched)} sesión(es) sin imagen coincidente"
            if skipped:
                msg += f" ({skipped} filas omitidas por coordenadas inválidas)"
            add_log(msg, "success" if not unmatched else "warning")
            return {
                "status": "success",
                "mode": "per_image",
                "skipped": skipped,
                "matched": matched,
                "unmatched": unmatched,
            }
    else:
        # Formato genérico: una cabecera con columnas id/x/y (nombres flexibles)
        try:
            df = pd.read_csv(io.StringIO(text), sep=None, engine="python")
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"No se pudo leer el CSV: {e}")

        columns = {str(c).strip().lower(): c for c in df.columns}
        label_col = _find_col(columns, RODS_LABEL_COLS)
        x_col = _find_col(columns, RODS_X_COLS)
        y_col = _find_col(columns, RODS_Y_COLS)
        if x_col is None or y_col is None:
            raise HTTPException(status_code=400,
                                detail=f"No se encontraron columnas de coordenadas X/Y. Columnas detectadas: {list(df.columns)}")
        z_col = _find_col(columns, RODS_Z_COLS)
        notes_col = _find_col(columns, RODS_NOTES_COLS)

        for _, row in df.iterrows():
            try:
                x, y = _num(row[x_col]), _num(row[y_col])
            except (TypeError, ValueError):
                skipped += 1
                continue
            if label_col is not None and not pd.isna(row[label_col]):
                label = str(row[label_col]).strip()
            else:
                label = f"VARILLA_{len(rods) + 1}"
            rod = {"label": label, "utm": [x, y]}
            if z_col is not None and not pd.isna(row[z_col]):
                try:
                    rod["z"] = _num(row[z_col])
                except (TypeError, ValueError):
                    pass
            if notes_col is not None and not pd.isna(row[notes_col]):
                rod["notes"] = str(row[notes_col]).strip()
            rods.append(rod)

    if not rods:
        raise HTTPException(status_code=400, detail="El CSV no contiene ninguna fila con coordenadas válidas")

    payload = {
        "cam_id": cam_id,
        "source_file": file.filename,
        "imported_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "rods": rods,
    }
    os.makedirs(CALIBRATION_DIR, exist_ok=True)
    with open(_rods_path(cam_id), "w") as f:
        json.dump(payload, f, indent=2)

    msg = f"Importadas {len(rods)} varillas para Cam {cam_id}"
    if skipped:
        msg += f" ({skipped} filas omitidas por coordenadas inválidas)"
    add_log(msg, "success")
    return {"status": "success", "mode": "catalog", "count": len(rods), "skipped": skipped, "rods": rods}

# DEBUG: devuelve el catálogo de varillas importado para una cámara (o vacío).
@app.get("/api/cameras/{cam_id}/rods")
def get_rods(cam_id: int):
    if cam_id not in CAMERAS:
        raise HTTPException(status_code=404, detail="Cámara no encontrada")
    path = _rods_path(cam_id)
    if os.path.exists(path):
        with open(path, "r") as f:
            return json.load(f)
    return {"cam_id": cam_id, "rods": []}

class RodIn(BaseModel):
    label: str
    utm: List[float]
    z: Optional[float] = None
    notes: Optional[str] = None
    pixel: Optional[List[float]] = None

class RodsUpdatePayload(BaseModel):
    rods: List[RodIn]

# Guarda el catálogo de varillas tras la revisión manual del usuario en el
# paso "Catálogo": permite corregir etiquetas/coordenadas mal importadas del
# CSV, borrar filas erróneas o añadir varillas a mano, sin volver a subir el
# archivo completo.
@app.put("/api/cameras/{cam_id}/rods")
def update_rods(cam_id: int, payload: RodsUpdatePayload):
    if cam_id not in CAMERAS:
        raise HTTPException(status_code=404, detail="Cámara no encontrada")
    for rod in payload.rods:
        if not rod.label.strip():
            raise HTTPException(status_code=400, detail="Todas las varillas necesitan una etiqueta")
        if len(rod.utm) != 2:
            raise HTTPException(status_code=400, detail=f"La varilla '{rod.label}' necesita coordenadas UTM [X, Y]")

    path = _rods_path(cam_id)
    existing = {}
    if os.path.exists(path):
        with open(path, "r") as f:
            existing = json.load(f)

    out = {
        "cam_id": cam_id,
        "source_file": existing.get("source_file"),
        "imported_at": existing.get("imported_at"),
        "edited_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "rods": [r.dict(exclude_none=True) for r in payload.rods],
    }
    os.makedirs(CALIBRATION_DIR, exist_ok=True)
    with open(path, "w") as f:
        json.dump(out, f, indent=2)

    add_log(f"Catálogo de varillas corregido manualmente para Cam {cam_id} ({len(payload.rods)} varillas)", "success")
    return {"status": "success", "count": len(payload.rods), "rods": out["rods"]}

# ── Frontend estático (app de escritorio) ─────────────────────────────────────
# Sirve frontend/dist/ (generado con `npm run build`) desde el propio backend,
# para que la app empaquetada sea UN solo proceso en vez de necesitar el dev
# server de Vite aparte. Registrado el ÚLTIMO a propósito: un mount en "/" con
# html=True es un catch-all, y si se registrara antes taparía las rutas /api/*
# de arriba. En modo desarrollo normal (sin build), FRONTEND_DIST no existe y
# el mount simplemente no se registra — la API sigue funcionando igual que
# siempre, servida aparte por el dev server de Vite.
if FROZEN:
    FRONTEND_DIST = os.path.join(BASE_DIR, "frontend_dist")
else:
    FRONTEND_DIST = os.path.join(BASE_DIR, "frontend", "dist")

if os.path.isdir(FRONTEND_DIST):
    app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")
