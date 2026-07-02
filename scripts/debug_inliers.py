#!/usr/bin/env python3
"""
debug_inliers.py — Pinta los inliers SIFT entre imagen de referencia e imagen nueva.

Genera tres ficheros en el directorio de salida:
  matches.jpg   → par de imágenes con líneas entre inliers (verde) y outliers (rojo)
  keypoints.jpg → keypoints detectados en cada imagen por separado
  blend.jpg     → referencia + imagen alineada al 50% para ver el desplazamiento

Uso:
    python scripts/debug_inliers.py --ref IMAGEN_REF.jpg --img IMAGEN_NUEVA.jpg
    python scripts/debug_inliers.py --ref ref.jpg --img nueva.jpg --cam 1 --out /tmp/debug
    python scripts/debug_inliers.py --ref ref.jpg --img nueva.jpg --cam 2 --no-clahe
"""

import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

# ── Configuración (mismos valores que align_images.py) ─────────────────────
SIFT_FEATURES = 3000
LOWE_RATIO    = 0.75
RANSAC_THRESH = 5.0
MASKS_PATH    = ROOT / "calibration" / "alignment_masks.json"


def build_mask(cam_id: int, h: int, w: int):
    if not MASKS_PATH.exists():
        return None
    with open(MASKS_PATH) as f:
        cfg = json.load(f)
    key = f"CAM_{cam_id}"
    if key not in cfg:
        return None
    canvas = np.zeros((h, w), dtype=np.uint8)
    for r in cfg[key]["regions"]:
        x0, y0 = int(r["x0"] * w), int(r["y0"] * h)
        x1, y1 = int(r["x1"] * w), int(r["y1"] * h)
        cv2.rectangle(canvas, (x0, y0), (x1, y1), 255, -1)
    return canvas

def check_lighting(gray: np.ndarray) -> tuple[bool, str]:
    mean, std = float(np.mean(gray)), float(np.std(gray))
    if mean > 200: return False, f"overexposed (mean={mean:.1f})"
    if mean < 30:  return False, f"underexposed (mean={mean:.1f})"
    if std < 18:   return False, f"low_contrast (std={std:.1f})"
    return True, f"ok (mean={mean:.1f}, std={std:.1f})"


def run(ref_path: Path, img_path: Path, cam_id: int | None, out_dir: Path, use_clahe: bool):
    out_dir.mkdir(parents=True, exist_ok=True)

    ref_bgr = cv2.imread(str(ref_path))
    img_bgr = cv2.imread(str(img_path))
    if ref_bgr is None: sys.exit(f"No se pudo leer: {ref_path}")
    if img_bgr is None: sys.exit(f"No se pudo leer: {img_path}")

    ref_gray = cv2.cvtColor(ref_bgr, cv2.COLOR_BGR2GRAY)
    img_gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)

    # ── Comprobación de iluminación ──────────────────────────────────────────
    ok_ref, info_ref = check_lighting(ref_gray)
    ok_img, info_img = check_lighting(img_gray)
    print(f"  Referencia  → iluminación {info_ref}")
    print(f"  Imagen nueva → iluminación {info_img}")
    if not ok_img:
        print(f"  [WARNING] Imagen nueva tiene iluminación problemática: {info_img}")

    # ── CLAHE ────────────────────────────────────────────────────────────────
    if use_clahe:
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        ref_gray = clahe.apply(ref_gray)
        img_gray = clahe.apply(img_gray)
        print("  CLAHE aplicado")

    h, w = ref_gray.shape

    # ── Máscara de zonas estables ────────────────────────────────────────────
    mask = build_mask(cam_id, h, w) if cam_id else None
    if mask is not None:
        print(f"  Máscara activa para CAM_{cam_id}")
        # Pintar máscara sobre la referencia para debug visual
        mask_vis = ref_bgr.copy()
        mask_vis[mask == 0] = (mask_vis[mask == 0] * 0.35).astype(np.uint8)
        cv2.imwrite(str(out_dir / "mascara.jpg"), mask_vis)
        print(f"  → mascara.jpg guardada")
    else:
        print("  Sin máscara (imagen completa)")

    # ── SIFT ─────────────────────────────────────────────────────────────────
    sift = cv2.SIFT_create(nfeatures=SIFT_FEATURES)

    img_mask_scaled = None
    if mask is not None:
        img_mask_scaled = cv2.resize(mask, (img_gray.shape[1], img_gray.shape[0]),
                                     interpolation=cv2.INTER_NEAREST)

    ref_kp, ref_des = sift.detectAndCompute(ref_gray, mask)
    img_kp, img_des = sift.detectAndCompute(img_gray, img_mask_scaled)

    print(f"  Keypoints ref: {len(ref_kp)}  |  img: {len(img_kp)}")

    if img_des is None or len(img_kp) < 8:
        sys.exit("  [ERROR] Muy pocos keypoints en la imagen nueva")

    # ── Matching + ratio test de Lowe ────────────────────────────────────────
    flann = cv2.FlannBasedMatcher({"algorithm": 1, "trees": 5}, {"checks": 50})
    raw   = flann.knnMatch(ref_des, img_des, k=2)
    good  = [m for m, n in raw if m.distance < LOWE_RATIO * n.distance]
    print(f"  Matches tras ratio test: {len(good)}")

    # ── RANSAC ───────────────────────────────────────────────────────────────
    src = np.float32([ref_kp[m.queryIdx].pt for m in good]).reshape(-1, 1, 2)
    dst = np.float32([img_kp[m.trainIdx].pt for m in good]).reshape(-1, 1, 2)
    H, hmask = cv2.findHomography(dst, src, cv2.RANSAC, RANSAC_THRESH)

    inliers  = int(hmask.ravel().sum()) if hmask is not None else 0
    outliers = len(good) - inliers
    ratio    = inliers / len(good) * 100 if good else 0
    print(f"  Inliers: {inliers}  |  Outliers: {outliers}  |  Ratio: {ratio:.1f}%")

    # ── Imagen 1: matches coloreados (verde=inlier, rojo=outlier) ───────────
    mask_list = hmask.ravel().tolist() if hmask is not None else [0] * len(good)
    matches_img = cv2.drawMatches(
        ref_bgr, ref_kp, img_bgr, img_kp, good, None,
        matchColor=(0, 220, 0),         # verde → inlier
        singlePointColor=(200, 200, 200),
        matchesMask=mask_list,
        flags=cv2.DrawMatchesFlags_NOT_DRAW_SINGLE_POINTS,
    )
    # Superponer outliers en rojo
    outlier_mask = [1 - v for v in mask_list]
    matches_img = cv2.drawMatches(
        ref_bgr, ref_kp, img_bgr, img_kp, good, matches_img,
        matchColor=(0, 0, 220),         # rojo → outlier
        singlePointColor=(200, 200, 200),
        matchesMask=outlier_mask,
        flags=cv2.DrawMatchesFlags_DRAW_OVER_OUTIMG | cv2.DrawMatchesFlags_NOT_DRAW_SINGLE_POINTS,
    )
    _add_stats(matches_img, inliers, outliers, ratio, use_clahe)
    cv2.imwrite(str(out_dir / "matches.jpg"), matches_img, [cv2.IMWRITE_JPEG_QUALITY, 92])
    print(f"  → matches.jpg guardada")

    # ── Imagen 2: keypoints por separado ─────────────────────────────────────
    ref_kp_img = cv2.drawKeypoints(ref_bgr, ref_kp, None,
                                   color=(0, 180, 255),
                                   flags=cv2.DRAW_MATCHES_FLAGS_DRAW_RICH_KEYPOINTS)
    img_kp_img = cv2.drawKeypoints(img_bgr, img_kp, None,
                                   color=(0, 180, 255),
                                   flags=cv2.DRAW_MATCHES_FLAGS_DRAW_RICH_KEYPOINTS)
    # Pintar solo inliers encima en verde
    inlier_ref_pts = [ref_kp[good[i].queryIdx] for i, v in enumerate(mask_list) if v]
    inlier_img_pts = [img_kp[good[i].trainIdx] for i, v in enumerate(mask_list) if v]
    ref_kp_img = cv2.drawKeypoints(ref_kp_img, inlier_ref_pts, None,
                                   color=(0, 255, 80),
                                   flags=cv2.DRAW_MATCHES_FLAGS_DRAW_RICH_KEYPOINTS)
    img_kp_img = cv2.drawKeypoints(img_kp_img, inlier_img_pts, None,
                                   color=(0, 255, 80),
                                   flags=cv2.DRAW_MATCHES_FLAGS_DRAW_RICH_KEYPOINTS)
    cv2.putText(ref_kp_img, f"REF  kp={len(ref_kp)}", (20, 50),
                cv2.FONT_HERSHEY_SIMPLEX, 1.4, (0, 0, 0), 4)
    cv2.putText(ref_kp_img, f"REF  kp={len(ref_kp)}", (20, 50),
                cv2.FONT_HERSHEY_SIMPLEX, 1.4, (255, 255, 255), 2)
    cv2.putText(img_kp_img, f"IMG  kp={len(img_kp)}  inliers={inliers}", (20, 50),
                cv2.FONT_HERSHEY_SIMPLEX, 1.4, (0, 0, 0), 4)
    cv2.putText(img_kp_img, f"IMG  kp={len(img_kp)}  inliers={inliers}", (20, 50),
                cv2.FONT_HERSHEY_SIMPLEX, 1.4, (255, 255, 255), 2)
    kp_side = np.hstack([
        cv2.resize(ref_kp_img, (w // 2, h // 2)),
        cv2.resize(img_kp_img, (w // 2, h // 2)),
    ])
    cv2.imwrite(str(out_dir / "keypoints.jpg"), kp_side, [cv2.IMWRITE_JPEG_QUALITY, 92])
    print(f"  → keypoints.jpg guardada")

    if H is not None:
        aligned = cv2.warpPerspective(img_bgr, H, (w, h))

        # Puntos inliers en coordenadas de la referencia
        inlier_pts_ref = [
            (int(ref_kp[good[i].queryIdx].pt[0]), int(ref_kp[good[i].queryIdx].pt[1]))
            for i, v in enumerate(mask_list) if v
        ]
        outlier_pts_ref = [
            (int(ref_kp[good[i].queryIdx].pt[0]), int(ref_kp[good[i].queryIdx].pt[1]))
            for i, v in enumerate(mask_list) if not v
        ]

        # ── Imagen 3: blend + inliers/outliers pintados encima ───────────────
        # Verde = inlier (RANSAC lo acepta como correspondencia válida)
        # Rojo  = outlier (match descartado por RANSAC)
        # Así se ve a la vez el desplazamiento visual Y dónde confía SIFT
        blend = cv2.addWeighted(ref_bgr, 0.5, aligned, 0.5, 0)
        for pt in outlier_pts_ref:
            cv2.circle(blend, pt, 10, (0, 0, 220), 2)   # rojo → outlier
            cv2.drawMarker(blend, pt, (0, 0, 220), cv2.MARKER_CROSS, 12, 2)
        for pt in inlier_pts_ref:
            cv2.circle(blend, pt, 10, (0, 220, 0), 2)   # verde → inlier
            cv2.drawMarker(blend, pt, (0, 220, 0), cv2.MARKER_CROSS, 12, 2)
        _add_stats(blend, inliers, outliers, ratio, use_clahe)
        cv2.imwrite(str(out_dir / "blend_inliers.jpg"), blend, [cv2.IMWRITE_JPEG_QUALITY, 92])
        print(f"  → blend_inliers.jpg guardada  (verde=inlier, rojo=outlier sobre blend ref+alineada)")

        # ── Imagen 4: mapa de diferencias + inliers/outliers pintados encima ─
        # Negro = zonas perfectamente alineadas, colores = diferencia entre imágenes
        # Los puntos muestran si los inliers están en zonas bien alineadas o no
        diff_abs  = np.abs(ref_bgr.astype(np.float32) - aligned.astype(np.float32)).mean(axis=2)
        diff_norm = cv2.normalize(diff_abs, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
        diff_map  = cv2.applyColorMap(diff_norm, cv2.COLORMAP_HOT)
        for pt in outlier_pts_ref:
            cv2.circle(diff_map, pt, 10, (255, 255, 0), 2)   # cian → outlier
            cv2.drawMarker(diff_map, pt, (255, 255, 0), cv2.MARKER_CROSS, 12, 2)
        for pt in inlier_pts_ref:
            cv2.circle(diff_map, pt, 10, (0, 220, 0), 2)     # verde → inlier
            cv2.drawMarker(diff_map, pt, (0, 220, 0), cv2.MARKER_CROSS, 12, 2)
        _add_stats(diff_map, inliers, outliers, ratio, use_clahe)
        cv2.imwrite(str(out_dir / "diff_inliers.jpg"), diff_map, [cv2.IMWRITE_JPEG_QUALITY, 92])
        print(f"  → diff_inliers.jpg guardada  (negro=alineado, rojo/blanco=diferencia)")

        # ── Imagen 5 y 6: base y alineada como ficheros separados ───────────
        base_out    = ref_bgr.copy()
        aligned_out = aligned.copy()
        _label(base_out,    "BASE (referencia)")
        _label(aligned_out, f"ALINEADA  inliers={inliers}  ratio={ratio:.1f}%")
        cv2.imwrite(str(out_dir / "base.jpg"),    base_out,    [cv2.IMWRITE_JPEG_QUALITY, 92])
        cv2.imwrite(str(out_dir / "alineada.jpg"), aligned_out, [cv2.IMWRITE_JPEG_QUALITY, 92])
        print(f"  → base.jpg guardada")
        print(f"  → alineada.jpg guardada")

    print(f"\n  Ficheros en: {out_dir}/")


def _label(img, text):
    cv2.putText(img, text, (16, 44), cv2.FONT_HERSHEY_SIMPLEX, 1.1, (0, 0, 0), 4)
    cv2.putText(img, text, (16, 44), cv2.FONT_HERSHEY_SIMPLEX, 1.1, (255, 255, 255), 2)


def _add_stats(img, inliers, outliers, ratio, clahe):
    txt = f"inliers={inliers}  outliers={outliers}  ratio={ratio:.1f}%"
    if clahe:
        txt += "  [CLAHE ON]"
    cv2.putText(img, txt, (20, img.shape[0] - 20),
                cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 0, 0), 4)
    cv2.putText(img, txt, (20, img.shape[0] - 20),
                cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 255, 200), 2)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Debug visual de inliers SIFT entre dos imágenes")
    ap.add_argument("--ref",      required=True,  type=Path, help="Imagen de referencia")
    ap.add_argument("--img",      required=True,  type=Path, help="Imagen nueva a comparar")
    ap.add_argument("--cam",      default=None,   type=int,  help="ID cámara (1-6) para aplicar máscara")
    ap.add_argument("--out",      default="/tmp/debug_inliers", type=Path, help="Directorio de salida")
    ap.add_argument("--no-clahe", action="store_true", help="Desactivar CLAHE (para comparar el efecto)")
    args = ap.parse_args()

    print(f"\n── Debug inliers SIFT ──")
    print(f"  Ref : {args.ref}")
    print(f"  Img : {args.img}")
    print(f"  Cam : {args.cam or 'sin máscara'}")
    print(f"  CLAHE: {'OFF' if args.no_clahe else 'ON'}\n")

    run(args.ref, args.img, args.cam, args.out, use_clahe=not args.no_clahe)
