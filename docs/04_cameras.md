# Sistema de Cámaras

← [Volver al índice](README.md)

---

## Estaciones registradas en Obscape

| Cámara | Station ID | Referencia | Latitud (°) | Longitud (°) | Dispositivos | Última actualización |
|--------|-----------|------------|-------------|--------------|:---:|----------------------|
| CAM 1 | 8213 | PTM61471 | 38.110327 | -0.643027 | 1 | 2026-05-20 15:01:55 UTC+2 |
| CAM 2 | 8214 | PTM61474 | 38.096291 | -0.645725 | 1 | 2026-05-20 15:02:15 UTC+2 |
| CAM 3 | 8212 | PTM61473 | 38.087348 | -0.646994 | 1 | 2026-05-20 15:03:28 UTC+2 |
| CAM 4 | 8211 | PTM61475 | 38.087385 | -0.647078 | 1 | 2026-05-20 15:02:24 UTC+2 |
| CAM 5 | 8209 | PTM61472 | 38.076774 | -0.648117 | 1 | 2026-05-20 15:02:11 UTC+2 |
| CAM 6 | 8210 | PTM61470 | 38.076796 | -0.648114 | 1 | 2026-05-20 15:02:13 UTC+2 |

Todas activas · Tipo: Camera · 1 dispositivo acoplado cada una.

## Notas geográficas

- **CAM 3 y CAM 4** son casi coincidentes (~38.0874°N, ~-0.647°E) — probablemente cubren el mismo tramo desde ángulos distintos.
- **CAM 5 y CAM 6** también son casi coincidentes (~38.0768°N, ~-0.6481°E).
- Las cámaras se distribuyen de norte a sur a lo largo del frente litoral.

## Ver en mapa

| Cámara | Google Maps | OpenStreetMap |
|--------|------------|---------------|
| CAM 1 | [38.110327, -0.643027](https://www.google.com/maps?q=38.110327,-0.643027) | [OSM](https://www.openstreetmap.org/?mlat=38.110327&mlon=-0.643027&zoom=17) |
| CAM 2 | [38.096291, -0.645725](https://www.google.com/maps?q=38.096291,-0.645725) | [OSM](https://www.openstreetmap.org/?mlat=38.096291&mlon=-0.645725&zoom=17) |
| CAM 3 | [38.087348, -0.646994](https://www.google.com/maps?q=38.087348,-0.646994) | [OSM](https://www.openstreetmap.org/?mlat=38.087348&mlon=-0.646994&zoom=17) |
| CAM 4 | [38.087385, -0.647078](https://www.google.com/maps?q=38.087385,-0.647078) | [OSM](https://www.openstreetmap.org/?mlat=38.087385&mlon=-0.647078&zoom=17) |
| CAM 5 | [38.076774, -0.648117](https://www.google.com/maps?q=38.076774,-0.648117) | [OSM](https://www.openstreetmap.org/?mlat=38.076774&mlon=-0.648117&zoom=17) |
| CAM 6 | [38.076796, -0.648114](https://www.google.com/maps?q=38.076796,-0.648114) | [OSM](https://www.openstreetmap.org/?mlat=38.076796&mlon=-0.648114&zoom=17) |

## Dataset de prueba

**CAM 2** (PTM61474) — imágenes en [`proces_images/images/`](../proces_images/images/)

- ~90 imágenes horarias (04:00–18:00h)
- Período: 29/04/2026 – 06/05/2026
- Origen: ZIP `camera_8214_from20260429_174800.zip` (facilitado manualmente)

## Perfiles de calibración (pendientes)

| Cámara | H matriz | Parámetros |
|--------|----------|------------|
| CAM 1 | `calibration/cam_1_H.npy` | `calibration/cam_1_params.json` |
| CAM 2 | `calibration/cam_2_H.npy` | `calibration/cam_2_params.json` |
| CAM 3 | `calibration/cam_3_H.npy` | `calibration/cam_3_params.json` |
| CAM 4 | `calibration/cam_4_H.npy` | `calibration/cam_4_params.json` |
| CAM 5 | `calibration/cam_5_H.npy` | `calibration/cam_5_params.json` |
| CAM 6 | `calibration/cam_6_H.npy` | `calibration/cam_6_params.json` |

Ver [Calibración](05_calibration.md) para el proceso de estimación.
