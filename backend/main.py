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

# Inicializar segmentador (usara fallback si no hay pesos)
CHECKPOINT_SAM = os.path.join(BASE_DIR, "sam_vit_h_4b8939.pth")
segmenter = None
if APP_MODE == "real":
    try:
        segmenter = SAMSegmenter(checkpoint_path=CHECKPOINT_SAM)
    except Exception as e:
        print(f"[ERROR] Error inicializando segmentador: {e}")

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
    
    H, mask = cv2.findHomography(pts_px, pts_utm, cv2.RANSAC, 5.0)
    
    if H is None:
        raise HTTPException(status_code=500, detail="Could not compute homography")
    
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
def analyze_roi(cam_id: int):
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
    img_path = os.path.join(DATA_DIR, info["folder"], info["file"])
    
    if not os.path.exists(img_path):
        raise HTTPException(status_code=404, detail="Image not found")
    
    img = cv2.imread(img_path)
    
    # 1. Segmentacion
    mask = segmenter.segment_dry_sand(img, str(cam_id))
    if mask is None:
        roi = segmenter.get_roi(str(cam_id))
        if roi:
            mask = color_fallback_segmentation(img, roi)
    
    # 2. Extraccion
    points = extract_coastline_from_mask(mask)
    
    # 3. Metricas
    dry_pixels = np.sum(mask > 0)
    dry_area = float(dry_pixels * 0.25) 
    confidence = 0.95 if segmenter.predictor else 0.70
    
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
    
    for file in files:
        file_path = os.path.join(cam_folder, file.filename)
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
    return {"status": "success", "count": len(files)}

@app.post("/api/cameras/{cam_id}/import-rods")
async def import_rods(cam_id: int, file: UploadFile = File(...)):
    # Placeholder para importacion de varillas
    return {"status": "success"}
