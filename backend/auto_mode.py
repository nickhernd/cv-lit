"""
auto_mode.py — Auto Mode: pipeline automático completo por rango de fechas.

Dado una cámara + un rango de fechas, hace de punta a punta lo que hoy se
hace a mano paso a paso:
  1. Descarga  — pide a la API de Obscape las imágenes de la cámara en ese
     rango y descarga las que aún no existen en disco.
  2. Base      — la imagen descargada con timestamp de captura más antiguo
     del lote se usa como referencia de alineación.
  3. Alineación — reutiliza batch_alignment.py (SIFT+FLANN+RANSAC) para
     alinear el resto del lote contra la base y comitea automáticamente
     (sin revisión humana: una alineación fallida queda "no aprobada" por
     defecto — ver AlignmentResult.__post_init__ — así que commit_batch()
     la deja fuera y el análisis usa la imagen original sin transformar).
  4. Análisis  — reutiliza main.analyze_roi() (mismo endpoint que dispara el
     botón "Analizar imagen" manual) para cada imagen resultante: segmenta,
     extrae la línea de costa, la proyecta a UTM y guarda el GeoJSON.

No reimplementa ninguna de esas piezas — solo las orquesta. Requiere que la
cámara YA esté calibrada (ver _is_calibrated): la calibración inicial sigue
siendo manual porque depende de coordenadas UTM de varillas reales, que no
vienen de la API de imágenes.

Mismo patrón que batch_alignment.py: job en memoria + background task +
polling desde el frontend.
"""
import json
import os
import sys
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel

router = APIRouter(prefix="/api/automode", tags=["automode"])

# Igual patrón que BASE_DIR en main.py: en el build de escritorio (PyInstaller
# congelado), __file__ no es una ruta real en disco, así que este
# sys.path.append no aporta nada ahí — la importación de obscape_api en
# _download_new_images() funciona en ese caso porque está declarada como
# hiddenimport en desktop_launcher.spec (bundle directo, sin depender de
# sys.path). Este bloque solo es necesario para el modo desarrollo/dev.
if not getattr(sys, "frozen", False):
    ACCES_API_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "acces_api")
    if ACCES_API_DIR not in sys.path:
        sys.path.append(ACCES_API_DIR)


# ── Modelos de dominio ───────────────────────────────────────────────────────

@dataclass
class ImageResult:
    filename: str
    captured_at: Optional[str] = None
    is_base: bool = False
    align_status: str = ""        # "" (sin intentar) | "ok" | "failed" | "reference"
    confidence: float = 0.0
    dry_area_m2: float = 0.0
    rejected: bool = False
    reject_reason: str = ""
    error: str = ""


@dataclass
class AutoJob:
    job_id: str
    cam_id: int
    from_date: str
    to_date: str
    status: str = "pending"       # pending|downloading|aligning|analyzing|done|error
    step: str = ""
    progress_current: int = 0
    progress_total: int = 0
    downloaded: List[str] = field(default_factory=list)
    results: List[ImageResult] = field(default_factory=list)
    error_msg: str = ""
    created_at: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))

    def summary(self) -> dict:
        ok = sum(1 for r in self.results if not r.rejected and not r.error)
        rejected = sum(1 for r in self.results if r.rejected)
        errors = sum(1 for r in self.results if r.error)
        return {
            "job_id": self.job_id,
            "cam_id": self.cam_id,
            "from_date": self.from_date,
            "to_date": self.to_date,
            "status": self.status,
            "step": self.step,
            "progress": {"current": self.progress_current, "total": self.progress_total},
            "downloaded": len(self.downloaded),
            "counts": {"ok": ok, "rejected": rejected, "errors": errors, "total": len(self.results)},
            "error": self.error_msg,
            "created_at": self.created_at,
        }


_jobs: Dict[str, AutoJob] = {}


class AutoStartRequest(BaseModel):
    cam_id: int
    from_date: str   # "YYYY-MM-DD"
    to_date: str      # "YYYY-MM-DD"


# ── Helpers ──────────────────────────────────────────────────────────────────

def _is_calibrated(cam_id: int) -> bool:
    from config import CALIBRATION_DIR
    h_path = os.path.join(CALIBRATION_DIR, f"cam_{cam_id}_H.npy")
    if os.path.exists(h_path):
        return True
    profile_path = os.path.join(CALIBRATION_DIR, f"cam_{cam_id}_profile.json")
    if os.path.exists(profile_path):
        try:
            with open(profile_path, "r") as f:
                return bool(json.load(f).get("H"))
        except (json.JSONDecodeError, OSError):
            return False
    return False


def _download_new_images(cam_id: int, from_date: str, to_date: str) -> List[str]:
    """Descarga las imágenes nuevas de Obscape para [from_date, to_date] directamente
    en DATA_DIR/{folder}/, planas y con el nombrado que ya reconoce el resto del
    backend (ver ObscapeClient.download_image_flat). Salta las que ya existen en
    disco. Devuelve los nombres de archivo descargados, ordenados por fecha de
    captura (el más antiguo primero)."""
    from config import CAMERAS, DATA_DIR
    from obscape_api import ObscapeClient
    from main import add_log  # import diferido: evita el ciclo main<->auto_mode al importar

    info = CAMERAS[cam_id]
    client = ObscapeClient()
    cam_folder = Path(DATA_DIR) / info["folder"]

    data = client.get_station_data(
        info["id"], from_dt=f"{from_date}T00:00:00", to_dt=f"{to_date}T23:59:59", tz="local"
    )
    points = data.get("data", [])

    # Cada imagen se descarga en su propio try/except: un timeout o error
    # puntual de Obscape en UNA captura del rango no debe tirar todo el job
    # (antes, una sola excepción aquí abortaba la descarga completa y se
    # perdían también las imágenes que ya se habían bajado bien antes de
    # llegar a la que falló).
    downloaded = []
    failed = 0
    for pt in points:
        ts = int(pt["time"]) if isinstance(pt, dict) else int(pt[0])
        try:
            path, is_new = client.download_image_flat(info["id"], info["serial"], ts, cam_folder)
        except Exception as e:
            failed += 1
            add_log(f"Auto Mode Cam {cam_id}: fallo al descargar la captura {ts} — {e}", "warning")
            continue
        if is_new and path:
            downloaded.append(path.name)

    if failed:
        add_log(f"Auto Mode Cam {cam_id}: {failed} captura(s) no se pudieron descargar, continuando con el resto", "warning")

    downloaded.sort()  # el nombre empieza por el epoch -> orden cronológico
    return downloaded


# ── Pipeline ─────────────────────────────────────────────────────────────────

async def _run_auto_pipeline(job_id: str):
    job = _jobs[job_id]
    from main import add_log  # import diferido: evita el ciclo main<->auto_mode al importar

    try:
        # 1. Descarga
        job.status = "downloading"
        job.step = "Descargando imágenes de Obscape"
        add_log(f"Auto Mode Cam {job.cam_id}: descargando {job.from_date} → {job.to_date}", "info")
        job.downloaded = _download_new_images(job.cam_id, job.from_date, job.to_date)

        if not job.downloaded:
            job.status = "done"
            job.step = "Sin imágenes nuevas en ese rango"
            add_log(f"Auto Mode Cam {job.cam_id}: no hay imágenes nuevas en el rango indicado", "warning")
            return

        # Base de alineación: SIEMPRE la reference_image PERSISTENTE de la
        # cámara (la misma que fija /set-reference y usa por defecto el flujo
        # manual) — nunca la imagen más antigua de este lote concreto. Si cada
        # lote semanal se alineara contra su propia base, cada semana quedaría
        # en un marco de píxeles distinto al que se usó para calcular la
        # homografía H (que se computa una sola vez, sobre calibrated_image);
        # la H fija aplicada a un marco de píxeles distinto de ese introduce
        # un desplazamiento sistemático que ni el RMSE de calibración (solo se
        # calcula una vez) ni la confianza de SAM detectan.
        from config import CAMERAS, DATA_DIR, CALIBRATION_DIR

        cam_folder = Path(DATA_DIR) / CAMERAS[job.cam_id]["folder"]
        profile_path = Path(CALIBRATION_DIR) / f"cam_{job.cam_id}_profile.json"
        reference_image = None
        if profile_path.exists():
            with open(profile_path, "r") as f:
                reference_image = json.load(f).get("reference_image")

        using_calibration_reference = bool(reference_image) and (cam_folder / reference_image).exists()
        base_filename = reference_image if using_calibration_reference else job.downloaded[0]
        job.results = [ImageResult(filename=fn, is_base=(fn == base_filename)) for fn in job.downloaded]

        # Alinear siempre que haya una reference_image de calibración válida
        # (incluso con una sola imagen nueva) — sin ella, mantener el
        # comportamiento anterior: un lote de una sola imagen no tiene nada
        # dentro del propio lote contra lo que alinearla, así que se salta.
        if using_calibration_reference or len(job.downloaded) > 1:
            job.status = "aligning"
            job.step = f"Alineando {len(job.downloaded)} imágenes contra la base"
            add_log(f"Auto Mode Cam {job.cam_id}: alineando {len(job.downloaded)} imágenes (base: {base_filename})", "info")

            import batch_alignment as ba

            batch_job_id = str(uuid.uuid4())[:8]
            batch_job = ba.BatchJob(
                job_id=batch_job_id,
                cam_id=job.cam_id,
                base_filename=base_filename,
                image_filenames=job.downloaded,
                progress_total=len(job.downloaded),
            )
            ba._jobs[batch_job_id] = batch_job

            image_paths = {fn: cam_folder / fn for fn in job.downloaded}
            await ba._run_pipeline(batch_job_id, image_paths, cam_folder / base_filename)

            align_by_filename = {r.filename: r for r in batch_job.results.values()}
            for item in job.results:
                r = align_by_filename.get(item.filename)
                if r:
                    item.align_status = r.status

            if batch_job.status == "ready":
                commit_result = ba.commit_batch(batch_job_id)
                add_log(
                    f"Auto Mode Cam {job.cam_id}: alineación comiteada "
                    f"({commit_result['committed']} ok, {commit_result['skipped']} descartadas)",
                    "info",
                )
            else:
                add_log(f"Auto Mode Cam {job.cam_id}: alineación no completada ({batch_job.error_msg})", "warning")
        else:
            job.results[0].align_status = "reference"

        # 3. Análisis (reutiliza el mismo endpoint que el flujo manual)
        job.status = "analyzing"
        job.step = f"Analizando {len(job.downloaded)} imágenes"
        job.progress_total = len(job.downloaded)

        from main import analyze_roi

        for i, item in enumerate(job.results):
            job.progress_current = i + 1
            try:
                res = analyze_roi(job.cam_id, item.filename)
                item.confidence = res.get("confidence", 0.0)
                item.dry_area_m2 = res.get("dry_area_m2", 0.0)
                item.rejected = bool(res.get("rejected", False))
                item.reject_reason = res.get("reject_reason", "")
                item.captured_at = res.get("timestamp")
            except HTTPException as e:
                item.error = str(e.detail)
            except Exception as e:
                item.error = str(e)

        job.status = "done"
        ok = sum(1 for r in job.results if not r.rejected and not r.error)
        job.step = f"Completado: {ok}/{len(job.results)} imágenes analizadas correctamente"
        add_log(f"Auto Mode Cam {job.cam_id}: {job.step}", "success")

    except Exception as e:
        job.status = "error"
        job.error_msg = str(e)
        add_log(f"Auto Mode Cam {job.cam_id}: fallo — {e}", "error")


# ── Router FastAPI ───────────────────────────────────────────────────────────

@router.post("/start")
async def start_auto_mode(req: AutoStartRequest, background_tasks: BackgroundTasks):
    from config import CAMERAS

    if req.cam_id not in CAMERAS:
        raise HTTPException(404, "Cámara no encontrada")
    if not _is_calibrated(req.cam_id):
        raise HTTPException(
            400,
            "Esta cámara todavía no está calibrada. Calibra al menos una imagen "
            "manualmente en 'Calibración' antes de usar Auto Mode.",
        )

    job_id = str(uuid.uuid4())[:8]
    job = AutoJob(job_id=job_id, cam_id=req.cam_id, from_date=req.from_date, to_date=req.to_date)
    _jobs[job_id] = job

    background_tasks.add_task(_run_auto_pipeline, job_id)
    return {"job_id": job_id}


@router.get("/{job_id}/status")
def get_auto_status(job_id: str):
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(404, "Job no encontrado")
    return job.summary()


@router.get("/{job_id}/results")
def get_auto_results(job_id: str):
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(404, "Job no encontrado")
    if job.status not in ("done", "error"):
        raise HTTPException(425, "El job aún está procesando")
    return {
        "job_id": job_id,
        "cam_id": job.cam_id,
        "items": [
            {
                "filename": r.filename,
                "captured_at": r.captured_at,
                "is_base": r.is_base,
                "align_status": r.align_status,
                "confidence": r.confidence,
                "dry_area_m2": r.dry_area_m2,
                "rejected": r.rejected,
                "reject_reason": r.reject_reason,
                "error": r.error,
            }
            for r in job.results
        ],
    }
