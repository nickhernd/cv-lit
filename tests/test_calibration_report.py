"""Tests de los endpoints de metadatos de perfil e informe PDF
(PUT /api/cameras/{id}/profile-metadata, GET /api/cameras/{id}/calibration-report.pdf)
— añadidos en 2026-08-11, cuando llevaban toda la ronda de trabajo (fase B)
sin cobertura automática pese al hardening de _pdf_safe() contra texto no
Latin-1 (operador/notas con acentos, guiones largos, emojis).

Sin mocks: usa el endpoint real /calculate-homography (ya cubierto en
test_geometry_warning.py) para dejar profile.json/anotaciones en un estado
válido, más una imagen JPG sintética real en disco para que
_build_calibration_report_pdf() pueda leer sus dimensiones.

Mismo patrón que test_marking_workflow.py: TestClient real contra main.app
con DATA_DIR/CALIBRATION_DIR temporales.
"""

import sys
import os
import json
import tempfile
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "backend"))

_TMP_DATA_DIR = tempfile.mkdtemp(prefix="cvlit_test_report_data_")
_TMP_CALIB_DIR = tempfile.mkdtemp(prefix="cvlit_test_report_calib_")
os.environ["CVLIT_DATA_DIR"] = _TMP_DATA_DIR
os.environ["CVLIT_CALIBRATION_DIR"] = _TMP_CALIB_DIR
os.environ.setdefault("APP_MODE", "real")

import numpy as np
import cv2
from fastapi.testclient import TestClient

import config
import main

client = TestClient(main.app)

CAM_ID = 1
FOLDER = config.CAMERAS[CAM_ID]["folder"]
IMAGE_NAME = "informe_test.jpg"


def _annotations_path(filename: str) -> Path:
    stem = Path(filename).stem
    return Path(main.DATA_DIR) / f"CAM_{CAM_ID}" / "json" / f"{stem}.json"


def _calibrate_camera():
    """Deja la cámara con una calibración real y válida: imagen JPG en disco
    + 4 GCPs bien condicionados + POST a /calculate-homography (igual que
    haría el frontend en el paso Cálculo)."""
    img_dir = Path(config.DATA_DIR) / FOLDER
    img_dir.mkdir(parents=True, exist_ok=True)
    img = np.full((200, 300, 3), 128, dtype=np.uint8)
    cv2.imwrite(str(img_dir / IMAGE_NAME), img)

    points = [
        {"pixel": [0, 0], "utm": [700000, 4200000], "label": "P1", "type": "calib", "confirmed": True},
        {"pixel": [100, 0], "utm": [700010, 4200000], "label": "P2", "type": "calib", "confirmed": True},
        {"pixel": [100, 100], "utm": [700010, 4200010], "label": "P3", "type": "calib", "confirmed": True},
        {"pixel": [0, 100], "utm": [700000, 4200010], "label": "P4", "type": "calib", "confirmed": True},
    ]
    ann_path = _annotations_path(IMAGE_NAME)
    ann_path.parent.mkdir(parents=True, exist_ok=True)
    ann_path.write_text(json.dumps({"points": points}), encoding="utf-8")

    resp = client.post(
        f"/api/cameras/{CAM_ID}/calculate-homography",
        json={"image_name": IMAGE_NAME, "threshold_px": 50.0, "excluded": []},
    )
    assert resp.status_code == 200


def setup_module(module):
    _calibrate_camera()


# ── PUT /profile-metadata ─────────────────────────────────────────────────────

def test_profile_metadata_round_trips_plain_text():
    resp = client.put(f"/api/cameras/{CAM_ID}/profile-metadata", json={
        "profile_name": "Campaña test",
        "operator": "J. Perez",
        "notes": "Sin incidencias",
    })
    assert resp.status_code == 200

    profile_resp = client.get(f"/api/cameras/{CAM_ID}/profile")
    profile = profile_resp.json()
    assert profile["profile_name"] == "Campaña test"
    assert profile["operator"] == "J. Perez"
    assert profile["notes"] == "Sin incidencias"


def test_profile_metadata_unknown_camera_returns_404():
    resp = client.put("/api/cameras/999/profile-metadata", json={"profile_name": "x"})
    assert resp.status_code == 404


def test_profile_metadata_partial_update_does_not_clear_other_fields():
    client.put(f"/api/cameras/{CAM_ID}/profile-metadata", json={"operator": "Operador A"})
    client.put(f"/api/cameras/{CAM_ID}/profile-metadata", json={"notes": "Nota nueva"})

    profile = client.get(f"/api/cameras/{CAM_ID}/profile").json()
    assert profile["operator"] == "Operador A"  # no se perdió al actualizar solo notes
    assert profile["notes"] == "Nota nueva"


# ── GET /calibration-report.pdf ───────────────────────────────────────────────

def test_calibration_report_pdf_generates_successfully():
    resp = client.get(f"/api/cameras/{CAM_ID}/calibration-report.pdf")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.content[:4] == b"%PDF"  # cabecera real de un PDF válido
    assert len(resp.content) > 1000


def test_calibration_report_pdf_survives_non_latin1_metadata():
    """El caso que motivó _pdf_safe(): em-dash, acentos y emoji en los campos
    de texto libre NO deben tumbar la generación (FPDFUnicodeEncodingException)."""
    client.put(f"/api/cameras/{CAM_ID}/profile-metadata", json={
        "profile_name": "Perfil piloto — verano 2026 🌊",
        "operator": "María Ángeles Peña",
        "notes": "Ojo: revisar en próxima campaña — prioridad alta. Emoji: ✅❌",
    })

    resp = client.get(f"/api/cameras/{CAM_ID}/calibration-report.pdf")
    assert resp.status_code == 200
    assert resp.content[:4] == b"%PDF"


def test_calibration_report_unknown_camera_returns_404():
    resp = client.get("/api/cameras/999/calibration-report.pdf")
    assert resp.status_code == 404


def test_calibration_report_without_calibration_returns_404():
    resp = client.get("/api/cameras/3/calibration-report.pdf")  # CAM 3, nunca calibrada en este test
    assert resp.status_code == 404
