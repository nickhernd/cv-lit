"""Tests de commit_batch() y AlignmentResult (backend/batch_alignment.py) —
añadidos en 2026-08-11, cuando la lógica de "qué se copia de verdad al
directorio final" llevaba toda la ronda de trabajo sin cobertura automática
pese a ser la única parte del módulo que escribe algo permanente.

Sin mocks: escribe archivos reales en el staging temporal (TEMP_BASE) y
comprueba lo que commit_batch() copia de verdad a DATA_DIR/{folder}/aligned/.

Mismo patrón que test_marking_workflow.py: DATA_DIR/CALIBRATION_DIR
temporales fijados por variables de entorno ANTES de importar config/main.
"""

import sys
import os
import json
import tempfile
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "backend"))

_TMP_DATA_DIR = tempfile.mkdtemp(prefix="cvlit_test_commit_data_")
_TMP_CALIB_DIR = tempfile.mkdtemp(prefix="cvlit_test_commit_calib_")
os.environ["CVLIT_DATA_DIR"] = _TMP_DATA_DIR
os.environ["CVLIT_CALIBRATION_DIR"] = _TMP_CALIB_DIR
os.environ.setdefault("APP_MODE", "real")

import numpy as np
import cv2

import config
import main
import batch_alignment as ba

CAM_ID = 1
FOLDER = config.CAMERAS[CAM_ID]["folder"]


# ── AlignmentResult.__post_init__: invariante de aprobación ──────────────────

def test_failed_alignment_is_never_approved_by_default():
    r = ba.AlignmentResult(filename="x.jpg", status="failed")
    assert r.approved is False


def test_ok_alignment_is_approved_by_default():
    r = ba.AlignmentResult(filename="x.jpg", status="ok", inliers=40)
    assert r.approved is True


def test_failed_alignment_approval_cannot_be_forced_true_via_default():
    # Ni siquiera pasando approved=True explícito debería colarse una fallida
    # aprobada sin revisión humana — __post_init__ pisa cualquier valor si status="failed".
    r = ba.AlignmentResult(filename="x.jpg", status="failed", approved=True)
    assert r.approved is False


# ── commit_batch(): qué se copia de verdad ────────────────────────────────────

def _make_job_with_staged_files(job_id: str, results: dict) -> ba.BatchJob:
    job = ba.BatchJob(
        job_id=job_id, cam_id=CAM_ID, base_filename="base.jpg",
        image_filenames=list(results.keys()), status="ready", results=results,
    )
    job.aligned_dir.mkdir(parents=True, exist_ok=True)
    for filename in results:
        img = np.full((10, 10, 3), 128, dtype=np.uint8)
        cv2.imwrite(str(job.aligned_dir / filename), img)
    return job


def test_commit_batch_copies_only_approved_images():
    results = {
        "ok1.jpg": ba.AlignmentResult(filename="ok1.jpg", status="ok", inliers=50, H=[1, 0, 0, 0, 1, 0, 0, 0, 1]),
        "failed1.jpg": ba.AlignmentResult(filename="failed1.jpg", status="failed"),
    }
    job = _make_job_with_staged_files("committest1", results)
    ba._jobs["committest1"] = job

    result = ba.commit_batch("committest1")

    assert result["committed"] == 1
    assert result["skipped"] == 1
    assert job.status == "committed"

    marking_dir = Path(config.DATA_DIR) / FOLDER / "aligned"
    assert (marking_dir / "ok1.jpg").exists()
    assert not (marking_dir / "failed1.jpg").exists()


def test_commit_batch_writes_sidecar_with_homography_and_reference():
    results = {
        "ok2.jpg": ba.AlignmentResult(filename="ok2.jpg", status="ok", inliers=33, mean_shift_px=1.2, H=[2, 0, 0, 0, 2, 0, 0, 0, 1]),
    }
    job = _make_job_with_staged_files("committest2", results)
    ba._jobs["committest2"] = job

    ba.commit_batch("committest2")

    marking_dir = Path(config.DATA_DIR) / FOLDER / "aligned"
    sidecar = json.loads((marking_dir / "ok2.jpg.align.json").read_text(encoding="utf-8"))
    assert sidecar["aligned"] is True
    assert sidecar["H"] == [2, 0, 0, 0, 2, 0, 0, 0, 1]
    assert sidecar["inliers"] == 33
    assert sidecar["reference_image"] == "base.jpg"


def test_commit_batch_rejects_job_not_in_ready_status():
    job = ba.BatchJob(job_id="committest3", cam_id=CAM_ID, base_filename="base.jpg", image_filenames=[], status="processing")
    ba._jobs["committest3"] = job

    try:
        ba.commit_batch("committest3")
        assert False, "debería haber lanzado HTTPException"
    except Exception as e:
        assert "409" in str(e) or "no se puede confirmar" in str(e)


def test_commit_batch_unknown_job_raises_404():
    try:
        ba.commit_batch("no-existe-nunca")
        assert False, "debería haber lanzado HTTPException"
    except Exception as e:
        assert "404" in str(e) or "no encontrado" in str(e)
