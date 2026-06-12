#!/usr/bin/env python3
"""
overlay_cameras.py - Mosaico de las 6 camaras con deteccion ORB

Uso:
  python overlay_cameras.py                    # mosaico con imagenes latest
  python overlay_cameras.py --match 1 2        # matching ORB entre CAM 1 y CAM 2
  python overlay_cameras.py --save             # guardar mosaico en output/
"""
import cv2
import numpy as np
import os
import argparse

BASE_DIR  = os.path.dirname(os.path.abspath(__file__))
DATA_DIR  = os.path.join(BASE_DIR, "data")
OUT_DIR   = os.path.join(BASE_DIR, "output")

CAMERAS = [
    {"name": "CAM 1", "id": "8213", "folder": "CAM_1", "file": "latest_8213.jpg"},
    {"name": "CAM 2", "id": "8214", "folder": "CAM_2", "file": "latest_8214.jpg"},
    {"name": "CAM 3", "id": "8212", "folder": "CAM_3", "file": "latest_8212.jpg"},
    {"name": "CAM 4", "id": "8211", "folder": "CAM_4", "file": "latest_8211.jpg"},
    {"name": "CAM 5", "id": "8209", "folder": "CAM_5", "file": "latest_8209.jpg"},
    {"name": "CAM 6", "id": "8210", "folder": "CAM_6", "file": "latest_8210.jpg"},
]

THUMB_W  = 640
THUMB_H  = 360
HEADER_H = 38
MARGIN   = 8
COLS     = 3
ROWS     = 2

_orb = cv2.ORB_create(nfeatures=400)


def _load_image(cam: dict) -> np.ndarray:
    path = os.path.join(DATA_DIR, cam["folder"], cam["file"])
    img  = cv2.imread(path)
    if img is None:
        img = np.full((THUMB_H, THUMB_W, 3), 60, dtype=np.uint8)
        cv2.putText(img, "NO DISPONIBLE", (30, THUMB_H // 2),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (80, 80, 220), 2)
    return cv2.resize(img, (THUMB_W, THUMB_H))


def _detect_orb(img: np.ndarray):
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    # Ignorar franja inferior (posible watermark)
    mask = np.ones(gray.shape, dtype=np.uint8) * 255
    mask[-35:, :] = 0
    return _orb.detectAndCompute(gray, mask)


def _make_cell(cam: dict) -> np.ndarray:
    img = _load_image(cam)
    kp, _  = _detect_orb(img)
    vis = cv2.drawKeypoints(img, kp, None, color=(0, 255, 80),
                            flags=cv2.DRAW_MATCHES_FLAGS_DRAW_RICH_KEYPOINTS)
    header = np.full((HEADER_H, THUMB_W, 3), 25, dtype=np.uint8)
    label  = f"{cam['name']}  (id {cam['id']})  -  {len(kp)} features"
    cv2.putText(header, label, (10, 25),
                cv2.FONT_HERSHEY_SIMPLEX, 0.58, (0, 220, 220), 1, cv2.LINE_AA)
    return np.vstack([header, vis])


def build_mosaic() -> np.ndarray:
    cells = [_make_cell(c) for c in CAMERAS]
    cell_h = cells[0].shape[0]
    cell_w = cells[0].shape[1]

    canvas_w = COLS * cell_w + (COLS - 1) * MARGIN
    canvas_h = ROWS * cell_h + (ROWS - 1) * MARGIN + 55
    canvas   = np.full((canvas_h, canvas_w, 3), 15, dtype=np.uint8)

    cv2.putText(canvas, "cv-lit - Mosaico de camaras con ORB features",
                (20, 38), cv2.FONT_HERSHEY_SIMPLEX, 0.85, (255, 255, 255), 2, cv2.LINE_AA)

    for i, cell in enumerate(cells):
        r, c  = divmod(i, COLS)
        y_off = 55 + r * (cell_h + MARGIN)
        x_off = c * (cell_w + MARGIN)
        canvas[y_off:y_off + cell_h, x_off:x_off + cell_w] = cell

    return canvas


def show_matching(idx_a: int, idx_b: int) -> np.ndarray:
    cam_a, cam_b = CAMERAS[idx_a - 1], CAMERAS[idx_b - 1]
    img_a = _load_image(cam_a)
    img_b = _load_image(cam_b)

    kp_a, des_a = _detect_orb(img_a)
    kp_b, des_b = _detect_orb(img_b)

    if des_a is None or des_b is None:
        print("No se pudieron calcular descriptores.")
        return np.zeros((100, 100, 3), dtype=np.uint8)

    bf      = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)
    matches = sorted(bf.match(des_a, des_b), key=lambda m: m.distance)
    top50   = matches[:50]

    vis = cv2.drawMatches(img_a, kp_a, img_b, kp_b, top50, None,
                          matchColor=(0, 255, 100),
                          singlePointColor=(200, 200, 0),
                          flags=cv2.DrawMatchesFlags_NOT_DRAW_SINGLE_POINTS)

    header = np.full((40, vis.shape[1], 3), 20, dtype=np.uint8)
    label  = (f"Matching ORB: {cam_a['name']} vs {cam_b['name']}"
              f"  -  {len(top50)} matches (de {len(matches)} totales)")
    cv2.putText(header, label, (12, 26),
                cv2.FONT_HERSHEY_SIMPLEX, 0.62, (0, 220, 220), 1, cv2.LINE_AA)
    return np.vstack([header, vis])


def _show(title: str, img: np.ndarray, save: bool = False, filename: str = "output.jpg"):
    if save:
        os.makedirs(OUT_DIR, exist_ok=True)
        out = os.path.join(OUT_DIR, filename)
        cv2.imwrite(out, img)
        print(f"Guardado en: {out}")

    h, w = img.shape[:2]
    win_w = min(1800, w)
    win_h = int(win_w * h / w)

    cv2.namedWindow(title, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(title, win_w, win_h)
    cv2.imshow(title, img)
    print("Presiona cualquier tecla para cerrar.")
    cv2.waitKey(0)
    cv2.destroyAllWindows()


def main():
    ap = argparse.ArgumentParser(description="Overlay y analisis de camaras")
    ap.add_argument("--match", nargs=2, type=int, metavar=("A", "B"),
                    help="Mostrar matching ORB entre CAM A y CAM B (1-6)")
    ap.add_argument("--save", action="store_true", help="Guardar imagen en output/")
    args = ap.parse_args()

    if args.match:
        a, b = args.match
        if not (1 <= a <= 6 and 1 <= b <= 6):
            print("Los indices de camara deben estar entre 1 y 6.")
            return
        img = show_matching(a, b)
        _show(f"Matching CAM {a} vs CAM {b}", img, args.save,
              f"matching_cam{a}_cam{b}.jpg")
    else:
        img = build_mosaic()
        _show("Mosaico camaras - ESC/tecla para cerrar", img, args.save,
              "mosaic_cameras.jpg")


if __name__ == "__main__":
    main()
