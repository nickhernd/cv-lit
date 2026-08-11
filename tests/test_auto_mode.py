"""Tests de Auto Mode (backend/auto_mode.py) — añadidos en 2026-08-11, cuando
el módulo llevaba toda la ronda de trabajo sin cobertura automática.

_download_new_images() habla con la API real de Obscape (credenciales +
red) — igual que el resto del proyecto no mockea su propia lógica pero SÍ
evita depender de servicios externos de terceros en los tests (ver
test_pipeline_integration.py y su "mockeando SAM" para heavy externo), aquí
se monkeypatchea justo esa función de frontera con el exterior. Todo lo
demás (validación del router, _is_calibrated, AutoJob.summary(), el pipeline
completo salvo la descarga) corre con código real, sin mocks.

Mismo patrón que test_marking_workflow.py: TestClient real contra main.app
con DATA_DIR/CALIBRATION_DIR temporales.
"""

import sys
import os
import json
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "backend"))

_TMP_DATA_DIR = tempfile.mkdtemp(prefix="cvlit_test_auto_data_")
_TMP_CALIB_DIR = tempfile.mkdtemp(prefix="cvlit_test_auto_calib_")
os.environ["CVLIT_DATA_DIR"] = _TMP_DATA_DIR
os.environ["CVLIT_CALIBRATION_DIR"] = _TMP_CALIB_DIR
os.environ.setdefault("APP_MODE", "real")

import numpy as np
import pytest
from fastapi.testclient import TestClient

import config
import main
import auto_mode

client = TestClient(main.app)

CAM_ID = 1
OTHER_CAM_ID = 2


def _clear_calibration(cam_id: int) -> None:
    for name in (f"cam_{cam_id}_H.npy", f"cam_{cam_id}_profile.json"):
        p = Path(config.CALIBRATION_DIR) / name
        if p.exists():
            p.unlink()


def _calibrate_with_profile_json(cam_id: int) -> None:
    """_is_calibrated() acepta un profile.json con clave "H" además del
    cam_{id}_H.npy — cubre las dos rutas que consulta."""
    profile_path = Path(config.CALIBRATION_DIR) / f"cam_{cam_id}_profile.json"
    profile_path.parent.mkdir(parents=True, exist_ok=True)
    profile_path.write_text(json.dumps({"H": [1, 0, 0, 0, 1, 0, 0, 0, 1]}), encoding="utf-8")


def _calibrate_with_npy(cam_id: int) -> None:
    Path(config.CALIBRATION_DIR).mkdir(parents=True, exist_ok=True)
    np.save(Path(config.CALIBRATION_DIR) / f"cam_{cam_id}_H.npy", np.eye(3))


# ── _is_calibrated ────────────────────────────────────────────────────────────

def test_is_calibrated_false_with_nothing_on_disk():
    _clear_calibration(OTHER_CAM_ID)
    assert auto_mode._is_calibrated(OTHER_CAM_ID) is False


def test_is_calibrated_true_with_h_npy():
    _clear_calibration(OTHER_CAM_ID)
    _calibrate_with_npy(OTHER_CAM_ID)
    assert auto_mode._is_calibrated(OTHER_CAM_ID) is True
    _clear_calibration(OTHER_CAM_ID)


def test_is_calibrated_true_with_profile_json():
    _clear_calibration(OTHER_CAM_ID)
    _calibrate_with_profile_json(OTHER_CAM_ID)
    assert auto_mode._is_calibrated(OTHER_CAM_ID) is True
    _clear_calibration(OTHER_CAM_ID)


def test_is_calibrated_false_with_profile_json_missing_h():
    _clear_calibration(OTHER_CAM_ID)
    profile_path = Path(config.CALIBRATION_DIR) / f"cam_{OTHER_CAM_ID}_profile.json"
    profile_path.parent.mkdir(parents=True, exist_ok=True)
    profile_path.write_text(json.dumps({"gcps": []}), encoding="utf-8")
    assert auto_mode._is_calibrated(OTHER_CAM_ID) is False
    _clear_calibration(OTHER_CAM_ID)


# ── AutoJob.summary() ─────────────────────────────────────────────────────────

def test_autojob_summary_counts_ok_rejected_and_errors():
    job = auto_mode.AutoJob(job_id="t1", cam_id=CAM_ID, from_date="2026-01-01", to_date="2026-01-02")
    job.status = "done"
    job.downloaded = ["a.jpg", "b.jpg", "c.jpg"]
    job.results = [
        auto_mode.ImageResult(filename="a.jpg"),
        auto_mode.ImageResult(filename="b.jpg", rejected=True, reject_reason="baja confianza"),
        auto_mode.ImageResult(filename="c.jpg", error="fallo de segmentación"),
    ]
    summary = job.summary()
    assert summary["downloaded"] == 3
    assert summary["counts"] == {"ok": 1, "rejected": 1, "errors": 1, "total": 3}
    assert summary["status"] == "done"


def test_autojob_summary_progress_shape():
    job = auto_mode.AutoJob(job_id="t2", cam_id=CAM_ID, from_date="2026-01-01", to_date="2026-01-02")
    job.progress_current = 2
    job.progress_total = 5
    assert job.summary()["progress"] == {"current": 2, "total": 5}


# ── Router: validación de /start ──────────────────────────────────────────────

def test_start_rejects_unknown_camera():
    resp = client.post("/api/automode/start", json={"cam_id": 999, "from_date": "2026-01-01", "to_date": "2026-01-02"})
    assert resp.status_code == 404


def test_start_rejects_uncalibrated_camera():
    _clear_calibration(OTHER_CAM_ID)
    resp = client.post("/api/automode/start", json={"cam_id": OTHER_CAM_ID, "from_date": "2026-01-01", "to_date": "2026-01-02"})
    assert resp.status_code == 400
    assert "no está calibrada" in resp.json()["detail"]


def test_status_unknown_job_returns_404():
    resp = client.get("/api/automode/no-existe/status")
    assert resp.status_code == 404


def test_results_unknown_job_returns_404():
    resp = client.get("/api/automode/no-existe/results")
    assert resp.status_code == 404


def test_results_while_processing_returns_425():
    job = auto_mode.AutoJob(job_id="processing1", cam_id=CAM_ID, from_date="2026-01-01", to_date="2026-01-02")
    job.status = "downloading"
    auto_mode._jobs["processing1"] = job
    resp = client.get("/api/automode/processing1/results")
    assert resp.status_code == 425


# ── Pipeline: sin imágenes nuevas (sin red real, _download_new_images mockeada) ─

def test_start_with_no_new_images_completes_immediately(monkeypatch):
    monkeypatch.setattr(auto_mode, "_download_new_images", lambda cam_id, from_date, to_date: [])
    _calibrate_with_npy(CAM_ID)

    resp = client.post("/api/automode/start", json={"cam_id": CAM_ID, "from_date": "2026-01-01", "to_date": "2026-01-02"})
    assert resp.status_code == 200
    job_id = resp.json()["job_id"]

    # BackgroundTasks corre dentro del propio ciclo de vida ASGI del
    # TestClient — para cuando la respuesta anterior vuelve, ya ha terminado
    # (nada de red real de por medio, así que no hace falta hacer polling).
    status_resp = client.get(f"/api/automode/{job_id}/status")
    assert status_resp.status_code == 200
    data = status_resp.json()
    assert data["status"] == "done"
    assert "Sin imágenes nuevas" in data["step"]
    assert data["downloaded"] == 0

    results_resp = client.get(f"/api/automode/{job_id}/results")
    assert results_resp.status_code == 200
    assert results_resp.json()["items"] == []

    _clear_calibration(CAM_ID)
