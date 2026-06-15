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

# Segmentador Global (Lazy Loading)
segmenter = None

def get_segmenter():
    global segmenter
    if segmenter is not None:
        return segmenter
    
    if APP_MODE == "demo":
        return None
        
    CHECKPOINT_SAM = os.path.join(BASE_DIR, "sam_vit_h_4b8939.pth")
    print(f"[INFO] Cargando segmentador SAM desde {CHECKPOINT_SAM}...")
    try:
        from segmentation_sam import SAMSegmenter
        segmenter = SAMSegmenter(checkpoint_path=CHECKPOINT_SAM)
    except Exception as e:
        print(f"[ERROR] No se pudo inicializar SAM: {e}")
        segmenter = False # Marcar como fallido para no reintentar cada vez
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
    """Alinea una imagen a una referencia usando ORB (más rápido que SIFT para la web)."""
    gray_img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    gray_ref = cv2.cvtColor(ref_img, cv2.COLOR_BGR2GRAY)
    
    orb = cv2.ORB_create(nfeatures=2000)
    kp1, des1 = orb.detectAndCompute(gray_img, None)
    kp2, des2 = orb.detectAndCompute(gray_ref, None)
    
    if des1 is None or des2 is None:
        return img
        
    bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)
    matches = bf.match(des1, des2)
    matches = sorted(matches, key=lambda x: x.distance)
    
    # Quedarnos con los mejores 10%
    good_matches = matches[:int(len(matches) * 0.15)]
    if len(good_matches) < 20:
        return img
        
    src_pts = np.float32([kp1[m.queryIdx].pt for m in good_matches]).reshape(-1, 1, 2)
    dst_pts = np.float32([kp2[m.trainIdx].pt for m in good_matches]).reshape(-1, 1, 2)
    
    H, mask = cv2.findHomography(src_pts, dst_pts, cv2.RANSAC, 5.0)
    if H is None:
        return img
        
    h, w = ref_img.shape[:2]
    return cv2.warpPerspective(img, H, (w, h))

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
    
    return {"status": "success", "reference_image": filename}

@app.get("/api/cameras/{cam_id}/images/{filename}/annotations")
def get_image_annotations(cam_id: int, filename: str):
    # Buscamos si existe un JSON especifico para esta imagen
    info = CAMERAS[cam_id]
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
        if is_calibrated:
            calibrated_count += 1
        
        cam_folder = os.path.join(DATA_DIR, info["folder"])
        images_count = 0
        if os.path.exists(cam_folder):
            images_count = len([f for f in os.listdir(cam_folder) if f.endswith(('.jpg', '.png'))])

        cameras_status.append({
            "id": f"C{cam_idx}",
            "idx": cam_idx,
            "name": info["name"],
            "status": "Calibrada" if is_calibrated else "Sin calibrar",
            "images": images_count
        })

    return {
        "cameras_calibrated": calibrated_count,
        "total_cameras": len(CAMERAS),
        "images_processed": 506, # Placeholder
        "avg_dry_area": "23 480 m2",
        "cameras": cameras_status
    }

@app.get("/api/cameras/{cam_id}/image")
def get_camera_image(cam_id: int, file: Optional[str] = None):
    if cam_id not in CAMERAS:
        raise HTTPException(status_code=404, detail="Camera not found")
    
    info = CAMERAS[cam_id]
    if file:
        img_path = os.path.join(DATA_DIR, info["folder"], file)
    else:
        img_path = os.path.join(DATA_DIR, info["folder"], info["file"])
    
    if not os.path.exists(img_path):
        raise HTTPException(status_code=404, detail="Image not found")
    
    return FileResponse(img_path)

@app.get("/api/cameras/{cam_id}/profile")
def get_camera_profile(cam_id: int):
    profile_path = os.path.join(CALIBRATION_DIR, f"cam_{cam_id}_profile.json")
    if not os.path.exists(profile_path):
        return {"cam_id": cam_id, "gcps": [], "status": "uncalibrated"}
    
    with open(profile_path, "r") as f:
        return json.load(f)

@app.post("/api/cameras/{cam_id}/calibrate")
def calibrate_camera(cam_id: int, profile: CalibrationProfile):
    os.makedirs(CALIBRATION_DIR, exist_ok=True)
    profile_path = os.path.join(CALIBRATION_DIR, f"cam_{cam_id}_profile.json")
    
    existing_h = None
    existing_rmse = None
    if os.path.exists(profile_path):
        with open(profile_path, "r") as f:
            old_data = json.load(f)
            existing_h = old_data.get("H")
            existing_rmse = old_data.get("rmse_m")

    data = {
        "cam_id": cam_id,
        "gcps": [gcp.dict() for gcp in profile.gcps],
        "status": "saved",
        "H": existing_h,
        "rmse_m": existing_rmse
    }
    
    with open(profile_path, "w") as f:
        json.dump(data, f, indent=2)
    
    return {"status": "success", "message": "Profile saved"}

@app.get("/api/cameras/{cam_id}/images")
def list_camera_images(cam_id: int):
    if cam_id not in CAMERAS:
        raise HTTPException(status_code=404, detail="Camera not found")
    
    info = CAMERAS[cam_id]
    cam_folder = os.path.join(DATA_DIR, info["folder"])
    if not os.path.exists(cam_folder):
        return []
    
    return sorted([f for f in os.listdir(cam_folder) if f.endswith(('.jpg', '.png'))], reverse=True)

@app.post("/api/cameras/{cam_id}/calculate-homography")
def calculate_homography(cam_id: int, image_name: Optional[str] = None):
    if APP_MODE == "demo":
        # Simulamos una homografía exitosa para que el usuario vea el flujo completo
        profile_path = os.path.join(CALIBRATION_DIR, f"cam_{cam_id}_profile.json")
        with open(profile_path, "r") as f:
            data = json.load(f)
        
        data["H"] = np.eye(3).tolist()
        data["rmse_m"] = 0.1234
        data["status"] = "calibrated"
        with open(profile_path, "w") as f:
            json.dump(data, f, indent=2)
            
        # Generar imagen dummy para el preview rectificado
        preview_path = os.path.join(CALIBRATION_DIR, f"cam_{cam_id}_rectified.jpg")
        info = CAMERAS[cam_id]
        img_path = os.path.join(DATA_DIR, info["folder"], image_name if image_name else info["file"])
        if os.path.exists(img_path):
            shutil.copy(img_path, preview_path) # En demo solo copiamos la original como "rectificada"
            
        return {"status": "success", "rmse_m": 0.1234, "H": data["H"]}

    profile_path = os.path.join(CALIBRATION_DIR, f"cam_{cam_id}_profile.json")
    if not os.path.exists(profile_path):
        raise HTTPException(status_code=404, detail="Profile not found")
    
    with open(profile_path, "r") as f:
        data = json.load(f)
    
    gcps = [g for g in data.get("gcps", []) if g.get("type") == "calib"]
    if len(gcps) < 4:
        raise HTTPException(status_code=400, detail="At least 4 GCPs are required")
    
    pts_px = np.array([g["pixel"] for g in gcps], dtype=np.float32)
    pts_utm = np.array([g["utm"] for g in gcps], dtype=np.float32)
    # RANSAC mas estricto para mayor precision
    H, mask = cv2.findHomography(pts_px, pts_utm, cv2.RANSAC, 3.0)

    if H is None:
        raise HTTPException(status_code=500, detail="Error matematico en el calculo")

    # RMSE real
    proj_utm = cv2.perspectiveTransform(pts_px.reshape(-1, 1, 2), H).reshape(-1, 2)
    rmse_m = float(np.sqrt(np.mean(np.linalg.norm(proj_utm - pts_utm, axis=1)**2)))

    data["H"] = H.tolist()
    data["rmse_m"] = round(rmse_m, 4)
    data["status"] = "calibrated"

    
    with open(profile_path, "w") as f:
        json.dump(data, f, indent=2)

    # Recti preview
    info = CAMERAS[cam_id]
    img_to_use = image_name if image_name else info["file"]
    img_path = os.path.join(DATA_DIR, info["folder"], img_to_use)
    
    if os.path.exists(img_path):
        img = cv2.imread(img_path)
        min_utm = np.min(pts_utm, axis=0)
        max_utm = np.max(pts_utm, axis=0)
        width = int((max_utm[0] - min_utm[0]) / 0.5) + 100
        height = int((max_utm[1] - min_utm[1]) / 0.5) + 100
        S = np.array([2, 0, -min_utm[0]*2 + 50], [0, -2, max_utm[1]*2 + 50], [0, 0, 1])
        H_rect = S @ H
        rectified = cv2.warpPerspective(img, H_rect, (width, height))
        preview_path = os.path.join(CALIBRATION_DIR, f"cam_{cam_id}_rectified.jpg")
        cv2.imwrite(preview_path, rectified)
    
    return {"status": "success", "rmse_m": rmse_m, "H": H.tolist()}

@app.get("/api/cameras/{cam_id}/rectified-preview")
def get_rectified_preview(cam_id: int):
    preview_path = os.path.join(CALIBRATION_DIR, f"cam_{cam_id}_rectified.jpg")
    if not os.path.exists(preview_path):
        raise HTTPException(status_code=404, detail="Preview not found")
    return FileResponse(preview_path)

@app.post("/api/cameras/{cam_id}/analyze-roi")
def analyze_roi(cam_id: int, filename: Optional[str] = None):
    if cam_id not in CAMERAS:
        raise HTTPException(status_code=404, detail="Camera not found")
    
    if APP_MODE == "demo":
        # Simular procesamiento instantaneo con variabilidad
        dry_area = 24500.50 + np.random.randint(-500, 500)
        return {
            "dry_area_m2": round(dry_area, 2),
            "confidence": 0.98,
            "timestamp": "2026-06-12T12:00:00"
        }

    info = CAMERAS[cam_id]
    target_file = filename if filename else info["file"]
    img_path = os.path.join(DATA_DIR, info["folder"], target_file)
    
    if not os.path.exists(img_path):
        raise HTTPException(status_code=404, detail="Image not found")
    
    img = cv2.imread(img_path)
    
    # 0. Alineacion Automatica (Feature: Registro de Imagenes)
    profile = get_camera_profile(cam_id)
    ref_name = profile.get("reference_image")
    is_aligned = False
    
    if ref_name and ref_name != target_file:
        ref_path = os.path.join(DATA_DIR, info["folder"], ref_name)
        if os.path.exists(ref_path):
            ref_img = cv2.imread(ref_path)
            img = align_image_to_ref(img, ref_img)
            is_aligned = True
            print(f"[INFO] Imagen {target_file} alineada con {ref_name}")

    # 1. Segmentacion
    s = get_segmenter()
    mask = None
    if s:
        mask = s.segment_dry_sand(img, str(cam_id))
    
    if mask is None:
        # Intentar fallback si SAM falla o no esta disponible
        from test_mes3_pipeline import color_fallback_segmentation
        # Obtener ROI manualmente si el segmentador no esta disponible
        # (Esto asume que tenemos acceso a la lógica de ROI)
        # Para simplificar, si no hay segmentador, usamos un ROI generico o lo buscamos
        roi = None
        if s:
            roi = s.get_roi(str(cam_id))
        else:
            # Fallback a buscar ROI directamente
            try:
                from segmentation_sam import SAMSegmenter
                temp_s = SAMSegmenter()
                roi = temp_s.get_roi(str(cam_id))
            except: pass
            
        if roi:
            mask = color_fallback_segmentation(img, roi)
    
    # 2. Extraccion
    if mask is not None:
        points = extract_coastline_from_mask(mask)
    else:
        points = None
    
    # 3. Metricas
    if mask is not None:
        dry_pixels = np.sum(mask > 0)
        dry_area = float(dry_pixels * 0.25) 
    else:
        dry_area = 0.0
        
    confidence = 0.95 if (s and s.predictor) else 0.70
    
    # 4. Viz
    viz = img.copy()
    if points:
        viz = draw_coastline(viz, points, color=(0, 255, 0), thickness=3)
    
    res_img_path = os.path.join(DATA_DIR, f"latest_analysis_cam{cam_id}.jpg")
    cv2.imwrite(res_img_path, viz)
    
    return {
        "dry_area_m2": round(dry_area, 2),
        "confidence": confidence,
        "timestamp": "2026-06-12T12:00:00"
    }

@app.get("/api/geojson")
def get_geojson():
    if APP_MODE == "demo":
        return {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": {"cam_id": "CAM_3", "confidence": 0.99},
                    "geometry": {
                        "type": "LineString",
                        "coordinates": [
                            [-0.648117, 38.076774],
                            [-0.647078, 38.087385],
                            [-0.643027, 38.110327]
                        ]
                    }
                }
            ]
        }
    path = os.path.join(DATA_DIR, "latest_result.json")
    if os.path.exists(path):
        with open(path, "r") as f:
            return json.load(f)
    return {"type": "FeatureCollection", "features": []}

@app.get("/api/cameras/{cam_id}/analysis-result")
def get_analysis_result(cam_id: int):
    path = os.path.join(DATA_DIR, f"latest_analysis_cam{cam_id}.jpg")
    if os.path.exists(path):
        return FileResponse(path)
    return get_camera_image(cam_id)

@app.post("/api/cameras/{cam_id}/upload-images")
async def upload_images(cam_id: int, files: List[UploadFile] = File(...)):
    if cam_id not in CAMERAS:
        raise HTTPException(status_code=404, detail="Camera not found")
    
    cam_folder = os.path.join(DATA_DIR, CAMERAS[cam_id]["folder"])
    os.makedirs(cam_folder, exist_ok=True)
    
    uploaded = []
    skipped = []
    
    for file in files:
        file_path = os.path.join(cam_folder, file.filename)
        if os.path.exists(file_path):
            skipped.append(file.filename)
            continue
            
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        uploaded.append(file.filename)
            
    return {
        "status": "success", 
        "uploaded": uploaded, 
        "skipped": skipped,
        "count": len(uploaded)
    }

@app.delete("/api/cameras/{cam_id}/images/{filename}")
def delete_camera_image(cam_id: int, filename: str):
    if cam_id not in CAMERAS:
        raise HTTPException(status_code=404, detail="Camera not found")
    
    cam_folder = os.path.join(DATA_DIR, CAMERAS[cam_id]["folder"])
    file_path = os.path.join(cam_folder, filename)
    
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")
    
    # Do not allow deleting the default reference file if you want
    if filename == CAMERAS[cam_id]["file"]:
         raise HTTPException(status_code=403, detail="Cannot delete default reference image")

    try:
        os.remove(file_path)
        return {"status": "success", "message": f"Deleted {filename}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/cameras/{cam_id}/import-rods")
async def import_rods(cam_id: int, file: UploadFile = File(...)):
    # Placeholder para importacion de varillas
    return {"status": "success"}
