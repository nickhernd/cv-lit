# Informe de Implementación — Hito Mes 2 (Calibración)

Se ha completado la implementación técnica de la mitad de las tareas del Mes 2, enfocadas en la robustez y mantenimiento del sistema de calibración geométrica.

## Mejoras Implementadas

1.  **Corrección de Distorsión de Lente (#29)**:
    - La clase `CalibrationTool` ahora soporta matrices `K` (intrínsecos) y `D` (distorsión).
    - Los puntos se corrigen automáticamente antes de calcular la homografía.

2.  **Validación Independiente (#31)**:
    - Se ha implementado la distinción entre puntos de **Calibración** (L-Click) y puntos de **Validación** (R-Click).
    - El RMSE se calcula por separado para ambos grupos, permitiendo una validación "ciega" de la calidad del ajuste.

3.  **Herramienta de Recalibración (#33)**:
    - Nuevo script `recalibrate.py` que permite arrastrar los GCPs existentes sobre una nueva imagen. Esto evita tener que reintroducir coordenadas UTM si la cámara sufre un ligero movimiento.

4.  **Visualización y Diagnóstico (#34, #35, #36)**:
    - Tecla `p`: Exporta una imagen de diagnóstico con los vectores de error magnificados (x10).
    - Reporte de RMSE en píxeles y metros directamente en la interfaz.

## Verificación Matemática
- Se ha ejecutado `test_calibration_logic.py` con datos sintéticos, confirmando que el motor de cálculo recupera la homografía con un error residual de ~0.000000 metros.

## Siguientes Pasos
- Cuando el IEL proporcione los GCPs reales (Issue #111), se deberán marcar en las imágenes de cada cámara para generar los perfiles definitivos.
- Comenzar con el Mes 3: Segmentación con SAM.
