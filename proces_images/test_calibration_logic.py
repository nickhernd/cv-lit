import numpy as np
import cv2
import json
import os

def test_homography_math():
    """Verifica que la homografía recupera puntos exactos en un caso ideal."""
    # 1. Puntos UTM sintéticos (un cuadrado de 10m en Guardamar)
    pts_utm = np.array([
        [711000, 4209000],
        [711010, 4209000],
        [711010, 4209010],
        [711000, 4209010]
    ], dtype=np.float32)

    # 2. Homografía arbitraria pero conocida (simulando una cámara)
    H_true = np.array([
        [1.2, 0.1, -853000],
        [0.05, 1.1, -4629000],
        [0.00001, 0.00002, 1.0]
    ])

    # 3. Proyectar UTM -> Pixel para obtener "mediciones" perfectas
    H_true_inv = np.linalg.inv(H_true)
    pts_px = cv2.perspectiveTransform(pts_utm.reshape(-1, 1, 2), H_true_inv).reshape(-1, 2)

    # 4. Estimar H a partir de pts_px y pts_utm
    H_est, _ = cv2.findHomography(pts_px, pts_utm)

    # 5. Validar que la H estimada proyecta de vuelta correctamente
    proj_utm = cv2.perspectiveTransform(pts_px.reshape(-1, 1, 2), H_est).reshape(-1, 2)
    rmse = np.sqrt(np.mean(np.linalg.norm(proj_utm - pts_utm, axis=1)**2))

    print(f"Test Homografía Matemática:")
    print(f"  RMSE proyectado: {rmse:.6f} metros")
    assert rmse < 1e-3, "El error matemático es demasiado alto"
    print("  [OK] Homografía recuperada con precisión.")

if __name__ == "__main__":
    test_homography_math()
