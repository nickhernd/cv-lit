# Plan de Trabajo

← [Volver al índice](README.md)

---

## Cronograma (6 meses)

| Mes | Objetivo | Resultado esperado |
|-----|----------|--------------------|
| 1 | Preparación datos + diseño interfaces | Base de datos + especificación técnica |
| 2 | Calibración geométrica | Perfiles de calibración por cámara (H + params) |
| 3 | Segmentación (prototipo) | Prototipo SAM funcional sobre imágenes de Guardamar |
| 4 | Extracción línea + georreferenciación | Generación automática línea de costa en UTM |
| 5 | Validación y robustez | Sistema fiable con métricas RMSE/MAE documentadas |
| 6 | Integración y entrega | Sistema desplegado + manual de uso + informe final |

## Hitos críticos

1. ✅ → ⬜ Confirmación acceso API Obscape para las 6 cámaras *(bloquea mes 1–2)*
2. ⬜ Recepción de GCPs GNSS del IEL *(bloquea mes 2)*
3. ⬜ Definición de ROI por cámara *(bloquea módulo SAM)*
4. ⬜ Primera línea de costa georreferenciada validada manualmente
5. ⬜ Validación cuantitativa con GCPs independientes (objetivo RMSE < 1.5 m)
