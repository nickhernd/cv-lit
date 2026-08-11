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

La calibración establece la homografía píxel → UTM (EPSG:25830) para cada cámara. Es un
asistente de 7 pasos: **Vista general → Imágenes → Alineación → Catálogo → Marcación →
Cálculo → Validación**.

1. Ir a **Calibración** en el menú lateral y seleccionar la cámara (1–6).
2. **Imágenes**: elegir o subir el fotograma a calibrar, y marcarlo como imagen de referencia.
3. **Marcación**: marcar los GCPs (Ground Control Points, "varillas") en la imagen — clic sobre
   el punto visible (apóyate en la lupa para el píxel exacto) y asigna sus coordenadas UTM
   (X, Y). Cada varilla queda "confirmada" (marcador verde) o "pendiente" (ámbar, si viene
   importada de un CSV con posición aproximada) — hace falta un mínimo de 4 confirmadas,
   recomendado 8+.
4. **Cálculo**: pulsar **Calcular homografía**. El sistema ajusta H con RANSAC a partir de las
   varillas confirmadas y muestra una tabla de error de reproyección por varilla — se puede
   excluir una varilla puntual y recalcular si su error está muy por encima del resto. Si las
   varillas marcadas quedan casi todas alineadas en una sola línea, el sistema avisa de que la
   geometría es inestable (RANSAC no encuentra un ajuste fiable) — en ese caso conviene añadir
   varillas repartidas en más de una zona/profundidad de la imagen.
5. **Validación**: resumen final — RMSE de reproyección (px) y RMSE en terreno (m). Objetivo:
   RMSE terreno < 2 m (el umbral por varilla en píxeles de la tabla de Cálculo es solo una ayuda
   para localizar una varilla mal marcada, no el criterio de aceptación).
6. El perfil se guarda automáticamente en `calibration/cam_X_profile.json` (y la matriz de
   homografía en `calibration/cam_X_H.npy`).

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

## 7. Modo automático

Automatiza de punta a punta lo que las secciones 4 y 6 hacen a mano, para un rango de fechas:
descarga las imágenes nuevas de la API de Obscape, alinea el lote contra la más antigua, y
analiza cada imagen resultante (segmentación + línea de costa + GeoJSON).

1. Ir a **Modo automático** en el menú lateral.
2. Elegir una cámara **ya calibrada** (las no calibradas aparecen deshabilitadas en el
   desplegable — la calibración inicial sigue siendo manual, ver sección 3).
3. Elegir el rango de fechas (desde / hasta).
4. Pulsar **Iniciar procesamiento automático** y esperar — la pantalla muestra el progreso por
   fase (Descarga → Alineación → Análisis) y, al terminar, una tabla con el resultado de cada
   imagen (confianza, área seca, si fue rechazada y por qué).
5. Exportar el GeoJSON combinado de la cámara desde el botón de la tabla de resultados.

Requiere `OBSCAPE_USERNAME`/`OBSCAPE_API_KEY` configurados (variables de entorno o `.env` en la
raíz del repo, ver `.env.example`).

---

## 8. Procesamiento automático a las 12:00h

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
| RMSE > 2 m en calibración | Pocos GCPs, GCPs mal marcados, o varillas casi alineadas en una sola línea (ver aviso de geometría inestable en el paso Cálculo) | Añadir más GCPs bien distribuidos en más de una zona/profundidad de la imagen |
| Backend no arranca | Dependencias faltantes | `pip install -r backend/requirements.txt` |
