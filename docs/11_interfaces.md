# Especificación de Interfaces

← [Volver al índice](README.md)

---

## 1. Interfaz de Entrada (Carga de Datos)
**Objetivo:** Permitir al usuario seleccionar las imágenes a procesar y los parámetros de calibración.

*   **Selector de Directorio:** Explorador de archivos para elegir la ruta de `data/raw/`.
*   **Filtro de Cámara:** Menú desplegable para seleccionar una o todas las cámaras (CAM 1–6).
*   **Rango Temporal:** Selector de fechas (calendario) para filtrar imágenes.
*   **Carga de Perfiles:** Botón para cargar archivos `.json` o `.yaml` con los parámetros intrínsecos/extrínsecos de cada cámara.
*   **Previsualización:** Mostrar la primera imagen del lote para confirmar la ROI.

## 2. Interfaz de Resultados (Visualización)
**Objetivo:** Mostrar el progreso y los resultados intermedios del procesamiento.

*   **Panel de Procesamiento:** Barra de progreso y log en tiempo real.
*   **Vista Dual:**
    *   **Izquierda:** Imagen original con la máscara de SAM superpuesta (semi-transparente).
    *   **Derecha:** Imagen rectificada con la línea de costa detectada superpuesta.
*   **Métricas Rápidas:** Panel lateral con el área segmentada (píxeles) y estimación de error (si hay GCPs disponibles).

## 3. Interfaz de Salida (Exportación)
**Objetivo:** Exportar los datos procesados para su uso en herramientas externas (QGIS).

*   **Botón "Exportar GeoJSON":** Genera un archivo con la geometría `MultiLineString` en EPSG:25830.
*   **Atributos Incluidos:**
    *   `timestamp`: Fecha y hora de captura.
    *   `cam_id`: Identificador de la cámara.
    *   `tide_level`: Nivel de marea (si está integrado).
    *   `quality_flag`: 0 (OK) o 1 (Inválida).
*   **Resumen de Proceso:** Opción de exportar un PDF con el informe de disponibilidad y calidad del lote procesado.
