<script setup>
import { ref, computed, watch, onBeforeUnmount } from 'vue'
import { API_BASE } from '../api.js'

const emit = defineEmits(['notify'])
const API = API_BASE

// ── Sección TEMPORAL de entrenamiento (#nuevo 2026-09-13) ────────────────────
// Pedida en la reunión de equipo del 11/09/2026: antes de poder cambiar el
// objetivo de segmentación de "toda la arena seca" a la "línea húmeda" real,
// el equipo de campo necesita marcar a mano, sobre ~20 imágenes por cámara,
// dónde debería estar esa línea. Esto NO usa SAM ni calcula nada — solo deja
// clicar puntos sobre la foto real y guarda la polilínea resultante por
// imagen, para exportarla después en JSON.

const camId       = ref(1)
const imageList   = ref([])
const selectedFile = ref('')
const points      = ref([])       // [[x_px, y_px], ...] en coordenadas de la imagen ORIGINAL
const saving      = ref(false)

const CAMS = [1, 2, 3, 4, 5, 6]

// Revisar/descartar antes de anotar (#nuevo 2026-09-14, pedido en la
// reunión): las imágenes descartadas ("excluded") no desaparecen de disco —
// solo se sacan de la cola de anotación por defecto, igual que descartar una
// varilla de calibración no borra el punto. showExcluded las vuelve a
// mostrar (para poder reincluirlas si fue un error).
const showExcluded = ref(false)
const visibleImages = computed(() => showExcluded.value ? imageList.value : imageList.value.filter(i => !i.excluded))
const excludedCount = computed(() => imageList.value.filter(i => i.excluded).length)

async function fetchImages() {
  imageList.value = []
  selectedFile.value = ''
  points.value = []
  try {
    const r = await fetch(`${API}/api/training/cameras/${camId.value}/images`)
    if (!r.ok) return
    const data = await r.json()
    imageList.value = data
    const firstVisible = data.find(i => !i.excluded) || data[0]
    if (firstVisible) await selectImage(firstVisible.filename)
  } catch (e) {
    emit('notify', 'Error cargando imágenes: ' + e.message, 'error')
  }
}

watch(camId, fetchImages, { immediate: true })

const currentIndex = computed(() => visibleImages.value.findIndex(i => i.filename === selectedFile.value))
const hasPrev = computed(() => currentIndex.value > 0)
const hasNext = computed(() => currentIndex.value >= 0 && currentIndex.value < visibleImages.value.length - 1)

const imageUrl = computed(() => {
  if (!selectedFile.value) return ''
  return `${API}/api/training/cameras/${camId.value}/image?file=${encodeURIComponent(selectedFile.value)}`
})

const selectedImageMeta = computed(() => imageList.value.find(i => i.filename === selectedFile.value))
const isAdditionalImage = computed(() => selectedImageMeta.value?.source === 'additional')

async function selectImage(filename) {
  selectedFile.value = filename
  points.value = []
  selectedIdx.value = null
  loupeVisible.value = false
  try {
    const r = await fetch(`${API}/api/training/cameras/${camId.value}/images/${encodeURIComponent(filename)}/polyline`)
    if (r.ok) {
      const data = await r.json()
      if (data.found) points.value = data.points
    }
  } catch (e) { /* imagen sin anotación todavía: se queda vacío */ }
}

// ── Lienzo (mismo patrón que Calibration.vue paso 5 "Marcación de varillas"):
// markStageRef es un div EXACTAMENTE del tamaño de la imagen renderizada (sin
// bandas de letterbox) — es la única referencia usada tanto para convertir un
// click en píxel real como para dibujar cada punto, así que ambos cálculos
// comparten siempre el mismo rectángulo. stagePanelRef es el visor que lo
// contiene, con scroll propio para el modo "doble zoom". ─────────────────────
const stagePanelRef = ref(null)
const markStageRef  = ref(null)
const markImgRef    = ref(null)
const imgNatural    = ref({ width: 0, height: 0 })
const panelSize     = ref({ width: 0, height: 0 })
const imageZoomMode = ref('fit')   // 'fit' = ajustada al visor; 'x2' = el doble, con scroll
let stageResizeObserver = null

const stageDisplaySize = computed(() => {
  const { width: natW, height: natH } = imgNatural.value
  const { width: boxW, height: boxH } = panelSize.value
  if (!natW || !natH || !boxW || !boxH) return { width: 0, height: 0 }
  const fitScale = Math.min(boxW / natW, boxH / natH)
  const scale = imageZoomMode.value === 'x2' ? fitScale * 2 : fitScale
  return { width: natW * scale, height: natH * scale }
})

function updatePanelSize() {
  if (!stagePanelRef.value) return
  panelSize.value = { width: stagePanelRef.value.clientWidth, height: stagePanelRef.value.clientHeight }
}

watch(stagePanelRef, (el) => {
  if (stageResizeObserver) { stageResizeObserver.disconnect(); stageResizeObserver = null }
  if (el) {
    updatePanelSize()
    stageResizeObserver = new ResizeObserver(updatePanelSize)
    stageResizeObserver.observe(el)
  }
})

function onMarkImageLoad(e) {
  imgNatural.value = { width: e.target.naturalWidth, height: e.target.naturalHeight }
}

// Convierte un evento de ratón sobre la foto en coordenadas de píxel nativas
// de la imagen — SIEMPRE contra markStageRef (nunca event.currentTarget), la
// misma referencia que usa el dibujado de los puntos, para que click y lupa
// midan exactamente contra la misma caja.
function eventToImagePixel(event) {
  const el = markStageRef.value
  if (!el) return null
  const box = el.getBoundingClientRect()
  if (!box.width || !box.height) return null
  const x = event.clientX - box.left
  const y = event.clientY - box.top
  if (x < 0 || y < 0 || x > box.width || y > box.height) return null
  return {
    pixelX: (x / box.width) * imgNatural.value.width,
    pixelY: (y / box.height) * imgNatural.value.height,
  }
}

// ── Lupa de precisión: recorte ampliado alrededor del cursor, igual que en
// Calibración/varillas — imprescindible para acertar el píxel exacto en
// fotos de varios miles de píxeles de ancho. ─────────────────────────────────
const zoomFactor = ref(6)
const LOUPE_SIZE = 220
const loupeCanvasRef = ref(null)
const loupeVisible = ref(false)
const loupeScreenPos = ref({ left: 0, top: 0 })
let loupeNaturalPos = { x: 0, y: 0 }

function drawLoupe() {
  const canvas = loupeCanvasRef.value
  const img = markImgRef.value
  if (!canvas || !img || !imgNatural.value.width) return
  const ctx = canvas.getContext('2d')
  const cropSize = LOUPE_SIZE / zoomFactor.value
  const sx = Math.min(Math.max(loupeNaturalPos.x - cropSize / 2, 0), Math.max(imgNatural.value.width - cropSize, 0))
  const sy = Math.min(Math.max(loupeNaturalPos.y - cropSize / 2, 0), Math.max(imgNatural.value.height - cropSize, 0))
  ctx.clearRect(0, 0, LOUPE_SIZE, LOUPE_SIZE)
  ctx.imageSmoothingEnabled = false
  ctx.drawImage(img, sx, sy, cropSize, cropSize, 0, 0, LOUPE_SIZE, LOUPE_SIZE)

  // Cruz roja = cursor ahora mismo (siempre centrada, el recorte está
  // centrado en ella).
  ctx.strokeStyle = 'rgba(239, 68, 68, 0.9)'
  ctx.lineWidth = 1
  ctx.beginPath()
  ctx.moveTo(LOUPE_SIZE / 2, 0); ctx.lineTo(LOUPE_SIZE / 2, LOUPE_SIZE)
  ctx.moveTo(0, LOUPE_SIZE / 2); ctx.lineTo(LOUPE_SIZE, LOUPE_SIZE / 2)
  ctx.stroke()

  // Cruz verde = posición exacta del punto SELECCIONADO (si cae dentro de lo
  // que se ve ahora en la lupa) — deja comparar cursor vs. punto ya fijado.
  const p = selectedIdx.value !== null ? points.value[selectedIdx.value] : null
  if (p) {
    const gx = (p[0] - sx) * zoomFactor.value
    const gy = (p[1] - sy) * zoomFactor.value
    if (gx >= 0 && gx <= LOUPE_SIZE && gy >= 0 && gy <= LOUPE_SIZE) {
      const armLen = 9
      ctx.strokeStyle = 'rgba(16, 185, 129, 0.95)'
      ctx.lineWidth = 2
      ctx.beginPath()
      ctx.moveTo(gx - armLen, gy); ctx.lineTo(gx + armLen, gy)
      ctx.moveTo(gx, gy - armLen); ctx.lineTo(gx, gy + armLen)
      ctx.stroke()
    }
  }
}

function onStageMouseMove(event) {
  const p = eventToImagePixel(event)
  if (!p) { loupeVisible.value = false; return }
  loupeNaturalPos = { x: p.pixelX, y: p.pixelY }
  loupeVisible.value = true
  // Posicionar la lupa cerca del cursor pero dentro del VISOR (stagePanelRef),
  // no del lienzo interior — en modo doble zoom el lienzo puede ser mucho más
  // grande que el visor y estar desplazado por el scroll.
  const panelBox = stagePanelRef.value.getBoundingClientRect()
  let left = event.clientX - panelBox.left + 24
  let top = event.clientY - panelBox.top - LOUPE_SIZE - 24
  if (left + LOUPE_SIZE > panelBox.width) left = event.clientX - panelBox.left - LOUPE_SIZE - 24
  if (top < 0) top = event.clientY - panelBox.top + 24
  loupeScreenPos.value = { left, top }
  requestAnimationFrame(drawLoupe)
}
function onStageMouseLeave() { loupeVisible.value = false }

// ── Puntos: clicar el lienzo añade uno nuevo AL FINAL y lo selecciona;
// clicar un punto YA puesto lo selecciona/deselecciona (para las flechas),
// sin moverlo — a diferencia de las varillas, aquí no hace falta "reposicionar
// con el siguiente click" porque cada punto tiene su propio círculo clicable. ─
const selectedIdx = ref(null)

function onStageClick(event) {
  const p = eventToImagePixel(event)
  if (!p) return
  points.value.push([Math.round(p.pixelX), Math.round(p.pixelY)])
  selectedIdx.value = points.value.length - 1
}

function selectPoint(idx) {
  selectedIdx.value = selectedIdx.value === idx ? null : idx
}

function undoLast() {
  points.value.pop()
  selectedIdx.value = null
}

function clearPoints() {
  points.value = []
  selectedIdx.value = null
}

// ── Flechas del teclado: ajuste fino del punto seleccionado, 1px (10px con
// Shift) — acertar el píxel exacto con el ratón es difícil en fotos de miles
// de píxeles. A diferencia de Calibración (que autoguarda en cada ajuste),
// aquí NO se autoguarda: esta pantalla ya tiene un botón "Guardar polilínea"
// explícito y cambiar ese comportamiento sin que lo pidan sería sorprendente. ─
const NUDGE_STEP = 1
const NUDGE_STEP_FAST = 10
const NUDGE_KEYS = { ArrowUp: [0, -1], ArrowDown: [0, 1], ArrowLeft: [-1, 0], ArrowRight: [1, 0] }

function nudgeSelectedPoint(dx, dy) {
  if (selectedIdx.value === null || !imgNatural.value.width) return
  const p = points.value[selectedIdx.value]
  if (!p) return
  const maxX = imgNatural.value.width, maxY = imgNatural.value.height
  p[0] = Math.min(Math.max(p[0] + dx, 0), maxX)
  p[1] = Math.min(Math.max(p[1] + dy, 0), maxY)
  loupeNaturalPos = { x: p[0], y: p[1] }
  loupeVisible.value = true
  requestAnimationFrame(drawLoupe)
}

function handleKeydown(event) {
  if (selectedIdx.value === null) return
  const tag = document.activeElement?.tagName
  if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return
  const dir = NUDGE_KEYS[event.key]
  if (!dir) return
  event.preventDefault()
  const step = event.shiftKey ? NUDGE_STEP_FAST : NUDGE_STEP
  nudgeSelectedPoint(dir[0] * step, dir[1] * step)
}

window.addEventListener('keydown', handleKeydown)
onBeforeUnmount(() => {
  window.removeEventListener('keydown', handleKeydown)
  if (stageResizeObserver) stageResizeObserver.disconnect()
})

async function goPrev() {
  if (!hasPrev.value) return
  await selectImage(visibleImages.value[currentIndex.value - 1].filename)
}
async function goNext() {
  if (!hasNext.value) return
  await selectImage(visibleImages.value[currentIndex.value + 1].filename)
}

async function savePolyline() {
  if (points.value.length < 2) {
    emit('notify', 'Marca al menos 2 puntos para formar una polilínea', 'error')
    return
  }
  saving.value = true
  try {
    const r = await fetch(
      `${API}/api/training/cameras/${camId.value}/images/${encodeURIComponent(selectedFile.value)}/polyline`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ points: points.value }),
      }
    )
    if (!r.ok) throw new Error(`HTTP ${r.status}`)
    const img = imageList.value.find(i => i.filename === selectedFile.value)
    if (img) img.annotated = true
    emit('notify', 'Polilínea guardada', 'success')
  } catch (e) {
    emit('notify', 'Error guardando polilínea: ' + e.message, 'error')
  } finally {
    saving.value = false
  }
}

async function discardPolyline() {
  try {
    const r = await fetch(
      `${API}/api/training/cameras/${camId.value}/images/${encodeURIComponent(selectedFile.value)}/polyline`,
      { method: 'DELETE' }
    )
    if (!r.ok) throw new Error(`HTTP ${r.status}`)
    points.value = []
    selectedIdx.value = null
    const img = imageList.value.find(i => i.filename === selectedFile.value)
    if (img) img.annotated = false
    emit('notify', 'Anotación descartada', 'info')
  } catch (e) {
    emit('notify', 'Error descartando anotación: ' + e.message, 'error')
  }
}

// Subir imágenes ADICIONALES (#nuevo 2026-09-14): pedido explícito del
// usuario — no hace falta que las fotos a marcar vengan de la carga normal
// de la cámara, se puede traer cualquier imagen suelta solo para entrenar.
const fileInputRef = ref(null)
const uploading = ref(false)

function triggerUpload() {
  fileInputRef.value?.click()
}

async function onFilesChosen(event) {
  const files = Array.from(event.target.files || [])
  event.target.value = ''  // permite volver a elegir el mismo fichero más tarde
  if (!files.length) return
  uploading.value = true
  try {
    const form = new FormData()
    files.forEach(f => form.append('files', f))
    const r = await fetch(`${API}/api/training/cameras/${camId.value}/upload-images`, {
      method: 'POST',
      body: form,
    })
    if (!r.ok) throw new Error(`HTTP ${r.status}`)
    const data = await r.json()
    emit('notify', `${data.saved.length} imagen(es) adicional(es) subida(s)`, 'success')
    const previouslySelected = selectedFile.value
    await fetchImages()
    if (data.saved.length && imageList.value.some(i => i.filename === data.saved[0])) {
      await selectImage(data.saved[0])
    } else if (previouslySelected && imageList.value.some(i => i.filename === previouslySelected)) {
      await selectImage(previouslySelected)
    }
  } catch (e) {
    emit('notify', 'Error subiendo imágenes: ' + e.message, 'error')
  } finally {
    uploading.value = false
  }
}

async function discardAdditionalImage() {
  if (!selectedFile.value) return
  try {
    const r = await fetch(
      `${API}/api/training/cameras/${camId.value}/additional-images/${encodeURIComponent(selectedFile.value)}`,
      { method: 'DELETE' }
    )
    if (!r.ok) throw new Error(`HTTP ${r.status}`)
    emit('notify', 'Imagen adicional eliminada', 'info')
    await fetchImages()
  } catch (e) {
    emit('notify', 'Error eliminando imagen: ' + e.message, 'error')
  }
}

// Descartar/reincluir (#nuevo 2026-09-14): a diferencia de "Eliminar imagen
// adicional" (borra el fichero), esto solo la saca/mete en la cola de
// anotación — reversible, no toca disco más que el flag. Vale tanto para
// imágenes de cámara como adicionales.
async function toggleExcluded() {
  if (!selectedFile.value) return
  const img = selectedImageMeta.value
  if (!img) return
  const method = img.excluded ? 'DELETE' : 'POST'
  try {
    const r = await fetch(
      `${API}/api/training/cameras/${camId.value}/images/${encodeURIComponent(selectedFile.value)}/exclude`,
      { method }
    )
    if (!r.ok) throw new Error(`HTTP ${r.status}`)
    img.excluded = !img.excluded
    emit('notify', img.excluded ? 'Imagen descartada del entrenamiento' : 'Imagen reincluida', 'info')
    // Al descartar la que se está viendo (y sin "mostrar descartadas"), salta
    // a la siguiente visible en vez de dejar la pantalla mirando una imagen
    // que ya no está en la cola.
    if (img.excluded && !showExcluded.value) {
      const next = visibleImages.value[0]
      if (next) await selectImage(next.filename)
    }
  } catch (e) {
    emit('notify', 'Error al descartar/reincluir: ' + e.message, 'error')
  }
}

async function exportJSON() {
  try {
    const r = await fetch(`${API}/api/training/cameras/${camId.value}/export`)
    if (!r.ok) throw new Error(`HTTP ${r.status}`)
    const data = await r.json()
    if (!data.annotations || data.annotations.length === 0) {
      emit('notify', 'No hay ninguna polilínea guardada todavía para esta cámara', 'error')
      return
    }
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
    const url  = URL.createObjectURL(blob)
    const a    = document.createElement('a')
    a.href     = url
    a.download = `cv-lit_cam${camId.value}_entrenamiento_polilineas.json`
    a.click()
    URL.revokeObjectURL(url)
    emit('notify', `JSON exportado (${data.annotations.length} imagen(es))`, 'success')
  } catch (e) {
    emit('notify', 'Error exportando JSON: ' + e.message, 'error')
  }
}

// Puntos en formato "svg-ready": el <svg> se dibuja con viewBox = tamaño
// natural de la imagen, así que son directamente las coordenadas guardadas.
const svgPoints = computed(() => points.value.map(p => p.join(',')).join(' '))
</script>

<template>
  <div class="flex h-full gap-4">

    <!-- ── Panel izquierdo: controles ──────────────────────────────────────── -->
    <aside class="w-72 shrink-0 flex flex-col gap-4">

      <div class="bg-amber-50 border border-amber-200 rounded-md p-3">
        <p class="text-xs font-semibold text-amber-700">Sección temporal</p>
        <p class="text-[10px] text-amber-600 mt-1 leading-relaxed">
          Marca a mano la línea húmeda real sobre imágenes reales. Estos datos
          se usarán para entrenar/ajustar la segmentación automática — no
          afecta a los resultados de "Resultados".
        </p>
      </div>

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

      <div class="card-standard p-4">
        <h3 class="text-[10px] font-semibold text-slate-400 uppercase tracking-wider mb-3">Imagen</h3>
        <select v-model="selectedFile" @change="selectImage(selectedFile)" class="input-standard w-full">
          <option v-if="visibleImages.length === 0" value="">Sin imágenes</option>
          <option v-for="img in visibleImages" :key="img.filename" :value="img.filename">
            {{ img.annotated ? '● ' : '' }}{{ img.source === 'additional' ? '[adicional] ' : '' }}{{ img.excluded ? '[descartada] ' : '' }}{{ img.filename }}
          </option>
        </select>
        <p class="text-[10px] text-slate-400 mt-2 font-mono">
          {{ imageList.filter(i => i.annotated).length }} / {{ imageList.length }} anotadas
        </p>
        <label v-if="excludedCount" class="flex items-center gap-1.5 mt-2 text-[10px] text-slate-500 cursor-pointer">
          <input type="checkbox" v-model="showExcluded">
          Mostrar descartadas ({{ excludedCount }})
        </label>
        <input ref="fileInputRef" type="file" accept="image/jpeg,image/png" multiple class="hidden" @change="onFilesChosen">
        <button @click="triggerUpload" :disabled="uploading" class="btn-secondary w-full justify-center py-1.5 text-xs mt-2 disabled:opacity-40">
          {{ uploading ? 'Subiendo…' : 'Subir imágenes adicionales' }}
        </button>
        <button v-if="selectedImageMeta" @click="toggleExcluded" class="w-full justify-center py-1.5 text-xs mt-1 hover:underline"
                :class="selectedImageMeta.excluded ? 'text-emerald-600' : 'text-amber-600'">
          {{ selectedImageMeta.excluded ? 'Reincluir esta imagen' : 'Descartar esta imagen (revisar antes de anotar)' }}
        </button>
        <button v-if="isAdditionalImage" @click="discardAdditionalImage" class="w-full justify-center py-1.5 text-xs mt-1 text-red-500 hover:underline">
          Eliminar esta imagen adicional
        </button>
      </div>

      <div class="card-standard p-4 space-y-2">
        <h3 class="text-[10px] font-semibold text-slate-400 uppercase tracking-wider mb-1">Polilínea</h3>
        <p class="text-xs text-slate-500">
          {{ points.length }} punto(s) marcado(s)
          <span v-if="selectedIdx !== null" class="text-emerald-600 font-semibold">· punto {{ selectedIdx + 1 }} seleccionado (usa las flechas)</span>
        </p>
        <div class="flex gap-2">
          <button @click="undoLast" :disabled="!points.length" class="btn-secondary flex-1 justify-center py-1.5 text-xs disabled:opacity-40 disabled:cursor-not-allowed">
            Deshacer
          </button>
          <button @click="clearPoints" :disabled="!points.length" class="btn-secondary flex-1 justify-center py-1.5 text-xs disabled:opacity-40 disabled:cursor-not-allowed">
            Limpiar
          </button>
        </div>
        <button @click="savePolyline" :disabled="saving || points.length < 2" class="btn-standard w-full justify-center py-2 text-sm disabled:opacity-40 disabled:cursor-not-allowed">
          {{ saving ? 'Guardando…' : 'Guardar polilínea' }}
        </button>
        <button @click="discardPolyline" :disabled="!selectedFile" class="btn-ghost-ok w-full justify-center py-1.5 text-xs text-red-500 disabled:opacity-40 disabled:cursor-not-allowed">
          Descartar anotación de esta imagen
        </button>
      </div>

      <button @click="exportJSON" class="btn-ghost-ok w-full justify-center">
        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"/>
        </svg>
        Exportar JSON (cámara)
      </button>

    </aside>

    <!-- ── Panel central: imagen + puntos marcados ─────────────────────────── -->
    <main class="flex-1 card-standard overflow-hidden flex flex-col">
      <div class="card-header flex items-center justify-between shrink-0 normal-case">
        <h2 class="text-[13px] font-semibold text-slate-700">
          Entrenamiento línea húmeda — CAM {{ camId }}
          <span v-if="selectedFile" class="font-normal text-slate-400 ml-2 text-xs font-mono">{{ selectedFile }}</span>
        </h2>
        <div v-if="imageList.length" class="flex items-center gap-1">
          <button @click="goPrev" :disabled="!hasPrev" title="Imagen anterior" class="w-6 h-6 flex items-center justify-center rounded border border-slate-200 text-slate-500 hover:bg-slate-50 disabled:opacity-30 disabled:cursor-not-allowed">
            <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" d="M15 19l-7-7 7-7"/></svg>
          </button>
          <span class="text-[10px] font-mono text-slate-400 w-12 text-center">{{ currentIndex + 1 }} / {{ imageList.length }}</span>
          <button @click="goNext" :disabled="!hasNext" title="Imagen siguiente" class="w-6 h-6 flex items-center justify-center rounded border border-slate-200 text-slate-500 hover:bg-slate-50 disabled:opacity-30 disabled:cursor-not-allowed">
            <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" d="M9 5l7 7-7 7"/></svg>
          </button>
        </div>
      </div>

      <!-- Vista completa/doble zoom + zoom de la lupa — mismos controles que
           Calibración (paso 5, Marcación de varillas). -->
      <div v-if="selectedFile" class="card-standard p-2.5 mx-4 mt-4 flex items-center gap-4 shrink-0">
        <div class="flex items-center gap-1.5 shrink-0">
          <span class="text-[9px] font-semibold text-slate-400 uppercase tracking-wider">Vista</span>
          <div class="segmented-light">
            <button @click="imageZoomMode = 'fit'" :class="{ active: imageZoomMode === 'fit' }" title="Imagen completa ajustada al panel">Completa</button>
            <button @click="imageZoomMode = 'x2'" :class="{ active: imageZoomMode === 'x2' }" title="El doble de tamaño — usa scroll para llegar a cada zona">Doble zoom</button>
          </div>
        </div>
        <div class="flex items-center gap-1.5 shrink-0">
          <span class="text-[9px] font-semibold text-slate-400 uppercase tracking-wider">Zoom lupa</span>
          <button @click="zoomFactor = Math.max(2, zoomFactor - 1)" class="w-5 h-5 flex items-center justify-center rounded border border-slate-200 text-slate-500 hover:bg-slate-50 text-xs leading-none">−</button>
          <span class="text-[10px] font-mono text-slate-600 w-6 text-center">×{{ zoomFactor }}</span>
          <button @click="zoomFactor = Math.min(15, zoomFactor + 1)" class="w-5 h-5 flex items-center justify-center rounded border border-slate-200 text-slate-500 hover:bg-slate-50 text-xs leading-none">+</button>
        </div>
        <span class="text-[10px] text-slate-400 ml-auto">Clic: añade punto · Clic en un punto: selecciona (flechas = mover 1px, Mayús = 10px)</span>
      </div>

      <div v-if="!selectedFile" class="flex-1 flex items-center justify-center bg-slate-50 p-4">
        <p class="text-sm font-medium text-slate-400">Selecciona una cámara con imágenes</p>
      </div>
      <div v-else ref="stagePanelRef"
           class="flex-1 overflow-auto stage-viewport bg-slate-900 relative flex items-center justify-center m-4 rounded-md">
        <!-- Lienzo: EXACTAMENTE del tamaño de la imagen renderizada (sin bandas) -->
        <div ref="markStageRef" class="relative shrink-0 cursor-crosshair"
             :style="{ width: stageDisplaySize.width + 'px', height: stageDisplaySize.height + 'px' }"
             @click="onStageClick" @mousemove="onStageMouseMove" @mouseleave="onStageMouseLeave">
          <img ref="markImgRef" :src="imageUrl" @load="onMarkImageLoad" draggable="false"
               class="absolute inset-0 w-full h-full select-none" alt="Imagen para marcar la línea húmeda" />
          <svg
            v-if="imgNatural.width"
            class="absolute inset-0 w-full h-full"
            :viewBox="`0 0 ${imgNatural.width} ${imgNatural.height}`"
            preserveAspectRatio="none"
            style="pointer-events:none">
            <polyline :points="svgPoints" fill="none" stroke="#f43f5e" stroke-width="6" />
            <circle v-for="(p, i) in points" :key="i"
                    @click.stop="selectPoint(i)"
                    :cx="p[0]" :cy="p[1]" :r="selectedIdx === i ? 16 : 11"
                    :fill="selectedIdx === i ? '#10b981' : '#f43f5e'"
                    stroke="white" :stroke-width="selectedIdx === i ? 4 : 3"
                    style="pointer-events:auto; cursor:pointer" />
          </svg>
        </div>

        <!-- Lupa: vive FUERA del lienzo (que hace scroll/zoom) y se posiciona
             contra el visor, para no perderse fuera de la pantalla. -->
        <div v-show="loupeVisible" class="absolute z-30 rounded-md overflow-hidden border-2 border-white/80 shadow-xl pointer-events-none"
             :style="{ left: loupeScreenPos.left + 'px', top: loupeScreenPos.top + 'px', width: LOUPE_SIZE + 'px', height: LOUPE_SIZE + 'px' }">
          <canvas ref="loupeCanvasRef" :width="LOUPE_SIZE" :height="LOUPE_SIZE" class="block bg-black"></canvas>
          <div class="absolute top-1 left-1 bg-black/70 text-white text-[8px] font-semibold px-1.5 py-0.5 rounded uppercase">×{{ zoomFactor }}</div>
          <div v-if="selectedIdx !== null" class="absolute bottom-1 left-1 right-1 bg-black/70 text-white text-[7px] font-semibold px-1.5 py-0.5 rounded uppercase flex items-center gap-2">
            <span class="flex items-center gap-1"><span class="w-2 h-px bg-red-500"></span>Cursor</span>
            <span class="flex items-center gap-1"><span class="w-2 h-px bg-emerald-500"></span>Punto seleccionado</span>
          </div>
        </div>
      </div>

      <div class="px-5 py-3 border-t border-slate-100 flex items-center gap-4 text-xs text-slate-500 shrink-0">
        <div class="flex items-center gap-1.5">
          <div class="w-3 h-0.5 bg-rose-500"></div>
          <span>Línea húmeda marcada a mano</span>
        </div>
      </div>
    </main>

  </div>
</template>
