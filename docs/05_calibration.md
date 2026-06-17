# Módulo de Calibración Offline [3.0]

← [Volver al índice](README.md)

---

## Descripción

Ejecución **única por cámara** (repetir si se reposiciona). Previa al pipeline de producción.

## Entradas

- **GCPs GNSS del IEL:** puntos de control con coordenadas (X, Y, Z) en EPSG:25830 y su píxel imagen (u, v). Mínimo 4 pares, recomendado ≥8.
- **Imagen de referencia:** fotografía de la escena en condiciones estables.

## Proceso

```
1. Corrección de distorsión
   cv2.calibrateCamera() con tablero de ajedrez o los propios GCPs
   → focal (fx, fy), centro óptico (cx, cy), coeficientes k1 k2 p1 p2 k3

2. Emparejamiento GCP <-> píxel
   Manual o semi-automático

3. Estimación de homografía con RANSAC
   H = cv2.findHomography(pts_img, pts_world, cv2.RANSAC, ransacReprojThreshold=5.0)
## Resultados de Calibración (Junio 2026)

Tras procesar los GCPs proporcionados por el IEL, se han obtenido los siguientes resultados de precisión:

| Cámara | Puntos | RMSE Calib (m) | RMSE Valid (m) | RMSE Valid (px) | Estado |
|--------|--------|----------------|----------------|-----------------|--------|
| CAM 1  | 51     | 1.53           | 1.45           | 19.36           | [OK]   |
| CAM 2  | 39     | 2.64           | 3.45           | 21.09           | [!] Revisar |
| CAM 3  | 49     | 1.61           | 2.32           | 38.38           | [OK]   |
| CAM 4  | 49     | 2.78           | 3.06           | 100.01          | [!] Revisar |
| CAM 5  | 61     | 1.45           | 1.38           | 14.81           | [OK]   |
| CAM 6  | 69     | 6.14           | 4.74           | 130.62          | [!] Crítico |

> **Nota:** Los errores elevados en CAM 4 y CAM 6 sugieren la necesidad de aplicar corrección de distorsión radial (intrínsecos) o revisar la consistencia de los puntos manuales.

## Salida por cámara

```
calibration/
├── cam_1_H.npy           # matriz H 3x3 en float64
├── cam_1_profile.json     # Metadatos, RMSE y fecha
├── diagnostics/
│   └── CAM1_diagnostic.jpg # Visualización GCPs vs Reproyección
└── ...
```

