# Pipeline de Procesamiento

← [Volver al índice](README.md)

---

## Esquema general

```
Imágenes cámaras (Obscape API / dataset manual)
      |
      v
[3.1] Adquisición y preprocesado
      +-- Normalización radiométrica
      +-- Corrección de contraste/balance
      \-- Recorte ROI por cámara
      |
      v
[3.2] Segmentación semántica (SAM)
      +-- Generación de regiones candidatas
      +-- Mapa probabilístico arena seca / húmeda / agua
      \-- Umbral adaptativo + filtrado morfológico -> máscara binaria
      |
      v
[3.3] Extracción de línea de costa
      +-- Cálculo de contornos (cv2.findContours)
      \-- Selección borde húmedo-seco -> polilínea en píxeles
      |
      v
[3.4] Proyección homografía
      \-- (u,v) píxel -> (X,Y) metros EPSG:25830
      |
      v
[3.5] Postprocesado + exportación
      +-- Suavizado / simplificación métrica
      +-- Filtros temporales (detección de anomalías)
      +-- Cálculo de área seca (m²)
      \-- GeoJSON: ID_Camara, Timestamp, Confianza_IA, Area_Seca_m2
```

---

## Módulo offline [3.0] — Calibración

Ejecución única por cámara. Ver [Calibración](05_calibration.md).

- Transectos GNSS del IEL (GCPs en EPSG:25830)
- Correspondencias píxel ↔ UTM
- Corrección distorsión de lente (parámetros intrínsecos, OpenCV)
- RANSAC → matriz H por cámara
- **Producto:** perfil de calibración (H + parámetros cámara + metadatos)

---

## Etapa 3.1 — Adquisición y preprocesado

- Descarga automática via [`obscape_api.py`](../obscape_api.py) (cuando las cámaras estén registradas).
- Fase horaria prioritaria: **12:00h solar local**.
- Por cámara: normalización radiométrica, corrección de contraste y balance de blancos, recorte a la ROI.

## Etapa 3.2 — Segmentación semántica con SAM

- Modelo: **Segment Anything Model (SAM)** de Meta AI → https://github.com/facebookresearch/segment-anything
- Modo *zero-shot*: sin datos de entrenamiento específicos de Guardamar.
- Prompt basado en puntos semilla o bounding boxes de la ROI por cámara.
- Salida: mapa probabilístico arena seca / arena húmeda / agua.
- Post-SAM: umbral adaptativo + filtrado morfológico → máscara binaria.

## Etapa 3.3 — Extracción de línea de costa

1. Cálculo de contornos sobre la máscara binaria (`cv2.findContours`).
2. Selección del contorno correspondiente al borde *arena húmeda – arena seca*.
3. Resultado: polilínea en coordenadas de píxel (u, v).

## Etapa 3.4 — Proyección por homografía

La homografía H_i transforma coordenadas imagen a EPSG:25830:

```
[X]       [u]
[Y] ~ H_i [v]
[1]       [1]
```

H_i (3×3) se carga desde el perfil de calibración de la cámara i.

## Etapa 3.5 — Postprocesado y exportación

- **Suavizado geométrico:** Douglas-Peucker o suavizado gaussiano.
- **Filtros temporales:** detección de anomalías respecto a la imagen anterior.
- **Cálculo de área seca:** integración del polígono en m².
- **Exportación GeoJSON:**

```json
{
  "type": "FeatureCollection",
  "crs": {
    "type": "name",
    "properties": { "name": "EPSG:25830" }
  },
  "features": [{
    "type": "Feature",
    "geometry": {
      "type": "LineString",
      "coordinates": [[711234.5, 4209876.3], ["..."]]
    },
    "properties": {
      "ID_Camara":    1,
      "Timestamp":    "2026-04-30T12:00:00Z",
      "Confianza_IA": 0.93,
      "Area_Seca_m2": 14250.7
    }
  }]
}
```
