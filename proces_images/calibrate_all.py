import os
import csv
import json
import numpy as np
import cv2
from pathlib import Path
from datetime import date

# Configuración de rutas
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
GCP_CSV = DATA_DIR / "GCP.csv"
CALIB_DIR = BASE_DIR.parent / "calibration"
DIAG_DIR = CALIB_DIR / "diagnostics"

os.makedirs(CALIB_DIR, exist_ok=True)
os.makedirs(DIAG_DIR, exist_ok=True)

def parse_utm(val):
    """Convierte '123,456' o '123.456' a float."""
    if not val: return 0.0
    return float(val.replace('"', '').replace(',', '.'))

def load_all_gcps(csv_path):
    gcps_by_cam = {f"CAM{i}": [] for i in range(1, 7)}
    
    with open(csv_path, newline='', encoding='utf-8') as f:
        # Saltar las dos líneas de cabecera complejas
        next(f)
        next(f)
        reader = csv.reader(f)
        for row in reader:
            if len(row) < 8: continue
            cam_id = row[1].strip().upper()
            if cam_id not in gcps_by_cam: continue
            
            try:
                u = float(row[4])
                v = float(row[5])
                x_utm = parse_utm(row[6])
                y_utm = parse_utm(row[7])
                file_tag = row[2]
                color = row[3]
                
                gcps_by_cam[cam_id].append({
                    "pixel": [u, v],
                    "utm": [x_utm, y_utm],
                    "file_tag": file_tag,
                    "color": color
                })
            except (ValueError, IndexError):
                continue
                
    return gcps_by_cam

def calibrate_camera(cam_id, gcps):
    print(f"\n--- Calibrando {cam_id} ({len(gcps)} puntos) ---")
    
    if len(gcps) < 4:
        print(f"  [!] Insuficientes puntos para {cam_id}")
        return None

    # Separar entrenamiento y validación (80/20)
    # Usamos una semilla fija para reproducibilidad
    np.random.seed(42)
    indices = np.arange(len(gcps))
    np.random.shuffle(indices)
    
    split = int(0.8 * len(gcps))
    train_idx = indices[:split]
    val_idx = indices[split:]
    
    train_gcps = [gcps[i] for i in train_idx]
    val_gcps = [gcps[i] for i in val_idx]

    pts_px = np.array([g["pixel"] for g in train_gcps], dtype=np.float32)
    pts_utm = np.array([g["utm"] for g in train_gcps], dtype=np.float32)

    # Calcular Homografía
    H, mask = cv2.findHomography(pts_px, pts_utm, cv2.RANSAC, 5.0)
    
    if H is None:
        print(f"  [!] Falló RANSAC para {cam_id}")
        return None

    # Métricas de entrenamiento
    H_inv = np.linalg.inv(H)
    proj_utm = cv2.perspectiveTransform(pts_px.reshape(-1, 1, 2), H).reshape(-1, 2)
    rmse_m = np.sqrt(np.mean(np.linalg.norm(proj_utm - pts_utm, axis=1)**2))
    
    reproj_px = cv2.perspectiveTransform(pts_utm.reshape(-1, 1, 2), H_inv).reshape(-1, 2)
    rmse_px = np.sqrt(np.mean(np.linalg.norm(reproj_px - pts_px, axis=1)**2))

    # Métricas de validación
    v_rmse_m, v_rmse_px = -1.0, -1.0
    if val_gcps:
        vpts_px = np.array([g["pixel"] for g in val_gcps], dtype=np.float32)
        vpts_utm = np.array([g["utm"] for g in val_gcps], dtype=np.float32)
        
        vproj_utm = cv2.perspectiveTransform(vpts_px.reshape(-1, 1, 2), H).reshape(-1, 2)
        v_rmse_m = np.sqrt(np.mean(np.linalg.norm(vproj_utm - vpts_utm, axis=1)**2))
        
        vrep_px = cv2.perspectiveTransform(vpts_utm.reshape(-1, 1, 2), H_inv).reshape(-1, 2)
        v_rmse_px = np.sqrt(np.mean(np.linalg.norm(vrep_px - vpts_px, axis=1)**2))

    print(f"  RMSE Calib: {rmse_px:.2f} px / {rmse_m:.2f} m")
    print(f"  RMSE Valid: {v_rmse_px:.2f} px / {v_rmse_m:.2f} m")

    # Guardar resultados
    cam_num = cam_id.replace("CAM", "")
    profile = {
        "cam_id": int(cam_num),
        "cam_name": f"CAM {cam_num}",
        "gcps_count": len(gcps),
        "H": H.tolist(),
        "rmse_px": float(rmse_px),
        "rmse_m": float(rmse_m),
        "rmse_val_px": float(v_rmse_px),
        "rmse_val_m": float(v_rmse_m),
        "date": str(date.today()),
        "epsg": 25830
    }
    
    json_path = CALIB_DIR / f"cam_{cam_num}_profile.json"
    with open(json_path, "w") as f:
        json.dump(profile, f, indent=2)
        
    np.save(CALIB_DIR / f"cam_{cam_num}_H.npy", H)
    
    # Generar visualización de diagnóstico
    generate_diagnostic(cam_id, gcps, H, train_idx, val_idx)
    
    return profile

def generate_diagnostic(cam_id, gcps, H, train_idx, val_idx):
    # Buscar una imagen de referencia para esta cámara
    cam_num = cam_id.replace("CAM", "")
    cam_folder = DATA_DIR / f"camera{cam_num}"
    img_files = list(cam_folder.glob("*.jpg"))
    
    if not img_files:
        return

    img = cv2.imread(str(img_files[0]))
    if img is None: return
    
    H_inv = np.linalg.inv(H)
    
    for i, gcp in enumerate(gcps):
        u, v = map(int, gcp["pixel"])
        pt_utm = np.array([[[gcp["utm"][0], gcp["utm"][1]]]], dtype=np.float32)
        rep_px = cv2.perspectiveTransform(pt_utm, H_inv).reshape(2)
        ru, rv = map(int, rep_px)
        
        # Color: Verde para entrenamiento, Azul para validación
        color = (0, 255, 0) if i in train_idx else (255, 0, 0)
        
        cv2.circle(img, (u, v), 10, color, 2)
        cv2.circle(img, (ru, rv), 5, (0, 0, 255), -1) # Reproyección en rojo
        cv2.line(img, (u, v), (ru, rv), (0, 255, 255), 1)

    # Añadir leyenda
    cv2.putText(img, f"{cam_id} - Ver: Calib, Az: Valid, Red: Reproj", (50, 50), 
                cv2.FONT_HERSHEY_SIMPLEX, 1.2, (255, 255, 255), 3)
    
    diag_path = DIAG_DIR / f"{cam_id}_diagnostic.jpg"
    cv2.imwrite(str(diag_path), img)

def main():
    gcps_by_cam = load_all_gcps(GCP_CSV)
    results = []
    
    for cam_id, gcps in gcps_by_cam.items():
        res = calibrate_camera(cam_id, gcps)
        if res:
            results.append(res)
            
    print("\n--- Resumen Final ---")
    print(f"{'Cam':<6} | {'RMSE px':<8} | {'RMSE m':<8} | {'Val RMSE m':<10}")
    print("-" * 45)
    for r in results:
        print(f"CAM {r['cam_id']:<2} | {r['rmse_px']:<8.2f} | {r['rmse_m']:<8.2f} | {r['rmse_val_m']:<10.2f}")

if __name__ == "__main__":
    main()
