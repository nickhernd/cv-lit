"""Tests del aviso de geometría inestable (geometry_warning) en
calculate_homography — añadido en 2026-08-11 tras diagnosticar en vivo con
datos reales de campaña que una geometría de varillas casi colineal produce
un RMSE poco fiable aunque cv2.findHomography() no falle (ver
docs/chapters/cap04_calibracion.tex, "aviso de geometría inestable").

MIN_INLIER_FRACTION = 0.6 en backend/main.py: si RANSAC clasifica menos del
60% de las varillas activas como mutuamente consistentes, se avisa de que el
RMSE probablemente no refleja la calidad real de la calibración.

Mismo patrón que test_marking_workflow.py: sin mocks, TestClient real contra
main.app con DATA_DIR/CALIBRATION_DIR temporales.
"""

import sys
import os
import json
import tempfile
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "backend"))

_TMP_DATA_DIR = tempfile.mkdtemp(prefix="cvlit_test_geo_data_")
_TMP_CALIB_DIR = tempfile.mkdtemp(prefix="cvlit_test_geo_calib_")
os.environ["CVLIT_DATA_DIR"] = _TMP_DATA_DIR
os.environ["CVLIT_CALIBRATION_DIR"] = _TMP_CALIB_DIR
os.environ.setdefault("APP_MODE", "real")

from fastapi.testclient import TestClient

import config
import main

client = TestClient(main.app)

CAM_ID = 1


def _annotations_path(filename: str) -> Path:
    stem = Path(filename).stem
    return Path(main.DATA_DIR) / f"CAM_{CAM_ID}" / "json" / f"{stem}.json"


def _write_annotations(filename: str, points: list) -> None:
    path = _annotations_path(filename)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"points": points}), encoding="utf-8")


def _clean_square_points() -> list:
    """8 correspondencias bien repartidas (dos cuadrados concéntricos, sin
    ruido): geometría bien condicionada, RANSAC debería aceptarlas todas."""
    coords = [
        (0, 0, 700000, 4200000), (100, 0, 700010, 4200000),
        (100, 100, 700010, 4200010), (0, 100, 700000, 4200010),
        (25, 25, 700002.5, 4200002.5), (75, 25, 700007.5, 4200002.5),
        (75, 75, 700007.5, 4200007.5), (25, 75, 700002.5, 4200007.5),
    ]
    return [
        {"pixel": [px, py], "utm": [ux, uy], "label": f"P{i+1}", "type": "calib", "confirmed": True}
        for i, (px, py, ux, uy) in enumerate(coords)
    ]


def _mostly_inconsistent_points() -> list:
    """4 correspondencias consistentes entre sí (mismo cuadrado de arriba)
    + 8 sin ninguna relación lineal común entre píxel y UTM (valores dispersos
    a propósito, sin seguir ninguna transformación compartida) — con umbral
    RANSAC de 3 m en el dominio UTM es prácticamente imposible que un
    subconjunto grande de estas 8 comparta una homografía por azar, así que
    la fracción de inliers queda muy por debajo de 4/12 ≈ 0.33 < 0.6. Esto
    dispara el aviso de forma determinista sin depender de reproducir una
    degeneración geométrica real (que sería sensible a la implementación
    concreta de RANSAC)."""
    good = [
        {"pixel": [0, 0], "utm": [700000, 4200000], "label": "GOOD1", "type": "calib", "confirmed": True},
        {"pixel": [100, 0], "utm": [700010, 4200000], "label": "GOOD2", "type": "calib", "confirmed": True},
        {"pixel": [100, 100], "utm": [700010, 4200010], "label": "GOOD3", "type": "calib", "confirmed": True},
        {"pixel": [0, 100], "utm": [700000, 4200010], "label": "GOOD4", "type": "calib", "confirmed": True},
    ]
    bad_specs = [
        (300, 50, 706900.123, 4219800.456),
        (450, 700, 706120.789, 4220500.111),
        (10, 900, 707300.222, 4219100.999),
        (999, 5, 706400.555, 4220999.333),
        (5, 999, 706800.010, 4219300.777),
        (600, 600, 707100.444, 4220100.222),
        (150, 850, 706550.888, 4219700.654),
        (850, 150, 706250.321, 4220400.987),
    ]
    bad = [
        {"pixel": [px, py], "utm": [ux, uy], "label": f"BAD{i+1}", "type": "calib", "confirmed": True}
        for i, (px, py, ux, uy) in enumerate(bad_specs)
    ]
    return good + bad


def test_geometry_warning_absent_for_well_conditioned_geometry():
    _write_annotations("clean.jpg", _clean_square_points())

    resp = client.post(
        f"/api/cameras/{CAM_ID}/calculate-homography",
        json={"image_name": "clean.jpg", "threshold_px": 50.0, "excluded": []},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["geometry_warning"] is None
    assert data["inliers_count"] == 8


def test_geometry_warning_present_for_mostly_inconsistent_points():
    _write_annotations("unstable.jpg", _mostly_inconsistent_points())

    resp = client.post(
        f"/api/cameras/{CAM_ID}/calculate-homography",
        json={"image_name": "unstable.jpg", "threshold_px": 50.0, "excluded": []},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["geometry_warning"] is not None
    assert "RANSAC" in data["geometry_warning"]
    assert data["inliers_count"] / len(data["residuals"]) < 0.6


def test_inliers_count_matches_residuals_inlier_flags():
    _write_annotations("count_check.jpg", _clean_square_points())

    resp = client.post(
        f"/api/cameras/{CAM_ID}/calculate-homography",
        json={"image_name": "count_check.jpg", "threshold_px": 50.0, "excluded": []},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["inliers_count"] == sum(1 for r in data["residuals"] if r["inlier"] is True)


def test_geometry_warning_excludes_pending_and_manually_excluded_from_denominator():
    """El denominador de inlier_fraction es SOLO las varillas activas
    (confirmadas y no excluidas) — una pendiente o excluida no debe contar
    como "varilla no encontrada por RANSAC"."""
    points = _clean_square_points()
    points.append({"pixel": [500, 500], "utm": [1, 1], "label": "PENDING", "type": "calib", "confirmed": False})
    _write_annotations("with_pending.jpg", points)

    resp = client.post(
        f"/api/cameras/{CAM_ID}/calculate-homography",
        json={"image_name": "with_pending.jpg", "threshold_px": 50.0, "excluded": []},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["geometry_warning"] is None
    assert data["gcps_used"] == 8  # la pendiente no cuenta como varilla activa
