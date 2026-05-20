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

4. Validación
   Error de reproyección sobre GCPs NO usados en estimación
   Umbral de calidad: RMSE < 1.5 px

5. Serialización
   calibration/cam_{i}_H.npy        <- matriz H (3x3)
   calibration/cam_{i}_params.json  <- parámetros intrínsecos + RMSE + fecha
```

## Dependencias

| Librería | Uso |
|----------|-----|
| `opencv-python` | RANSAC, corrección distorsión |
| `numpy` | Álgebra matricial, serialización `.npy` |
| `pyproj` | Validación EPSG:25830 |
| `matplotlib` | Visualización errores de reproyección |

## Salida por cámara

```
calibration/
├── cam_1_H.npy           # matriz H 3x3 en float64
├── cam_1_params.json     # {"fx":..., "fy":..., "cx":..., "cy":...,
│                         #  "k1":..., "k2":..., "p1":..., "p2":...,
│                         #  "k3":..., "rmse_px":..., "date":...}
├── cam_2_H.npy
├── cam_2_params.json
└── ...
```
