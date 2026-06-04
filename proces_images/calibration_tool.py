#!/usr/bin/env python3
"""
calibration_tool.py — Herramienta interactiva de calibración píxel↔UTM

Flujo:
  1. Cargar imagen de referencia de una cámara
  2. Click izquierdo → marcar punto GCP en la imagen
  3. Introducir coordenadas UTM (X Y) por terminal
  4. Repetir hasta tener ≥4 pares (recomendado ≥8)
  5. Pulsar 'h' → calcular homografía con RANSAC + mostrar RMSE
  6. Pulsar 's' → guardar perfil en calibration/
  7. Pulsar 'r' → deshacer último punto
  8. Pulsar 'q' → salir

Uso:
  python calibration_tool.py --cam 1
  python calibration_tool.py --cam 3 --image /ruta/imagen.jpg
  python calibration_tool.py --cam 1 --load   # cargar GCPs existentes
"""
import cv2
import numpy as np
import json
import os
import argparse
from datetime import date

BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
DATA_DIR   = os.path.join(BASE_DIR, "data")
CALIB_DIR  = os.path.join(os.path.dirname(BASE_DIR), "calibration")

CAMERAS = {
    1: {"name": "CAM 1", "id": "8213", "serial": "PTM61471",
        "folder": "CAM_1", "file": "latest_8213.jpg"},
    2: {"name": "CAM 2", "id": "8214", "serial": "PTM61474",
        "folder": "CAM_2", "file": "latest_8214.jpg"},
    3: {"name": "CAM 3", "id": "8212", "serial": "PTM61473",
        "folder": "CAM_3", "file": "latest_8212.jpg"},
    4: {"name": "CAM 4", "id": "8211", "serial": "PTM61475",
        "folder": "CAM_4", "file": "latest_8211.jpg"},
    5: {"name": "CAM 5", "id": "8209", "serial": "PTM61472",
        "folder": "CAM_5", "file": "latest_8209.jpg"},
    6: {"name": "CAM 6", "id": "8210", "serial": "PTM61470",
        "folder": "CAM_6", "file": "latest_8210.jpg"},
}

COLORS = {
    "gcp":       (0, 255, 100),
    "validated": (255, 200, 0),
    "reproj":    (0, 80, 255),
    "text":      (255, 255, 255),
    "panel":     (20, 20, 20),
}


class CalibrationTool:
    def __init__(self, cam_idx: int, image_path: str | None = None):
        self.cam      = CAMERAS[cam_idx]
        self.cam_idx  = cam_idx
        self.gcps: list[dict] = []   # [{pixel:[u,v], utm:[X,Y], label:"GCP_01", type:"calib"}]
        self.H: np.ndarray | None = None
        self.rmse_px: float = -1.0
        self.rmse_m:  float = -1.0
        self.rmse_val_px: float = -1.0
        self.rmse_val_m:  float = -1.0

        # Parámetros intrínsecos (Issue #29)
        self.K = np.eye(3, dtype=np.float64)
        self.D = np.zeros(5, dtype=np.float64)
        self.use_undistort = False

        if image_path:
            self.img_path = image_path
        else:
            self.img_path = os.path.join(DATA_DIR, self.cam["folder"], self.cam["file"])

        img = cv2.imread(self.img_path)
        if img is None:
            raise FileNotFoundError(f"No se encontró la imagen: {self.img_path}")
        self.img_orig = img.copy()
        self.display  = img.copy()

    # ------------------------------------------------------------------
    # Persistencia
    # ------------------------------------------------------------------

    def profile_path(self) -> str:
        os.makedirs(CALIB_DIR, exist_ok=True)
        return os.path.join(CALIB_DIR, f"cam_{self.cam_idx}_profile.json")

    def load_intrinsics(self, path: str) -> bool:
        """Carga parámetros K y D de un JSON."""
        if not os.path.exists(path):
            return False
        try:
            with open(path) as f:
                data = json.load(f)
            self.K = np.array(data["K"], dtype=np.float64)
            self.D = np.array(data["D"], dtype=np.float64)
            self.use_undistort = True
            print(f"Intrínsecos cargados desde {path}")
            return True
        except Exception as e:
            print(f"Error cargando intrínsecos: {e}")
            return False

    def load_gcps(self) -> bool:
        path = self.profile_path()
        if not os.path.exists(path):
            print(f"No hay perfil previo en {path}")
            return False
        with open(path) as f:
            data = json.load(f)
        self.gcps = data.get("gcps", [])
        H_list    = data.get("H")
        if H_list:
            self.H       = np.array(H_list, dtype=np.float64)
            self.rmse_px = data.get("rmse_px", -1.0)
            self.rmse_m  = data.get("rmse_m",  -1.0)
            self.rmse_val_px = data.get("rmse_val_px", -1.0)
            self.rmse_val_m  = data.get("rmse_val_m",  -1.0)
        
        # Cargar intrínsecos si existen en el perfil
        if "K" in data and "D" in data:
            self.K = np.array(data["K"], dtype=np.float64)
            self.D = np.array(data["D"], dtype=np.float64)
            self.use_undistort = True

        print(f"Perfil cargado: {len(self.gcps)} GCPs, RMSE={self.rmse_px:.2f}px")
        return True

    def save_profile(self):
        os.makedirs(CALIB_DIR, exist_ok=True)
        data = {
            "cam_id":    self.cam_idx,
            "cam_name":  self.cam["name"],
            "device_id": self.cam["id"],
            "serial":    self.cam["serial"],
            "image_ref": self.img_path,
            "gcps":      self.gcps,
            "H":         self.H.tolist() if self.H is not None else None,
            "K":         self.K.tolist(),
            "D":         self.D.tolist(),
            "rmse_px":     round(self.rmse_px, 4),
            "rmse_m":      round(self.rmse_m,  4),
            "rmse_val_px": round(self.rmse_val_px, 4),
            "rmse_val_m":  round(self.rmse_val_m,  4),
            "n_gcps":    len(self.gcps),
            "date":      str(date.today()),
            "epsg":      25830,
        }
        path = self.profile_path()
        with open(path, "w") as f:
            json.dump(data, f, indent=2)

        # También guardar H como .npy para uso directo en OpenCV
        if self.H is not None:
            npy_path = path.replace("_profile.json", "_H.npy")
            np.save(npy_path, self.H)
            print(f"  Matriz H guardada: {npy_path}")

        print(f"Perfil guardado: {path}")

    # ------------------------------------------------------------------
    # Calibración
    # ------------------------------------------------------------------

    def undistort_points(self, pts_px: np.ndarray) -> np.ndarray:
        """Aplica corrección de distorsión a puntos en píxeles."""
        if not self.use_undistort:
            return pts_px
        pts_reshaped = pts_px.reshape(-1, 1, 2).astype(np.float32)
        undistorted  = cv2.undistortPoints(pts_reshaped, self.K, self.D, P=self.K)
        return undistorted.reshape(-1, 2)

    def compute_homography(self) -> bool:
        # Separar puntos de calibración y validación (Issue #31)
        calib_gcps = [g for g in self.gcps if g.get("type", "calib") == "calib"]
        val_gcps   = [g for g in self.gcps if g.get("type") == "val"]

        if len(calib_gcps) < 4:
            print(f"Faltan GCPs de calibración: {len(calib_gcps)}/4 mínimo.")
            return False

        pts_px_orig  = np.array([[g["pixel"][0], g["pixel"][1]] for g in calib_gcps],
                                dtype=np.float32)
        pts_utm = np.array([[g["utm"][0],   g["utm"][1]]   for g in calib_gcps],
                           dtype=np.float32)

        # Corregir distorsión si aplica (Issue #29)
        pts_px = self.undistort_points(pts_px_orig)

        H, mask = cv2.findHomography(pts_px, pts_utm,
                                     cv2.RANSAC, ransacReprojThreshold=5.0)
        if H is None:
            print("RANSAC no pudo estimar la homografía.")
            return False

        self.H = H
        inliers = int(mask.sum()) if mask is not None else len(calib_gcps)

        # RMSE Calibración
        H_inv, _ = cv2.invert(H)
        proj_utm = cv2.perspectiveTransform(pts_px.reshape(-1, 1, 2), H).reshape(-1, 2)
        self.rmse_m = float(np.sqrt(np.mean(np.linalg.norm(proj_utm - pts_utm, axis=1)**2)))
        
        reproj_px = cv2.perspectiveTransform(pts_utm.reshape(-1, 1, 2), H_inv).reshape(-1, 2)
        self.rmse_px = float(np.sqrt(np.mean(np.linalg.norm(reproj_px - pts_px, axis=1)**2)))

        # RMSE Validación (Issue #31)
        if val_gcps:
            vpts_px_orig = np.array([[g["pixel"][0], g["pixel"][1]] for g in val_gcps], dtype=np.float32)
            vpts_utm     = np.array([[g["utm"][0],   g["utm"][1]]   for g in val_gcps], dtype=np.float32)
            vpts_px      = self.undistort_points(vpts_px_orig)
            
            vproj_utm = cv2.perspectiveTransform(vpts_px.reshape(-1, 1, 2), H).reshape(-1, 2)
            self.rmse_val_m = float(np.sqrt(np.mean(np.linalg.norm(vproj_utm - vpts_utm, axis=1)**2)))
            
            vrep_px = cv2.perspectiveTransform(vpts_utm.reshape(-1, 1, 2), H_inv).reshape(-1, 2)
            self.rmse_val_px = float(np.sqrt(np.mean(np.linalg.norm(vrep_px - vpts_px, axis=1)**2)))
        else:
            self.rmse_val_px = -1.0
            self.rmse_val_m  = -1.0

        print(f"\n  Homografía calculada  ({inliers}/{len(calib_gcps)} inliers)")
        print(f"  RMSE Calib : {self.rmse_px:.3f} px / {self.rmse_m:.3f} m")
        if val_gcps:
            print(f"  RMSE Valid : {self.rmse_val_px:.3f} px / {self.rmse_val_m:.3f} m")
        return True

    # ------------------------------------------------------------------
    # Visualización
    # ------------------------------------------------------------------

    def _render(self):
        self.display = self.img_orig.copy()
        h, w = self.display.shape[:2]

        for i, gcp in enumerate(self.gcps):
            u, v   = int(gcp["pixel"][0]), int(gcp["pixel"][1])
            is_val = gcp.get("type") == "val"
            color  = (255, 100, 0) if is_val else COLORS["gcp"] # Azul para validación
            label  = gcp.get("label", f"GCP_{i+1:02d}")
            
            cv2.circle(self.display, (u, v), 8, color, 2)
            cv2.circle(self.display, (u, v), 2, color, -1)
            cv2.putText(self.display, label, (u + 10, v - 6),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, COLORS["text"], 1, cv2.LINE_AA)

            # Reproyección (si H existe)
            if self.H is not None:
                H_inv, _ = cv2.invert(self.H)
                pt_utm   = np.array([[[gcp["utm"][0], gcp["utm"][1]]]], dtype=np.float32)
                rep_px_undist = cv2.perspectiveTransform(pt_utm, H_inv).reshape(2)
                
                # Para visualizar sobre la imagen distorsionada original, 
                # en teoría deberíamos "redistorsionar" el punto, pero por ahora 
                # asumimos que la visualización es aproximada o la imagen ya está corregida.
                # Si use_undistort es True, los puntos dibujados estarán ligeramente desplazados
                # respecto a sus posiciones corregidas.
                ru, rv = int(rep_px_undist[0]), int(rep_px_undist[1])
                cv2.circle(self.display, (ru, rv), 6, COLORS["reproj"], 2)
                cv2.line(self.display, (u, v), (ru, rv), COLORS["reproj"], 1)

        # Panel de estado (esquina superior izquierda)
        n_cal = len([g for g in self.gcps if g.get("type", "calib") == "calib"])
        n_val = len([g for g in self.gcps if g.get("type") == "val"])
        
        lines = [
            f"Camara : {self.cam['name']}  (id {self.cam['id']})",
            f"GCPs   : {n_cal} calib / {n_val} val",
            f"Intrin : {'SI' if self.use_undistort else 'NO'}",
            f"RMSE C : {self.rmse_px:.2f} px / {self.rmse_m:.2f} m"
              if self.H is not None else "RMSE C : (sin calibrar)",
        ]
        if self.rmse_val_px >= 0:
            lines.append(f"RMSE V : {self.rmse_val_px:.2f} px / {self.rmse_val_m:.2f} m")
        
        lines += [
            "",
            "L-Click → añadir GCP CALIB",
            "R-Click → añadir GCP VALID",
            "'h'     → calcular homografia",
            "'s'     → guardar perfil",
            "'r'     → deshacer ultimo",
            "'q'     → salir",
        ]
        
        panel_w = 360
        panel_h = len(lines) * 22 + 16
        overlay = self.display.copy()
        cv2.rectangle(overlay, (6, 6), (panel_w, panel_h), COLORS["panel"], -1)
        cv2.addWeighted(overlay, 0.75, self.display, 0.25, 0, self.display)
        for j, line in enumerate(lines):
            color = (80, 220, 80) if (line.startswith("RMSE") or "Intrin" in line) and self.H is not None \
                    else COLORS["text"]
            cv2.putText(self.display, line, (14, 26 + j * 22),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1, cv2.LINE_AA)

    # ------------------------------------------------------------------
    # Bucle principal
    # ------------------------------------------------------------------

    def _mouse_callback(self, event, x, y, flags, param):
        if event not in [cv2.EVENT_LBUTTONDOWN, cv2.EVENT_RBUTTONDOWN]:
            return

        is_val = (event == cv2.EVENT_RBUTTONDOWN)
        type_str = "VALID" if is_val else "CALIB"
        
        label = f"GCP_{len(self.gcps) + 1:02d}"
        print(f"\n  Punto {type_str} {label} en pixel ({x}, {y})")
        print("  Introduce coordenadas UTM EPSG:25830  →  X Y  (o Enter para cancelar): ",
              end="", flush=True)

        try:
            raw = input().strip()
        except (EOFError, KeyboardInterrupt):
            return

        if not raw:
            print("  Cancelado.")
            return

        parts = raw.replace(",", " ").split()
        if len(parts) != 2:
            print("  Formato incorrecto. Usa: 711234.5 4209876.3")
            return

        try:
            X, Y = float(parts[0]), float(parts[1])
        except ValueError:
            print("  Valores no numéricos.")
            return

        self.gcps.append({
            "pixel": [x, y], 
            "utm": [X, Y], 
            "label": label, 
            "type": "val" if is_val else "calib"
        })
        print(f"  GCP añadido: {label} ({type_str}) → pixel({x},{y}) UTM({X:.2f},{Y:.2f})")
        self._render()
        cv2.imshow(self._win_name, self.display)

    def save_diagnostic_image(self):
        """Exporta una imagen con los errores de reproyección magnificados."""
        if self.H is None:
            return
        
        diag = self.img_orig.copy()
        H_inv, _ = cv2.invert(self.H)
        
        for gcp in self.gcps:
            u, v = gcp["pixel"]
            pt_utm = np.array([[[gcp["utm"][0], gcp["utm"][1]]]], dtype=np.float32)
            rep_px = cv2.perspectiveTransform(pt_utm, H_inv).reshape(2)
            ru, rv = int(rep_px[0]), int(rep_px[1])
            
            # Dibujar vector de error magnificado (x10 para visibilidad)
            mag = 10
            eu, ev = ru - u, rv - v
            cv2.line(diag, (u, v), (u + eu*mag, v + ev*mag), (0, 0, 255), 2)
            cv2.circle(diag, (u, v), 4, (0, 255, 0), -1)
            
        out_path = self.profile_path().replace("_profile.json", "_diagnostic.png")
        cv2.imwrite(out_path, diag)
        print(f"Imagen de diagnóstico guardada: {out_path}")

    def run(self):
        # Simplificar nombre para evitar problemas con algunos backends de GUI
        self._win_name = f"Calibration - {self.cam['name']}"
        self._render()

        cv2.namedWindow(self._win_name, cv2.WINDOW_NORMAL)
        h, w = self.display.shape[:2]
        cv2.resizeWindow(self._win_name, min(1280, w), min(720, int(min(1280, w) * h / w)))
        
        # Mostrar primero, luego configurar el raton (evita Null pointer)
        cv2.imshow(self._win_name, self.display)
        cv2.setMouseCallback(self._win_name, self._mouse_callback)

        print(f"\n=== Calibración {self.cam['name']} ===")
        print(f"  Imagen: {self.img_path}")
        print(f"  GCPs cargados: {len(self.gcps)}")
        print("  L-Click: añadir CALIB, R-Click: añadir VALID.\n")

        while True:
            key = cv2.waitKey(50) & 0xFF
            if key == ord('q'):
                break
            elif key == ord('h'):
                if self.compute_homography():
                    self._render()
                    cv2.imshow(self._win_name, self.display)
            elif key == ord('s'):
                if self.H is None:
                    print("Calcula primero la homografía con 'h'.")
                else:
                    self.save_profile()
            elif key == ord('p'):
                self.save_diagnostic_image()
            elif key == ord('r'):
                if self.gcps:
                    removed = self.gcps.pop()
                    print(f"  Eliminado: {removed['label']}")
                    self._render()
                    cv2.imshow(self._win_name, self.display)

        cv2.destroyAllWindows()


def main():
    ap = argparse.ArgumentParser(description="Herramienta de calibración píxel↔UTM")
    ap.add_argument("--cam",   type=int, required=True, choices=range(1, 7),
                    help="Índice de cámara (1–6)")
    ap.add_argument("--image", type=str, default=None,
                    help="Ruta a imagen de referencia (por defecto: latest de la cámara)")
    ap.add_argument("--load",  action="store_true",
                    help="Cargar GCPs existentes del perfil guardado")
    args = ap.parse_args()

    tool = CalibrationTool(args.cam, args.image)
    if args.load:
        tool.load_gcps()
    tool.run()


if __name__ == "__main__":
    main()
