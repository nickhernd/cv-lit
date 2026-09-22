<script setup>
import { ref, computed, watch } from 'vue'
import { API_BASE } from '../api.js'

const emit = defineEmits(['notify'])
const API = API_BASE

// ── Estado ───────────────────────────────────────────────────────────────────
const camId        = ref(1)
const imageList    = ref([])
const selectedFile = ref('')
const loading      = ref(false)
const result       = ref(null)   // respuesta de analyze-roi
const imgTs        = ref(Date.now())  // cache-buster para la imagen resultado

// ── Cargar lista de imágenes cuando cambia la cámara ─────────────────────────
async function fetchImages() {
  imageList.value = []
  selectedFile.value = ''
  try {
    const r = await fetch(`${API}/api/cameras/${camId.value}/images`)
    if (!r.ok) return
    const data = await r.json()
    imageList.value = data
    if (data.length > 0) selectedFile.value = data[0].filename
  } catch (e) {
    emit('notify', 'Error cargando imágenes: ' + e.message, 'error')
  }
}

watch(camId, fetchImages, { immediate: true })

// ── Flechas para pasar entre imágenes (#nuevo 2026-09-11) ────────────────────
// Sugerencia del usuario: tras analizar (una o todas), poder ir viendo la
// segmentación de cada imagen sin volver a abrir el desplegable cada vez.
const currentIndex = computed(() => imageList.value.findIndex(i => i.filename === selectedFile.value))
const hasPrev = computed(() => currentIndex.value > 0)
const hasNext = computed(() => currentIndex.value >= 0 && currentIndex.value < imageList.value.length - 1)

// Bug real detectado 2026-09-11 (aviso del propio usuario): la primera
// versión de esto volvía a analizar con SAM CADA VEZ que se pasaba de
// imagen con las flechas, aunque esa foto ya se hubiera analizado hace un
// segundo (p.ej. justo después de "Analizar todas") — SAM tarda varios
// segundos por foto, no tiene sentido repetirlo solo para volver a MIRAR
// algo ya calculado. Ahora, antes de analizar, se comprueba si ya hay un
// resultado ACEPTADO guardado para esa imagen concreta
// (GET .../cached-result, lee el histórico sin tocar SAM) — si lo hay, se
// muestra al instante; si no (nunca se analizó, o se rechazó), se analiza
// de verdad, igual que con el botón "Analizar imagen".
async function loadOrAnalyze(filename) {
  if (!filename) return
  loading.value = true
  try {
    const r = await fetch(`${API}/api/cameras/${camId.value}/images/${encodeURIComponent(filename)}/cached-result`)
    if (r.ok) {
      const cached = await r.json()
      if (cached.found) {
        result.value = cached
        imgTs.value = Date.now()
        loading.value = false
        return
      }
    }
  } catch (e) { /* si falla la comprobación, se cae al análisis real de abajo */ }
  await analyze()
}

async function goPrev() {
  if (!hasPrev.value) return
  selectedFile.value = imageList.value[currentIndex.value - 1].filename
  await loadOrAnalyze(selectedFile.value)
}
async function goNext() {
  if (!hasNext.value) return
  selectedFile.value = imageList.value[currentIndex.value + 1].filename
  await loadOrAnalyze(selectedFile.value)
}

// ── Análisis ─────────────────────────────────────────────────────────────────
async function analyze() {
  if (!selectedFile.value) {
    emit('notify', 'Selecciona una imagen primero', 'error')
    return
  }
  loading.value = true
  result.value  = null
  try {
    const r = await fetch(
      `${API}/api/cameras/${camId.value}/analyze-roi?filename=${encodeURIComponent(selectedFile.value)}`,
      { method: 'POST' }
    )
    if (!r.ok) throw new Error(`HTTP ${r.status}`)
    const data = await r.json()
    result.value = data
    imgTs.value  = Date.now()

    if (data.rejected) {
      emit('notify', `Imagen rechazada: ${data.reject_reason}`, 'error')
    } else {
      emit('notify', `Análisis completado — ${data.points_utm} puntos UTM`, 'success')
    }
  } catch (e) {
    emit('notify', 'Error en análisis: ' + e.message, 'error')
  } finally {
    loading.value = false
  }
}

// ── Analizar TODAS las imágenes de la cámara seleccionada (#nuevo 2026-09-11) ─
// Esta pantalla ("Resultados") es donde se ve la segmentación de una imagen
// suelta, pero hasta ahora solo dejaba analizar de una en una — para ver la
// evolución temporal del área seca hacía falta ir a otra pantalla (Carga de
// Imágenes) a buscar el botón de análisis en lote, cosa nada obvia si es
// aquí donde se mira el resultado. Mismo patrón que ImageIngest.vue
// (analyze-roi no admite lote, se procesa una a una en secuencia); al
// terminar deja seleccionada y mostrada la última imagen procesada.
const batchProcessing = ref(false)
const batchProgress = ref({ done: 0, total: 0 })

async function analyzeAllImages() {
  if (!imageList.value.length) {
    emit('notify', 'No hay imágenes en esta cámara', 'error')
    return
  }
  batchProcessing.value = true
  batchProgress.value = { done: 0, total: imageList.value.length }
  let ok = 0, failed = 0
  for (const img of imageList.value) {
    try {
      const r = await fetch(
        `${API}/api/cameras/${camId.value}/analyze-roi?filename=${encodeURIComponent(img.filename)}`,
        { method: 'POST' }
      )
      if (!r.ok) throw new Error(`HTTP ${r.status}`)
      const data = await r.json()
      if (!data.rejected) ok++; else failed++
      // Deja a la vista el resultado de la última imagen procesada (misma
      // lógica que analyze(), para que el panel central se actualice según avanza).
      selectedFile.value = img.filename
      result.value = data
      imgTs.value = Date.now()
    } catch (e) {
      failed++
    }
    batchProgress.value = { ...batchProgress.value, done: batchProgress.value.done + 1 }
  }
  batchProcessing.value = false
  emit('notify', `Lote terminado: ${ok} aceptada(s), ${failed} rechazada(s)/con error de ${imageList.value.length} imagen(es)`, failed && !ok ? 'error' : 'success')
}

// ── Exportar GeoJSON ─────────────────────────────────────────────────────────
async function exportGeoJSON() {
  try {
    const r = await fetch(`${API}/api/cameras/${camId.value}/geojson`)
    if (!r.ok) throw new Error(`HTTP ${r.status}`)
    const data = await r.json()
    if (!data.features || data.features.length === 0) {
      emit('notify', 'No hay resultados para exportar. Ejecuta el análisis primero.', 'error')
      return
    }
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
    const url  = URL.createObjectURL(blob)
    const a    = document.createElement('a')
    a.href     = url
    a.download = `cv-lit_cam${camId.value}_costa.geojson`
    a.click()
    URL.revokeObjectURL(url)
    emit('notify', 'GeoJSON exportado', 'success')
  } catch (e) {
    emit('notify', 'Error exportando GeoJSON: ' + e.message, 'error')
  }
}

// ── Helpers ──────────────────────────────────────────────────────────────────
const resultImageUrl = computed(() => {
  if (!result.value || result.value.rejected) return ''
  return `${API}/api/cameras/${camId.value}/analysis-result?file=${encodeURIComponent(selectedFile.value)}&t=${imgTs.value}`
})

const confidenceColor = computed(() => {
  if (!result.value || result.value.confidence == null) return 'bg-slate-300'
  const c = result.value.confidence
  if (c >= 0.7) return 'bg-emerald-500'
  if (c >= 0.5) return 'bg-amber-400'
  return 'bg-red-500'
})

const confidencePct = computed(() => {
  if (!result.value || result.value.confidence == null) return 0
  return Math.round(result.value.confidence * 100)
})

// ── Edición manual de la línea detectada (#nuevo 2026-09-14, pedido en la
// reunión: "permite editar manualmente las segmentaciones automáticas...
// conservar las correcciones como datos de entrenamiento"). Reutiliza el
// MISMO endpoint que la sección de Entrenamiento
// (/api/training/.../polyline) — una corrección hecha aquí y una polilínea
// marcada a mano en Entrenamiento acaban en el mismo sitio, un único
// conjunto de datos de entrenamiento en vez de dos separados. Empieza
// precargada con result.points_px (la línea que dio SAM, simplificada a
// puntos de control editables — ver approxPolyDP en analyze_roi/main.py),
// así que corregir es mover/borrar/añadir puntos sobre lo ya detectado, no
// dibujar desde cero. ─────────────────────────────────────────────────────
const editing = ref(false)
const editPoints = ref([])
const savingCorrection = ref(false)
const editImgEl = ref(null)
const editNaturalW = ref(0)
const editNaturalH = ref(0)
const draggingIdx = ref(null)

const editImageUrl = computed(() => {
  if (!selectedFile.value) return ''
  return `${API}/api/cameras/${camId.value}/image?file=${encodeURIComponent(selectedFile.value)}`
})
const editSvgPoints = computed(() => editPoints.value.map(p => p.join(',')).join(' '))

function startEditing() {
  if (!result.value) return
  editPoints.value = (result.value.points_px || []).map(p => [...p])
  editing.value = true
}
function cancelEditing() {
  editing.value = false
  editPoints.value = []
  draggingIdx.value = null
}
// Cambiar de imagen (flechas, selector, nuevo análisis) sale del modo edición
// — los puntos son de UNA imagen concreta, seguir editando tras cambiar de
// foto movería puntos de la línea de otra imagen sin que se note.
watch(selectedFile, cancelEditing)
function onEditImgLoad(e) {
  editNaturalW.value = e.target.naturalWidth
  editNaturalH.value = e.target.naturalHeight
}
function editEventToPixel(event) {
  const el = editImgEl.value
  if (!el) return null
  const rect = el.getBoundingClientRect()
  return {
    x: ((event.clientX - rect.left) / rect.width) * editNaturalW.value,
    y: ((event.clientY - rect.top) / rect.height) * editNaturalH.value,
  }
}
function onEditStageClick(event) {
  if (draggingIdx.value !== null) return  // el mouseup de un drag no debe añadir un punto nuevo
  const p = editEventToPixel(event)
  if (!p) return
  editPoints.value.push([Math.round(p.x), Math.round(p.y)])
}
function startDrag(idx) { draggingIdx.value = idx }
function onEditStageMouseMove(event) {
  if (draggingIdx.value === null) return
  const p = editEventToPixel(event)
  if (!p) return
  editPoints.value[draggingIdx.value] = [Math.round(p.x), Math.round(p.y)]
}
function endDrag() {
  // pequeño retardo: si no, el click sintético que sigue al mouseup (mismo
  // gesto) llega con draggingIdx ya a null y añade un punto de más justo
  // donde se soltó el arrastre.
  setTimeout(() => { draggingIdx.value = null }, 0)
}
function deletePoint(idx) {
  editPoints.value.splice(idx, 1)
}

async function saveCorrection() {
  if (editPoints.value.length < 2) {
    emit('notify', 'Marca al menos 2 puntos para guardar la corrección', 'error')
    return
  }
  savingCorrection.value = true
  try {
    const r = await fetch(
      `${API}/api/training/cameras/${camId.value}/images/${encodeURIComponent(selectedFile.value)}/polyline`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ points: editPoints.value }),
      }
    )
    if (!r.ok) throw new Error(`HTTP ${r.status}`)
    emit('notify', 'Corrección guardada como dato de entrenamiento', 'success')
    editing.value = false
  } catch (e) {
    emit('notify', 'Error guardando la corrección: ' + e.message, 'error')
  } finally {
    savingCorrection.value = false
  }
}

const CAMS = [1, 2, 3, 4, 5, 6]
</script>

<template>
  <div class="flex h-full gap-4">

    <!-- ── Panel izquierdo: controles ──────────────────────────────────────── -->
    <aside class="w-72 shrink-0 flex flex-col gap-4">

      <!-- Selector de cámara -->
      <div class="card-standard p-4">
        <h3 class="text-[10px] font-semibold text-slate-400 uppercase tracking-wider mb-3">Cámara</h3>
        <div class="grid grid-cols-3 gap-2">
          <button
            v-for="c in CAMS" :key="c"
            @click="camId = c"
            :class="camId === c ? 'chip active' : 'chip'"
            class="text-center">
            CAM {{ c }}
          </button>
        </div>
      </div>

      <!-- Selector de imagen -->
      <div class="card-standard p-4">
        <h3 class="text-[10px] font-semibold text-slate-400 uppercase tracking-wider mb-3">Imagen</h3>
        <select v-model="selectedFile" class="input-standard w-full">
          <option v-if="imageList.length === 0" value="">Sin imágenes</option>
          <option v-for="img in imageList" :key="img.filename" :value="img.filename">
            {{ img.filename }}
          </option>
        </select>
        <p class="text-[10px] text-slate-400 mt-2 font-mono">{{ imageList.length }} imágenes disponibles</p>
      </div>

      <!-- Botón analizar -->
      <button
        @click="analyze"
        :disabled="loading || !selectedFile"
        class="btn-standard w-full justify-center py-2.5 text-sm">
        <svg v-if="!loading" class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-width="2" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2"/>
        </svg>
        <svg v-else class="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
          <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"/>
          <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/>
        </svg>
        {{ loading ? 'Analizando…' : 'Analizar imagen' }}
      </button>

      <!-- Analizar TODAS las imágenes de esta cámara (#nuevo 2026-09-11):
           para ver la evolución temporal del área seca sin salir de esta
           pantalla ni ir imagen a imagen. -->
      <button
        @click="analyzeAllImages"
        :disabled="loading || batchProcessing || !imageList.length"
        title="Analiza de golpe TODAS las imágenes de esta cámara (aunque ya tuvieran un resultado antes) — para actualizar el histórico completo, por ejemplo tras una mejora del análisis."
        class="btn-secondary w-full justify-center py-2.5 text-sm disabled:opacity-40 disabled:cursor-not-allowed">
        <svg v-if="!batchProcessing" class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"/>
        </svg>
        <svg v-else class="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
          <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"/>
          <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/>
        </svg>
        {{ batchProcessing ? `Analizando ${batchProgress.done}/${batchProgress.total}…` : `Analizar todas (${imageList.length})` }}
      </button>

      <!-- Métricas (#86) -->
      <div v-if="result" class="card-standard overflow-hidden">
        <div class="card-header">Métricas</div>
        <div class="p-4 space-y-4">

        <!-- Alerta rechazo -->
        <div v-if="result.rejected" class="bg-red-50 border border-red-200 rounded-md p-3">
          <p class="text-xs font-semibold text-red-600 mb-1">Imagen rechazada</p>
          <p class="text-[10px] text-red-500 font-mono">{{ result.reject_reason }}</p>
        </div>

        <template v-else>
          <!-- Confianza con barra -->
          <div>
            <div class="flex justify-between text-xs mb-1">
              <span class="text-slate-500 font-medium">Confianza</span>
              <span class="font-mono font-semibold" :class="result.confidence >= 0.7 ? 'text-emerald-600' : result.confidence >= 0.5 ? 'text-amber-500' : 'text-red-500'">
                {{ confidencePct }}%
              </span>
            </div>
            <div class="w-full bg-slate-100 rounded-full h-1.5">
              <div :class="confidenceColor" class="h-1.5 rounded-full transition-all duration-500"
                   :style="`width:${confidencePct}%`"></div>
            </div>
          </div>

          <!-- Transectos: anchura de playa (#nuevo 2026-09-14) — indicador
               principal pedido en la reunión, sustituye al área en fiabilidad;
               el área se deja visible debajo por si sigue siendo útil como
               referencia, no se ha quitado nada. -->
          <div v-if="result.transects && result.transects.length" class="space-y-1.5">
            <span class="text-xs text-slate-500">Anchura de playa (transectos)</span>
            <div v-for="t in result.transects" :key="t.label" class="flex justify-between items-center pl-1">
              <span class="text-[11px] text-slate-600">{{ t.label }}</span>
              <span class="text-sm font-mono font-semibold text-emerald-700">{{ t.distance_m?.toLocaleString('es-ES') }} m</span>
            </div>
          </div>

          <!-- Área seca -->
          <div class="flex justify-between items-center">
            <span class="text-xs text-slate-500">Área seca</span>
            <span class="text-sm font-mono font-semibold text-slate-800">{{ result.dry_area_m2?.toLocaleString('es-ES') }} m²</span>
          </div>

          <!-- Puntos UTM -->
          <div class="flex justify-between items-center">
            <span class="text-xs text-slate-500">Puntos UTM</span>
            <span class="text-sm font-mono font-semibold text-slate-800">{{ result.points_utm }}</span>
          </div>

          <!-- Timestamp -->
          <div>
            <span class="text-xs text-slate-500">Timestamp</span>
            <p class="text-[10px] font-mono text-slate-600 mt-0.5 break-all">{{ result.timestamp }}</p>
          </div>
        </template>
        </div>
      </div>

      <!-- Botón GeoJSON (#87) -->
      <button @click="exportGeoJSON" class="btn-ghost-ok w-full justify-center">
        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"/>
        </svg>
        Exportar GeoJSON
      </button>

    </aside>

    <!-- ── Panel central: imagen con overlay de segmentación y línea de costa (#84, #85) ── -->
    <main class="flex-1 card-standard overflow-hidden flex flex-col">
      <div class="card-header flex items-center justify-between shrink-0 normal-case">
        <h2 class="text-[13px] font-semibold text-slate-700">
          Línea de costa — CAM {{ camId }}
          <span v-if="selectedFile" class="font-normal text-slate-400 ml-2 text-xs font-mono">{{ selectedFile }}</span>
        </h2>
        <div class="flex items-center gap-3">
          <!-- Flechas para pasar entre imágenes viendo su segmentación
               (#nuevo 2026-09-11) — reanalizan la imagen anterior/siguiente
               de la lista, no solo cambian de foto. -->
          <div v-if="imageList.length" class="flex items-center gap-1">
            <button @click="goPrev" :disabled="!hasPrev || loading || batchProcessing"
                    title="Imagen anterior" class="w-6 h-6 flex items-center justify-center rounded border border-slate-200 text-slate-500 hover:bg-slate-50 disabled:opacity-30 disabled:cursor-not-allowed">
              <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" d="M15 19l-7-7 7-7"/></svg>
            </button>
            <span class="text-[10px] font-mono text-slate-400 w-12 text-center">{{ currentIndex + 1 }} / {{ imageList.length }}</span>
            <button @click="goNext" :disabled="!hasNext || loading || batchProcessing"
                    title="Imagen siguiente" class="w-6 h-6 flex items-center justify-center rounded border border-slate-200 text-slate-500 hover:bg-slate-50 disabled:opacity-30 disabled:cursor-not-allowed">
              <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" d="M9 5l7 7-7 7"/></svg>
            </button>
          </div>
          <template v-if="result && !result.rejected && !editing">
            <button @click="startEditing" :disabled="!result.points_px || !result.points_px.length"
                    title="Corrige a mano la línea detectada — la corrección se guarda como dato de entrenamiento"
                    class="btn-secondary text-[10px] uppercase py-1 px-2 disabled:opacity-40 disabled:cursor-not-allowed">
              Editar línea manualmente
            </button>
            <span class="badge badge-ok">
              <span class="w-1.5 h-1.5 rounded-full bg-emerald-500"></span>
              Segmentación activa
            </span>
          </template>
          <template v-if="editing">
            <span class="text-[10px] text-amber-600 font-semibold uppercase">{{ editPoints.length }} puntos · clic: añadir · arrastrar: mover · doble clic: borrar</span>
            <button @click="cancelEditing" class="btn-secondary text-[10px] uppercase py-1 px-2">Cancelar</button>
            <button @click="saveCorrection" :disabled="savingCorrection || editPoints.length < 2" class="btn-standard text-[10px] uppercase py-1 px-2 disabled:opacity-40 disabled:cursor-not-allowed">
              {{ savingCorrection ? 'Guardando…' : 'Guardar corrección' }}
            </button>
          </template>
        </div>
      </div>

      <div class="flex-1 flex items-center justify-center bg-slate-50 p-4">
        <!-- Estado inicial -->
        <div v-if="!result && !loading" class="text-center text-slate-400">
          <svg class="w-16 h-16 mx-auto mb-4 opacity-30" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-width="1.5" d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z"/>
          </svg>
          <p class="text-sm font-medium">Selecciona una imagen y pulsa "Analizar"</p>
          <p class="text-xs mt-1">La línea de costa y segmentación se mostrarán aquí</p>
        </div>

        <!-- Spinner -->
        <div v-else-if="loading" class="text-center text-slate-500">
          <svg class="w-12 h-12 mx-auto mb-4 animate-spin text-blue-500" fill="none" viewBox="0 0 24 24">
            <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"/>
            <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/>
          </svg>
          <p class="text-sm font-medium">Ejecutando segmentación SAM…</p>
          <p class="text-xs text-slate-400 mt-1">Puede tardar unos segundos</p>
        </div>

        <!-- Rechazo -->
        <div v-else-if="result && result.rejected" class="text-center">
          <div class="w-16 h-16 rounded-full bg-red-100 flex items-center justify-center mx-auto mb-4">
            <svg class="w-8 h-8 text-red-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"/>
            </svg>
          </div>
          <p class="text-sm font-semibold text-red-600">Imagen rechazada</p>
          <p class="text-xs text-red-400 mt-1 font-mono">{{ result.reject_reason }}</p>
        </div>

        <!-- Edición manual de la línea (#nuevo 2026-09-14): imagen ORIGINAL
             (sin la línea ya "quemada" en el JPG, como en resultImageUrl) +
             overlay editable — clic para añadir, arrastrar para mover, doble
             clic para borrar un punto. -->
        <div v-else-if="editing" class="relative inline-block" style="cursor: crosshair;">
          <img ref="editImgEl" :src="editImageUrl" @load="onEditImgLoad" draggable="false"
               @click="onEditStageClick" @mousemove="onEditStageMouseMove" @mouseup="endDrag" @mouseleave="endDrag"
               class="max-w-full max-h-[70vh] object-contain rounded-md block select-none" alt="Imagen original para corregir la línea" />
          <svg v-if="editNaturalW" class="absolute top-0 left-0 w-full h-full" style="pointer-events:none"
               :viewBox="`0 0 ${editNaturalW} ${editNaturalH}`" preserveAspectRatio="none">
            <polyline :points="editSvgPoints" fill="none" stroke="#f43f5e" stroke-width="6" />
            <circle v-for="(p, i) in editPoints" :key="i"
                    @mousedown.stop="startDrag(i)" @dblclick.stop="deletePoint(i)"
                    :cx="p[0]" :cy="p[1]" :r="draggingIdx === i ? 15 : 10"
                    fill="#f43f5e" stroke="white" stroke-width="3"
                    style="pointer-events:auto; cursor:grab" />
          </svg>
        </div>

        <!-- Imagen resultado con segmentación + línea de costa superpuesta (#84, #85) -->
        <img v-else-if="resultImageUrl"
             :src="resultImageUrl"
             :key="imgTs"
             class="max-w-full max-h-full object-contain rounded-md"
             alt="Línea de costa detectada" />
      </div>

      <!-- Leyenda -->
      <div v-if="result && !result.rejected" class="px-5 py-3 border-t border-slate-100 flex items-center gap-4 text-xs text-slate-500 shrink-0">
        <div class="flex items-center gap-1.5">
          <div class="w-3 h-0.5 bg-red-500"></div>
          <span>Línea de costa</span>
        </div>
        <div class="flex items-center gap-1.5">
          <div class="w-3 h-3 rounded-sm bg-amber-300 opacity-70"></div>
          <span>Zona baja confianza</span>
        </div>
        <span class="ml-auto text-slate-400">EPSG:25830 · UTM zona 30N</span>
      </div>
    </main>

  </div>
</template>
