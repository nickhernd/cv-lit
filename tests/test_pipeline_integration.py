#!/usr/bin/env python3
"""
test_pipeline_integration.py - Tests de integracion del pipeline Mes 3 + Mes 4.

Issue #107 — 7 tests pytest que cubren el flujo completo mockeando SAM.

Tests:
  1. test_sam_segmenter_no_model        — SAMSegmenter sin checkpoint no crashea.
  2. test_remove_false_detections       — Filtro HSV elimina espuma sintetica.
  3. test_temporal_consistency_low_iou  — IoU bajo → inconsistente.
  4. test_temporal_consistency_high_iou — IoU alto → consistente.
  5. test_extract_coastline_synthetic   — Linea de costa extraida de mascara rectangular.
  6. test_pixels_to_utm_identity        — Proyeccion con H identidad.
  7. test_confidence_index_range        — Indice de confianza dentro de [0,1].
"""

import sys
import numpy as np
import pytest
from pathlib import Path

# Asegurar imports desde raiz del proyecto
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from proces_images.segmentation_sam import (
    SAMSegmenter,
    remove_false_detections,
    check_temporal_consistency,
    generate_probability_map,
)
from proces_images.extract_coastline import extract_coastline_from_mask
from proces_images.georef_export import pixels_to_utm, confidence_index


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture()
def blank_image_800():
    """Imagen BGR 800x600 en gris medio."""
    return np.full((600, 800, 3), 128, dtype=np.uint8)


@pytest.fixture()
def mask_lower_half():
    """Mascara binaria con la mitad inferior activa (simula arena)."""
    m = np.zeros((600, 800), dtype=np.uint8)
    m[300:, :] = 255
    return m


@pytest.fixture()
def H_identity():
    """Homografia que mapea pixeles a metros 1:1 (caso degenerado para test)."""
    return np.eye(3, dtype=np.float64)


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_sam_segmenter_no_model():
    """SAMSegmenter sin checkpoint inicializa sin lanzar excepciones (#43)."""
    seg = SAMSegmenter(model_type="vit_h", checkpoint_path=None)
    assert seg.predictor is None  # sin modelo, predictor es None


def test_remove_false_detections(blank_image_800, mask_lower_half):
    """Zona de espuma HSV (blanco saturado) debe eliminarse de la mascara (#48)."""
    image = blank_image_800.copy()
    mask  = mask_lower_half.copy()

    # Pintar zona de espuma (S=0, V=240 en HSV → R=G=B=240 en BGR)
    espuma_color = np.array([240, 240, 240], dtype=np.uint8)
    image[400:450, 100:300] = espuma_color

    result = remove_false_detections(mask, image)

    # La zona de espuma debe estar apagada en el resultado
    espuma_region = result[400:450, 100:300]
    assert espuma_region.max() == 0, "La espuma deberia haberse eliminado"

    # El tercio superior siempre se elimina
    assert result[:200, :].max() == 0, "El tercio superior siempre se elimina"


def test_temporal_consistency_low_iou():
    """IoU muy bajo (mascaras disjuntas) → inconsistente (#50)."""
    prev = np.zeros((100, 100), dtype=np.uint8)
    curr = np.zeros((100, 100), dtype=np.uint8)
    prev[:, :50] = 255   # mitad izquierda
    curr[:, 50:] = 255   # mitad derecha

    consistent, iou = check_temporal_consistency(prev, curr, threshold=0.15)
    assert not consistent, f"IoU={iou:.3f} deberia ser inconsistente"
    assert iou == pytest.approx(0.0, abs=0.01)


def test_temporal_consistency_high_iou():
    """IoU alto (mascaras casi identicas) → consistente (#50)."""
    prev = np.zeros((100, 100), dtype=np.uint8)
    curr = np.zeros((100, 100), dtype=np.uint8)
    prev[20:80, 20:80] = 255
    curr[22:82, 20:80] = 255  # desplazamiento minimo

    consistent, iou = check_temporal_consistency(prev, curr, threshold=0.15)
    assert consistent, f"IoU={iou:.3f} deberia ser consistente"
    assert iou > 0.8


def test_extract_coastline_synthetic():
    """Mascara con banda horizontal extrae linea de costa (#56, #57, #58)."""
    # Rectangulo en parte inferior: simula arena seca cruzando todo el ancho
    mask = np.zeros((600, 800), dtype=np.uint8)
    mask[350:580, 30:770] = 255  # banda ancha, en la mitad inferior

    points = extract_coastline_from_mask(mask, min_length=100, smooth=False)

    assert points is not None, "Deberia detectarse una linea de costa"
    assert len(points) >= 4, f"Demasiados pocos puntos: {len(points)}"

    # Los puntos deben estar en la mitad inferior
    raw = [p["point"] if isinstance(p, dict) else p for p in points]
    ys = [pt[1] for pt in raw]
    assert all(y >= 300 for y in ys), "Los puntos deben estar en la mitad inferior"


def test_pixels_to_utm_identity(H_identity):
    """Con homografia identidad, los pixeles se mapean a coordenadas UTM iguales (#64)."""
    pts_px = np.array([[100.0, 200.0], [300.0, 400.0]])
    utm = pixels_to_utm(pts_px, H_identity)

    assert utm.shape == (2, 2)
    np.testing.assert_allclose(utm, pts_px, rtol=1e-6)


def test_confidence_index_range(mask_lower_half):
    """El indice de confianza debe estar dentro de [0, 1] (#66)."""
    # Caso con calibracion perfecta (RMSE=0) y mascara valida
    ci = confidence_index(mask_lower_half, rmse_m=0.5)
    assert 0.0 <= ci <= 1.0, f"Confianza fuera de rango: {ci}"

    # Caso degradado: RMSE muy alto
    ci_bad = confidence_index(mask_lower_half, rmse_m=100.0)
    assert 0.0 <= ci_bad <= 1.0
    assert ci_bad < ci, "Con RMSE alto la confianza debe ser menor"

    # Caso sin mascara
    ci_none = confidence_index(None, rmse_m=1.5)
    assert 0.0 <= ci_none <= 1.0
