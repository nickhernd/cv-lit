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
        self.gcps: list[dict] = []   # [{pixel:[u,v], utm:[X,Y], label:"GCP_01"}]
        self.H: np.ndarray | None = None
        self.rmse_px: float = -1.0
        self.rmse_m:  float = -1.0

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
            "rmse_px":   round(self.rmse_px, 4),
            "rmse_m":    round(self.rmse_m,  4),
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

    def compute_homography(self) -> bool:
        if len(self.gcps) < 4:
            print(f"Faltan GCPs: {len(self.gcps)}/4 mínimo.")
            return False

        pts_px  = np.array([[g["pixel"][0], g["pixel"][1]] for g in self.gcps],
                           dtype=np.float32)
        pts_utm = np.array([[g["utm"][0],   g["utm"][1]]   for g in self.gcps],
                           dtype=np.float32)

        H, mask = cv2.findHomography(pts_px, pts_utm,
                                     cv2.RANSAC, ransacReprojThreshold=5.0)
        if H is None:
            print("RANSAC no pudo estimar la homografía.")
            return False

        self.H = H
        inliers = int(mask.sum()) if mask is not None else len(self.gcps)

        # RMSE en píxeles (reproyección inversa UTM→pixel)
        H_inv, _ = cv2.invert(H)
        reproj   = cv2.perspectiveTransform(pts_utm.reshape(-1, 1, 2), H_inv)
        reproj   = reproj.reshape(-1, 2)
        errors   = np.linalg.norm(reproj - pts_px, axis=1)
        self.rmse_px = float(np.sqrt(np.mean(errors ** 2)))

        # RMSE en metros (proyección pixel→UTM)
        proj_utm = cv2.perspectiveTransform(pts_px.reshape(-1, 1, 2), H)
        proj_utm = proj_utm.reshape(-1, 2)
        errors_m = np.linalg.norm(proj_utm - pts_utm, axis=1)
        self.rmse_m = float(np.sqrt(np.mean(errors_m ** 2)))

        print(f"\n  Homografía calculada  ({inliers}/{len(self.gcps)} inliers)")
        print(f"  RMSE reproyección : {self.rmse_px:.3f} px  "
              f"({'OK' if self.rmse_px < 2.0 else 'ALTO — revisar GCPs'})")
        print(f"  RMSE geométrico   : {self.rmse_m:.3f} m  "
              f"({'OK' if self.rmse_m < 1.5 else 'ALTO — revisar GCPs'})")
        return True

    # ------------------------------------------------------------------
    # Visualización
    # ------------------------------------------------------------------

    def _render(self):
        self.display = self.img_orig.copy()
        h, w = self.display.shape[:2]

        for i, gcp in enumerate(self.gcps):
            u, v   = int(gcp["pixel"][0]), int(gcp["pixel"][1])
            label  = gcp.get("label", f"GCP_{i+1:02d}")
            cv2.circle(self.display, (u, v), 8, COLORS["gcp"], 2)
            cv2.circle(self.display, (u, v), 2, COLORS["gcp"], -1)
            cv2.putText(self.display, label, (u + 10, v - 6),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, COLORS["text"], 1, cv2.LINE_AA)

            # Reproyección (si H existe)
            if self.H is not None:
                H_inv, _ = cv2.invert(self.H)
                pt_utm  = np.array([[[gcp["utm"][0], gcp["utm"][1]]]], dtype=np.float32)
                rep_px  = cv2.perspectiveTransform(pt_utm, H_inv).reshape(2)
                ru, rv  = int(rep_px[0]), int(rep_px[1])
                cv2.circle(self.display, (ru, rv), 6, COLORS["reproj"], 2)
                cv2.line(self.display, (u, v), (ru, rv), COLORS["reproj"], 1)

        # Panel de estado (esquina superior izquierda)
        lines = [
            f"Camara : {self.cam['name']}  (id {self.cam['id']})",
            f"GCPs   : {len(self.gcps)}  (min 4, rec. 8+)",
            f"RMSE   : {self.rmse_px:.2f} px / {self.rmse_m:.2f} m"
              if self.H is not None else "RMSE   : (sin calibrar)",
            "",
            "Click  → añadir GCP",
            "'h'    → calcular homografia",
            "'s'    → guardar perfil",
            "'r'    → deshacer ultimo",
            "'q'    → salir",
        ]
        panel_w = 340
        panel_h = len(lines) * 22 + 16
        overlay = self.display.copy()
        cv2.rectangle(overlay, (6, 6), (panel_w, panel_h), COLORS["panel"], -1)
        cv2.addWeighted(overlay, 0.75, self.display, 0.25, 0, self.display)
        for j, line in enumerate(lines):
            color = (80, 220, 80) if line.startswith("RMSE") and self.H is not None \
                    else COLORS["text"]
            cv2.putText(self.display, line, (14, 26 + j * 22),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1, cv2.LINE_AA)

    # ------------------------------------------------------------------
    # Bucle principal
    # ------------------------------------------------------------------

    def _mouse_callback(self, event, x, y, flags, param):
        if event != cv2.EVENT_LBUTTONDOWN:
            return

        label = f"GCP_{len(self.gcps) + 1:02d}"
        print(f"\n  Punto {label} en pixel ({x}, {y})")
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

        # Validación básica: bbox Guardamar del Segura en EPSG:25830
        if not (690000 < X < 740000 and 4195000 < Y < 4230000):
            print(f"  Advertencia: ({X:.1f}, {Y:.1f}) parece estar fuera del "
                  f"area de Guardamar del Segura. Añadido de todas formas.")

        self.gcps.append({"pixel": [x, y], "utm": [X, Y], "label": label})
        print(f"  GCP añadido: {label} → pixel({x},{y}) UTM({X:.2f},{Y:.2f})")
        self._render()
        cv2.imshow(self._win_name, self.display)

    def run(self):
        self._win_name = f"Calibración — {self.cam['name']}"
        self._render()

        cv2.namedWindow(self._win_name, cv2.WINDOW_NORMAL)
        h, w = self.display.shape[:2]
        cv2.resizeWindow(self._win_name, min(1280, w), min(720, int(min(1280, w) * h / w)))
        cv2.setMouseCallback(self._win_name, self._mouse_callback)
        cv2.imshow(self._win_name, self.display)

        print(f"\n=== Calibración {self.cam['name']} ===")
        print(f"  Imagen: {self.img_path}")
        print(f"  GCPs cargados: {len(self.gcps)}")
        print("  Click en la imagen para añadir puntos GCP.\n")

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
