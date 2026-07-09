"""
batch_alignment.py — Módulo de alineación masiva no-destructiva

Estado del job:
    idle → pending → processing → ready → committed | failed | discarded

La filosofía central es la separación entre staging y commit:
  - Todo el trabajo vive en TEMP_DIR/batch_{job_id}/
  - Los originales nunca se tocan
  - El commit (writing al módulo de marcación) ocurre solo en /commit explícito
"""

import asyncio
import uuid
import shutil
import json
import io
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Literal
from pathlib import Path
from datetime import datetime

import cv2
import numpy as np
from fastapi import APIRouter, HTTPException, BackgroundTasks
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel

# ── Constantes ──────────────────────────────────────────────────────────────
SIFT_FEATURES    = 3000
LOWE_RATIO       = 0.75
MIN_INLIERS      = 15    # más bajo con máscara (menos píxeles disponibles)
MIN_INLIERS_FULL = 30    # umbral sin máscara (imagen completa)
RANSAC_THRESH    = 5.0

# ── Corrección de iluminación ───────────────────────────────────────────────
# SIFT es sensible a la ón: sol directo, reflejos en el agua o cielo
# sobreexpuesto generan keypoints en zonas dinámicas que producen matches falsos
# y sesgan la homografía (pocos inliers reales en RANSAC).
#
# Solución en dos pasos aplicados ANTES de detectAndCompute en _align_to_reference:
#   1. _check_lighting  → descarta imágenes con iluminación extrema.
#   2. _CLAHE.apply     → ecualización adaptativa local (bloques 8×8 px).
#                         Normaliza contraste entre tomas de distintas horas.
# ────────────────────────────────────────────────────────────────────────────
_CLAHE = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))

def _check_lighting(gray: np.ndarray) -> tuple[bool, str]:
    """Detecta condiciones de iluminación que degradan SIFT."""
    mean = float(np.mean(gray))
    std  = float(np.std(gray))
    if mean > 200:
        return False, "overexposed"   # sol directo / reflejos saturados
    if mean < 30:
        return False, "underexposed"  # amanecer / anochecer
    if std < 18:
        return False, "low_contrast"  # niebla / calima
    return True, ""

TEMP_BASE    = Path("/tmp/cv_lit_batch")
TEMP_BASE.mkdir(parents=True, exist_ok=True)

# ── Máscaras de zonas estables por cámara ───────────────────────────────────
# Cada cámara tiene zonas con estructura fija (horizonte, edificios, vegetación)
# que son buenos anclajes para SIFT porque no cambian entre tomas.
# Las zonas dinámicas (agua, olas, personas, gaviotas) se excluyen porque
# generan keypoints falsos que sesgan la homografía.
# Configuración en calibration/alignment_masks.json — coordenadas fraccionarias
# [0.0–1.0] para que escalen a cualquier resolución de cámara.
# El usuario las edita desde la interfaz (paso "Alineación" al elegir la base,
# ver BatchAlignment.vue) dibujando rectángulos sobre la imagen base; se guardan
# aquí vía PUT /api/batch/masks/{cam_id} y se leen del disco en cada job (sin
# caché en memoria, para que un cambio se refleje en el siguiente lote sin
# reiniciar el backend).
MASKS_PATH = Path(__file__).parent.parent / "calibration" / "alignment_masks.json"

def _load_masks() -> dict:
    if not MASKS_PATH.exists():
        return {}
    with open(MASKS_PATH, encoding="utf-8") as f:
        return json.load(f)


def _save_masks(masks: dict) -> None:
    """
    Serializa a mano (una región por línea) en vez de json.dump(indent=2) para no
    convertir el fichero entero en un diff gigante de una clave por línea cada vez
    que se guarda una máscara desde la interfaz.
    """
    MASKS_PATH.parent.mkdir(parents=True, exist_ok=True)
    cam_keys = [k for k in masks if k != "_comment"]
    lines = ["{"]
    if "_comment" in masks:
        lines.append(f'  "_comment": {json.dumps(masks["_comment"], ensure_ascii=False)},')
    for i, key in enumerate(cam_keys):
        comma = "," if i < len(cam_keys) - 1 else ""
        regions = masks[key].get("regions", [])
        lines.append(f'  "{key}": {{')
        if regions:
            region_lines = [
                "      " + json.dumps(r, ensure_ascii=False) for r in regions
            ]
            lines.append('    "regions": [')
            lines.append(",\n".join(region_lines))
            lines.append('    ]')
        else:
            lines.append('    "regions": []')
        lines.append(f'  }}{comma}')
    lines.append("}")
    MASKS_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _build_mask(cam_id: int, h: int, w: int) -> Optional[np.ndarray]:
    """
    Genera una máscara binaria uint8 (255=zona válida para SIFT, 0=ignorar)
    a partir de las regiones definidas en alignment_masks.json para la cámara dada.

    Las coordenadas en el JSON son fracciones [0.0–1.0] de la imagen,
    por lo que escalan automáticamente a cualquier resolución.

    Retorna None si no hay config o no hay regiones para esta cámara
    (SIFT corre sin restricción, sobre la imagen completa).
    """
    masks = _load_masks()
    key = f"CAM_{cam_id}"
    regions = masks.get(key, {}).get("regions", [])
    if not regions:
        return None  # sin regiones → imagen completa (NO una máscara vacía/negra)

    canvas = np.zeros((h, w), dtype=np.uint8)
    for region in regions:
        # Convertir fracción → píxel para la resolución actual
        x0 = int(region["x0"] * w)
        y0 = int(region["y0"] * h)
        x1 = int(region["x1"] * w)
        y1 = int(region["y1"] * h)
        cv2.rectangle(canvas, (x0, y0), (x1, y1), 255, -1)  # 255 = zona activa

    return canvas

# ── Modelos de dominio ───────────────────────────────────────────────────────

@dataclass
class AlignmentResult:
    filename: str
    status: str                    # "ok" | "failed" | "reference"
    inliers: int = 0
    mean_shift_px: float = 0.0     # mediana de flujo óptico residual
    H: Optional[List] = None       # matriz 3x3 como lista plana
    approved: bool = True          # override de aprobación por imagen
    fail_reason: str = ""          # "no_features" | "low_matches" | "ransac_failed" | "bad_lighting:*"
    used_mask: bool = False        # True si la alineación usó máscara de zonas
    lighting_issue: str = ""       # "overexposed" | "underexposed" | "low_contrast" | ""


@dataclass
class BatchJob:
    job_id: str
    cam_id: int
    base_filename: str
    image_filenames: List[str]
    status: str = "pending"        # pending | processing | ready | committed | failed | discarded
    results: Dict[str, AlignmentResult] = field(default_factory=dict)
    progress_current: int = 0
    progress_total: int = 0
    error_msg: str = ""
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    @property
    def temp_dir(self) -> Path:
        return TEMP_BASE / self.job_id

    @property
    def aligned_dir(self) -> Path:
        return self.temp_dir / "aligned"

    @property
    def diff_dir(self) -> Path:
        return self.temp_dir / "diff"

    @property
    def blend_dir(self) -> Path:
        return self.temp_dir / "blend"

    def summary(self) -> dict:
        results_list = list(self.results.values())
        ok    = sum(1 for r in results_list if r.status in ("ok", "reference") and r.approved)
        warn  = sum(1 for r in results_list if r.status in ("ok", "reference") and not r.approved)
        failed= sum(1 for r in results_list if r.status == "failed")
        return {
            "job_id":   self.job_id,
            "cam_id":   self.cam_id,
            "status":   self.status,
            "progress": {"current": self.progress_current, "total": self.progress_total},
            "counts":   {"ok": ok, "warn": warn, "failed": failed, "total": len(results_list)},
            "error":    self.error_msg,
            "created_at": self.created_at,
            "base_filename": self.base_filename,
        }


# ── Registro en memoria ──────────────────────────────────────────────────────
_jobs: Dict[str, BatchJob] = {}


# ── Lógica de procesamiento de imágenes ─────────────────────────────────────

def _compute_diff_map(ref: np.ndarray, aligned: np.ndarray) -> np.ndarray:
    """
    Genera mapa de diferencias en tres capas:
      1. Heatmap pixel-level (COLORMAP_HOT: negro=alineado, rojo/blanco=error)
      2. Edge-diff overlay (bordes divergentes en cian)
      3. Resultado compuesto final

    Negro absoluto = alineación perfecta.
    """
    h, w = ref.shape[:2]
    aligned_r = cv2.resize(aligned, (w, h))

    ref_f  = ref.astype(np.float32)
    ali_f  = aligned_r.astype(np.float32)

    

    # ── Capa 1: heatmap de diferencia absoluta por canal ────────────────────
    diff_abs = np.abs(ref_f - ali_f).mean(axis=2)  # (H, W) float
    diff_norm = cv2.normalize(diff_abs, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
    heatmap = cv2.applyColorMap(diff_norm, cv2.COLORMAP_HOT)

    # ── Capa 2: divergencia de bordes ───────────────────────────────────────
    ref_gray = cv2.cvtColor(ref, cv2.COLOR_BGR2GRAY)
    ali_gray = cv2.cvtColor(aligned_r, cv2.COLOR_BGR2GRAY)
    edges_ref = cv2.Canny(ref_gray, 40, 120)
    edges_ali = cv2.Canny(ali_gray, 40, 120)
    edge_diff = cv2.absdiff(edges_ref, edges_ali)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (4, 4))
    edge_diff = cv2.dilate(edge_diff, kernel)

    # Pintar bordes divergentes en cian sobre el heatmap
    composite = heatmap.copy()
    composite[edge_diff > 0] = (255, 255, 0)  # cian (BGR)

    return composite


def _compute_mean_shift(ref_gray: np.ndarray, aligned_gray: np.ndarray) -> float:
    """Flujo óptico Farneback → mediana de magnitud = desplazamiento residual en píxeles."""
    try:
        flow = cv2.calcOpticalFlowFarneback(
            ref_gray, aligned_gray, None,
            pyr_scale=0.5, levels=3, winsize=15,
            iterations=3, poly_n=5, poly_sigma=1.2, flags=0
        )
        mag, _ = cv2.cartToPolar(flow[..., 0], flow[..., 1])
        return float(np.median(mag))
    except Exception:
        return -1.0


def _blend_grayscale(ref: np.ndarray, aligned: np.ndarray) -> np.ndarray:
    h, w = ref.shape[:2]
    aligned_r = cv2.resize(aligned, (w, h))
    ref_bw = cv2.cvtColor(ref, cv2.COLOR_BGR2GRAY)
    ali_bw = cv2.cvtColor(aligned_r, cv2.COLOR_BGR2GRAY)
    blend  = cv2.addWeighted(ref_bw, 0.5, ali_bw, 0.5, 0)
    return cv2.cvtColor(blend, cv2.COLOR_GRAY2BGR)


def _try_align(
    gray: np.ndarray,
    ref_kp, ref_des,
    mask: Optional[np.ndarray],
    threshold: int,
) -> tuple[Optional[np.ndarray], int, int, str]:
    """
    Intenta alinear con los keypoints dados.
    Retorna (H, inliers, n_good_matches, fail_reason).
    H=None si falla.
    """
    sift = cv2.SIFT_create(nfeatures=SIFT_FEATURES)
    kp, des = sift.detectAndCompute(gray, mask)

    if des is None or len(kp) < 8:
        return None, 0, 0, "no_features"

    flann = cv2.FlannBasedMatcher({"algorithm": 1, "trees": 5}, {"checks": 50})
    matches = flann.knnMatch(ref_des, des, k=2)
    good = [m for m, n in matches if m.distance < LOWE_RATIO * n.distance]

    if len(good) < threshold:
        return None, 0, len(good), "low_matches"

    src = np.float32([ref_kp[m.queryIdx].pt for m in good]).reshape(-1, 1, 2)
    dst = np.float32([kp[m.trainIdx].pt for m in good]).reshape(-1, 1, 2)

    H, hmask = cv2.findHomography(dst, src, cv2.RANSAC, RANSAC_THRESH)
    inliers = int(hmask.ravel().sum()) if hmask is not None else 0

    if H is None or inliers < threshold:
        return None, inliers, len(good), "ransac_failed"

    return H, inliers, len(good), "ok"


def _align_to_reference(
    img: np.ndarray,
    ref_gray: np.ndarray,
    ref_kp, ref_des,
    ref_img: np.ndarray,
    feat_mask: Optional[np.ndarray] = None,
    ref_kp_full=None, ref_des_full=None,
) -> tuple[np.ndarray, AlignmentResult, str]:
    """
    Alinea img respecto a ref usando SIFT+FLANN+RANSAC.

    Estrategia de dos pasos:
      1. Intenta con la máscara de zonas estables (si existe) — umbral MIN_INLIERS
      2. Si falla, reintenta con imagen completa — umbral MIN_INLIERS_FULL
         (el fallback evita que imágenes válidas fallen por zonas insuficientes)

    Retorna (aligned_img, AlignmentResult, status_str).
    """
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    h_img, w_img = gray.shape
    h_ref, w_ref = ref_gray.shape
    used_mask = False

    # Paso 1: filtro de iluminación — descarta imágenes con luz extrema antes de SIFT
    ok, light_reason = _check_lighting(gray)
    if not ok:
        return img.copy(), AlignmentResult(
            filename="", status="failed", inliers=0,
            fail_reason=f"bad_lighting:{light_reason}",
            lighting_issue=light_reason,
        ), f"bad_lighting:{light_reason}"

    # Paso 2: normalización de contraste local — iguala condiciones entre tomas
    gray = _CLAHE.apply(gray)

    H, inliers, n_good, reason = None, 0, 0, "no_features"

    # Paso 3a: alineación con máscara de zonas estables.
    # Umbral bajo (MIN_INLIERS=15) porque la máscara filtra ruido y los inliers
    # que quedan son de alta calidad (estructuras fijas: horizonte, edificios).
    if feat_mask is not None and ref_des is not None:
        mask_scaled = cv2.resize(feat_mask, (w_img, h_img), interpolation=cv2.INTER_NEAREST)
        H, inliers, n_good, reason = _try_align(gray, ref_kp, ref_des, mask_scaled, MIN_INLIERS)
        if H is not None:
            used_mask = True

    # Paso 3b: fallback sin máscara si las zonas estables no dan suficientes matches.
    # Ocurre en imágenes donde el horizonte está ocluido (niebla, lluvia) o la
    # máscara recorta demasiado. Umbral más alto (MIN_INLIERS_FULL=30) para
    # compensar el mayor ruido al usar la imagen completa.
    if H is None and ref_des_full is not None:
        H, inliers, n_good, reason = _try_align(
            gray, ref_kp_full, ref_des_full, None, MIN_INLIERS_FULL
        )

    # Caso sin máscara configurada: camino directo sin restricción de zona.
    if H is None and feat_mask is None and ref_des is not None:
        H, inliers, n_good, reason = _try_align(gray, ref_kp, ref_des, None, MIN_INLIERS_FULL)

    if H is None:
        return img.copy(), AlignmentResult(
            filename="", status="failed", inliers=inliers, fail_reason=reason
        ), reason

    aligned = cv2.warpPerspective(img, H, (w_ref, h_ref))

    ref_gray_local = cv2.cvtColor(ref_img, cv2.COLOR_BGR2GRAY)
    ali_gray_r     = cv2.resize(cv2.cvtColor(aligned, cv2.COLOR_BGR2GRAY), (w_ref, h_ref))
    mean_shift     = _compute_mean_shift(ref_gray_local, ali_gray_r)

    result = AlignmentResult(
        filename="",
        status="ok",
        inliers=inliers,
        mean_shift_px=round(mean_shift, 2),
        H=H.flatten().tolist(),
        used_mask=used_mask,
        fail_reason="",
    )
    return aligned, result, "ok"


async def _run_pipeline(job_id: str, image_paths: Dict[str, Path], base_path: Path):
    """
    Tarea de fondo. Puebla job.results y escribe en temp_dir.
    Nunca toca los originales.
    """
    job = _jobs[job_id]
    job.status = "processing"
    job.temp_dir.mkdir(parents=True, exist_ok=True)
    job.aligned_dir.mkdir(exist_ok=True)
    job.diff_dir.mkdir(exist_ok=True)
    job.blend_dir.mkdir(exist_ok=True)

    ref_img  = cv2.imread(str(base_path))
    if ref_img is None:
        job.status = "failed"
        job.error_msg = f"No se pudo leer la imagen base: {base_path}"
        return

    ref_gray = cv2.cvtColor(ref_img, cv2.COLOR_BGR2GRAY)
    ref_gray = _CLAHE.apply(ref_gray)
    h_ref, w_ref = ref_gray.shape

    # Máscara de zonas estables: restringe SIFT al horizonte y estructuras fijas.
    # Si no hay config para esta cámara devuelve None y SIFT usa la imagen completa.
    feat_mask = _build_mask(job.cam_id, h_ref, w_ref)

    sift = cv2.SIFT_create(nfeatures=SIFT_FEATURES)

    # Precalcular keypoints de la referencia una sola vez para todo el batch.
    # Con máscara: keypoints solo en zonas estables (más precisos, menos ruido).
    # Sin máscara: keypoints en toda la imagen (fallback si la máscara falla).
    ref_kp,      ref_des      = sift.detectAndCompute(ref_gray, feat_mask)
    ref_kp_full, ref_des_full = sift.detectAndCompute(ref_gray, None) if feat_mask is not None else (ref_kp, ref_des)

    job.progress_total = len(image_paths)

    for i, (filename, img_path) in enumerate(image_paths.items()):
        job.progress_current = i + 1

        if filename == job.base_filename:
            ref_copy   = ref_img.copy()
            diff_black = np.zeros_like(ref_img)
            cv2.imwrite(str(job.aligned_dir / filename), ref_copy)
            cv2.imwrite(str(job.diff_dir    / filename), diff_black)
            cv2.imwrite(str(job.blend_dir   / filename), ref_img.copy())
            job.results[filename] = AlignmentResult(
                filename=filename,
                status="reference",
                inliers=len(ref_kp),
                mean_shift_px=0.0,
            )
            continue

        img = cv2.imread(str(img_path))
        if img is None:
            job.results[filename] = AlignmentResult(filename=filename, status="failed")
            continue

        aligned, result, _ = _align_to_reference(
            img, ref_gray, ref_kp, ref_des, ref_img,
            feat_mask=feat_mask,
            ref_kp_full=ref_kp_full,
            ref_des_full=ref_des_full,
        )
        result.filename = filename

        # Escribir en staging temp (NO en originales)
        cv2.imwrite(str(job.aligned_dir / filename), aligned)
        cv2.imwrite(str(job.diff_dir  / filename), _compute_diff_map(ref_img, aligned))
        cv2.imwrite(str(job.blend_dir / filename), _blend_grayscale(ref_img, aligned))

        job.results[filename] = result

        # Yield control para no bloquear el event loop
        await asyncio.sleep(0)

    job.status = "ready"


# ── Router FastAPI ───────────────────────────────────────────────────────────

router = APIRouter(prefix="/api/batch", tags=["batch"])


class BatchStartRequest(BaseModel):
    cam_id: int
    base_filename: str
    image_filenames: List[str]


class MaskRegion(BaseModel):
    label: str
    x0: float
    y0: float
    x1: float
    y1: float


class MaskUpdateRequest(BaseModel):
    regions: List[MaskRegion]


@router.get("/masks/{cam_id}")
def get_mask(cam_id: int):
    """
    Regiones de máscara SIFT actuales para la cámara (coordenadas fraccionarias
    0.0-1.0). Lista vacía = sin máscara, SIFT usa la imagen completa.
    """
    masks = _load_masks()
    regions = masks.get(f"CAM_{cam_id}", {}).get("regions", [])
    return {"cam_id": cam_id, "regions": regions}


@router.put("/masks/{cam_id}")
def save_mask(cam_id: int, req: MaskUpdateRequest):
    """
    Guarda las regiones de máscara SIFT de la cámara en calibration/alignment_masks.json.
    Se usa desde la interfaz al elegir la imagen base (BatchAlignment.vue): el usuario
    dibuja rectángulos sobre zonas estables, o deja la lista vacía para usar la imagen
    completa. Afecta a todos los lotes de esta cámara procesados a partir de ahora.
    """
    from config import CAMERAS
    if cam_id not in CAMERAS:
        raise HTTPException(404, "Cámara no encontrada")

    masks = _load_masks()
    masks[f"CAM_{cam_id}"] = {"regions": [r.model_dump() for r in req.regions]}
    _save_masks(masks)
    return {"cam_id": cam_id, "regions": masks[f"CAM_{cam_id}"]["regions"]}


@router.post("/start")
async def start_batch(req: BatchStartRequest, background_tasks: BackgroundTasks):
    """
    Inicia un job de alineación masiva.
    Retorna job_id inmediatamente; el procesamiento ocurre en background.
    El caller debe hacer polling a GET /api/batch/{job_id}/status.
    """
    from config import CAMERAS, DATA_DIR  # import local para evitar ciclos

    if req.cam_id not in CAMERAS:
        raise HTTPException(404, "Cámara no encontrada")

    cam_folder = Path(DATA_DIR) / CAMERAS[req.cam_id]["folder"]

    # Validar que todos los archivos existen antes de encolar
    image_paths: Dict[str, Path] = {}
    missing = []
    for fn in req.image_filenames:
        p = cam_folder / fn
        if not p.exists():
            missing.append(fn)
        else:
            image_paths[fn] = p

    if missing:
        raise HTTPException(400, f"Imágenes no encontradas: {missing[:5]}")

    base_path = cam_folder / req.base_filename
    if not base_path.exists():
        raise HTTPException(400, f"Imagen base no encontrada: {req.base_filename}")

    job_id = str(uuid.uuid4())[:8]
    job = BatchJob(
        job_id=job_id,
        cam_id=req.cam_id,
        base_filename=req.base_filename,
        image_filenames=req.image_filenames,
        progress_total=len(image_paths),
    )
    _jobs[job_id] = job

    background_tasks.add_task(_run_pipeline, job_id, image_paths, base_path)
    return {"job_id": job_id, "total": len(image_paths)}


@router.get("/{job_id}/status")
def get_status(job_id: str):
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(404, "Job no encontrado")
    return job.summary()


@router.get("/{job_id}/results")
def get_results(job_id: str):
    """Lista completa de resultados con métricas por imagen."""
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(404, "Job no encontrado")
    if job.status not in ("ready", "committed"):
        raise HTTPException(425, "El job aún está procesando")

    items = []
    for fn in job.image_filenames:
        r = job.results.get(fn)
        if r:
            items.append({
                "filename":       r.filename,
                "status":         r.status,
                "inliers":        r.inliers,
                "mean_shift_px":  r.mean_shift_px,
                "approved":       r.approved,
                "fail_reason":    r.fail_reason,
                "used_mask":      r.used_mask,
                "lighting_issue": r.lighting_issue,
            })
    return {"job_id": job_id, "base": job.base_filename, "items": items}


def _serve_image(path: Path) -> StreamingResponse:
    if not path.exists():
        raise HTTPException(404, "Imagen no disponible")
    img = cv2.imread(str(path))
    if img is None:
        raise HTTPException(500, "Error al leer imagen")
    _, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 88])
    return StreamingResponse(io.BytesIO(buf.tobytes()), media_type="image/jpeg")


@router.get("/{job_id}/preview/original/{filename}")
def preview_original(job_id: str, filename: str):
    """Imagen original (sin transformar) desde la carpeta de la cámara."""
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(404, "Job no encontrado")
    from config import CAMERAS, DATA_DIR
    path = Path(DATA_DIR) / CAMERAS[job.cam_id]["folder"] / filename
    return _serve_image(path)


@router.get("/{job_id}/preview/aligned/{filename}")
def preview_aligned(job_id: str, filename: str):
    """Imagen alineada en staging (no-destructiva)."""
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(404, "Job no encontrado")
    return _serve_image(job.aligned_dir / filename)


@router.get("/{job_id}/preview/diff/{filename}")
def preview_diff(job_id: str, filename: str):
    """Mapa de diferencias: negro=alineado, rojo/blanco=error, cian=bordes divergentes."""
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(404, "Job no encontrado")
    return _serve_image(job.diff_dir / filename)


@router.get("/{job_id}/preview/blend/{filename}")
def preview_blend(job_id: str, filename: str):
    """Blend 50/50 en escala de grises."""
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(404, "Job no encontrado")
    return _serve_image(job.blend_dir / filename)


@router.patch("/{job_id}/approve/{filename}")
def toggle_approval(job_id: str, filename: str, approved: bool):
    """Override de aprobación individual. No escribe nada en disco."""
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(404, "Job no encontrado")
    r = job.results.get(filename)
    if not r:
        raise HTTPException(404, "Imagen no encontrada en el job")
    r.approved = approved
    return {"filename": filename, "approved": approved}


@router.post("/{job_id}/commit")
def commit_batch(job_id: str):
    """
    Two-phase commit: mueve las imágenes aprobadas del staging temp
    al directorio del módulo de marcación.

    Sólo en este punto se produce escritura permanente.
    Las imágenes rechazadas (approved=False) no se copian.
    """
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(404, "Job no encontrado")
    if job.status != "ready":
        raise HTTPException(409, f"El job está en estado '{job.status}', no se puede confirmar")

    from config import CAMERAS, DATA_DIR
    # Directorio destino en el módulo de marcación
    marking_dir = Path(DATA_DIR) / CAMERAS[job.cam_id]["folder"] / "aligned"
    marking_dir.mkdir(parents=True, exist_ok=True)

    committed = []
    skipped   = []

    for filename, result in job.results.items():
        if not result.approved:
            skipped.append(filename)
            continue
        src = job.aligned_dir / filename
        dst = marking_dir / filename
        if src.exists():
            shutil.copy2(src, dst)
            committed.append(filename)

    job.status = "committed"
    return {
        "job_id":    job_id,
        "committed": len(committed),
        "skipped":   len(skipped),
        "dest_dir":  str(marking_dir),
    }


@router.delete("/{job_id}")
def discard_batch(job_id: str):
    """
    Descarta el job y elimina el directorio temp.
    Los originales permanecen intactos.
    """
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(404, "Job no encontrado")
    if job.temp_dir.exists():
        shutil.rmtree(job.temp_dir)
    job.status = "discarded"
    _jobs.pop(job_id, None)
    return {"status": "discarded"}
