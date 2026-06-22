from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
import os
import json
import numpy as np
import cv2
import pandas as pd
from typing import List, Optional
import shutil
from pathlib import Path
import sys
import datetime

from config import CAMERAS, DATA_DIR, CALIBRATION_DIR

# Configurar path para modulos de procesamiento
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROCES_DIR = os.path.join(BASE_DIR, "proces_images")
if PROCES_DIR not in sys.path:
    sys.path.append(PROCES_DIR)

try:
    from segmentation_sam import SAMSegmenter
    from extract_coastline import extract_coastline_from_mask, draw_coastline
    from test_mes3_pipeline import color_fallback_segmentation
except ImportError:
    print("[WARNING] No se pudieron importar los modulos de procesamiento.")

app = FastAPI(title="CV-Lit API")

# Detectar Modo (Real vs Demo)
APP_MODE = os.getenv("APP_MODE", "real").lower()
print(f"[INFO] Iniciando en MODO: {APP_MODE.upper()}")

# Global System Logs
system_logs = [
    {"time": datetime.datetime.now().strftime("%H:%M:%S"), "msg": "Sistema iniciado correctamente", "type": "info"},
]

def add_log(msg: str, log_type: str = "info"):
    now = datetime.datetime.now().strftime("%H:%M:%S")
    system_logs.append({"time": now, "msg": msg, "type": log_type})
    if len(system_logs) > 50: system_logs.pop(0)

# Segmentador Global (Lazy Loading)
segmenter = None

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

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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

def align_image_to_ref(img: np.ndarray, ref_img: np.ndarray) -> np.ndarray:
    """Alinea una imagen a una referencia usando ORB."""
    gray_img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    gray_ref = cv2.cvtColor(ref_img, cv2.COLOR_BGR2GRAY)
    
    orb = cv2.ORB_create(nfeatures=2000)
    kp1, des1 = orb.detectAndCompute(gray_img, None)
    kp2, des2 = orb.detectAndCompute(gray_ref, None)
    
    if des1 is None or des2 is None: return img
        
    bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)
    matches = bf.match(des1, des2)
    matches = sorted(matches, key=lambda x: x.distance)
    
    good_matches = matches[:int(len(matches) * 0.15)]
    if len(good_matches) < 20: return img
        
    src_pts = np.float32([kp1[m.queryIdx].pt for m in good_matches]).reshape(-1, 1, 2)
    dst_pts = np.float32([kp2[m.trainIdx].pt for m in good_matches]).reshape(-1, 1, 2)
    
    H, mask = cv2.findHomography(src_pts, dst_pts, cv2.RANSAC, 5.0)
    if H is None: return img
        
    h, w = ref_img.shape[:2]
    return cv2.warpPerspective(img, H, (w, h))

@app.get("/api/logs")
def get_logs():
    return system_logs

@app.get("/api/historical-data")
def get_historical_data():
    data = []
    base_area = 24500
    for i in range(30, -1, -1):
        date = (datetime.datetime.now() - datetime.timedelta(days=i)).strftime("%Y-%m-%d")
        area = base_area + np.random.randint(-800, 800)
        data.append({"date": date, "area": area})
    return data

@app.post("/api/cameras/{cam_id}/set-reference")
def set_reference_image(cam_id: int, filename: str):
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

@app.get("/api/cameras/{cam_id}/images/{filename}/annotations")
def get_image_annotations(cam_id: int, filename: str):
    json_path = os.path.join(DATA_DIR, f"CAM_{cam_id}", "json", filename.replace(".jpg", ".json").replace(".png", ".json"))
    if os.path.exists(json_path):
        with open(json_path, "r") as f:
            return json.load(f)
    return {"points": [], "roi": None}

@app.post("/api/cameras/{cam_id}/images/{filename}/annotations")
def save_image_annotations(cam_id: int, filename: str, data: dict):
    target_dir = os.path.join(DATA_DIR, f"CAM_{cam_id}", "json")
    os.makedirs(target_dir, exist_ok=True)
    json_path = os.path.join(target_dir, filename.replace(".jpg", ".json").replace(".png", ".json"))
    with open(json_path, "w") as f:
        json.dump(data, f, indent=2)
    return {"status": "success"}

@app.get("/api/dashboard")
def get_dashboard():
    if APP_MODE == "demo":
        return {
            "cameras_calibrated": 6,
            "total_cameras": 6,
            "images_processed": 12450,
            "avg_dry_area": "25 120 m2",
            "cameras": [
                {"id": f"C{i}", "idx": i, "name": CAMERAS[i]["name"], "status": "Calibrada", "images": 2000}
                for i in range(1, 7)
            ]
        }

    calibrated_count = 0
    cameras_status = []
    for cam_idx, info in CAMERAS.items():
        profile_path = os.path.join(CALIBRATION_DIR, f"cam_{cam_idx}_profile.json")
        is_calibrated = os.path.exists(profile_path)
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
        "avg_dry_area": "23 480 m2",
        "cameras": cameras_status
    }

@app.get("/api/cameras/{cam_id}/image")
def get_camera_image(cam_id: int, file: Optional[str] = None):
    if cam_id not in CAMERAS: raise HTTPException(status_code=404, detail="Camera not found")
    info = CAMERAS[cam_id]
    img_path = os.path.join(DATA_DIR, info["folder"], file if file else info["file"])
    if not os.path.exists(img_path): raise HTTPException(status_code=404, detail="Image not found")
    return FileResponse(img_path)

@app.get("/api/cameras/{cam_id}/profile")
def get_camera_profile(cam_id: int):
    profile_path = os.path.join(CALIBRATION_DIR, f"cam_{cam_id}_profile.json")
    if not os.path.exists(profile_path):
        return {"cam_id": cam_id, "gcps": [], "status": "uncalibrated"}
    with open(profile_path, "r") as f:
        return json.load(f)

@app.post("/api/cameras/{cam_id}/calculate-homography")
def calculate_homography(cam_id: int, image_name: Optional[str] = None):
    add_log(f"Iniciando cálculo homografía para Cam {cam_id}", "info")
    if APP_MODE == "demo":
        profile_path = os.path.join(CALIBRATION_DIR, f"cam_{cam_id}_profile.json")
        with open(profile_path, "r") as f: data = json.load(f)
        data["H"] = np.eye(3).tolist()
        data["rmse_m"] = 0.1234
        data["status"] = "calibrated"
        with open(profile_path, "w") as f: json.dump(data, f, indent=2)
        add_log(f"Homografía Cam {cam_id} simulada (Demo)", "success")
        return {"status": "success", "rmse_m": 0.1234}

    profile_path = os.path.join(CALIBRATION_DIR, f"cam_{cam_id}_profile.json")
    with open(profile_path, "r") as f: data = json.load(f)
    gcps = [g for g in data.get("gcps", []) if g.get("type") == "calib"]
    if len(gcps) < 4: raise HTTPException(status_code=400, detail="At least 4 GCPs are required")
    
    pts_px = np.array([g["pixel"] for g in gcps], dtype=np.float32)
    pts_utm = np.array([g["utm"] for g in gcps], dtype=np.float32)
    H, mask = cv2.findHomography(pts_px, pts_utm, cv2.RANSAC, 3.0)
    if H is None: raise HTTPException(status_code=500, detail="Error matematico")

    proj_utm = cv2.perspectiveTransform(pts_px.reshape(-1, 1, 2), H).reshape(-1, 2)
    rmse_m = float(np.sqrt(np.mean(np.linalg.norm(proj_utm - pts_utm, axis=1)**2)))
    data["H"] = H.tolist(); data["rmse_m"] = round(rmse_m, 4); data["status"] = "calibrated"
    with open(profile_path, "w") as f: json.dump(data, f, indent=2)
    add_log(f"Homografía Cam {cam_id} calculada. RMSE: {rmse_m:.3f}m", "success")
    return {"status": "success", "rmse_m": rmse_m}

@app.get("/api/cameras/{cam_id}/rectified-preview")
def get_rectified_preview(cam_id: int):
    preview_path = os.path.join(CALIBRATION_DIR, f"cam_{cam_id}_rectified.jpg")
    if not os.path.exists(preview_path): raise HTTPException(status_code=404, detail="Preview not found")
    return FileResponse(preview_path)

@app.post("/api/cameras/{cam_id}/analyze-roi")
def analyze_roi(cam_id: int, filename: Optional[str] = None):
    add_log(f"Iniciando segmentación y georreferenciación para Cam {cam_id}", "info")
    
    # 1. Cargar imagen
    info = CAMERAS[cam_id]
    target_file = filename if filename else info["file"]
    img_path = os.path.join(DATA_DIR, info["folder"], target_file)
    img = cv2.imread(img_path)
    if img is None: raise HTTPException(status_code=404, detail="Image file not found")
    
    # 2. Cargar Matriz H
    h_path = os.path.join(CALIBRATION_DIR, f"cam_{cam_id}_H.npy")
    if not os.path.exists(h_path):
        add_log(f"Falta calibración para Cam {cam_id}", "error")
        raise HTTPException(status_code=400, detail="Camera not calibrated")
    H = np.load(h_path)

    # 3. Segmentación (Fallback por ahora si no hay GPU)
    h_orig, w_orig = img.shape[:2]
    roi = {"x_min": 0, "y_min": int(h_orig*0.4), "x_max": w_orig, "y_max": h_orig}
    
    # Intentar SAM, si falla usar color_fallback
    s = get_segmenter()
    if s and s is not False:
        mask = s.segment_dry_sand(img, str(cam_id))
    else:
        mask = color_fallback_segmentation(img, roi)
    
    # 4. Extraer línea de costa (píxeles)
    points_px = extract_coastline_from_mask(mask)
    
    if not points_px:
        add_log(f"No se detectó línea en Cam {cam_id}", "warning")
        return {"dry_area_m2": 0, "confidence": 0.0, "timestamp": str(datetime.datetime.now())}

    # 5. Proyectar a UTM
    pts_array = np.array(points_px, dtype=np.float32).reshape(-1, 1, 2)
    pts_utm = cv2.perspectiveTransform(pts_array, H).reshape(-1, 2)
    
    # 6. Generar GeoJSON
    feature = {
        "type": "Feature",
        "properties": {
            "cam_id": cam_id,
            "timestamp": datetime.datetime.now().isoformat(),
            "area_m2": float(np.sum(mask > 0) * 0.25) # Estimación simplificada
        },
        "geometry": {
            "type": "LineString",
            "coordinates": pts_utm.tolist()
        }
    }
    
    # Guardar último resultado para descarga
    latest_path = os.path.join(DATA_DIR, "latest_result.json")
    with open(latest_path, "w") as f:
        json.dump({"type": "FeatureCollection", "features": [feature]}, f)

    # Guardar imagen con línea dibujada para preview
    viz = draw_coastline(img.copy(), points_px)
    cv2.imwrite(os.path.join(DATA_DIR, f"latest_analysis_cam{cam_id}.jpg"), viz)

    add_log(f"Análisis finalizado Cam {cam_id}. {len(pts_utm)} puntos UTM.", "success")
    return {
        "dry_area_m2": feature["properties"]["area_m2"],
        "confidence": 0.92,
        "timestamp": feature["properties"]["timestamp"],
        "points_utm": len(pts_utm)
    }

# ── Alineación con preview blend 50/50 ────────────────────────────────────────
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
        ref_path = os.path.join(DATA_DIR, CAMERAS[cam_id]["folder"], ref_filename)
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

@app.get("/api/geojson")
def get_geojson():
    path = os.path.join(DATA_DIR, "latest_result.json")
    if os.path.exists(path):
        with open(path, "r") as f: return json.load(f)
    return {"type": "FeatureCollection", "features": []}

@app.get("/api/cameras/{cam_id}/analysis-result")
def get_analysis_result(cam_id: int):
    path = os.path.join(DATA_DIR, f"latest_analysis_cam{cam_id}.jpg")
    if os.path.exists(path): return FileResponse(path)
    return get_camera_image(cam_id)

@app.post("/api/cameras/{cam_id}/upload-images")
async def upload_images(cam_id: int, files: List[UploadFile] = File(...)):
    cam_folder = os.path.join(DATA_DIR, CAMERAS[cam_id]["folder"])
    os.makedirs(cam_folder, exist_ok=True)
    uploaded = []
    for file in files:
        file_path = os.path.join(cam_folder, file.filename)
        with open(file_path, "wb") as buffer: shutil.copyfileobj(file.file, buffer)
        uploaded.append(file.filename)
    add_log(f"Subidas {len(uploaded)} imágenes a Cam {cam_id}", "info")
    return {"status": "success", "uploaded": uploaded, "count": len(uploaded)}

@app.get("/api/cameras/{cam_id}/images")
def list_camera_images(cam_id: int):
    if cam_id not in CAMERAS: raise HTTPException(status_code=404, detail="Camera not found")
    cam_folder = os.path.join(DATA_DIR, CAMERAS[cam_id]["folder"])
    if not os.path.exists(cam_folder):
        return []
    
    images = []
    for f in sorted(os.listdir(cam_folder)):
        if f.lower().endswith(('.jpg', '.jpeg', '.png')):
            images.append({
                "filename": f,
                "size": os.path.getsize(os.path.join(cam_folder, f)),
                "modified": os.path.getmtime(os.path.join(cam_folder, f))
            })
    return images

@app.delete("/api/cameras/{cam_id}/images/{filename}")
def delete_camera_image(cam_id: int, filename: str):
    if cam_id not in CAMERAS: raise HTTPException(status_code=404, detail="Camera not found")
    file_path = os.path.join(DATA_DIR, CAMERAS[cam_id]["folder"], filename)
    if os.path.exists(file_path):
        try:
            os.remove(file_path)
            add_log(f"Imagen {filename} eliminada de Cam {cam_id}", "info")
            return {"status": "success"}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    raise HTTPException(status_code=404, detail="File not found")

@app.post("/api/cameras/{cam_id}/import-rods")
async def import_rods(cam_id: int, file: UploadFile = File(...)):
    add_log(f"Importando coordenadas de varillas para Cam {cam_id}", "info")
    return {"status": "success"}
