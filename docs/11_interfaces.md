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

## 3. Interfaz de Validación por Lotes (Alineación Masiva)

> Implementada en `frontend/src/components/BatchAlignment.vue` + `backend/batch_alignment.py`.
> Documentación completa: [14_batch_alignment.md](14_batch_alignment.md)

**Objetivo:** Sustituir la validación unitaria imagen a imagen por un flujo de revisión masiva
donde el operador define una imagen base y el sistema alinea todo el set automáticamente.

**Fases de la interfaz:**

1. **Configuración** — selector de imagen base + checkboxes para incluir/excluir imágenes del lote.
2. **Procesamiento** — barra de progreso en tiempo real (polling 800ms al backend).
3. **Revisión** — interfaz unificada con:
   - **Filmstrip** lateral con indicadores de estado por imagen (verde/ámbar/rojo/azul).
   - **Visor dual** side-by-side: original izquierda, resultado derecha.
   - **Tres modos de comparación:** mapa de delta, blend 50/50 en B&W, imagen alineada.
   - **Métricas por imagen:** inliers RANSAC + desplazamiento residual en píxeles.
   - **Override individual:** el operador puede desaprobar imágenes concretas antes del commit.
4. **Commit** — confirmación del lote completo → carga directa al módulo de marcación (`CAM_X/aligned/`).

**Principio de no-destructividad:** los originales nunca se tocan hasta el commit explícito.
Todo el trabajo intermedio vive en `/tmp/cv_lit_batch/{job_id}/`.

---

## 4. Interfaz de Salida (Exportación)
**Objetivo:** Exportar los datos procesados para su uso en herramientas externas (QGIS).

*   **Botón "Exportar GeoJSON":** Genera un archivo con la geometría `MultiLineString` en EPSG:25830.
*   **Atributos Incluidos:**
    *   `timestamp`: Fecha y hora de captura.
    *   `cam_id`: Identificador de la cámara.
    *   `tide_level`: Nivel de marea (si está integrado).
    *   `quality_flag`: 0 (OK) o 1 (Inválida).
*   **Resumen de Proceso:** Opción de exportar un PDF con el informe de disponibilidad y calidad del lote procesado.
