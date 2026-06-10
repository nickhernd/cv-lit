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

from config import CAMERAS, DATA_DIR, CALIBRATION_DIR

app = FastAPI(title="CV-Lit API")

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

class CalibrationProfile(BaseModel):
    cam_id: int
    gcps: List[GCP]

@app.get("/api/dashboard")
def get_dashboard():
    # Count calibrated cameras
    calibrated_count = 0
    cameras_status = []
    
    for cam_idx, info in CAMERAS.items():
        profile_path = os.path.join(CALIBRATION_DIR, f"cam_{cam_idx}_profile.json")
        is_calibrated = os.path.exists(profile_path)
        if is_calibrated:
            calibrated_count += 1
        
        # Count images (placeholder logic)
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
        "avg_dry_area": "23 480 m²", # Placeholder
        "cameras": cameras_status
    }

@app.get("/api/cameras/{cam_id}/image")
def get_camera_image(cam_id: int):
    if cam_id not in CAMERAS:
        raise HTTPException(status_code=404, detail="Camera not found")
    
    info = CAMERAS[cam_id]
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
    
    # Preserve H if it exists
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
    
    return [f for f in os.listdir(cam_folder) if f.endswith(('.jpg', '.png'))]

@app.post("/api/cameras/{cam_id}/calculate-homography")
def calculate_homography(cam_id: int, image_name: Optional[str] = None):
    profile_path = os.path.join(CALIBRATION_DIR, f"cam_{cam_id}_profile.json")
    if not os.path.exists(profile_path):
        raise HTTPException(status_code=404, detail="Profile not found")
    
    with open(profile_path, "r") as f:
        data = json.load(f)
    
    gcps = data.get("gcps", [])
    if len(gcps) < 4:
        raise HTTPException(status_code=400, detail="At least 4 GCPs are required")
    
    pts_px = np.array([g["pixel"] for g in gcps], dtype=np.float32)
    pts_utm = np.array([g["utm"] for g in gcps], dtype=np.float32)
    
    H, mask = cv2.findHomography(pts_px, pts_utm, cv2.RANSAC, 5.0)
    
    if H is None:
        raise HTTPException(status_code=500, detail="Could not compute homography")
    
    # Calculate RMSE
    proj_utm = cv2.perspectiveTransform(pts_px.reshape(-1, 1, 2), H).reshape(-1, 2)
    rmse_m = float(np.sqrt(np.mean(np.linalg.norm(proj_utm - pts_utm, axis=1)**2)))
    
    data["H"] = H.tolist()
    data["rmse_m"] = round(rmse_m, 4)
    data["status"] = "calibrated"
    
    with open(profile_path, "w") as f:
        json.dump(data, f, indent=2)

    # Generate Rectified Preview
    info = CAMERAS[cam_id]
    img_to_use = image_name if image_name else info["file"]
    img_path = os.path.join(DATA_DIR, info["folder"], img_to_use)
    
    if os.path.exists(img_path):
        img = cv2.imread(img_path)
        # Simple recti preview: map to a 800x800 area around the first GCP
        # In a real app, this would use the UTM bounds
        min_utm = np.min(pts_utm, axis=0)
        max_utm = np.max(pts_utm, axis=0)
        
        # Output resolution 1px = 0.5m
        width = int((max_utm[0] - min_utm[0]) / 0.5) + 100
        height = int((max_utm[1] - min_utm[1]) / 0.5) + 100
        
        # Shift H to output space
        S = np.array([[2, 0, -min_utm[0]*2 + 50], [0, -2, max_utm[1]*2 + 50], [0, 0, 1]])
        H_rect = S @ H
        
        rectified = cv2.warpPerspective(img, H_rect, (width, height))
        preview_path = os.path.join(CALIBRATION_DIR, f"cam_{cam_id}_rectified.jpg")
        cv2.imwrite(preview_path, rectified)
    
    return {
        "status": "success",
        "rmse_m": rmse_m,
        "H": H.tolist()
    }

@app.get("/api/cameras/{cam_id}/rectified-preview")
def get_rectified_preview(cam_id: int):
    preview_path = os.path.join(CALIBRATION_DIR, f"cam_{cam_id}_rectified.jpg")
    if not os.path.exists(preview_path):
        raise HTTPException(status_code=404, detail="Preview not found. Calculate homography first.")
    return FileResponse(preview_path)

@app.post("/api/cameras/{cam_id}/analyze-roi")
def analyze_roi(cam_id: int):
    # Dummy analysis result
    dry_area = 24500 + np.random.randint(-1000, 1000)
    
    # Save a fake GeoJSON result
    result_geojson = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {
                    "type": "LineString",
                    "coordinates": [
                        [-0.648, 38.085],
                        [-0.647 + (np.random.random()*0.001), 38.084],
                        [-0.646, 38.083]
                    ]
                },
                "properties": {
                    "cam_id": cam_id,
                    "dry_area_m2": dry_area,
                    "timestamp": "2026-06-10T10:30:00"
                }
            }
        ]
    }
    
    with open(os.path.join(DATA_DIR, "latest_result.json"), "w") as f:
        json.dump(result_geojson, f)

    return {
        "dry_area_m2": dry_area,
        "confidence": 0.92,
        "timestamp": "2026-06-10T10:30:00"
    }

@app.get("/api/geojson")
def get_geojson():
    path = os.path.join(DATA_DIR, "latest_result.json")
    if os.path.exists(path):
        with open(path, "r") as f:
            return json.load(f)
            
    # Default placeholder
    return {
        "type": "FeatureCollection",
        "features": []
    }

@app.get("/api/cameras/{cam_id}/analysis-result")
def get_analysis_result(cam_id: int):
    # Just return the camera image for now as a placeholder
    return get_camera_image(cam_id)
