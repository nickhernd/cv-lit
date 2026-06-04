# Actualización del Sistema — Descargas y Calibración

Este documento resume las mejoras implementadas en los módulos de adquisición de datos y calibración geométrica.

---

## 1. Automatización de Descargas (`acces_api/`)

Se ha robustecido el sistema de descarga de imágenes de Obscape para asegurar la continuidad del dataset.

### Mejoras principales:
*   **Ventana de Seguridad (Rolling Window)**: El script `scheduled_download.py` ahora revisa por defecto los últimos **14 días**. Esto garantiza que si una descarga falla un día, se recupere automáticamente al día siguiente.
*   **Control de Duplicados**: El cliente API (`obscape_api.py`) comprueba la existencia del archivo en disco antes de descargar. Si la imagen ya existe, se omite para ahorrar ancho de banda.
*   **Formato de Archivo**: Se utiliza un nombre determinista: `YYYYMMDD_HHMMSS_ID.jpg`.
*   **Reporte de Estado**: Al finalizar la descarga, se muestra un resumen con el total de imágenes nuevas y las omitidas.

### Cómo usarlo:
```bash
# Descarga automática (últimas 2 semanas, a las 12:00h)
python3 acces_api/scheduled_download.py

# Personalizar días y hora
python3 acces_api/scheduled_download.py --days 30 --hour 15
```

---

## 2. Mejoras en Calibración Geométrica (`proces_images/`)

Se ha avanzado en el hito del Mes 2 implementando herramientas de precisión y mantenimiento.

### Herramientas nuevas y actualizadas:
*   **`calibration_tool.py` (Actualizado)**:
    *   **Corrección de Distorsión**: Soporte para parámetros intrínsecos (matriz K y coeficientes D).
    *   **Validación Independiente**: Diferenciación entre puntos de calibración (Click Izq.) y validación (Click Der.).
    *   **Reporte Visual (Tecla 'p')**: Exporta una imagen de diagnóstico con los vectores de error magnificados x10.
*   **`recalibrate.py` (Nuevo)**:
    *   Permite actualizar la homografía arrastrando los puntos existentes sobre una nueva imagen. Muy útil si la cámara sufre ligeros movimientos.
*   **`test_calibration_logic.py` (Nuevo)**:
    *   Script de verificación matemática que asegura que los cálculos de RMSE y Homografía son correctos mediante datos sintéticos.

### Cómo usarlo:
*   **Lanzador visual rápido**: `python3 visualizar_calibracion.py`
*   **Recalibración**: `python3 proces_images/recalibrate.py --cam 1 --image ruta/foto.jpg`

---

## 3. Estado de las Issues (Mes 2)

| ID | Tarea | Estado |
|---|---|---|
| #29 | Módulo de corrección de distorsión | ✅ Completado |
| #30 | Estimación homografía con RANSAC | ✅ Completado |
| #31 | Validación con GCPs independientes | ✅ Completado |
| #32 | Guardar perfil de calibración (JSON) | ✅ Completado |
| #33 | Script de recalibración rápida | ✅ Completado |
| #34 | Visualización de reproyección | ✅ Completado |
| #35 | Criterio RMSE < 2px | ✅ Implementado |
| #36 | Criterio RMSE < 1.5m | ✅ Implementado |
