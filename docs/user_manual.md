# CV-LIT — Manual de Usuario

Sistema de monitorización costera con visión por computador para 6 cámaras fijas en Guardamar del Segura (Alicante).

---

## 1. Requisitos e instalación

**Software necesario:**
- Python 3.11+
- Node.js 18+
- OpenCV, NumPy, FastAPI, Uvicorn (ver `backend/requirements.txt`)
- Vue 3 + Vite + Tailwind (instalados con npm)

**Instalación:**
```bash
# Clonar repositorio
git clone <url> cv-lit && cd cv-lit

# Entorno Python
conda env create -f environment.yml
conda activate cv-lit

# Dependencias frontend
cd frontend && npm install && cd ..
```

---

## 2. Arrancar el sistema

**Backend (FastAPI):**
```bash
cd backend
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

**Frontend (Vue/Vite):**
```bash
cd frontend
npm run dev
```

Abrir el navegador en `http://localhost:5173`.

**Modo demo** (sin SAM ni datos reales):
```bash
APP_MODE=demo uvicorn main:app --reload
```

---

## 3. Calibración de cámaras

La calibración establece la homografía píxel → UTM (EPSG:25830) para cada cámara.

1. Ir a **Calibración** en el menú lateral.
2. Seleccionar la cámara (1–6).
3. Marcar los GCPs (Ground Control Points) en la imagen: hacer clic en el punto visible y asignar las coordenadas UTM (X, Y) del GCP correspondiente.
   - Mínimo 4 GCPs de tipo `calib`, recomendado 8+.
   - Los GCPs de validación (`val`) no se usan en el ajuste; sirven para medir el RMSE independiente.
4. Pulsar **Calcular homografía**.
   - El sistema calcula H con RANSAC y muestra RMSE en metros.
   - Objetivo: RMSE < 1.5 m.
5. El perfil se guarda automáticamente en `calibration/cam_X_profile.json` y `calibration/cam_X_profile.yaml`.

---

## 4. Análisis de línea de costa

1. Ir a **Análisis Costa** en el menú lateral.
2. Seleccionar la cámara y la imagen a procesar.
3. Pulsar **Analizar imagen**.
   - El sistema ejecuta segmentación (SAM si está disponible, fallback por color/Otsu).
   - Aparece la imagen con la línea de costa dibujada en rojo.
   - Si la confianza es baja (< umbral por cámara), la imagen se rechaza automáticamente.
4. Las métricas se muestran en el panel derecho:
   - **Confianza IA**: barra verde/amarillo/rojo según nivel de certeza.
   - **Área seca (m²)**: extensión de arena seca estimada.
   - **Puntos UTM**: número de vértices de la polilínea en coordenadas UTM.

### Umbrales de confianza por cámara

| Cámara | Confianza mínima |
|--------|-----------------|
| 1, 2, 5 | 0.45 |
| 3, 4 | 0.40 |
| 6 | 0.50 |

Para ajustar el umbral global: `CONFIDENCE_THRESHOLD=0.40 uvicorn main:app ...`

---

## 5. Exportar GeoJSON

Pulsar **Exportar GeoJSON** en el panel de análisis (o tras ejecutar el análisis).

El fichero descargado (`cv-lit_camX_costa.geojson`) contiene:
```json
{
  "type": "FeatureCollection",
  "features": [{
    "type": "Feature",
    "properties": {
      "ID_Camara": 1,
      "Timestamp": "2026-06-01T12:00:00",
      "Confianza_IA": 0.87,
      "Area_Seca_m2": 24500.0,
      "EPSG": 25830
    },
    "geometry": { "type": "LineString", "coordinates": [[...]] }
  }]
}
```

Para validar en QGIS: arrastrar el fichero → verificar que se proyecta correctamente en EPSG:25830.

---

## 6. Alineación masiva de imágenes

La alineación SIFT corrige pequeños desplazamientos de cámara entre sesiones.

1. Ir a **Vista General** → seleccionar cámara → **Alineación masiva**.
2. Elegir la imagen de referencia (base).
3. Seleccionar las imágenes a alinear.
4. Pulsar **Iniciar alineación**.
   - La barra de progreso muestra el avance.
   - Cada imagen muestra: inliers, desplazamiento residual (px), estado (OK/fallido).
5. Revisar los resultados — desmarcar imágenes problemáticas.
6. Pulsar **Confirmar** para mover las imágenes alineadas al directorio de producción.

**Debug visual de la alineación:**
```bash
python scripts/debug_all_demo.py --cams 1 --max-imgs 10
# Resultados en /tmp/debug_demo/CAM_1/
```

---

## 7. Procesamiento automático a las 12:00h

El script `scripts/auto_process_noon.py` procesa automáticamente la imagen de mediodía de cada cámara.

**Ejecución manual:**
```bash
python scripts/auto_process_noon.py
python scripts/auto_process_noon.py --date 2026-06-01
```

**Configurar en crontab** (ejecuta cada día a las 12:00h):
```bash
crontab -e
# Añadir la línea:
0 12 * * * cd /home/nickhernd/Desktop/cv-lit && python scripts/auto_process_noon.py >> /tmp/cv_lit_noon.log 2>&1
```

Los resultados diarios se guardan en `proces_images/data/noon_summary_YYYY-MM-DD.json`.

---

## Solución de problemas

| Síntoma | Causa probable | Solución |
|---------|---------------|----------|
| `SAM no disponible` | Sin checkpoint o GPU | Colocar `sam_vit_h_4b8939.pth` en la raíz o usar `APP_MODE=demo` |
| Imagen rechazada `low_confidence` | Iluminación difícil | Ajustar `CONFIDENCE_THRESHOLD` o revisar máscara SIFT |
| RMSE > 1.5 m en calibración | Pocos GCPs o GCPs mal marcados | Añadir más GCPs bien distribuidos en la imagen |
| Backend no arranca | Dependencias faltantes | `pip install -r backend/requirements.txt` |
