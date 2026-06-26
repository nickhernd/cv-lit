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
| `MIN_INLIERS` | 30 | Inliers mínimos RANSAC para aceptar alineación |
| `RANSAC_THRESH` | 5.0 px | Umbral de reproyección RANSAC |
