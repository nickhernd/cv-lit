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

## Factores de error a monitorizar

- **Calidad de imagen:** niebla, reflejo solar, lluvia, espuma.
- **Mareas:** afectan la posición real de la línea de costa.
- **Deriva de cámara:** movimiento del soporte a lo largo del tiempo.
- **Precisión GCPs:** exactitud del levantamiento GNSS del IEL.
