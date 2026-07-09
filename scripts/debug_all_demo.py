#!/usr/bin/env python3
"""
debug_all_demo.py — Debug visual batch de alineación SIFT sobre imágenes de demo.

Procesa todas las imágenes en proces_images/CAM_X/images/ en pares consecutivos
y genera por cada par:
  matches.jpg         — líneas inlier (verde) / outlier (rojo) entre imágenes
  keypoints.jpg       — todos los keypoints y los inliers destacados
  blend_inliers.jpg   — blend 50%% ref+alineada con marcadores inlier/outlier
  diff_inliers.jpg    — mapa de diferencias + marcadores
  base.jpg            — imagen de referencia etiquetada
  alineada.jpg        — imagen alineada etiquetada
  homography.jpg      — imagen con la descomposición visual de la homografía:
                         ángulo de rotación, traslación (dx,dy), escala y flechas

Cada ejecución borra por completo el directorio de salida (debug_demo/) antes de
regenerarlo, salvo que se use --skip-existing.

Uso:
    python scripts/debug_all_demo.py
    python scripts/debug_all_demo.py --cams 1 2 5 --out /tmp/mi_debug
    python scripts/debug_all_demo.py --cams 1 --base proces_images/CAM_1/images/20260304_120000_8213.jpg
    python scripts/debug_all_demo.py --cams 1 --no-clahe --skip-existing
"""

import argparse
import json
import shutil
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT       = Path(__file__).parent.parent
DEMO_BASE  = ROOT / "proces_images"
MASKS_PATH = ROOT / "calibration" / "alignment_masks.json"

SIFT_FEATURES = 3000
LOWE_RATIO    = 0.75
RANSAC_THRESH = 5.0

ALL_CAMS = [1, 2, 3, 4, 5, 6]


# ── Máscara por cámara ───────────────────────────────────────────────────────

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


# ── Utilidades de texto ──────────────────────────────────────────────────────

def _put(img, text, pos, scale=1.1, color=(255, 255, 255)):
    cv2.putText(img, text, pos, cv2.FONT_HERSHEY_SIMPLEX, scale, (0, 0, 0), 4)
    cv2.putText(img, text, pos, cv2.FONT_HERSHEY_SIMPLEX, scale, color, 2)


def _add_stats(img, inliers, outliers, ratio, clahe):
    txt = f"inliers={inliers}  outliers={outliers}  ratio={ratio:.1f}%"
    if clahe:
        txt += "  [CLAHE]"
    _put(img, txt, (20, img.shape[0] - 20), scale=1.1)


# ── Comprobación de iluminación ──────────────────────────────────────────────

def check_lighting(gray):
    mean, std = float(np.mean(gray)), float(np.std(gray))
    if mean > 200: return False, f"overexposed mean={mean:.0f}"
    if mean < 30:  return False, f"underexposed mean={mean:.0f}"
    if std < 18:   return False, f"low_contrast std={std:.0f}"
    return True, f"ok mean={mean:.0f} std={std:.0f}"


# ── Descomposición de la homografía ─────────────────────────────────────────

def decompose_homography(H: np.ndarray):
    """
    Descompone H en rotación (grados), traslación (dx, dy en píxeles) y escala.

    Se usa SVD del bloque 2×2 superior izquierdo de H normalizada (H/H[2,2]).
    El ángulo de rotación es el atan2 del primer vector columna de R.
    La traslación son los elementos H[0,2] y H[1,2] de H normalizada.
    La escala es la media geométrica de los valores singulares del bloque 2×2.
    """
    Hn = H / H[2, 2]          # normalizar por h33
    A  = Hn[:2, :2]            # bloque de rotación+escala

    U, s, Vt = np.linalg.svd(A)
    R = U @ Vt

    angle_deg  = float(np.degrees(np.arctan2(R[1, 0], R[0, 0])))
    scale      = float(np.sqrt(s[0] * s[1]))   # media geométrica de singulares
    tx         = float(Hn[0, 2])
    ty         = float(Hn[1, 2])

    return angle_deg, tx, ty, scale


# ── Imagen de debug: homografía visual ──────────────────────────────────────

def make_homography_debug(ref_bgr, aligned_bgr, H, angle_deg, tx, ty, scale,
                          inliers, ratio, img_name):
    """
    Crea imagen de debug con información visual de la transformación.

    Panel izquierdo: imagen de referencia con ejes de rotación dibujados.
    Panel derecho: imagen alineada con la flecha de traslación.
    Panel inferior: recuadro de texto con los parámetros numéricos.
    """
    h, w = ref_bgr.shape[:2]

    # Escala de visualización: reducir a máx 900px de ancho por panel
    scale_vis = min(1.0, 900 / w)
    nw = int(w * scale_vis)
    nh = int(h * scale_vis)
    ref_s  = cv2.resize(ref_bgr.copy(),     (nw, nh))
    alin_s = cv2.resize(aligned_bgr.copy(), (nw, nh))

    cx, cy = nw // 2, nh // 2

    # ── Panel izquierdo: ejes de la rotación estimada ────────────────────────
    L = min(nw, nh) // 4   # longitud de los ejes
    ang_rad = np.radians(angle_deg)

    # Eje X transformado (dirección 0°+ rotación)
    ax = int(cx + L * np.cos(ang_rad))
    ay = int(cy - L * np.sin(ang_rad))
    cv2.arrowedLine(ref_s, (cx, cy), (ax, ay), (0, 80, 255), 3, tipLength=0.2)
    _put(ref_s, "X'", (ax + 5, ay - 5), scale=0.8, color=(0, 80, 255))

    # Eje Y transformado
    bx = int(cx - L * np.sin(ang_rad))
    by = int(cy - L * np.cos(ang_rad))
    cv2.arrowedLine(ref_s, (cx, cy), (bx, by), (255, 80, 0), 3, tipLength=0.2)
    _put(ref_s, "Y'", (bx + 5, by - 5), scale=0.8, color=(255, 80, 0))

    cv2.circle(ref_s, (cx, cy), 6, (255, 255, 255), -1)
    _put(ref_s, "REF", (12, 38), scale=1.0, color=(200, 200, 200))
    _put(ref_s, f"rot={angle_deg:+.2f}deg", (12, 72), scale=0.9, color=(0, 220, 255))

    # ── Panel derecho: flecha de traslación ──────────────────────────────────
    tx_s = int(tx * scale_vis)
    ty_s = int(ty * scale_vis)
    arrow_len = int(min(nw, nh) * 0.15)
    # Normalizar la flecha para que sea visible aunque la traslación sea grande
    mag = max(1, np.sqrt(tx_s**2 + ty_s**2))
    norm_tx = int(tx_s / mag * arrow_len)
    norm_ty = int(ty_s / mag * arrow_len)
    end_x = cx + norm_tx
    end_y = cy + norm_ty
    cv2.arrowedLine(alin_s, (cx, cy), (end_x, end_y), (0, 255, 120), 4, tipLength=0.25)
    _put(alin_s, "ALINEADA", (12, 38), scale=1.0, color=(200, 200, 200))
    _put(alin_s, f"traslacion ({tx:+.1f}, {ty:+.1f}) px", (12, 72), scale=0.9,
         color=(0, 255, 120))
    _put(alin_s, f"escala={scale:.4f}", (12, 106), scale=0.9, color=(255, 200, 0))

    panels = np.hstack([ref_s, alin_s])

    # ── Banner inferior con resumen numérico ─────────────────────────────────
    bh = 140
    banner = np.zeros((bh, panels.shape[1], 3), dtype=np.uint8)
    banner[:] = (20, 20, 30)

    quality = "BUENA" if ratio > 40 else ("MEDIA" if ratio > 20 else "MALA")
    q_color = (0, 220, 0) if ratio > 40 else ((0, 200, 255) if ratio > 20 else (0, 60, 220))

    lines_txt = [
        f"IMAGEN: {img_name}",
        f"Rotacion: {angle_deg:+.3f} deg   "
        f"Traslacion: ({tx:+.1f}, {ty:+.1f}) px   "
        f"Escala: {scale:.5f}",
        f"Inliers: {inliers}   Ratio: {ratio:.1f}%   Calidad: {quality}",
    ]
    for i, line in enumerate(lines_txt):
        col = (255, 255, 255) if i == 0 else (180, 220, 255)
        if i == 2:
            col = q_color
        _put(banner, line, (16, 36 + i * 40), scale=0.95, color=col)

    result = np.vstack([panels, banner])
    return result


# ── Preparación de la referencia (una sola vez por cámara) ──────────────────

def prepare_reference(ref_path: Path, cam_id: int, use_clahe: bool,
                      use_mask: bool = True) -> dict:
    """
    Carga y procesa la imagen de referencia: CLAHE, máscara y keypoints SIFT.
    Retorna un dict con todo lo necesario para comparar N imágenes contra ella.
    Llamar una sola vez por cámara; reutilizar en cada process_image().
    """
    ref_bgr = cv2.imread(str(ref_path))
    if ref_bgr is None:
        raise FileNotFoundError(f"No se pudo leer la referencia: {ref_path}")

    ref_gray = cv2.cvtColor(ref_bgr, cv2.COLOR_BGR2GRAY)
    ok, info = check_lighting(ref_gray)
    if not ok:
        raise ValueError(f"Referencia con iluminación problemática: {info}")

    if use_clahe:
        clahe    = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        ref_gray = clahe.apply(ref_gray)

    h, w = ref_gray.shape
    mask = build_mask(cam_id, h, w) if use_mask else None

    sift   = cv2.SIFT_create(nfeatures=SIFT_FEATURES)
    ref_kp, ref_des = sift.detectAndCompute(ref_gray, mask)

    return {
        "path":     ref_path,
        "bgr":      ref_bgr,
        "gray":     ref_gray,
        "kp":       ref_kp,
        "des":      ref_des,
        "mask":     mask,
        "h":        h,
        "w":        w,
        "use_clahe": use_clahe,
        "cam_id":   cam_id,
    }


# ── Procesamiento de una imagen contra la referencia ────────────────────────

def process_image(ref: dict, img_path: Path, out_dir: Path) -> dict:
    """
    Alinea img_path contra la referencia precalculada y guarda los outputs.
    ref es el dict devuelto por prepare_reference().
    """
    out_dir.mkdir(parents=True, exist_ok=True)

    ref_bgr  = ref["bgr"]
    ref_kp   = ref["kp"]
    ref_des  = ref["des"]
    mask     = ref["mask"]
    h, w     = ref["h"], ref["w"]
    use_clahe = ref["use_clahe"]

    img_bgr = cv2.imread(str(img_path))
    if img_bgr is None:
        return {"error": "no se pudo leer la imagen"}

    img_gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    ok_img, info_img = check_lighting(img_gray)
    if not ok_img:
        return {"error": f"iluminación: {info_img}"}

    if use_clahe:
        clahe    = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        img_gray = clahe.apply(img_gray)

    img_mask_scaled = (cv2.resize(mask, (img_gray.shape[1], img_gray.shape[0]),
                                  interpolation=cv2.INTER_NEAREST)
                       if mask is not None else None)

    sift = cv2.SIFT_create(nfeatures=SIFT_FEATURES)
    img_kp, img_des = sift.detectAndCompute(img_gray, img_mask_scaled)

    # Guardar visualización de la máscara solo una vez (en el primer proceso)
    mascara_path = out_dir.parent / "mascara.jpg"
    if mask is not None and not mascara_path.exists():
        vis = ref_bgr.copy()
        vis[mask == 0] = (vis[mask == 0] * 0.35).astype(np.uint8)
        cv2.imwrite(str(mascara_path), vis, [cv2.IMWRITE_JPEG_QUALITY, 90])

    if img_des is None or len(img_kp) < 8:
        return {"error": f"muy pocos keypoints: ref={len(ref_kp)} img={len(img_kp)}"}

    flann  = cv2.FlannBasedMatcher({"algorithm": 1, "trees": 5}, {"checks": 50})
    raw    = flann.knnMatch(ref_des, img_des, k=2)
    good   = [m for m, n in raw if m.distance < LOWE_RATIO * n.distance]

    if len(good) < 4:
        return {"error": f"matches insuficientes: {len(good)}"}

    src = np.float32([ref_kp[m.queryIdx].pt for m in good]).reshape(-1, 1, 2)
    dst = np.float32([img_kp[m.trainIdx].pt for m in good]).reshape(-1, 1, 2)
    H, hmask = cv2.findHomography(dst, src, cv2.RANSAC, RANSAC_THRESH)

    if H is None:
        return {"error": "RANSAC no convergió"}

    mask_list = hmask.ravel().tolist()
    inliers   = int(hmask.ravel().sum())
    outliers  = len(good) - inliers
    ratio     = inliers / len(good) * 100 if good else 0

    # ── Descomposición de la homografía ──────────────────────────────────────
    angle_deg, tx, ty, scale_h = decompose_homography(H)

    # ── 1. matches.jpg ────────────────────────────────────────────────────────
    outlier_mask = [1 - int(v) for v in mask_list]
    matches_img = cv2.drawMatches(
        ref_bgr, ref_kp, img_bgr, img_kp, good, None,
        matchColor=(0, 220, 0),
        singlePointColor=(180, 180, 180),
        matchesMask=mask_list,
        flags=cv2.DrawMatchesFlags_NOT_DRAW_SINGLE_POINTS,
    )
    matches_img = cv2.drawMatches(
        ref_bgr, ref_kp, img_bgr, img_kp, good, matches_img,
        matchColor=(0, 0, 220),
        singlePointColor=(180, 180, 180),
        matchesMask=outlier_mask,
        flags=(cv2.DrawMatchesFlags_DRAW_OVER_OUTIMG |
               cv2.DrawMatchesFlags_NOT_DRAW_SINGLE_POINTS),
    )
    _add_stats(matches_img, inliers, outliers, ratio, use_clahe)
    cv2.imwrite(str(out_dir / "matches.jpg"), matches_img,
                [cv2.IMWRITE_JPEG_QUALITY, 90])

    # ── 2. keypoints.jpg ─────────────────────────────────────────────────────
    ref_kp_img  = cv2.drawKeypoints(ref_bgr, ref_kp, None,
                                    color=(0, 160, 255),
                                    flags=cv2.DRAW_MATCHES_FLAGS_DRAW_RICH_KEYPOINTS)
    img_kp_img  = cv2.drawKeypoints(img_bgr, img_kp, None,
                                    color=(0, 160, 255),
                                    flags=cv2.DRAW_MATCHES_FLAGS_DRAW_RICH_KEYPOINTS)
    inlier_ref  = [ref_kp[good[i].queryIdx] for i, v in enumerate(mask_list) if v]
    inlier_img2 = [img_kp[good[i].trainIdx] for i, v in enumerate(mask_list) if v]
    ref_kp_img  = cv2.drawKeypoints(ref_kp_img, inlier_ref, None,
                                    color=(0, 255, 80),
                                    flags=cv2.DRAW_MATCHES_FLAGS_DRAW_RICH_KEYPOINTS)
    img_kp_img  = cv2.drawKeypoints(img_kp_img, inlier_img2, None,
                                    color=(0, 255, 80),
                                    flags=cv2.DRAW_MATCHES_FLAGS_DRAW_RICH_KEYPOINTS)
    _put(ref_kp_img,  f"REF  kp={len(ref_kp)}", (20, 50))
    _put(img_kp_img,  f"IMG  kp={len(img_kp)}  inliers={inliers}", (20, 50))
    kp_side = np.hstack([
        cv2.resize(ref_kp_img,  (w // 2, h // 2)),
        cv2.resize(img_kp_img,  (w // 2, h // 2)),
    ])
    cv2.imwrite(str(out_dir / "keypoints.jpg"), kp_side,
                [cv2.IMWRITE_JPEG_QUALITY, 90])

    aligned = cv2.warpPerspective(img_bgr, H, (w, h))

    inlier_pts_ref  = [(int(ref_kp[good[i].queryIdx].pt[0]),
                        int(ref_kp[good[i].queryIdx].pt[1]))
                       for i, v in enumerate(mask_list) if v]
    outlier_pts_ref = [(int(ref_kp[good[i].queryIdx].pt[0]),
                        int(ref_kp[good[i].queryIdx].pt[1]))
                       for i, v in enumerate(mask_list) if not v]

    # ── 3. blend_inliers.jpg ─────────────────────────────────────────────────
    blend = cv2.addWeighted(ref_bgr, 0.5, aligned, 0.5, 0)
    for pt in outlier_pts_ref:
        cv2.circle(blend, pt, 8, (0, 0, 220), 2)
        cv2.drawMarker(blend, pt, (0, 0, 220), cv2.MARKER_CROSS, 10, 2)
    for pt in inlier_pts_ref:
        cv2.circle(blend, pt, 8, (0, 220, 0), 2)
        cv2.drawMarker(blend, pt, (0, 220, 0), cv2.MARKER_CROSS, 10, 2)
    _add_stats(blend, inliers, outliers, ratio, use_clahe)
    cv2.imwrite(str(out_dir / "blend_inliers.jpg"), blend,
                [cv2.IMWRITE_JPEG_QUALITY, 90])

    # ── 4. diff_inliers.jpg ──────────────────────────────────────────────────
    diff_abs  = np.abs(ref_bgr.astype(np.float32) - aligned.astype(np.float32)).mean(axis=2)
    diff_norm = cv2.normalize(diff_abs, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
    diff_map  = cv2.applyColorMap(diff_norm, cv2.COLORMAP_HOT)
    for pt in outlier_pts_ref:
        cv2.circle(diff_map, pt, 8, (255, 255, 0), 2)
        cv2.drawMarker(diff_map, pt, (255, 255, 0), cv2.MARKER_CROSS, 10, 2)
    for pt in inlier_pts_ref:
        cv2.circle(diff_map, pt, 8, (0, 220, 0), 2)
        cv2.drawMarker(diff_map, pt, (0, 220, 0), cv2.MARKER_CROSS, 10, 2)
    _add_stats(diff_map, inliers, outliers, ratio, use_clahe)
    cv2.imwrite(str(out_dir / "diff_inliers.jpg"), diff_map,
                [cv2.IMWRITE_JPEG_QUALITY, 90])

    # ── 5. base.jpg + alineada.jpg ────────────────────────────────────────────
    base_out    = ref_bgr.copy()
    aligned_out = aligned.copy()
    _put(base_out,    "BASE (referencia)", (16, 44))
    _put(aligned_out, f"ALINEADA  inliers={inliers}  ratio={ratio:.1f}%", (16, 44))
    cv2.imwrite(str(out_dir / "base.jpg"),     base_out,    [cv2.IMWRITE_JPEG_QUALITY, 90])
    cv2.imwrite(str(out_dir / "alineada.jpg"), aligned_out, [cv2.IMWRITE_JPEG_QUALITY, 90])

    # ── 6. homography.jpg — descomposición visual ─────────────────────────────
    hom_img = make_homography_debug(
        ref_bgr, aligned,
        H, angle_deg, tx, ty, scale_h,
        inliers, ratio,
        img_name=img_path.name,
    )
    cv2.imwrite(str(out_dir / "homography.jpg"), hom_img,
                [cv2.IMWRITE_JPEG_QUALITY, 90])

    return {
        "ref":       ref["path"].name,
        "img":       img_path.name,
        "kp_ref":    len(ref_kp),
        "kp_img":    len(img_kp),
        "matches":   len(good),
        "inliers":   inliers,
        "ratio":     round(ratio, 2),
        "angle_deg": round(angle_deg, 4),
        "tx_px":     round(tx, 2),
        "ty_px":     round(ty, 2),
        "scale":     round(scale_h, 6),
        "clahe":     use_clahe,
        "light_img": info_img,
    }


# ── Escaneo de imágenes por cámara ──────────────────────────────────────────

def gather_images(cam_id: int) -> list[Path]:
    cam_dir = DEMO_BASE / f"CAM_{cam_id}" / "images"
    if not cam_dir.exists():
        return []
    return sorted(cam_dir.glob("*.jpg")) + sorted(cam_dir.glob("*.JPG"))


def _capture_hour(path: Path) -> float | None:
    """Extrae la hora de captura (0-24) del nombre <epoch>_<YYYYMMDD>_<HHMMSS>_tag.jpg."""
    parts = path.stem.split("_")
    if len(parts) < 3 or len(parts[2]) != 6 or not parts[2].isdigit():
        return None
    hhmmss = parts[2]
    return int(hhmmss[:2]) + int(hhmmss[2:4]) / 60


def pick_default_base(imgs: list[Path]) -> Path:
    """
    Elige como referencia la imagen cuya hora de captura está más cerca de la
    mediana del conjunto, en vez de simplemente la más antigua.

    Coger siempre la más antigua puede hacer que la base sea, p. ej., la única
    foto de mediodía de la carpeta mientras el resto son del amanecer: la
    diferencia de luces/sombras hunde el ratio de inliers aunque la máscara y
    el resto del pipeline funcionen bien.
    """
    horas = [(p, _capture_hour(p)) for p in imgs]
    validas = [(p, h) for p, h in horas if h is not None]
    if not validas:
        return imgs[0]
    medianas = sorted(h for _, h in validas)
    mediana = medianas[len(medianas) // 2]
    return min(validas, key=lambda ph: abs(ph[1] - mediana))[0]


# ── Entry point ──────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(
        description="Debug batch SIFT: todas las imágenes contra una base fija",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    ap.add_argument("--cams", nargs="+", type=int, default=ALL_CAMS,
                    metavar="N", help="Cámaras a procesar (por defecto todas)")
    ap.add_argument("--base", type=Path, default=None,
                    help="Imagen de referencia fija (por defecto: primera imagen de cada cámara)")
    ap.add_argument("--out", type=Path, default=ROOT / "debug_demo",
                    help="Directorio raíz de salida (default: <repo>/debug_demo)")
    ap.add_argument("--no-clahe", action="store_true",
                    help="Desactivar CLAHE")
    ap.add_argument("--no-mask", action="store_true",
                    help="Ignorar máscaras de zonas estables")
    ap.add_argument("--skip-existing", action="store_true",
                    help="Saltar imágenes ya procesadas (existe homography.jpg)")
    ap.add_argument("--max-imgs", type=int, default=None,
                    help="Máximo de imágenes por cámara (para pruebas rápidas)")
    args = ap.parse_args()

    use_clahe = not args.no_clahe
    use_mask  = not args.no_mask
    results_all = {}

    if not args.skip_existing and args.out.exists():
        print(f"Limpiando resultados anteriores en {args.out}/ ...")
        # Se borra el contenido en vez del directorio en sí: en Windows el
        # directorio puede quedar con un handle abierto (Explorer, terminal
        # con ese cwd, etc.) y shutil.rmtree() sobre el propio dir falla.
        for child in args.out.iterdir():
            if child.is_dir():
                shutil.rmtree(child, ignore_errors=True)
            else:
                child.unlink(missing_ok=True)

    for cam_id in args.cams:
        imgs = gather_images(cam_id)
        if not imgs:
            print(f"CAM_{cam_id}: sin imágenes en {DEMO_BASE}/CAM_{cam_id}/images/")
            continue

        # Elegir base: --base explícita o la imagen más representativa en hora
        if args.base and args.base.exists():
            base_path = args.base
        else:
            base_path = pick_default_base(imgs)

        # Imágenes a comparar: todas excepto la propia base
        to_compare = [p for p in imgs if p != base_path]
        if args.max_imgs:
            to_compare = to_compare[: args.max_imgs]

        print(f"\n══════════════════════════════════════════")
        print(f"  CAM_{cam_id}  —  base: {base_path.name}")
        print(f"  {len(to_compare)} imágenes a comparar")
        print(f"══════════════════════════════════════════")

        # Preparar referencia una sola vez para toda la cámara
        try:
            ref = prepare_reference(base_path, cam_id, use_clahe, use_mask)
        except (FileNotFoundError, ValueError) as e:
            print(f"  ERROR en referencia: {e}")
            continue

        print(f"  Referencia lista: {len(ref['kp'])} keypoints"
              + (" con máscara" if ref["mask"] is not None else " sin máscara"))

        cam_dir = args.out / f"CAM_{cam_id}"
        cam_dir.mkdir(parents=True, exist_ok=True)

        # Guardar la base una sola vez en el directorio de la cámara
        base_out = ref["bgr"].copy()
        _put(base_out, f"BASE: {base_path.name}", (16, 44))
        _put(base_out, f"kp={len(ref['kp'])}  {'CLAHE' if use_clahe else 'sin CLAHE'}", (16, 88))
        cv2.imwrite(str(cam_dir / "base.jpg"), base_out, [cv2.IMWRITE_JPEG_QUALITY, 90])

        cam_results = []

        for idx, img_path in enumerate(to_compare, start=1):
            out_dir = cam_dir / img_path.stem

            if args.skip_existing and (out_dir / "homography.jpg").exists():
                print(f"  [{idx:03d}/{len(to_compare)}] SKIP  {img_path.name}")
                continue

            print(f"  [{idx:03d}/{len(to_compare)}] {img_path.name}", end="  ", flush=True)

            stat = process_image(ref, img_path, out_dir)

            if "error" in stat:
                print(f"ERROR: {stat['error']}")
            else:
                quality = ("BUENA" if stat["ratio"] > 40
                           else ("MEDIA" if stat["ratio"] > 20 else "MALA"))
                print(f"rot={stat['angle_deg']:+.3f}°  "
                      f"t=({stat['tx_px']:+.1f},{stat['ty_px']:+.1f})px  "
                      f"inliers={stat['inliers']}  ratio={stat['ratio']:.1f}%  [{quality}]")

            cam_results.append({"img": img_path.name, **stat})

        results_all[f"CAM_{cam_id}"] = cam_results

        ok  = [r for r in cam_results if "error" not in r]
        err = [r for r in cam_results if "error" in r]
        if ok:
            avg_ratio = sum(r["ratio"] for r in ok) / len(ok)
            avg_angle = sum(abs(r["angle_deg"]) for r in ok) / len(ok)
            print(f"\n  Resumen CAM_{cam_id}: {len(ok)} ok / {len(err)} errores")
            print(f"  Ratio medio: {avg_ratio:.1f}%  |  Rot. media: {avg_angle:.3f}°")

    # Resumen global JSON
    summary_path = args.out / "summary.json"
    args.out.mkdir(parents=True, exist_ok=True)
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(results_all, f, indent=2, ensure_ascii=False)

    print(f"\n✓ Resultados en: {args.out}/")
    print(f"  Resumen JSON:  {summary_path}")

    all_ok = [r for cam in results_all.values() for r in cam if "error" not in r]
    if all_ok:
        worst = sorted(all_ok, key=lambda r: r["ratio"])[:5]
        print(f"\n  Peores 5 imágenes por inlier ratio:")
        for r in worst:
            print(f"    {r['img']}  ratio={r['ratio']:.1f}%  rot={r['angle_deg']:+.3f}°")


if __name__ == "__main__":
    main()
