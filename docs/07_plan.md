# Plan de Trabajo

← [Volver al indice](README.md)

---

## Cronograma (6 meses)

| Mes | Objetivo | Resultado esperado |
|-----|----------|--------------------|
| 1 | Preparacion datos + diseno interfaces | Base de datos + especificacion tecnica |
| 2 | Calibracion geometrica | Perfiles de calibracion por camara (H + params) |
| 3 | Segmentacion (prototipo) | Prototipo SAM funcional sobre imagenes de Guardamar |
| 4 | Extraccion linea + georreferenciacion | Generacion automatica linea de costa en UTM |
| 5 | Validacion y robustez | Sistema fiable con metricas RMSE/MAE documentadas |
| 6 | Integracion y entrega | Sistema desplegado + manual de uso + informe final |

## Hitos criticos

1. [OK] Confirmacion acceso API Obscape para las 6 camaras *(Completado)*
2. [ ] Recepcion de GCPs GNSS del IEL *(bloquea mes 2 - PENDIENTE)*
3. [OK] Definicion preliminar de ROI por camara *(Completado)*
4. [ ] Primera linea de costa georreferenciada validada manualmente
5. [ ] Validacion cuantitativa con GCPs independientes (objetivo RMSE < 1.5 m)
