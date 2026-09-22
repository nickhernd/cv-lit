<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import { API_BASE } from '../api.js'

const emit = defineEmits(['notify', 'go-resultados'])
const API = API_BASE

const cameras = ref([])
const camId = ref(null)
const images = ref([])
const selected = ref(new Set())
const dateFrom = ref('')
const dateTo = ref('')
const isDraggingOver = ref(false)
const profile = ref(null)

// Previsualizar antes de procesar (#nuevo 2026-09-14, pedido en la reunión
// de equipo): la miniatura de la cuadrícula es demasiado pequeña para
// juzgar si una imagen es válida (niebla, cámara movida, gente tapando la
// zona...) — este visor abre la foto real a tamaño completo, con la opción
// de descartarla (eliminarla) directamente desde ahí sin volver a la
// cuadrícula primero.
const previewFile = ref(null)
function openPreview(filename) { previewFile.value = filename }
function closePreview() { previewFile.value = null }
const previewImg = computed(() => filteredImages.value.find(i => i.filename === previewFile.value))
async function discardFromPreview() {
  if (!previewFile.value) return
  await deleteImage(previewFile.value)
  closePreview()
}

async function fetchCameras() {
  try {
    const res = await fetch(`${API}/api/dashboard`)
    const data = await res.json()
    cameras.value = data.cameras
    if (!camId.value && data.cameras.length) camId.value = data.cameras[0].idx
  } catch (e) { emit('notify', 'Error al cargar cámaras', 'error') }
}

async function fetchImages() {
  if (!camId.value) return
  selected.value = new Set()
  // Limpiar y capturar la cámara actual para no renderizar miniaturas de la
  // cámara anterior con el id nuevo (provocaba 404 en /image al cambiar rápido)
  images.value = []
  const snapshot = camId.value
  try {
    const res = await fetch(`${API}/api/cameras/${snapshot}/images`)
    const imgs = await res.json()
    if (snapshot !== camId.value) return
    images.value = imgs
  } catch (e) { emit('notify', 'Error al cargar imágenes', 'error') }
}

async function fetchProfile() {
  if (!camId.value) return
  const snapshot = camId.value
  try {
    const res = await fetch(`${API}/api/cameras/${snapshot}/profile`)
    const data = await res.json()
    if (snapshot !== camId.value) return
    profile.value = data
  } catch (e) { profile.value = null }
}

async function handleFiles(files) {
  if (!camId.value || !files.length) return
  const form = new FormData()
  for (const f of files) form.append('files', f)
  try {
    const res = await fetch(`${API}/api/cameras/${camId.value}/upload-images`, { method: 'POST', body: form })
    const data = await res.json()
    if (res.ok) {
      emit('notify', `Subidos ${data.uploaded.length} archivos`, 'success')
      fetchImages()
    }
  } catch (e) { emit('notify', 'Error al subir imágenes', 'error') }
}

function onDrop(e) {
  isDraggingOver.value = false
  if (e.dataTransfer.files.length) handleFiles(e.dataTransfer.files)
}

function toggleSelect(filename) {
  const next = new Set(selected.value)
  next.has(filename) ? next.delete(filename) : next.add(filename)
  selected.value = next
}

function selectAll() { selected.value = new Set(filteredImages.value.map(i => i.filename)) }
function selectNone() { selected.value = new Set() }

// "Analizar todas las pendientes" (evolución temporal del área seca, #nuevo
// 2026-09-10): selecciona de golpe las imágenes de la cámara activa que
// AÚN NO tienen un resultado aceptado en el histórico (img.analyzed, ver
// list_camera_images() en el backend, que lo calcula a partir de
// coastline_history_cam{id}.json) y reutiliza el mismo procesado secuencial
// que ya usa "Procesar selección" — sin endpoint nuevo, sin lote en el
// backend (SAM no lo admite, ver comentario de processSelection).
const pendingCount = computed(() => filteredImages.value.filter(img => !img.analyzed).length)
function selectPending() {
  selected.value = new Set(filteredImages.value.filter(img => !img.analyzed).map(i => i.filename))
}
async function analyzeAllPending() {
  selectPending()
  if (!selected.value.size) { emit('notify', 'No hay imágenes pendientes de analizar', 'success'); return }
  await processSelection()
}

// "Reanalizar TODAS" (#nuevo 2026-09-10): a diferencia del botón de arriba,
// esta reprocesa TAMBIÉN las que ya tienen un resultado guardado — hace
// falta después de una mejora de segmentación como la de hoy, para que las
// fotos ya analizadas con el código viejo se actualicen con el nuevo sin
// tener que ir marcándolas una a una a mano.
async function reanalyzeAll() {
  if (!filteredImages.value.length) { emit('notify', 'No hay imágenes en esta cámara', 'error'); return }
  selected.value = new Set(filteredImages.value.map(i => i.filename))
  await processSelection()
}

// Hora del reloj con más imágenes en la lista filtrada — permite seleccionar
// de un click la sesión de disparo dominante en vez de marcar una a una.
const dominantHour = computed(() => {
  if (!filteredImages.value.length) return null
  const counts = {}
  filteredImages.value.forEach(img => {
    const h = new Date(img.modified * 1000).getHours()
    counts[h] = (counts[h] || 0) + 1
  })
  return Object.entries(counts).sort((a, b) => b[1] - a[1])[0]?.[0] ?? null
})
function selectDominantHour() {
  if (dominantHour.value === null) return
  selected.value = new Set(
    filteredImages.value
      .filter(img => new Date(img.modified * 1000).getHours() === Number(dominantHour.value))
      .map(i => i.filename)
  )
}

async function deleteImage(filename) {
  if (!confirm(`¿Eliminar ${filename}?`)) return
  try {
    const res = await fetch(`${API}/api/cameras/${camId.value}/images/${filename}`, { method: 'DELETE' })
    if (res.ok) { emit('notify', 'Imagen eliminada', 'success'); fetchImages() }
  } catch (e) { emit('notify', 'Error al eliminar imagen', 'error') }
}

const processing = ref(false)

// Bug real detectado 2026-08-31: solo se analizaba la PRIMERA imagen
// seleccionada (llamada única a analyze-roi) aunque el aviso decía
// "Procesando N imagen(es)" y el botón muestra el total seleccionado —
// las demás se descartaban en silencio. Se procesan una a una (analyze-roi
// tarda varios segundos por imagen; SAM no admite lote) y se avisa de
// cuántas terminaron bien de verdad.
async function processSelection() {
  if (!selected.value.size) { emit('notify', 'Selecciona al menos una imagen', 'error'); return }
  processing.value = true
  const filenames = [...selected.value]
  let ok = 0
  let failed = 0
  for (const filename of filenames) {
    try {
      const res = await fetch(`${API}/api/cameras/${camId.value}/analyze-roi?filename=${encodeURIComponent(filename)}`, { method: 'POST' })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      ok++
    } catch (e) { failed++ }
  }
  processing.value = false
  if (ok) {
    emit('notify', failed ? `${ok} imagen(es) procesada(s), ${failed} fallaron — ver Resultados` : `${ok} imagen(es) procesada(s) — ver Resultados`, failed ? 'error' : 'success')
    emit('go-resultados', camId.value)
  } else {
    emit('notify', 'No se pudo procesar ninguna imagen', 'error')
  }
}

const filteredImages = computed(() => {
  return images.value.filter(img => {
    if (!dateFrom.value && !dateTo.value) return true
    const d = new Date(img.modified * 1000).toISOString().slice(0, 10)
    if (dateFrom.value && d < dateFrom.value) return false
    if (dateTo.value && d > dateTo.value) return false
    return true
  })
})

watch(camId, () => { fetchImages(); fetchProfile() })

onMounted(async () => {
  await fetchCameras()
  fetchImages()
  fetchProfile()
})
</script>

<template>
  <div class="space-y-4">
    <div class="flex justify-end gap-2">
      <button @click="reanalyzeAll" :disabled="processing || !filteredImages.length"
              title="Vuelve a analizar TODAS las imágenes de esta cámara, incluidas las que ya tenían un resultado guardado — para actualizarlas todas de golpe después de una mejora del análisis."
              class="btn-secondary uppercase text-xs disabled:opacity-40 disabled:cursor-not-allowed">
        {{ processing ? 'Procesando…' : `Reanalizar todas (${filteredImages.length})` }}
      </button>
      <button @click="analyzeAllPending" :disabled="processing || !pendingCount"
              title="Analiza de golpe todas las imágenes de esta cámara que aún no tienen un resultado en el histórico — para ver la evolución temporal del área seca sin seleccionarlas una a una."
              class="btn-secondary uppercase text-xs disabled:opacity-40 disabled:cursor-not-allowed">
        {{ processing ? 'Procesando…' : `Analizar pendientes (${pendingCount})` }}
      </button>
      <button @click="processSelection" :disabled="processing || !selected.size" class="btn-standard uppercase text-xs disabled:opacity-40 disabled:cursor-not-allowed">
        {{ processing ? 'Procesando…' : `Procesar selección (${selected.size})` }}
      </button>
    </div>

    <div class="grid grid-cols-1 lg:grid-cols-4 gap-4">
      <!-- CAMARA -->
      <div class="card-standard">
        <div class="card-header uppercase tracking-wider text-[10px]">Cámara</div>
        <div class="divide-y divide-slate-100">
          <button v-for="cam in cameras" :key="cam.idx" @click="camId = cam.idx"
                  :class="camId === cam.idx ? 'bg-blue-50 text-blue-700' : 'hover:bg-slate-50 text-slate-700'"
                  class="w-full flex items-center justify-between px-4 py-3 text-left transition-colors">
            <span class="text-xs font-semibold">{{ cam.name }}</span>
            <span :class="cam.status === 'Sin calibrar' ? 'bg-slate-100 text-slate-500' : 'bg-emerald-100 text-emerald-700'"
                  class="text-[9px] font-semibold uppercase px-1.5 py-0.5 rounded">{{ cam.status === 'Sin calibrar' ? 'Sin calib' : 'Calib' }}</span>
          </button>
        </div>
      </div>

      <!-- DIRECTORIO / IMAGENES -->
      <div class="lg:col-span-2 space-y-4">
        <div class="card-standard p-4 space-y-4">
          <div @dragover.prevent="isDraggingOver = true" @dragleave.prevent="isDraggingOver = false" @drop.prevent="onDrop"
               :class="isDraggingOver ? 'border-blue-600 bg-blue-50' : 'border-slate-200'"
               class="p-4 border-2 border-dashed rounded-md text-center relative transition-colors">
            <input type="file" multiple @change="handleFiles($event.target.files)" class="absolute inset-0 opacity-0 cursor-pointer">
            <p class="text-xs font-semibold text-slate-600 uppercase">Arrastra o haz click para añadir imágenes</p>
          </div>
          <div class="grid grid-cols-2 gap-3">
            <div class="space-y-1">
              <label class="text-[10px] font-semibold text-slate-400 uppercase">Desde</label>
              <input type="date" v-model="dateFrom" class="w-full input-standard text-xs">
            </div>
            <div class="space-y-1">
              <label class="text-[10px] font-semibold text-slate-400 uppercase">Hasta</label>
              <input type="date" v-model="dateTo" class="w-full input-standard text-xs">
            </div>
          </div>
        </div>

        <div class="card-standard flex flex-col">
          <div class="card-header flex justify-between items-center">
            <span>Imágenes encontradas ({{ filteredImages.length }})</span>
            <div class="space-x-2 text-[10px] font-semibold uppercase">
              <button v-if="dominantHour !== null" @click="selectDominantHour" class="text-blue-600 hover:underline">
                Solo {{ dominantHour.toString().padStart(2, '0') }}:00h
              </button>
              <button @click="selectAll" class="text-blue-600 hover:underline">Todas</button>
              <button @click="selectNone" class="text-slate-400 hover:underline">Ninguna</button>
            </div>
          </div>
          <p v-if="selected.size" class="px-3.5 pt-2 text-[10px] text-slate-400">
            {{ selected.size }} seleccionada{{ selected.size === 1 ? '' : 's' }} · clic en una miniatura para (de)seleccionarla
          </p>
          <div class="grid grid-cols-3 sm:grid-cols-4 gap-2 p-4 max-h-[420px] overflow-y-auto">
            <div v-for="img in filteredImages" :key="img.filename" @click="toggleSelect(img.filename)"
                 :class="selected.has(img.filename) ? 'ring-2 ring-blue-600' : 'hover:ring-1 hover:ring-slate-300'"
                 class="relative rounded overflow-hidden cursor-pointer group aspect-video bg-slate-200">
              <img :src="`${API}/api/cameras/${camId}/image?file=${img.filename}&thumb=1`" class="w-full h-full object-cover">
              <span v-if="img.analyzed" title="Ya tiene un resultado en el histórico" class="absolute top-1 left-1 w-2.5 h-2.5 rounded-full bg-emerald-500 ring-1 ring-white"></span>
              <div v-if="selected.has(img.filename)" class="absolute top-1 right-1 w-4 h-4 rounded-full bg-blue-600 flex items-center justify-center">
                <svg class="w-2.5 h-2.5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-width="3" d="M5 13l4 4L19 7"/></svg>
              </div>
              <button @click.stop="openPreview(img.filename)" title="Ver a tamaño completo antes de procesar"
                      class="absolute bottom-1 left-1 opacity-0 group-hover:opacity-100 bg-black/60 rounded p-0.5 transition-opacity">
                <svg class="w-3 h-3 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-width="2" d="M2.5 12s3.5-7 9.5-7 9.5 7 9.5 7-3.5 7-9.5 7-9.5-7-9.5-7z"/><circle cx="12" cy="12" r="2.5"/></svg>
              </button>
              <button @click.stop="deleteImage(img.filename)" class="absolute bottom-1 right-1 opacity-0 group-hover:opacity-100 bg-red-600/90 rounded p-0.5 transition-opacity">
                <svg class="w-3 h-3 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-width="2" d="M6 18L18 6M6 6l12 12"/></svg>
              </button>
              <span class="absolute bottom-0.5 left-1 text-[8px] font-semibold text-white bg-black/50 px-1 rounded">{{ new Date(img.modified*1000).toLocaleTimeString('es-ES', {hour:'2-digit', minute:'2-digit'}) }}</span>
            </div>
            <p v-if="!filteredImages.length" class="col-span-full text-center text-xs text-slate-400 py-8">Sin imágenes para esta cámara</p>
          </div>
        </div>
      </div>

      <!-- PERFIL DE CALIBRACION -->
      <div class="card-standard p-4 space-y-3 h-fit">
        <div class="text-[10px] font-semibold text-slate-400 uppercase tracking-wider">Perfil de calibración cargado</div>
        <div v-if="profile && profile.gcps_count" class="space-y-2">
          <div class="flex items-center space-x-2">
            <span class="bg-emerald-100 text-emerald-700 text-[9px] font-semibold px-2 py-0.5 rounded uppercase">{{ cameras.find(c => c.idx === camId)?.id }} — {{ profile.date }}</span>
          </div>
          <p class="text-xs text-slate-600">RMSE {{ profile.rmse_m?.toFixed(2) }} m · {{ profile.gcps_count }} GCPs</p>
        </div>
        <p v-else class="text-xs text-slate-400 italic">Cámara sin calibrar todavía</p>
      </div>
    </div>

    <!-- Visor de previsualización (#nuevo 2026-09-14): foto real a tamaño
         completo para poder juzgar si una imagen sirve (niebla, cámara
         movida, algo tapando la zona...) antes de procesarla — la miniatura
         de la cuadrícula es demasiado pequeña para eso. -->
    <div v-if="previewFile" @click.self="closePreview"
         class="fixed inset-0 z-50 bg-black/80 flex items-center justify-center p-8">
      <div class="max-w-5xl w-full flex flex-col items-center gap-3">
        <img :src="`${API}/api/cameras/${camId}/image?file=${previewFile}`" class="max-w-full max-h-[75vh] object-contain rounded-md">
        <div class="flex items-center justify-between w-full text-white">
          <div class="text-xs">
            <p class="font-mono">{{ previewFile }}</p>
            <p v-if="previewImg" class="text-slate-300">{{ new Date(previewImg.modified*1000).toLocaleString('es-ES') }}</p>
          </div>
          <div class="flex items-center gap-2">
            <button @click="discardFromPreview" class="text-xs uppercase font-semibold px-3 py-1.5 rounded-md bg-red-600 hover:bg-red-700 transition-colors">
              Descartar
            </button>
            <button @click="closePreview" class="text-xs uppercase font-semibold px-3 py-1.5 rounded-md bg-white/10 hover:bg-white/20 transition-colors">
              Cerrar
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
