# Estado Actual del Proyecto

← [Volver al índice](README.md)

> Última actualización: 2026-05-20

---

## Archivos disponibles

| Fichero | Descripción |
|---------|-------------|
| [`obscape_api.py`](../obscape_api.py) | Cliente API Obscape. Funcional pero sin acceso a las cámaras de Guardamar aún |
| [`proces_images/images/`](../proces_images/images/) | ~90 imágenes horarias PTM61474 (29/04 – 06/05/2026) |
| `proces_images/horizon_correct.py` | Corrección interactiva de curvatura de horizonte |
| [`map_ubication.png`](../map_ubication.png) | Mapa ubicación proyecto Ketel Haven en Obscape |

## Completado ✅

- [x] Diseño del pipeline completo (módulos 3.0–3.5) → ver [Pipeline](03_pipeline.md)
- [x] Cliente API Obscape funcional (`obscape_api.py`)
- [x] Dataset de prueba disponible (~90 imágenes PTM61474)
- [x] IDs y coordenadas de las 6 cámaras confirmados → ver [Cámaras](04_cameras.md)
- [x] Documentación del sistema

## Pendiente ⬜

- [ ] Confirmar nombre del proyecto Obscape para las 6 cámaras de Guardamar → ver [API](02_api.md)
- [ ] Obtener transectos GNSS del IEL (GCPs en EPSG:25830)
- [ ] Definir ROI por cámara
- [ ] Implementar módulo de calibración offline 3.0 → ver [Calibración](05_calibration.md)
- [ ] Implementar segmentación con SAM (módulo 3.2)
- [ ] Implementar extracción de línea de costa (módulo 3.3)
- [ ] Implementar proyección a EPSG:25830 (módulo 3.4)
- [ ] Implementar postprocesado y exportación GeoJSON (módulo 3.5)
- [ ] Validar con transectos GNSS independientes → ver [Validación](08_validation.md)

## Bloqueos activos 🔴

1. **Acceso API Obscape** para las 6 cámaras: sin esto no hay imágenes de producción. PTM61474 permite desarrollo pero es una cámara distinta a las 6 de Guardamar.
2. **GCPs GNSS del IEL**: sin ellos no se puede ejecutar la calibración (3.0) ni el resto del pipeline.
