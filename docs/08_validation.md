# Validación

← [Volver al índice](README.md)

---

## Estrategia

Comparación de la línea de costa detectada automáticamente contra **transectos GNSS independientes** del IEL — puntos **no usados** en la calibración de homografía.

## Métricas

**RMSE** (Error cuadrático medio):
```
RMSE = sqrt( (1/N) * sum(di²) )
```

**MAE** (Error medio absoluto):
```
MAE = (1/N) * sum(di)
```

donde `di` es la distancia mínima en metros del punto GNSS i a la polilínea detectada.

## Criterios de aceptación

| Métrica | Objetivo |
|---------|---------|
| RMSE | < 1.5 m en condiciones estándar (12:00h, sin interferencias) |
| MAE | < 1.0 m (objetivo secundario) |
| Cobertura temporal | ≥ 90% de imágenes a 12:00h procesadas sin error |

## Configuración QGIS para Validación

Para realizar la validación visual y métrica, se debe configurar un proyecto en QGIS siguiendo estos pasos:

1.  **Sistema de Coordenadas (CRS):** Configurar el proyecto en `EPSG:25830` (ETRS89 / UTM zona 30N).
2.  **Capas de Referencia:**
    *   **Ortofoto PNOA:** Cargar vía WMS/WMTS del IGN para referencia visual histórica.
    *   **GCPs (GNSS):** Importar el CSV de puntos del IEL como capa de puntos en EPSG:25830.
3.  **Carga de Resultados:**
    *   Los archivos GeoJSON generados por el pipeline en `data/processed/lines/` pueden arrastrarse directamente a QGIS.
4.  **Validación Geométrica:**
    *   Usar la herramienta "Distancia a la polilínea más cercana" para calcular `di` entre puntos GNSS y la línea detectada.

## Factores de error a monitorizar

- **Calidad de imagen:** niebla, reflejo solar, lluvia, espuma.
- **Mareas:** afectan la posición real de la línea de costa.
- **Deriva de cámara:** movimiento del soporte a lo largo del tiempo.
- **Precisión GCPs:** exactitud del levantamiento GNSS del IEL.
