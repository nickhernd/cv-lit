"""Tests de la lógica de Marcación/Alineación añadida en 2026-07-25:
    - varillas "pendientes de confirmar" (confirmed=False) excluidas del ajuste
      de la homografía, y el mensaje de error que distingue pendientes de
      exclusiones manuales.
    - resolución de la imagen a usar para marcar/analizar (aligned/ vs original).
    - endpoint de info de alineación por imagen.
    - reproyección de anotaciones cuando cambia la H de alineación de una imagen.

No mockean nada: levantan main.app con un DATA_DIR/CALIBRATION_DIR temporales
(vía las variables de entorno CVLIT_DATA_DIR/CVLIT_CALIBRATION_DIR, que se
DEBEN fijar antes de importar config/main — esos módulos las leen una sola vez
al cargarse). Por eso este archivo importa backend/ de forma manual en vez de
depender de un conftest.py compartido.

Aviso para quien añada más tests de main.py/batch_alignment.py: una vez este
archivo se ha importado en el proceso de pytest, main/config quedan cacheados
en sys.modules apuntando a estos directorios temporales — reutiliza `client`,
`config` y `main` de aquí en vez de volver a importarlos con otras rutas.
"""

import sys
import os
import json
import tempfile
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "backend"))

_TMP_DATA_DIR = tempfile.mkdtemp(prefix="cvlit_test_data_")
_TMP_CALIB_DIR = tempfile.mkdtemp(prefix="cvlit_test_calib_")
os.environ["CVLIT_DATA_DIR"] = _TMP_DATA_DIR
os.environ["CVLIT_CALIBRATION_DIR"] = _TMP_CALIB_DIR
os.environ.setdefault("APP_MODE", "real")

import pytest
from fastapi.testclient import TestClient

import config
import main
import batch_alignment

client = TestClient(main.app)

CAM_ID = 1
FOLDER = config.CAMERAS[CAM_ID]["folder"]


def _annotations_path(filename: str) -> Path:
    stem = Path(filename).stem
    return Path(main.DATA_DIR) / f"CAM_{CAM_ID}" / "json" / f"{stem}.json"


def _write_annotations(filename: str, points: list) -> None:
    path = _annotations_path(filename)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"points": points}), encoding="utf-8")


def _four_confirmed_points() -> list:
    """Cuatro correspondencias no degeneradas (escala 0.1 + traslación pura),
    suficientes para que cv2.findHomography ajuste sin ambigüedad."""
    return [
        {"pixel": [0, 0], "utm": [700000, 4200000], "label": "P1", "type": "calib", "confirmed": True},
        {"pixel": [100, 0], "utm": [700010, 4200000], "label": "P2", "type": "calib", "confirmed": True},
        {"pixel": [100, 100], "utm": [700010, 4200010], "label": "P3", "type": "calib", "confirmed": True},
        {"pixel": [0, 100], "utm": [700000, 4200010], "label": "P4", "type": "calib", "confirmed": True},
    ]


# ── calculate_homography: pendientes excluidas del ajuste ────────────────────

def test_calculate_homography_excludes_pending_point():
    points = _four_confirmed_points()
    points.append({"pixel": [50, 50], "utm": [700005, 4200005], "label": "PENDING", "type": "calib", "confirmed": False})
    _write_annotations("imgA.jpg", points)

    resp = client.post(
        f"/api/cameras/{CAM_ID}/calculate-homography",
        json={"image_name": "imgA.jpg", "threshold_px": 5.0, "excluded": []},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["gcps_used"] == 4  # la pendiente no cuenta como "usada"

    pending_residual = next(r for r in data["residuals"] if r["label"] == "PENDING")
    assert pending_residual["pending"] is True
    assert pending_residual["excluded"] is False  # no es una exclusión del usuario
    assert pending_residual["inlier"] is None      # fuera del ajuste RANSAC


def test_calculate_homography_blocks_and_explains_pending():
    points = _four_confirmed_points()[:2]  # solo 2 confirmadas
    points.append({"pixel": [10, 10], "utm": [700001, 4200001], "label": "PEND1", "type": "calib", "confirmed": False})
    points.append({"pixel": [20, 20], "utm": [700002, 4200002], "label": "PEND2", "type": "calib", "confirmed": False})
    _write_annotations("imgB.jpg", points)

    resp = client.post(
        f"/api/cameras/{CAM_ID}/calculate-homography",
        json={"image_name": "imgB.jpg", "threshold_px": 5.0, "excluded": []},
    )
    assert resp.status_code == 400
    detail = resp.json()["detail"]
    assert "2 pendiente" in detail
    assert "excluida" not in detail  # no hay exclusiones manuales aquí


def test_calculate_homography_blocks_and_explains_manual_exclusion():
    points = _four_confirmed_points()  # las 4 confirmadas
    _write_annotations("imgC.jpg", points)

    resp = client.post(
        f"/api/cameras/{CAM_ID}/calculate-homography",
        json={"image_name": "imgC.jpg", "threshold_px": 5.0, "excluded": [0]},
    )
    assert resp.status_code == 400
    detail = resp.json()["detail"]
    assert "1 excluida" in detail
    assert "pendiente" not in detail  # no hay pendientes aquí, solo exclusión manual


# ── Info de alineación por imagen ─────────────────────────────────────────────

def test_alignment_endpoint_without_sidecar():
    resp = client.get(f"/api/cameras/{CAM_ID}/images/no-existe.jpg/alignment")
    assert resp.status_code == 200
    assert resp.json() == {"aligned": False}


def test_alignment_endpoint_with_sidecar():
    aligned_dir = Path(main.DATA_DIR) / FOLDER / "aligned"
    aligned_dir.mkdir(parents=True, exist_ok=True)
    (aligned_dir / "imgD.jpg.align.json").write_text(
        json.dumps({"aligned": True, "H": [1, 0, 0, 0, 1, 0, 0, 0, 1], "inliers": 55}),
        encoding="utf-8",
    )
    resp = client.get(f"/api/cameras/{CAM_ID}/images/imgD.jpg/alignment")
    assert resp.status_code == 200
    data = resp.json()
    assert data["aligned"] is True
    assert data["inliers"] == 55


# ── Resolución de imagen para marcar/analizar ─────────────────────────────────

def test_resolve_camera_image_path_prefers_aligned_when_present():
    base_dir = Path(main.DATA_DIR) / FOLDER
    base_dir.mkdir(parents=True, exist_ok=True)
    (base_dir / "imgE.jpg").write_bytes(b"raw")

    assert main._resolve_camera_image_path(CAM_ID, "imgE.jpg") == str(base_dir / "imgE.jpg")

    aligned_dir = base_dir / "aligned"
    aligned_dir.mkdir(exist_ok=True)
    (aligned_dir / "imgE.jpg").write_bytes(b"aligned")

    assert main._resolve_camera_image_path(CAM_ID, "imgE.jpg") == str(aligned_dir / "imgE.jpg")


# ── Reproyección de anotaciones al cambiar la H de alineación ────────────────

def test_reproject_annotations_rescales_pixel_and_marks_pending():
    ann_path = _annotations_path("imgF.jpg")
    ann_path.parent.mkdir(parents=True, exist_ok=True)
    ann_path.write_text(json.dumps({"points": [
        {"pixel": [100.0, 100.0], "utm": [1, 1], "label": "P", "type": "calib", "confirmed": True},
    ]}), encoding="utf-8")

    new_H = [2, 0, 0, 0, 2, 0, 0, 0, 1]  # escala x2
    changed = batch_alignment._reproject_annotations(
        CAM_ID, "imgF.jpg", new_H, w=1000, h=1000, committed_at="2026-01-01T00:00:00"
    )
    assert changed == 1

    data = json.loads(ann_path.read_text(encoding="utf-8"))
    p = data["points"][0]
    assert p["pixel"] == pytest.approx([200.0, 200.0])
    assert p["rel"] == pytest.approx([20.0, 20.0])  # 200/1000 * 100
    assert p["confirmed"] is False
    assert p["reprojected_at"] == "2026-01-01T00:00:00"

    # Volver a aplicar la MISMA H no debe tocar nada (ya está expresado en ella).
    changed_again = batch_alignment._reproject_annotations(
        CAM_ID, "imgF.jpg", new_H, w=1000, h=1000, committed_at="2026-01-01T00:00:01"
    )
    assert changed_again == 0
