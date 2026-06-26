# Alineación Masiva — Módulo de Validación por Lotes

← [Volver al índice](README.md)

---

## Motivación

El flujo anterior validaba fotogramas de forma unitaria: una llamada API por imagen, sin visión global del lote.
Este módulo sustituye ese proceso por una validación masiva en una sola sesión de revisión.

**Flujo nuevo:**
1. El operador define una **imagen base de referencia** para la cámara.
2. El sistema alinea automáticamente todo el set (SIFT + FLANN + RANSAC).
3. Se presenta una **interfaz única de validación** con comparativa visual y mapa de diferencias.
4. El operador confirma el lote completo → las imágenes aprobadas se cargan al módulo de marcación.

---

## Arquitectura de estados

```
idle → configuring → processing → reviewing → committed
                  ↘              ↗
                    discarded (cualquier fase — no-op en disco)
```

**Principio de no-destructividad:** todo el trabajo intermedio vive en un directorio temporal
`/tmp/cv_lit_batch/{job_id}/`. Los originales de cada cámara nunca se modifican.
La escritura permanente al módulo de marcación ocurre **únicamente** en el commit explícito.

### Estructura del directorio temporal por job

```
/tmp/cv_lit_batch/{job_id}/
  aligned/    ← imágenes con warpPerspective aplicado (staging)
  diff/       ← mapas de delta de alineación por imagen
  blend/      ← blend 50/50 en escala de grises
```

---

## Backend: `backend/batch_alignment.py`

### Modelos de dominio

```python
@dataclass
class AlignmentResult:
    filename: str
    status: str            # "ok" | "failed" | "reference"
    inliers: int           # inliers RANSAC
    mean_shift_px: float   # mediana del flujo óptico residual (px)
    H: Optional[List]      # homografía 3×3 como lista plana de 9 valores
    approved: bool = True  # override de aprobación por imagen

@dataclass
class BatchJob:
    job_id: str
    cam_id: int
    base_filename: str
    image_filenames: List[str]
    status: str            # pending|processing|ready|committed|failed|discarded
    results: Dict[str, AlignmentResult]
    progress_current: int
    progress_total: int
```

El registro de jobs vive en memoria (`_jobs: Dict[str, BatchJob]`).
Cada `BatchJob` conoce su propio `temp_dir` y lo gestiona de forma autónoma.

### Endpoints del router `/api/batch/`

| Método | Ruta | Descripción |
|--------|------|-------------|
| `POST` | `/start` | Encola pipeline en background y retorna `job_id` inmediatamente |
| `GET` | `/{id}/status` | Polling de progreso durante la fase `processing` |
| `GET` | `/{id}/results` | Lista completa de métricas cuando `status=ready` |
| `GET` | `/{id}/preview/original/{fn}` | Imagen original sin transformar |
| `GET` | `/{id}/preview/aligned/{fn}` | Imagen alineada en staging |
| `GET` | `/{id}/preview/diff/{fn}` | Mapa de delta (ver sección siguiente) |
| `GET` | `/{id}/preview/blend/{fn}` | Blend 50/50 en escala de grises |
| `PATCH` | `/{id}/approve/{fn}?approved=bool` | Override de aprobación individual (no toca disco) |
| `POST` | `/{id}/commit` | Two-phase commit → copia aprobadas a `CAM_X/aligned/` |
| `DELETE` | `/{id}` | Descarta job y elimina `temp_dir` (no afecta originales) |

### Pipeline de alineación (`_run_pipeline`)

Tarea de fondo que procesa cada imagen secuencialmente:

1. Carga imagen base → extrae keypoints con `cv2.SIFT_create(nfeatures=3000)`
2. Por cada imagen del lote:
   - Detecta features → matching FLANN con ratio test de Lowe (0.75)
   - RANSAC (umbral 5px, mínimo 30 inliers) → homografía H
   - `cv2.warpPerspective` → imagen alineada → escribe en `aligned/`
   - `_compute_diff_map` → escribe en `diff/`
   - `_blend_grayscale` → escribe en `blend/`
   - `_compute_mean_shift` → métrica escalar `mean_shift_px`
3. Actualiza `job.progress_current` en cada iteración (polling frontend cada 800ms)
4. `job.status = "ready"` al finalizar

---

## Lógica de renderizado del delta

La función `_compute_diff_map(ref, aligned)` genera una imagen compuesta de tres capas:

### Capa 1 — Heatmap de diferencia absoluta

```python
diff_abs = np.abs(ref_f - aligned_f).mean(axis=2)   # promedio por canal (H,W)
diff_norm = cv2.normalize(diff_abs, None, 0, 255, cv2.NORM_MINMAX)
heatmap = cv2.applyColorMap(diff_norm, cv2.COLORMAP_HOT)
```

| Color | Significado |
|-------|-------------|
| Negro | Diferencia 0 — alineación perfecta |
| Rojo/naranja | Error de intensidad moderado |
| Amarillo/blanco | Error severo — región mal alineada |

### Capa 2 — Divergencia de bordes (overlay cian)

```python
edges_ref = cv2.Canny(ref_gray, 40, 120)
edges_ali = cv2.Canny(aligned_gray, 40, 120)
edge_diff = cv2.dilate(cv2.absdiff(edges_ref, edges_ali), kernel_5x5)
composite[edge_diff > 0] = (255, 255, 0)  # cian en BGR
```

Los bordes que no coinciden entre ref y alineada aparecen en **cian**:
identifican exactamente qué objeto se desplazó y en qué dirección.

### Capa 3 — Métrica escalar `mean_shift_px`

```python
flow = cv2.calcOpticalFlowFarneback(ref_gray, aligned_gray, ...)
mag, _ = cv2.cartToPolar(flow[..., 0], flow[..., 1])
mean_shift_px = float(np.median(mag))
```

Mediana de la magnitud del campo de flujo óptico residual post-warp.
Mide cuántos píxeles de desplazamiento sistemático quedan tras la homografía.
Umbral de alerta en la UI: **> 3 px**.

---

## Frontend: `BatchAlignment.vue`

Componente Vue 3 con máquina de estados interna (sin Pinia — sólo `ref` + `reactive`).

### Fases y transiciones

```
idle
  └─ startConfiguring() ──────────────────────→ configuring
                                                    └─ startBatch() ──→ processing
                                                                           └─ poll ready ──→ reviewing
                                                                                               └─ commitBatch() ──→ committed
       ←─── discardJob() ───────────────────────────────────────────────────────────────────────┘
```

### Variables de estado clave

```javascript
const phase     = ref('idle')     // fase actual de la máquina de estados
const jobId     = ref(null)       // ID del job backend activo
const results   = ref([])         // lista de AlignmentResult del lote
const selected  = ref(null)       // filename seleccionado en el filmstrip
const viewMode  = ref('diff')     // modo del visor: 'diff' | 'blend' | 'aligned'
```

### Layout de la fase `reviewing`

```
┌──────────────────────┬──────────────────────────────────────────────────┐
│ RESUMEN              │ [Mapa delta]  [Blend 50/50]  [Alineada]          │
│  Aprobadas: 44       ├──────────────────────────┬───────────────────────┤
│  Omitidas:   3       │                          │                       │
│  Fallidas:   0       │     ORIGINAL             │   DELTA / BLEND / ALI │
├──────────────────────│     <img>                │   <img>               │
│ FILMSTRIP            │                          │                       │
│ ● img_001  OK        │                          │                       │
│ ▶ img_002  ~2.1px    ├──────────────────────────┴───────────────────────┤
│ ● img_003  FAIL      │  Leyenda: ■negro=OK  ■rojo=error  ■cian=bordes  │
│ ● img_004  SKIP      │                                                   │
│   ...                │  inliers: 152   delta: 1.4 px   [✓ Aprobada]    │
├──────────────────────┴──────────────────────────────────────────────────┤
│  [Confirmar lote (44)]          [Descartar sin guardar]                 │
└─────────────────────────────────────────────────────────────────────────┘
```

### Props / Emits

```javascript
// Props
camId:     Number   // ID de cámara (1-6)
imageList: Array    // [{filename, size, modified}, ...]

// Emits
'notify'(message, type)   // toast del sistema
'committed'({ jobId, committed })  // lote confirmado con éxito
'discard'()               // usuario descartó el job
```

### Indicadores de estado en el filmstrip

| Color | Estado |
|-------|--------|
| Azul | Imagen de referencia base |
| Verde | Alineada correctamente (`mean_shift_px ≤ 3`) |
| Amarillo | Alineada con drift notable (`mean_shift_px > 3`) |
| Ámbar | Aprobación retirada manualmente (`approved = false`) |
| Rojo | Alineación fallida (RANSAC insuficiente) |

---

## Commit: two-phase write

```
reviewing ──[commitBatch()]──→
  POST /api/batch/{id}/commit
    ├─ Por cada result donde approved=true:
    │    shutil.copy2(temp/aligned/{fn}, data/CAM_X/aligned/{fn})
    └─ job.status = "committed"
```

Las imágenes con `approved=false` o `status="failed"` **no se copian**.
El directorio destino `data/CAM_X/aligned/` es el punto de entrada al módulo de marcación.

---

## Integración en el sistema

La vista se registra en `App.vue` como `currentView = 'batch'` y se accede desde el sidebar "Alineación Masiva".
Al navegar desde Dashboard a una cámara específica, `goToBatch(camId)` precarga la lista de imágenes.

Ruta en el módulo de marcación que consume los resultados:

```
data/
  CAM_1/
    images/     ← originales (nunca modificados)
    aligned/    ← salida del commit del batch (entrada al módulo de marcación)
```

---

## Parámetros de alineación (configurables en `batch_alignment.py`)

| Parámetro | Valor actual | Descripción |
|-----------|-------------|-------------|
| `SIFT_FEATURES` | 3000 | Keypoints máximos por imagen |
| `LOWE_RATIO` | 0.75 | Ratio test de Lowe para filtrar matches |
| `MIN_INLIERS` | 15 | Inliers mínimos con máscara activa |
| `MIN_INLIERS_FULL` | 30 | Inliers mínimos sin máscara (fallback) |
| `RANSAC_THRESH` | 5.0 px | Umbral de reproyección RANSAC |

---

## Máscaras de zonas estables por cámara

### Qué son y por qué existen

SIFT sin restricciones detecta features en cualquier región de la imagen, incluyendo:
- Gaviotas y pájaros en vuelo (zona de cielo/horizonte)
- Olas y espuma de mar (bordes dinámicos)
- Personas y bañistas en la playa

Estos puntos son **inestables entre tomas**: producen matches erróneos que corrompen la homografía.
Las máscaras restringen SIFT a **zonas fijas** (estructuras estáticas como el horizonte del mar,
edificios, rocas, dunas) donde los features son fiables entre diferentes fechas.

### Fichero de configuración

**Ubicación:** `calibration/alignment_masks.json`

El fichero JSON define las zonas estables de cada cámara usando **coordenadas fraccionarias** (0.0–1.0)
independientes de la resolución real de la imagen:

```
x=0.0 → borde izquierdo de la imagen
x=1.0 → borde derecho de la imagen
y=0.0 → borde superior de la imagen
y=1.0 → borde inferior de la imagen
```

### Estructura del fichero

```json
{
  "_comment": "Ajustar con imágenes reales de cada cámara. Coordenadas en fracción (0.0-1.0).",
  "CAM_1": {
    "regions": [
      {"label": "horizonte_mar",   "x0": 0.00, "y0": 0.31, "x1": 1.00, "y1": 0.40},
      {"label": "arena_baja",      "x0": 0.00, "y0": 0.73, "x1": 0.60, "y1": 0.88},
      {"label": "vegetacion_dcha", "x0": 0.60, "y0": 0.73, "x1": 1.00, "y1": 0.92}
    ]
  },
  "CAM_2": { ... }
}
```

Cada región tiene:
- `label` — nombre descriptivo (sólo para legibilidad, no afecta al procesamiento)
- `x0`, `y0` — esquina superior izquierda de la zona (fracciones 0.0–1.0)
- `x1`, `y1` — esquina inferior derecha de la zona (fracciones 0.0–1.0)

### Zonas configuradas por cámara

| Cámara | Zona 1 | Zona 2 | Zona 3 | Notas |
|--------|--------|--------|--------|-------|
| CAM_1 | Horizonte mar (y=0.31–0.40) | Arena baja izq (y=0.73–0.88) | Vegetación/duna dcha | Excluye el cielo donde se concentran gaviotas |
| CAM_2 | Horizonte (y=0.26–0.40) | El Peñón (x=0.58–0.88) | — | El Peñón de Ifach es referencia fija excelente |
| CAM_3 | Horizonte (y=0.34–0.48) | Edificio derecho (x=0.72–1.00) | — | Edificio como anclaje vertical |
| CAM_4 | Horizonte (y=0.30–0.44) | Edificio izquierdo (x=0.00–0.28) | — | Edificio como anclaje vertical |
| CAM_5 | Horizonte (y=0.28–0.42) | Zona izquierda (x=0.00–0.32) | — | |
| CAM_6 | Horizonte (y=0.32–0.46) | Edificios izquierda (x=0.00–0.35) | — | |

### Estrategia de dos pasadas (fallback automático)

El pipeline intenta la alineación en dos pasos:

1. **Pasada con máscara** (`MIN_INLIERS=15`): extrae features sólo en las zonas estables.
   Si obtiene ≥15 inliers → acepta la alineación.
2. **Fallback sin máscara** (`MIN_INLIERS_FULL=30`): si la pasada 1 falla, reintenta usando
   toda la imagen con un umbral más alto. El campo `used_mask` del resultado indica qué pasada tuvo éxito.

Esto garantiza que una máscara demasiado restrictiva no bloquee lotes enteros.

### Cómo verificar las zonas visualmente

Ejecutar el script de visualización (requiere OpenCV y una imagen de referencia):

```python
# visualize_mask.py
import cv2, json, numpy as np
from pathlib import Path

IMG = "proces_images/data/camera1/1779787800_20260526_093000_PTM61471.jpg"
MASKS = "calibration/alignment_masks.json"
CAM = "CAM_1"

img = cv2.imread(IMG)
h, w = img.shape[:2]
overlay = img.copy()

with open(MASKS) as f:
    cfg = json.load(f)

for r in cfg[CAM]["regions"]:
    x0, y0 = int(r["x0"]*w), int(r["y0"]*h)
    x1, y1 = int(r["x1"]*w), int(r["y1"]*h)
    cv2.rectangle(overlay, (x0,y0), (x1,y1), (0,255,0), -1)
    cv2.putText(overlay, r["label"], (x0+10, y0+30),
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0,0,0), 2)

result = cv2.addWeighted(img, 0.5, overlay, 0.5, 0)
cv2.imwrite("/tmp/mask_check.jpg", result)
print(f"Imagen guardada en /tmp/mask_check.jpg")
print(f"Resolución: {w}x{h}")
for r in cfg[CAM]["regions"]:
    print(f"  {r['label']}: ({int(r['x0']*w)},{int(r['y0']*h)}) → ({int(r['x1']*w)},{int(r['y1']*h)})")
```

Ejecutar desde la raíz del proyecto: `python visualize_mask.py`

### Cómo ajustar una máscara

1. Abrir una imagen real de la cámara en un visor de imágenes que muestre coordenadas de píxel.
2. Identificar las regiones estables (sin gaviotas, olas, personas).
3. Anotar las coordenadas en píxeles de las esquinas.
4. Convertir a fracciones: `x_frac = pixel_x / ancho_imagen`, `y_frac = pixel_y / alto_imagen`.
5. Editar `calibration/alignment_masks.json` con los nuevos valores.
6. Ejecutar `visualize_mask.py` para confirmar que las zonas verdes cubren lo esperado.
7. Volver a lanzar el lote de alineación desde la UI.

**Ejemplo — CAM_1 (4608×2682 píxeles):**

| Zona | Pixels | Fracciones |
|------|--------|------------|
| Horizonte mar | (0,831)→(4608,1072) | y0=0.31, y1=0.40 |
| Arena baja izq | (0,1957)→(2764,2360) | y0=0.73, x1=0.60, y1=0.88 |
| Vegetación dcha | (2764,1957)→(4608,2467) | x0=0.60, y0=0.73, y1=0.92 |

### Por qué CAM_1 excluye el cielo

En Guardamar del Segura, la CAM_1 apunta hacia el norte sobre la playa. En las imágenes de la mañana,
es frecuente encontrar 5–10 gaviotas sobrevolando en la banda y=0.14–0.30 (cielo bajo).
La máscara anterior comenzaba en y=0.24, capturando esa zona. Las gaviotas producen features
brillantes y muy contrastados que SIFT detecta con alta confianza, pero que se mueven entre tomas.
Resultado: matches entre gaviotas en posiciones distintas → homografía sesgada → imágenes "giradas".

La zona `horizonte_mar` (y=0.31–0.40) está justo en la franja de mar cerca del horizonte:
agua con ligeras olas que produce features reproducibles de la línea de costa/horizon.

---

## Archivos del módulo

| Archivo | Descripción |
|---------|-------------|
| `backend/batch_alignment.py` | Pipeline de alineación, endpoints FastAPI, lógica de delta |
| `backend/main.py` | Registra el router: `app.include_router(batch_router)` |
| `frontend/src/components/BatchAlignment.vue` | UI completa — máquina de estados, filmstrip, visor |
| `frontend/src/components/Calibration.vue` | Paso 3 del flujo de calibración — monta BatchAlignment |
| `calibration/alignment_masks.json` | Zonas estables SIFT por cámara (ajustable sin recompilar) |
| `homography/align_images.py` | CLI standalone de alineación — acepta `--cam N` para aplicar máscaras |
