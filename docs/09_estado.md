# Estado Actual del Proyecto

← [Volver al índice](README.md)

> Última actualización: 2026-06-04

---

## Archivos disponibles

| Fichero | Descripción |
|---------|-------------|
| [`obscape_api.py`](../obscape_api.py) | Cliente API Obscape. Soporta control de duplicados y ventana de 2 semanas. |
| [`proces_images/calibration_tool.py`](../proces_images/calibration_tool.py) | Herramienta de calibración con soporte para intrínsecos y validación. |
| [`proces_images/recalibrate.py`](../proces_images/recalibrate.py) | Herramienta de recalibración rápida mediante arrastre de GCPs. |
| [`visualizar_calibracion.py`](../visualizar_calibracion.py) | Lanzador simplificado para pruebas visuales. |

## Completado ✅

- [x] Diseño del pipeline completo (módulos 3.0–3.5) → ver [Pipeline](03_pipeline.md)
- [x] Cliente API Obscape funcional y automatizado (`obscape_api.py`)
- [x] Implementar módulo de calibración offline 3.0 (#29, #30, #31, #32, #34)
- [x] Script de recalibración rápida (#33)
- [x] Validación matemática de la homografía (`test_calibration_logic.py`)
- [x] IDs y coordenadas de las 6 cámaras confirmados

## Pendiente ⬜

- [ ] Confirmar nombre del proyecto Obscape para las 6 cámaras de Guardamar
- [ ] Obtener transectos GNSS del IEL (GCPs en EPSG:25830)
- [ ] Definir ROI por cámara
- [ ] Implementar segmentación con SAM (módulo 3.2)
- [ ] Implementar extracción de línea de costa (módulo 3.3)
- [ ] Implementar proyección a EPSG:25830 (módulo 3.4)
- [ ] Implementar postprocesado y exportación GeoJSON (módulo 3.5)

## Bloqueos activos 🔴

1. **Acceso API Obscape** para las 6 cámaras: sin esto no hay imágenes de producción. PTM61474 permite desarrollo pero es una cámara distinta a las 6 de Guardamar.
2. **GCPs GNSS del IEL**: sin ellos no se puede ejecutar la calibración (3.0) ni el resto del pipeline.
