# Estado Actual del Proyecto

← [Volver al indice](README.md)

> Ultima actualizacion: 2026-06-04

---

## Archivos disponibles

| Fichero | Descripcion |
|---------|-------------|
| [`obscape_api.py`](../obscape_api.py) | Cliente API Obscape. Soporta control de duplicados y ventana de 2 semanas. |
| [`proces_images/calibration_tool.py`](../proces_images/calibration_tool.py) | Herramienta de calibracion con soporte para intrinsecos y validacion. |
| [`proces_images/recalibrate.py`](../proces_images/recalibrate.py) | Herramienta de recalibracion rapida mediante arrastre de GCPs. |
| [`visualizar_calibracion.py`](../visualizar_calibracion.py) | Lanzador simplificado para pruebas visuales. |

## Completado [OK]

- [x] Diseno del pipeline completo (modulos 3.0–3.5) -> ver [Pipeline](03_pipeline.md)
- [x] Cliente API Obscape funcional y verificado (`obscape_api.py`)
- [x] Acceso confirmado a las 6 camaras de Guardamar via API
- [x] Implementar modulo de calibracion offline 3.0 (`calibration_tool.py`)
- [x] Script de recalibracion rapida (`recalibrate.py`)
- [x] Validacion matematica de la homografia (`test_calibration_logic.py`)
- [x] Definicion preliminar de ROI por camara (`roi_config.json`)
- [x] IDs y coordenadas de las 6 camaras confirmados
- [x] Prototipo de segmentacion con SAM (modulo 3.2) (`segmentation_sam.py`)
- [x] Prototipo de extraccion de linea de costa (modulo 3.3) (`extract_coastline.py`)
- [x] Script de validacion de pipeline Mes 3 (`test_mes3_pipeline.py`)

## Pendiente [ ]

- [x] Obtener transectos GNSS del IEL (GCPs en EPSG:25830)
- [x] Calibracion final de las 6 camaras con datos reales (perfiles generados en /calibration/)
- [x] Implementar proyeccion a EPSG:25830 (modulo 3.4)
- [x] Implementar postprocesado y exportacion GeoJSON (modulo 3.5)

## Bloqueos activos [BLOQUEO]

1. **Ninguno**: El sistema es funcional end-to-end desde la descarga hasta la generación de GeoJSON georreferenciado.
