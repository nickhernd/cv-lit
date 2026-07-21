<script setup>
import { ref, onMounted, computed, watch } from 'vue'
import BatchAlignment from './BatchAlignment.vue'
import Map from './Map.vue'

const props = defineProps({
  initialCamId: { type: Number, default: null }
})

const emit = defineEmits(['notify'])

const currentStep = ref(1)
const selectedCamId = ref(props.initialCamId)
const cameras = ref([])
const availableImages = ref([])
const selectedImage = ref('')
const currentProfile = ref({ gcps: [], reference_image: null })
const loading = ref(false)
const saving = ref(false)
const calculating = ref(false)
const rmse = ref(null)

// Calibración por imagen: resultado del último cálculo (residuos por varilla)
const calibResult = ref(null)
const excludedIdx = ref([])
const threshold = ref(1.0)
const rectifiedFailed = ref(false)

// Catálogo de varillas topografiadas (UTM) a nivel de cámara — solo aplica
// al CSV genérico (sin columna FILE), donde las varillas son fijas y valen
// para cualquier imagen de la cámara.
const rods = ref([])
const importingRods = ref(false)
const savingRods = ref(false)
const rodsDirty = ref(false)
const rodsMeta = ref({ source_file: null, imported_at: null, edited_at: null })

// Importación "por imagen": el CSV de campo (columna FILE) trae varillas
// distintas para cada sesión de disparo. Cada grupo se revisa y se guarda
// como anotación de SU imagen, no como catálogo compartido.
const importMode = ref(null)          // null | 'catalog' | 'per_image'
const imageGroups = ref([])           // [{ filename, captured_at, file_tag, points, saving, savedAt }]
const unmatchedGroups = ref([])       // [{ file_tag, points, assignedFilename, saving, savedAt }]

// UX State
const selectedGcpIdx = ref(null)
const isDraggingOver = ref(false)
const isDraggingRodsCsv = ref(false)

// Vista de mapa en el paso de Marcación: sitúa las varillas marcadas (UTM)
// sobre un mapa real para comprobar de un vistazo que las coordenadas caen
// donde tienen que caer, en vez de fiarse solo de la tabla de números.
const mapView = ref(false)
const mapFitSignal = ref(0)
const gcpGeoJson = computed(() => ({
  type: 'FeatureCollection',
  features: (currentProfile.value.gcps || [])
    .filter(g => Array.isArray(g.utm) && g.utm.length === 2 && g.utm.every(v => v !== null && v !== '' && !Number.isNaN(Number(v))))
    .map((g, i) => ({
      type: 'Feature',
      geometry: { type: 'Point', coordinates: [Number(g.utm[0]), Number(g.utm[1])] },
      properties: { label: g.label, idx: i }
    }))
}))
watch(mapView, (v) => { if (v) mapFitSignal.value++ })

const steps = [
  { id: 1, name: 'Vista general', desc: 'Perfiles de calibración' },
  { id: 2, name: 'Imágenes', desc: 'Gestionar Fotogramas' },
  { id: 3, name: 'Alineación', desc: 'Configurar Referencia' },
  { id: 4, name: 'Catálogo', desc: 'Importar y Corregir Varillas' },
  { id: 5, name: 'Marcación', desc: 'Etiquetado Varillas' },
  { id: 6, name: 'Validación', desc: 'Perfil Final' }
]

// API Helpers
async function fetchCameras() {
  try {
    const res = await fetch('http://localhost:8000/api/cameras')
    cameras.value = await res.json()
  } catch (err) { emit('notify', 'Error al cargar estaciones', 'error') }
}

function editCamera(idx) {
  selectedCamId.value = idx
  currentStep.value = 2
}

function viewCamera(idx) {
  selectedCamId.value = idx
  currentStep.value = 6
}

const calibratedCount = computed(() => cameras.value.filter(c => c.calibrated).length)
const avgRmse = computed(() => {
  const vals = cameras.value.filter(c => c.rmse_m != null).map(c => c.rmse_m)
  if (!vals.length) return '—'
  return (vals.reduce((a, b) => a + b, 0) / vals.length).toFixed(2) + ' m'
})
const totalGcps = computed(() => cameras.value.reduce((a, c) => a + (c.gcps_count || 0), 0))

async function fetchImages() {
  if (!selectedCamId.value) return
  // Limpiar inmediatamente para evitar que imágenes de la cámara anterior
  // aparezcan en el contexto de la nueva (race condition entre fetches)
  availableImages.value = []
  selectedImage.value   = ''
  const camSnapshot = selectedCamId.value
  try {
    const res = await fetch(`http://localhost:8000/api/cameras/${camSnapshot}/images`)
    const imgs = await res.json()
    // Descartar la respuesta si el usuario ya cambió de cámara mientras esperábamos
    if (camSnapshot !== selectedCamId.value) return
    availableImages.value = imgs
    if (imgs.length > 0) selectedImage.value = imgs[0].filename
  } catch (err) { console.error(err) }
}

async function runAlignment() {
  alignState.value = 'loading'
  blendUrl.value   = ''
  alignError.value = ''

  try {
    // Obtener la imagen target como Blob desde su URL del backend
    const tgtResp = await fetch(imageUrl.value)  // URL de la imagen seleccionada en paso 2
    if (!tgtResp.ok) throw new Error('No se pudo cargar la imagen target')
    const tgtBlob = await tgtResp.blob()

    const form = new FormData()
    form.append('target', tgtBlob, 'target.jpg')
    // No enviamos 'reference' → el backend la lee del perfil JSON automáticamente

    const resp = await fetch(
      `http://localhost:8000/api/cameras/${selectedCamId.value}/align-preview`,
      { method: 'POST', body: form }
    )

    if (!resp.ok) {
      const err = await resp.json()
      throw new Error(err.detail ?? 'Error desconocido')
    }

    if (blendUrl.value) URL.revokeObjectURL(blendUrl.value) // limpiar anterior
    blendUrl.value   = URL.createObjectURL(await resp.blob())
    alignState.value = 'done'

  } catch (e) {
    alignError.value = e.message
    alignState.value = 'error'
  }
}

async function fetchProfile() {
  if (!selectedCamId.value) return
  loading.value = true
  try {
    const res = await fetch(`http://localhost:8000/api/cameras/${selectedCamId.value}/profile`)
    currentProfile.value = await res.json()
    if (!currentProfile.value.gcps) currentProfile.value.gcps = []
    rmse.value = currentProfile.value.rmse_m || null
  } catch (err) { console.error(err) }
  finally { loading.value = false }
}

async function fetchRods() {
  if (!selectedCamId.value) return
  try {
    const res = await fetch(`http://localhost:8000/api/cameras/${selectedCamId.value}/rods`)
    const data = await res.json()
    rods.value = data.rods || []
    rodsMeta.value = { source_file: data.source_file, imported_at: data.imported_at, edited_at: data.edited_at }
    rodsDirty.value = false
  } catch (err) { console.error(err) }
}

async function importRodsCsvFile(file) {
  if (!file || !selectedCamId.value) return
  importingRods.value = true
  const form = new FormData()
  form.append('file', file)
  try {
    const res = await fetch(`http://localhost:8000/api/cameras/${selectedCamId.value}/import-rods`, {
      method: 'POST', body: form
    })
    const data = await res.json()
    if (!res.ok) throw new Error(data.detail || 'Error al importar el CSV')

    if (data.mode === 'per_image') {
      // CSV de campo (columna FILE): cada sesión de disparo trae sus propias
      // varillas — se reparten entre las imágenes reales, no van a un catálogo.
      importMode.value = 'per_image'
      rods.value = []
      imageGroups.value = data.matched.map(g => ({
        filename: g.filename, captured_at: g.captured_at, file_tag: g.file_tag,
        points: g.points.map(p => ({ ...p, pixel: [...(p.pixel || [0, 0])], utm: [...p.utm] })),
        saving: false, savedAt: null
      }))
      unmatchedGroups.value = data.unmatched.map(g => ({
        file_tag: g.file_tag,
        points: g.points.map(p => ({ ...p, pixel: [...(p.pixel || [0, 0])], utm: [...p.utm] })),
        assignedFilename: '', saving: false, savedAt: null
      }))
      const totalPts = imageGroups.value.reduce((a, g) => a + g.points.length, 0)
        + unmatchedGroups.value.reduce((a, g) => a + g.points.length, 0)
      let msg = `Importadas ${totalPts} varillas en ${imageGroups.value.length} imagen(es)`
      if (unmatchedGroups.value.length) msg += ` · ${unmatchedGroups.value.length} sesión(es) sin imagen — asígnalas abajo`
      if (data.skipped) msg += ` (${data.skipped} filas omitidas)`
      emit('notify', msg, unmatchedGroups.value.length ? 'error' : 'success')
    } else {
      importMode.value = 'catalog'
      imageGroups.value = []
      unmatchedGroups.value = []
      rods.value = data.rods
      rodsMeta.value = { source_file: file.name, imported_at: new Date().toISOString(), edited_at: null }
      rodsDirty.value = false
      const extra = data.skipped ? ` (${data.skipped} filas omitidas por coordenadas inválidas)` : ''
      emit('notify', `Importadas ${data.count} varillas${extra}`, 'success')
    }
  } catch (err) { emit('notify', err.message, 'error') }
  finally { importingRods.value = false }
}

// Emparejamiento por imagen (CSV de campo) ------------------------------------
// Etiquetas repetidas o coordenadas vacías/rotas dentro del grupo de una imagen.
function pointIssues(points) {
  const counts = {}
  points.forEach(p => {
    const key = (p.label || '').trim().toUpperCase()
    counts[key] = (counts[key] || 0) + 1
  })
  return points.map(p => {
    const key = (p.label || '').trim().toUpperCase()
    const badPair = (arr) => !Array.isArray(arr) || arr.length !== 2 || arr.some(v => v === null || v === '' || Number.isNaN(Number(v)))
    return {
      emptyLabel: !key,
      duplicateLabel: key && counts[key] > 1,
      invalidPixel: badPair(p.pixel),
      invalidUtm: badPair(p.utm)
    }
  })
}
function groupHasIssues(points) {
  return pointIssues(points).some(i => i.emptyLabel || i.duplicateLabel || i.invalidPixel || i.invalidUtm)
}

function addGroupPoint(points) {
  points.push({ label: `VARILLA_${points.length + 1}`, pixel: [0, 0], utm: [0, 0], notes: '' })
}
function removeGroupPoint(points, idx) { points.splice(idx, 1) }

function loadImageSize(filename) {
  return new Promise((resolve, reject) => {
    const img = new Image()
    img.onload = () => resolve({ width: img.naturalWidth, height: img.naturalHeight })
    img.onerror = () => reject(new Error('No se pudo cargar la imagen para calcular su tamaño'))
    img.src = `http://localhost:8000/api/cameras/${selectedCamId.value}/image?file=${filename}`
  })
}

// Persiste los puntos de un grupo como anotaciones de su imagen (misma ruta
// que usa la marcación manual), calculando "rel" a partir del tamaño real
// de la imagen para que el punto se pinte en el sitio correcto en el paso 5.
async function saveImageGroup(group, filename) {
  if (!filename || groupHasIssues(group.points)) return
  group.saving = true
  try {
    const { width, height } = await loadImageSize(filename)
    const points = group.points.map(p => ({
      pixel: p.pixel.map(Number),
      utm: p.utm.map(Number),
      label: p.label,
      type: 'calib',
      rel: [(Number(p.pixel[0]) / width) * 100, (Number(p.pixel[1]) / height) * 100],
      ...(p.notes ? { notes: p.notes } : {})
    }))
    const res = await fetch(`http://localhost:8000/api/cameras/${selectedCamId.value}/images/${filename}/annotations`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ points })
    })
    if (!res.ok) throw new Error('Error al guardar las varillas de esta imagen')
    group.savedAt = new Date().toISOString()
    emit('notify', `Guardadas ${points.length} varillas en ${filename}`, 'success')
    fetchImages()
  } catch (err) { emit('notify', err.message, 'error') }
  finally { group.saving = false }
}

function importRodsCsv(event) {
  const file = event.target.files?.[0]
  importRodsCsvFile(file)
  event.target.value = ''
}

function onDropRodsCsv(e) {
  isDraggingRodsCsv.value = false
  const file = e.dataTransfer.files?.[0]
  if (file) importRodsCsvFile(file)
}

// Edición manual del catálogo (paso "Catálogo") ------------------------------
function addRodRow() {
  rods.value.push({ label: `VARILLA_${rods.value.length + 1}`, utm: [0, 0], z: null, notes: '' })
  rodsDirty.value = true
}

function removeRodRow(idx) {
  rods.value.splice(idx, 1)
  rodsDirty.value = true
}

function markRodsDirty() { rodsDirty.value = true }

// Etiquetas repetidas o coordenadas vacías: se resaltan en la tabla para que
// el usuario las corrija antes de guardar el catálogo.
const rodsIssues = computed(() => {
  const counts = {}
  rods.value.forEach(r => {
    const key = (r.label || '').trim().toUpperCase()
    counts[key] = (counts[key] || 0) + 1
  })
  return rods.value.map(r => {
    const key = (r.label || '').trim().toUpperCase()
    return {
      emptyLabel: !key,
      duplicateLabel: key && counts[key] > 1,
      invalidCoords: !Array.isArray(r.utm) || r.utm.length !== 2 || r.utm.some(v => v === null || v === '' || Number.isNaN(Number(v)))
    }
  })
})
const rodsHasIssues = computed(() => rodsIssues.value.some(i => i.emptyLabel || i.duplicateLabel || i.invalidCoords))

async function saveRodsCatalog() {
  if (!selectedCamId.value || rodsHasIssues.value) return
  savingRods.value = true
  try {
    const res = await fetch(`http://localhost:8000/api/cameras/${selectedCamId.value}/rods`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ rods: rods.value.map(r => ({
        label: r.label,
        utm: r.utm.map(Number),
        z: r.z === '' || r.z === undefined ? null : r.z,
        notes: r.notes || null
      })) })
    })
    const data = await res.json()
    if (!res.ok) throw new Error(data.detail || 'Error al guardar el catálogo')
    rods.value = data.rods
    rodsDirty.value = false
    emit('notify', `Catálogo guardado: ${data.count} varillas`, 'success')
  } catch (err) { emit('notify', err.message, 'error') }
  finally { savingRods.value = false }
}

// Autocompleta etiqueta y UTM del punto seleccionado desde el catálogo
function assignRod(rodIdx) {
  const rod = rods.value[rodIdx]
  if (selectedGcpIdx.value === null || !rod) return
  const gcp = currentProfile.value.gcps[selectedGcpIdx.value]
  gcp.label = rod.label
  gcp.utm = [...rod.utm]
  saveAnnotations()
}

// Calcula la homografía de la imagen activa con sus varillas marcadas y guarda
// el resultado (residuos por varilla, RMSE, umbral) para el paso de validación.
async function calculateHomography(excluded = []) {
  if (!selectedCamId.value || !selectedImage.value) return
  calculating.value = true
  try {
    const res = await fetch(`http://localhost:8000/api/cameras/${selectedCamId.value}/calculate-homography`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        image_name: selectedImage.value,
        threshold_px: threshold.value,
        excluded
      })
    })
    const data = await res.json()
    if (!res.ok) throw new Error(data.detail || 'Error en el cálculo')
    calibResult.value = data
    excludedIdx.value = [...(data.excluded || [])]
    rmse.value = data.rmse_m
    rectifiedFailed.value = false
    const flagged = (data.residuals || []).filter(r => r.above_threshold).length
    if (flagged > 0) {
      emit('notify', `Homografía calculada: ${flagged} varilla(s) superan el umbral de ${threshold.value} px`, 'error')
    } else {
      emit('notify', `Homografía calculada. RMSE ${data.rmse_px?.toFixed(2)} px`, 'success')
    }
    currentStep.value = 6
    fetchImages()
    fetchCameras()
  } catch (err) { emit('notify', err.message, 'error') }
  finally { calculating.value = false }
}

function recalculate() { calculateHomography(excludedIdx.value) }

function toggleExcluded(idx) {
  if (excludedIdx.value.includes(idx)) excludedIdx.value = excludedIdx.value.filter(i => i !== idx)
  else excludedIdx.value.push(idx)
}

// Excluye de golpe todas las varillas que superan el umbral y recalcula
function excludeFlagged() {
  const flagged = (calibResult.value?.residuals || []).filter(r => r.above_threshold).map(r => r.idx)
  excludedIdx.value = [...new Set([...excludedIdx.value, ...flagged])]
  recalculate()
}

// Al entrar en Validación sin cálculo en memoria, recupera la última calibración
// guardada de la imagen calibrada de esta cámara.
async function loadSavedCalibration() {
  if (calibResult.value || !selectedCamId.value) return
  try {
    const res = await fetch(`http://localhost:8000/api/cameras/${selectedCamId.value}/profile`)
    const profile = await res.json()
    const img = profile.calibrated_image || profile.reference_image
    if (!img || !profile.H) return
    const annRes = await fetch(`http://localhost:8000/api/cameras/${selectedCamId.value}/images/${img}/annotations`)
    const ann = await annRes.json()
    if (ann.calibration) {
      calibResult.value = ann.calibration
      excludedIdx.value = [...(ann.calibration.excluded || [])]
      threshold.value = ann.calibration.threshold_px ?? threshold.value
      rmse.value = ann.calibration.rmse_m
      selectedImage.value = img
    }
  } catch (err) { console.error(err) }
}

function formatTs(iso) {
  if (!iso) return '—'
  const d = new Date(iso)
  if (isNaN(d)) return iso
  return d.toLocaleString('es-ES', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' })
}

const flaggedCount = computed(() => (calibResult.value?.residuals || []).filter(r => r.above_threshold).length)
const calibOk = computed(() => calibResult.value && flaggedCount.value === 0)

async function fetchImageAnnotations() {
  if (!selectedCamId.value || !selectedImage.value) return
  try {
    const res = await fetch(`http://localhost:8000/api/cameras/${selectedCamId.value}/images/${selectedImage.value}/annotations`)
    const data = await res.json()
    currentProfile.value.gcps = data.points || []
  } catch (err) { console.error(err) }
}

async function saveAnnotations() {
  if (!selectedCamId.value || !selectedImage.value) return
  saving.value = true
  try {
    await fetch(`http://localhost:8000/api/cameras/${selectedCamId.value}/images/${selectedImage.value}/annotations`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ points: currentProfile.value.gcps })
    })
    emit('notify', 'Anotaciones guardadas', 'success')
  } catch (err) { emit('notify', 'Error al guardar anotaciones', 'error') }
  finally { saving.value = false }
}

async function setAsReference(filename) {
  try {
    const res = await fetch(`http://localhost:8000/api/cameras/${selectedCamId.value}/set-reference?filename=${filename}`, {
      method: 'POST'
    })
    if (res.ok) {
      currentProfile.value.reference_image = filename
      emit('notify', 'Imagen establecida como referencia base', 'success')
    }
  } catch (err) { emit('notify', 'Error al establecer referencia', 'error') }
}

async function deleteImage(filename) {
  if (!confirm(`¿Seguro que quieres eliminar ${filename}?`)) return
  try {
    const res = await fetch(`http://localhost:8000/api/cameras/${selectedCamId.value}/images/${filename}`, {
      method: 'DELETE'
    })
    if (res.ok) {
      emit('notify', 'Imagen eliminada', 'success')
      if (selectedImage.value === filename) selectedImage.value = ''
      fetchImages()
    }
  } catch (err) { emit('notify', 'Error al eliminar imagen', 'error') }
}

async function handleFiles(files) {
  const formData = new FormData()
  for (let f of files) formData.append('files', f)
  try {
    const res = await fetch(`http://localhost:8000/api/cameras/${selectedCamId.value}/upload-images`, {
      method: 'POST', body: formData
    })
    const data = await res.json()
    if (res.ok) {
      emit('notify', `Subidos ${data.uploaded.length} archivos`, 'success')
      fetchImages()
    }
  } catch (err) { emit('notify', 'Error al subir imágenes', 'error') }
}

function onDrop(e) {
  isDraggingOver.value = false
  const files = e.dataTransfer.files
  if (files.length > 0) handleFiles(files)
}

// Computed
const imageUrl = computed(() => {
  if (!selectedCamId.value || !selectedImage.value) return null
  return `http://localhost:8000/api/cameras/${selectedCamId.value}/image?file=${selectedImage.value}&t=${Date.now()}`
})

const rectifiedUrl = computed(() => {
  if (!selectedCamId.value || !rmse.value) return null
  return `http://localhost:8000/api/cameras/${selectedCamId.value}/rectified-preview?t=${Date.now()}`
})

// Handlers
function handleImageClick(event) {
  if (currentStep.value !== 5) return
  const rect = event.target.getBoundingClientRect()
  const x = event.clientX - rect.left
  const y = event.clientY - rect.top
  const relX = (x / event.target.clientWidth) * 100
  const relY = (y / event.target.clientHeight) * 100

  const newGcp = {
    pixel: [x, y],
    utm: [0, 0],
    label: `VARILLA_${currentProfile.value.gcps.length + 1}`,
    type: 'calib',
    rel: [relX, relY]
  }

  currentProfile.value.gcps.push(newGcp)
  selectedGcpIdx.value = currentProfile.value.gcps.length - 1
  saveAnnotations()
}

// Watches
watch(selectedCamId, () => {
  if (selectedCamId.value) {
    fetchProfile()
    fetchImages()
    fetchRods()
    calibResult.value = null
    excludedIdx.value = []
    selectedGcpIdx.value = null
    importMode.value = null
    imageGroups.value = []
    unmatchedGroups.value = []
  }
})

watch(currentStep, (step) => {
  if (step === 6) loadSavedCalibration()
})

watch(selectedImage, () => {
  if (selectedImage.value) {
    fetchImageAnnotations()
    selectedGcpIdx.value = null
    mapFitSignal.value++
  }
})

onMounted(() => {
  fetchCameras()
  if (selectedCamId.value) {
    fetchProfile()
    fetchImages()
    fetchRods()
    currentStep.value = 2
  }
})
</script>

<template>
  <div class="space-y-6">
    <div class="flex justify-between items-center border-b border-slate-200 pb-4">
      <h1 class="text-xl font-semibold text-slate-900 tracking-tight">Calibración Geométrica</h1>
      <div v-if="selectedCamId" class="flex items-center space-x-2 text-xs font-bold text-blue-600 uppercase">
        <span>Cámara Activa:</span>
        <span class="bg-blue-600 text-white px-2 py-0.5 rounded shadow-sm">{{ cameras.find(c => c.idx === selectedCamId)?.name }}</span>
      </div>
    </div>

    <!-- TABS -->
    <div class="flex bg-white rounded-md shadow-sm border border-slate-200 overflow-hidden">
      <button v-for="step in steps" :key="step.id"
              @click="currentStep = step.id"
              :disabled="!selectedCamId && step.id > 1"
              :class="[
                currentStep === step.id ? 'bg-blue-600 text-white' : 'text-slate-500 hover:bg-slate-50',
                !selectedCamId && step.id > 1 ? 'opacity-50 cursor-not-allowed' : ''
              ]"
              class="px-4 py-3 text-[10px] font-bold uppercase tracking-widest transition-all flex-1 text-center border-r last:border-r-0 border-slate-200">
        {{ step.id }}. {{ step.name }}
      </button>
    </div>

    <!-- PASO 1: VISTA GENERAL -->
    <div v-if="currentStep === 1" class="space-y-6">
      <div class="grid grid-cols-3 gap-4">
        <div class="card-standard p-4">
          <p class="text-[9px] font-bold text-slate-400 uppercase tracking-widest mb-1">Cámaras calibradas</p>
          <p class="text-xl font-bold text-slate-900 tabular-nums">{{ calibratedCount }} / {{ cameras.length }}</p>
        </div>
        <div class="card-standard p-4">
          <p class="text-[9px] font-bold text-slate-400 uppercase tracking-widest mb-1">RMSE medio</p>
          <p class="text-xl font-bold text-slate-900 tabular-nums">{{ avgRmse }}</p>
        </div>
        <div class="card-standard p-4">
          <p class="text-[9px] font-bold text-slate-400 uppercase tracking-widest mb-1">GCPs registrados</p>
          <p class="text-xl font-bold text-slate-900 tabular-nums">{{ totalGcps }}</p>
        </div>
      </div>

      <div class="card-standard overflow-hidden">
        <div class="card-header uppercase tracking-wider text-[10px]">Perfiles de calibración</div>
        <div class="overflow-x-auto">
          <table class="w-full text-left text-sm">
            <thead class="bg-slate-50/60 text-slate-500 font-semibold border-b border-slate-100">
              <tr>
                <th class="px-6 py-3 uppercase tracking-widest text-[10px]">Cám.</th>
                <th class="px-6 py-3 uppercase tracking-widest text-[10px]">Estado</th>
                <th class="px-6 py-3 uppercase tracking-widest text-[10px]">Última calibración</th>
                <th class="px-6 py-3 uppercase tracking-widest text-[10px]">RMSE</th>
                <th class="px-6 py-3 uppercase tracking-widest text-[10px]">GCPs</th>
                <th class="px-6 py-3 text-right uppercase tracking-widest text-[10px]">Acciones</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-slate-100">
              <tr v-for="cam in cameras" :key="cam.idx" class="hover:bg-slate-50 transition-colors text-slate-700">
                <td class="px-6 py-4">
                  <p class="font-bold uppercase text-[11px]">{{ cam.id }}</p>
                  <p class="text-[10px] text-slate-400">{{ cam.name }}</p>
                </td>
                <td class="px-6 py-4">
                  <span class="inline-flex items-center space-x-1.5">
                    <span :class="cam.calibrated ? 'bg-emerald-500' : 'bg-slate-300'" class="w-1.5 h-1.5 rounded-full"></span>
                    <span class="text-[10px] font-bold uppercase">{{ cam.calibrated ? 'Calibrada' : 'Sin calibrar' }}</span>
                  </span>
                </td>
                <td class="px-6 py-4 text-[10px] font-mono text-slate-500">{{ cam.last_calibration_date || '—' }}</td>
                <td class="px-6 py-4 text-[10px] font-mono" :class="cam.rmse_m > 2 ? 'text-amber-600' : 'text-slate-600'">
                  <template v-if="cam.rmse_m != null">
                    {{ cam.rmse_m.toFixed(2) }} m<span v-if="cam.rmse_px != null" class="text-slate-400"> · {{ cam.rmse_px.toFixed(2) }} px</span>
                  </template>
                  <template v-else>—</template>
                </td>
                <td class="px-6 py-4 text-[10px] font-mono text-slate-500">{{ cam.gcps_count ?? '—' }}</td>
                <td class="px-6 py-4 text-right space-x-2">
                  <button v-if="cam.calibrated" @click="viewCamera(cam.idx)" class="btn-secondary py-1 px-3 text-[10px]">Ver</button>
                  <button @click="editCamera(cam.idx)" class="btn-standard py-1 px-3 text-[10px]">{{ cam.calibrated ? 'Editar' : 'Iniciar' }}</button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- PASO 2: GESTION DE IMAGENES -->
    <div v-if="currentStep === 2" class="grid grid-cols-1 lg:grid-cols-4 gap-6">
       <!-- Upload & List -->
       <div class="lg:col-span-1 space-y-4">
          <div @dragover.prevent="isDraggingOver = true"
               @dragleave.prevent="isDraggingOver = false"
               @drop.prevent="onDrop"
               :class="isDraggingOver ? 'border-blue-600 bg-blue-50' : 'border-slate-200 bg-white'"
               class="p-6 border-2 border-dashed rounded-lg text-center transition-colors relative">
            <input type="file" multiple @change="handleFiles($event.target.files)" class="absolute inset-0 opacity-0 cursor-pointer">
            <svg class="w-8 h-8 mx-auto text-slate-400 mb-2" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M12 4v16m8-8H4" stroke-width="2"/></svg>
            <p class="text-xs font-bold text-slate-600 uppercase">Añadir Imágenes</p>
            <p class="text-[9px] text-slate-400 uppercase mt-1">Arrastra o haz click</p>
          </div>

          <div class="card-standard flex flex-col h-[500px]">
            <div class="card-header flex justify-between">
              <span>Fotogramas ({{ availableImages.length }})</span>
              <button @click="fetchImages" class="text-blue-600 hover:underline">↻</button>
            </div>
            <div class="flex-1 overflow-y-auto divide-y divide-slate-100">
               <div v-for="img in availableImages" :key="img.filename"
                    @click="selectedImage = img.filename"
                    :class="selectedImage === img.filename ? 'bg-blue-50' : 'hover:bg-slate-50'"
                    class="p-3 cursor-pointer flex items-center space-x-3 transition-colors group">
                  <div class="w-12 h-8 bg-slate-200 rounded overflow-hidden shrink-0">
                    <img :src="`http://localhost:8000/api/cameras/${selectedCamId}/image?file=${img.filename}&thumb=1`" class="w-full h-full object-cover">
                  </div>
                  <div class="flex-1 min-w-0">
                    <p class="text-[10px] font-bold truncate" :class="selectedImage === img.filename ? 'text-blue-700' : 'text-slate-700'">{{ img.filename }}</p>
                    <p class="text-[9px] text-slate-400">
                      <span class="font-mono">{{ img.captured_at ? formatTs(img.captured_at) : 'Sin fecha de captura' }}</span>
                      <span class="uppercase"> · {{ (img.size / 1024 / 1024).toFixed(1) }} MB</span>
                    </p>
                  </div>
                  <span v-if="img.calibrated" title="Imagen con calibración calculada" class="w-1.5 h-1.5 rounded-full bg-emerald-500 shrink-0"></span>
                  <span v-else-if="img.annotated" title="Imagen con varillas marcadas" class="w-1.5 h-1.5 rounded-full bg-amber-400 shrink-0"></span>
                  <button @click.stop="deleteImage(img.filename)" class="opacity-0 group-hover:opacity-100 p-1 text-red-500 hover:bg-red-50 rounded transition-all">
                    <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" stroke-width="2"/></svg>
                  </button>
               </div>
            </div>
          </div>
       </div>

       <!-- Preview -->
       <div class="lg:col-span-3 card-standard flex flex-col overflow-hidden bg-slate-900 relative">
          <div v-if="selectedImage" class="h-full flex flex-col">
            <div class="flex-1 flex items-center justify-center p-4">
              <img :src="imageUrl" class="max-w-full max-h-full object-contain shadow-2xl">
            </div>
            <div class="p-4 bg-slate-900/90 backdrop-blur border-t border-white/10 flex justify-between items-center">
              <div class="flex space-x-4 items-center">
                <span class="text-xs font-bold text-white uppercase">{{ selectedImage }}</span>
                <span v-if="currentProfile.reference_image === selectedImage" class="bg-emerald-600 text-white text-[9px] font-bold px-2 py-0.5 rounded shadow-sm">REFERENCIA BASE</span>
              </div>
              <div class="space-x-2">
                <button v-if="currentProfile.reference_image !== selectedImage" @click="setAsReference(selectedImage)" class="btn-secondary py-1 text-[10px]">Set como Referencia</button>
                <button @click="currentStep = 3" :disabled="!currentProfile.reference_image" class="btn-standard py-1 text-[10px] disabled:opacity-40 disabled:cursor-not-allowed" :title="!currentProfile.reference_image ? 'Primero establece una imagen de referencia' : ''">Alinear lote completo →</button>
              </div>
            </div>
          </div>
          <div v-else class="flex-1 flex flex-col items-center justify-center text-slate-500 space-y-4">
            <svg class="w-16 h-16 opacity-20" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" stroke-width="1.5"/></svg>
            <p class="text-sm font-bold uppercase tracking-widest">Selecciona o sube un fotograma</p>
          </div>
       </div>
    </div>

    <!-- PASO 3: ALINEACION MASIVA POR LOTES -->
    <div v-if="currentStep === 3" class="card-standard p-4 flex flex-col min-h-[600px]">
      <BatchAlignment
        :cam-id="selectedCamId"
        :image-list="availableImages"
        :initial-base="currentProfile.reference_image || ''"
        @notify="(msg, type) => emit('notify', msg, type)"
        @committed="currentStep = 4"
        @discard="currentStep = 2"
      />
    </div>

    <!-- PASO 4: CATALOGO (importar CSV de varillas topografiadas y corregirlas) -->
    <div v-if="currentStep === 4" class="space-y-6">
      <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div @dragover.prevent="isDraggingRodsCsv = true"
             @dragleave.prevent="isDraggingRodsCsv = false"
             @drop.prevent="onDropRodsCsv"
             :class="isDraggingRodsCsv ? 'border-blue-600 bg-blue-50' : 'border-slate-200 bg-white'"
             class="p-6 border-2 border-dashed rounded-lg text-center transition-colors relative">
          <input type="file" accept=".csv,.txt" @change="importRodsCsv" class="absolute inset-0 opacity-0 cursor-pointer" :disabled="importingRods">
          <svg class="w-8 h-8 mx-auto text-slate-400 mb-2" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M12 4v16m8-8H4" stroke-width="2"/></svg>
          <p class="text-xs font-bold text-slate-600 uppercase">{{ importingRods ? 'Importando…' : (importMode ? 'Reimportar CSV' : 'Importar CSV de Varillas') }}</p>
          <p class="text-[9px] text-slate-400 uppercase mt-1">Arrastra el archivo o haz click</p>
        </div>

        <div class="lg:col-span-2 card-standard p-4 flex flex-col justify-center space-y-2">
          <p class="text-[10px] font-bold text-slate-500 uppercase tracking-widest">Formato esperado</p>
          <p class="text-xs text-slate-500 leading-relaxed">
            Columnas <span class="font-mono text-slate-700">id / X / Y</span> (o equivalentes en español: <span class="font-mono text-slate-700">nombre, este, norte</span>…),
            opcionalmente <span class="font-mono text-slate-700">Z</span> y <span class="font-mono text-slate-700">notas</span>. Separador coma o punto y coma, decimales con coma o punto.
          </p>
          <p class="text-xs text-slate-500 leading-relaxed">
            Si el CSV es el levantamiento de campo del proyecto (con columna <span class="font-mono text-slate-700">FILE</span>), cada varilla pertenece a UNA imagen
            concreta (la de esa sesión de disparo) — se emparejan automáticamente por fecha/hora y se revisan y guardan imagen por imagen, no como catálogo único.
          </p>
          <p v-if="rodsMeta.source_file && importMode === 'catalog'" class="text-[10px] text-slate-400 font-mono pt-1">
            Último origen: {{ rodsMeta.source_file }}
            <span v-if="rodsMeta.edited_at"> · corregido {{ formatTs(rodsMeta.edited_at) }}</span>
            <span v-else-if="rodsMeta.imported_at"> · importado {{ formatTs(rodsMeta.imported_at) }}</span>
          </p>
        </div>
      </div>

      <!-- Modo "por imagen": CSV de campo con columna FILE -->
      <div v-if="importMode === 'per_image'" class="space-y-4">
        <div v-if="unmatchedGroups.length" class="card-standard border-red-200 overflow-hidden">
          <div class="card-header bg-red-50 text-red-700 border-red-200">⚠ Sesiones sin imagen coincidente ({{ unmatchedGroups.length }})</div>
          <div class="divide-y divide-slate-100">
            <div v-for="(group, gi) in unmatchedGroups" :key="'u' + gi" class="p-4 space-y-3">
              <div class="flex items-center justify-between flex-wrap gap-2">
                <div>
                  <p class="text-xs font-bold text-slate-700">Sesión <span class="font-mono">{{ group.file_tag || '(sin etiqueta)' }}</span></p>
                  <p class="text-[10px] text-slate-400">{{ group.points.length }} varilla(s) · no se encontró ninguna imagen subida con esa fecha/hora</p>
                </div>
                <div class="flex items-center space-x-2">
                  <select v-model="group.assignedFilename" class="input-standard text-xs py-1">
                    <option value="" disabled>Asignar a imagen…</option>
                    <option v-for="img in availableImages" :key="img.filename" :value="img.filename">{{ img.filename }}</option>
                  </select>
                  <button @click="saveImageGroup(group, group.assignedFilename)"
                          :disabled="!group.assignedFilename || groupHasIssues(group.points) || group.saving"
                          class="btn-secondary py-1 text-[10px] uppercase disabled:opacity-40 disabled:cursor-not-allowed">
                    {{ group.saving ? 'Guardando…' : (group.savedAt ? 'Guardado ✓' : 'Guardar en esta imagen') }}
                  </button>
                </div>
              </div>
              <div class="overflow-x-auto border border-slate-100 rounded">
                <table class="w-full text-left text-sm">
                  <thead class="bg-slate-50/60 text-slate-500 font-semibold border-b border-slate-100">
                    <tr>
                      <th class="px-3 py-2 uppercase tracking-widest text-[9px]">Etiqueta</th>
                      <th class="px-3 py-2 uppercase tracking-widest text-[9px]">Píxel X</th>
                      <th class="px-3 py-2 uppercase tracking-widest text-[9px]">Píxel Y</th>
                      <th class="px-3 py-2 uppercase tracking-widest text-[9px]">UTM X</th>
                      <th class="px-3 py-2 uppercase tracking-widest text-[9px]">UTM Y</th>
                      <th class="px-3 py-2 uppercase tracking-widest text-[9px]">Notas</th>
                      <th class="px-3 py-2 uppercase tracking-widest text-[9px] text-center">Quitar</th>
                    </tr>
                  </thead>
                  <tbody class="divide-y divide-slate-100">
                    <tr v-for="(p, pi) in group.points" :key="pi"
                        :class="Object.values(pointIssues(group.points)[pi]).some(Boolean) ? 'bg-red-50' : ''">
                      <td class="px-2 py-1.5"><input v-model="p.label" class="w-28 input-standard py-1 text-[11px] font-mono uppercase"></td>
                      <td class="px-2 py-1.5"><input type="number" step="any" v-model.number="p.pixel[0]" class="w-20 input-standard py-1 text-[11px] font-mono text-right"></td>
                      <td class="px-2 py-1.5"><input type="number" step="any" v-model.number="p.pixel[1]" class="w-20 input-standard py-1 text-[11px] font-mono text-right"></td>
                      <td class="px-2 py-1.5"><input type="number" step="any" v-model.number="p.utm[0]" class="w-24 input-standard py-1 text-[11px] font-mono text-right"></td>
                      <td class="px-2 py-1.5"><input type="number" step="any" v-model.number="p.utm[1]" class="w-24 input-standard py-1 text-[11px] font-mono text-right"></td>
                      <td class="px-2 py-1.5"><input v-model="p.notes" placeholder="—" class="w-full input-standard py-1 text-[11px]"></td>
                      <td class="px-2 py-1.5 text-center">
                        <button @click="removeGroupPoint(group.points, pi)" class="p-1 text-red-500 hover:bg-red-50 rounded transition-colors">
                          <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" stroke-width="2"/></svg>
                        </button>
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
              <button @click="addGroupPoint(group.points)" class="text-blue-600 hover:underline text-[10px] font-bold uppercase">+ Añadir varilla</button>
            </div>
          </div>
        </div>

        <div v-if="!imageGroups.length" class="card-standard p-12 text-center space-y-2">
          <p class="text-sm font-bold uppercase tracking-widest text-slate-300">Ninguna imagen emparejada</p>
          <p class="text-[10px] text-slate-400">Sube antes las imágenes de esta cámara (paso 2) o asigna manualmente las sesiones de arriba.</p>
        </div>

        <div v-for="(group, gi) in imageGroups" :key="'m' + gi" class="card-standard overflow-hidden">
          <div class="card-header flex items-center justify-between flex-wrap gap-2">
            <div>
              <span class="uppercase tracking-wider text-[10px]">{{ group.filename }}</span>
              <span class="text-[9px] text-slate-400 ml-2">{{ formatTs(group.captured_at) }} · {{ group.points.length }} varilla(s)</span>
            </div>
            <div class="flex items-center space-x-3">
              <span v-if="groupHasIssues(group.points)" class="text-[9px] font-bold text-red-600 uppercase">⚠ Corrige antes de guardar</span>
              <span v-else-if="group.savedAt" class="text-[9px] font-bold text-emerald-600 uppercase">Guardado {{ formatTs(group.savedAt) }}</span>
              <button @click="addGroupPoint(group.points)" class="text-blue-600 hover:underline text-[10px] font-bold uppercase">+ Añadir</button>
              <button @click="saveImageGroup(group, group.filename)" :disabled="groupHasIssues(group.points) || group.saving"
                      class="btn-standard py-1 text-[10px] uppercase disabled:opacity-40 disabled:cursor-not-allowed">
                {{ group.saving ? 'Guardando…' : 'Guardar en esta imagen' }}
              </button>
            </div>
          </div>
          <div class="overflow-x-auto">
            <table class="w-full text-left text-sm">
              <thead class="bg-slate-50/60 text-slate-500 font-semibold border-b border-slate-100">
                <tr>
                  <th class="px-4 py-3 uppercase tracking-widest text-[10px]">#</th>
                  <th class="px-4 py-3 uppercase tracking-widest text-[10px]">Etiqueta</th>
                  <th class="px-4 py-3 uppercase tracking-widest text-[10px]">Píxel X</th>
                  <th class="px-4 py-3 uppercase tracking-widest text-[10px]">Píxel Y</th>
                  <th class="px-4 py-3 uppercase tracking-widest text-[10px]">UTM X</th>
                  <th class="px-4 py-3 uppercase tracking-widest text-[10px]">UTM Y</th>
                  <th class="px-4 py-3 uppercase tracking-widest text-[10px]">Notas</th>
                  <th class="px-4 py-3 uppercase tracking-widest text-[10px] text-center">Quitar</th>
                </tr>
              </thead>
              <tbody class="divide-y divide-slate-100">
                <tr v-for="(p, pi) in group.points" :key="pi"
                    :class="Object.values(pointIssues(group.points)[pi]).some(Boolean) ? 'bg-red-50' : ''">
                  <td class="px-4 py-2 text-[10px] font-bold text-slate-400">{{ pi + 1 }}</td>
                  <td class="px-2 py-2"><input v-model="p.label" class="w-full input-standard py-1 text-[11px] font-mono uppercase"></td>
                  <td class="px-2 py-2"><input type="number" step="any" v-model.number="p.pixel[0]" class="w-20 input-standard py-1 text-[11px] font-mono text-right"></td>
                  <td class="px-2 py-2"><input type="number" step="any" v-model.number="p.pixel[1]" class="w-20 input-standard py-1 text-[11px] font-mono text-right"></td>
                  <td class="px-2 py-2"><input type="number" step="any" v-model.number="p.utm[0]" class="w-24 input-standard py-1 text-[11px] font-mono text-right"></td>
                  <td class="px-2 py-2"><input type="number" step="any" v-model.number="p.utm[1]" class="w-24 input-standard py-1 text-[11px] font-mono text-right"></td>
                  <td class="px-2 py-2"><input v-model="p.notes" placeholder="—" class="w-full input-standard py-1 text-[11px]"></td>
                  <td class="px-2 py-2 text-center">
                    <button @click="removeGroupPoint(group.points, pi)" class="p-1 text-red-500 hover:bg-red-50 rounded transition-colors">
                      <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" stroke-width="2"/></svg>
                    </button>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>

        <div class="flex justify-end">
          <button @click="currentStep = 5" class="btn-standard py-1.5 text-[10px] uppercase">Continuar a Marcación →</button>
        </div>
      </div>

      <!-- Modo "catálogo": CSV genérico sin columna FILE, varillas fijas para toda la cámara -->
      <div v-else class="card-standard flex flex-col">
        <div class="card-header flex justify-between items-center">
          <span class="uppercase tracking-wider text-[10px]">Catálogo de Varillas ({{ rods.length }})</span>
          <div class="flex items-center space-x-3">
            <span v-if="rodsHasIssues" class="text-[9px] font-bold text-red-600 uppercase">⚠ Corrige las filas resaltadas antes de guardar</span>
            <span v-else-if="rodsDirty" class="text-[9px] font-bold text-amber-600 uppercase">Cambios sin guardar</span>
            <button @click="addRodRow" class="text-blue-600 hover:underline text-[10px] font-bold uppercase">+ Añadir fila</button>
          </div>
        </div>

        <div v-if="!rods.length" class="p-12 text-center space-y-2">
          <p class="text-sm font-bold uppercase tracking-widest text-slate-300">Sin varillas todavía</p>
          <p class="text-[10px] text-slate-400">Importa un CSV o añade filas manualmente para construir el catálogo.</p>
        </div>

        <div v-else class="overflow-x-auto">
          <table class="w-full text-left text-sm">
            <thead class="bg-slate-50/60 text-slate-500 font-semibold border-b border-slate-100">
              <tr>
                <th class="px-4 py-3 uppercase tracking-widest text-[10px]">#</th>
                <th class="px-4 py-3 uppercase tracking-widest text-[10px]">Etiqueta</th>
                <th class="px-4 py-3 uppercase tracking-widest text-[10px]">UTM X</th>
                <th class="px-4 py-3 uppercase tracking-widest text-[10px]">UTM Y</th>
                <th class="px-4 py-3 uppercase tracking-widest text-[10px]">Z</th>
                <th class="px-4 py-3 uppercase tracking-widest text-[10px]">Notas</th>
                <th class="px-4 py-3 uppercase tracking-widest text-[10px] text-center">Quitar</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-slate-100">
              <tr v-for="(rod, idx) in rods" :key="idx"
                  :class="(rodsIssues[idx]?.emptyLabel || rodsIssues[idx]?.duplicateLabel || rodsIssues[idx]?.invalidCoords) ? 'bg-red-50' : ''"
                  class="transition-colors">
                <td class="px-4 py-2 text-[10px] font-bold text-slate-400">{{ idx + 1 }}</td>
                <td class="px-2 py-2">
                  <input v-model="rod.label" @input="markRodsDirty"
                         :class="(rodsIssues[idx]?.emptyLabel || rodsIssues[idx]?.duplicateLabel) ? 'border-red-300 focus:border-red-400' : ''"
                         class="w-full input-standard py-1 text-[11px] font-mono uppercase">
                </td>
                <td class="px-2 py-2">
                  <input type="number" step="any" v-model.number="rod.utm[0]" @input="markRodsDirty"
                         :class="rodsIssues[idx]?.invalidCoords ? 'border-red-300 focus:border-red-400' : ''"
                         class="w-24 input-standard py-1 text-[11px] font-mono text-right">
                </td>
                <td class="px-2 py-2">
                  <input type="number" step="any" v-model.number="rod.utm[1]" @input="markRodsDirty"
                         :class="rodsIssues[idx]?.invalidCoords ? 'border-red-300 focus:border-red-400' : ''"
                         class="w-24 input-standard py-1 text-[11px] font-mono text-right">
                </td>
                <td class="px-2 py-2">
                  <input type="number" step="any" v-model.number="rod.z" @input="markRodsDirty" placeholder="—"
                         class="w-16 input-standard py-1 text-[11px] font-mono text-right">
                </td>
                <td class="px-2 py-2">
                  <input v-model="rod.notes" @input="markRodsDirty" placeholder="—"
                         class="w-full input-standard py-1 text-[11px]">
                </td>
                <td class="px-2 py-2 text-center">
                  <button @click="removeRodRow(idx)" class="p-1 text-red-500 hover:bg-red-50 rounded transition-colors">
                    <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" stroke-width="2"/></svg>
                  </button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <div class="p-4 border-t border-slate-100 bg-slate-50 flex justify-between items-center">
          <button @click="saveRodsCatalog" :disabled="!rodsDirty || rodsHasIssues || savingRods || !rods.length"
                  class="btn-secondary py-1.5 text-[10px] uppercase disabled:opacity-40 disabled:cursor-not-allowed">
            {{ savingRods ? 'Guardando…' : 'Guardar correcciones' }}
          </button>
          <button @click="currentStep = 5" :disabled="!rods.length"
                  class="btn-standard py-1.5 text-[10px] uppercase disabled:opacity-40 disabled:cursor-not-allowed"
                  :title="!rods.length ? 'Importa o añade al menos una varilla' : ''">
            Continuar a Marcación →
          </button>
        </div>
      </div>
    </div>

    <!-- PASO 5: MARCACION (GCPs) -->
    <div v-if="currentStep === 5" class="grid grid-cols-1 lg:grid-cols-4 gap-6">
       <div class="lg:col-span-3 card-standard overflow-hidden bg-slate-900 relative min-h-[600px]">
          <div class="absolute top-4 right-4 z-20 flex bg-black/60 backdrop-blur border border-white/20 rounded-full overflow-hidden shadow-xl">
            <button @click="mapView = false" :class="!mapView ? 'bg-blue-600 text-white' : 'text-slate-300 hover:bg-white/10'" class="px-3 py-1.5 text-[9px] font-bold uppercase transition-colors">Foto</button>
            <button @click="mapView = true" :class="mapView ? 'bg-blue-600 text-white' : 'text-slate-300 hover:bg-white/10'" class="px-3 py-1.5 text-[9px] font-bold uppercase transition-colors">Mapa</button>
          </div>

          <template v-if="!mapView">
            <img :src="imageUrl" @click="handleImageClick" class="absolute inset-0 w-full h-full object-contain cursor-crosshair select-none">

            <div v-for="(gcp, idx) in currentProfile.gcps" :key="idx"
                 class="absolute -translate-x-1/2 -translate-y-1/2"
                 :style="{ left: gcp.rel[0] + '%', top: gcp.rel[1] + '%' }">
              <div @click.stop="selectedGcpIdx = idx"
                   :class="selectedGcpIdx === idx ? 'bg-yellow-400 scale-150 ring-4 ring-white' : 'bg-blue-600 scale-100'"
                   class="w-4 h-4 rounded-full border-2 border-white shadow-lg cursor-pointer transition-all hover:scale-125 z-10 flex items-center justify-center">
                   <span class="text-[8px] font-bold text-white">{{ idx + 1 }}</span>
              </div>
            </div>
            <div class="absolute bottom-4 left-4 bg-black/60 text-white text-[10px] px-3 py-1.5 rounded-full font-bold uppercase tracking-widest backdrop-blur-sm border border-white/20 shadow-xl">Modo Marcación: Varillas GCP</div>
          </template>

          <div v-else class="absolute inset-0">
            <Map :geojsonData="gcpGeoJson" :fit-signal="mapFitSignal" />
            <div v-if="!gcpGeoJson.features.length" class="absolute inset-0 flex items-center justify-center pointer-events-none">
              <p class="bg-black/60 text-white text-[10px] font-bold uppercase tracking-widest px-4 py-2 rounded-full">Ninguna varilla con UTM válida todavía</p>
            </div>
            <div class="absolute bottom-4 left-4 bg-black/60 text-white text-[10px] px-3 py-1.5 rounded-full font-bold uppercase tracking-widest backdrop-blur-sm border border-white/20 shadow-xl z-[401]">Vista mapa: verificación UTM</div>
          </div>
       </div>

       <aside class="space-y-6">
          <div v-if="selectedGcpIdx !== null" class="card-standard border-blue-200 shadow-xl animate-fade-in">
            <div class="card-header bg-blue-600 text-white flex justify-between items-center py-2">
              <span class="text-[10px] font-bold uppercase tracking-widest">Editar Punto {{ selectedGcpIdx + 1 }}</span>
              <button @click="selectedGcpIdx = null" class="hover:bg-blue-700 rounded px-1">×</button>
            </div>
            <div class="p-4 space-y-4">
              <div v-if="rods.length" class="space-y-1">
                <label class="text-[10px] font-bold text-slate-500 uppercase">Varilla del catálogo</label>
                <select @change="assignRod($event.target.value)" class="w-full input-standard text-xs">
                  <option value="" selected disabled>Autocompletar desde catálogo…</option>
                  <option v-for="(rod, i) in rods" :key="i" :value="i">
                    {{ rod.label }} — {{ rod.utm[0].toFixed(1) }}, {{ rod.utm[1].toFixed(1) }}
                  </option>
                </select>
              </div>
              <div class="space-y-1">
                <label class="text-[10px] font-bold text-slate-500 uppercase">Etiqueta</label>
                <input v-model="currentProfile.gcps[selectedGcpIdx].label" class="w-full input-standard">
              </div>
              <div class="grid grid-cols-2 gap-2">
                <div class="space-y-1">
                  <label class="text-[10px] font-bold text-slate-500 uppercase">UTM X</label>
                  <input type="number" v-model.number="currentProfile.gcps[selectedGcpIdx].utm[0]" class="w-full input-standard font-mono text-xs">
                </div>
                <div class="space-y-1">
                  <label class="text-[10px] font-bold text-slate-500 uppercase">UTM Y</label>
                  <input type="number" v-model.number="currentProfile.gcps[selectedGcpIdx].utm[1]" class="w-full input-standard font-mono text-xs">
                </div>
              </div>
              <button @click="currentProfile.gcps.splice(selectedGcpIdx, 1); selectedGcpIdx = null; saveAnnotations()" class="w-full bg-red-50 text-red-600 text-[10px] font-bold py-2 rounded uppercase border border-red-100 hover:bg-red-100 transition-colors">Eliminar Punto</button>
            </div>
          </div>

          <div class="card-standard">
            <div class="card-header flex justify-between items-center">
              <span class="uppercase tracking-wider text-[10px]">Catálogo UTM ({{ rods.length }})</span>
              <button @click="currentStep = 4" class="text-blue-600 hover:underline text-[10px] font-bold uppercase">Editar catálogo</button>
            </div>
            <p v-if="!rods.length" class="p-3 text-[10px] text-slate-400 leading-relaxed">
              Todavía no hay varillas topografiadas. Ve al paso <strong>Catálogo</strong> para importar el CSV o añadirlas a mano.
            </p>
            <p v-else class="p-3 text-[10px] text-slate-500">
              {{ rods.length }} varillas disponibles para autocompletar al editar un punto.
            </p>
          </div>

          <div class="card-standard flex flex-col h-[420px]">
            <div class="card-header uppercase tracking-wider text-[10px]">Listado de Varillas ({{ currentProfile.gcps.length }})</div>
            <div class="flex-1 overflow-y-auto divide-y divide-slate-100 custom-scrollbar">
               <div v-for="(gcp, idx) in currentProfile.gcps" :key="idx"
                    @click="selectedGcpIdx = idx"
                    class="p-3 text-xs flex justify-between items-center cursor-pointer hover:bg-slate-50 transition-colors"
                    :class="selectedGcpIdx === idx ? 'bg-blue-50 border-l-4 border-blue-600' : ''">
                  <div>
                    <p class="font-bold text-slate-700 uppercase text-[10px]">{{ gcp.label }}</p>
                    <p class="text-[9px] text-slate-400 font-mono">{{ gcp.utm[0].toFixed(1) }}, {{ gcp.utm[1].toFixed(1) }}</p>
                  </div>
                  <span class="text-[9px] font-bold text-slate-300">#{{ idx + 1 }}</span>
               </div>
            </div>
            <div class="p-4 border-t border-slate-100 bg-slate-50 space-y-2">
              <button @click="calculateHomography()" :disabled="currentProfile.gcps.length < 4 || calculating"
                      class="btn-standard w-full uppercase text-xs">
                {{ calculating ? 'Calculando...' : 'Calcular homografía' }}
              </button>
              <p v-if="currentProfile.gcps.length < 4" class="text-[9px] text-slate-400 text-center uppercase">
                Faltan {{ 4 - currentProfile.gcps.length }} varillas (mínimo 4)
              </p>
            </div>
          </div>
       </aside>
    </div>

    <!-- PASO 6: VALIDACION (análisis de error de reproyección por varilla) -->
    <div v-if="currentStep === 6" class="space-y-6">
      <div v-if="!calibResult" class="card-standard p-16 text-center space-y-4 min-h-[400px] flex flex-col items-center justify-center">
        <svg class="w-12 h-12 text-slate-200" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" stroke-width="1.5"/></svg>
        <p class="text-sm font-bold uppercase tracking-widest text-slate-400">Esta imagen aún no tiene calibración calculada</p>
        <button @click="currentStep = 5" class="btn-standard uppercase text-xs">Ir a Marcación</button>
      </div>

      <template v-else>
        <div class="flex items-center justify-between flex-wrap gap-2">
          <div :class="calibOk ? 'bg-emerald-100 text-emerald-800 border-emerald-200' : 'bg-red-100 text-red-800 border-red-200'"
               class="inline-flex items-center space-x-2 px-5 py-1.5 rounded-full text-xs font-bold uppercase tracking-widest border shadow-sm">
            <svg v-if="!calibOk" class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M12 9v2m0 4h.01M5.07 19h13.86c1.54 0 2.5-1.67 1.73-3L13.73 4c-.77-1.33-2.69-1.33-3.46 0L3.34 16c-.77 1.33.19 3 1.73 3z" stroke-width="2"/></svg>
            <span>{{ calibOk ? 'Calibración dentro de tolerancia' : `${flaggedCount} varilla(s) superan el umbral` }}</span>
          </div>
          <p class="text-[10px] text-slate-400 font-mono">{{ calibResult.image }} · {{ formatTs(calibResult.date) }}</p>
        </div>

        <div class="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div class="card-standard p-4">
            <p class="text-[9px] font-bold text-slate-400 uppercase tracking-widest mb-1">RMSE reproyección</p>
            <p class="text-xl font-bold font-mono" :class="calibOk ? 'text-slate-900' : 'text-red-600'">{{ calibResult.rmse_px?.toFixed(2) }} px</p>
          </div>
          <div class="card-standard p-4">
            <p class="text-[9px] font-bold text-slate-400 uppercase tracking-widest mb-1">RMSE terreno</p>
            <p class="text-xl font-bold text-slate-900 font-mono">{{ calibResult.rmse_m?.toFixed(3) }} m</p>
          </div>
          <div class="card-standard p-4">
            <p class="text-[9px] font-bold text-slate-400 uppercase tracking-widest mb-1">Varillas usadas</p>
            <p class="text-xl font-bold text-slate-900 font-mono">{{ calibResult.gcps_used }} / {{ calibResult.residuals?.length }}</p>
          </div>
          <div class="card-standard p-4">
            <p class="text-[9px] font-bold text-slate-400 uppercase tracking-widest mb-1">Estado · EPSG:25830</p>
            <div class="flex items-center space-x-2">
              <div :class="calibOk ? 'bg-emerald-500' : 'bg-red-500'" class="w-2 h-2 rounded-full animate-pulse"></div>
              <p class="text-sm font-bold uppercase" :class="calibOk ? 'text-slate-700' : 'text-red-600'">{{ calibOk ? 'Óptimo' : 'Revisar' }}</p>
            </div>
          </div>
        </div>

        <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <!-- Tabla de residuos por varilla -->
          <div class="lg:col-span-2 card-standard overflow-hidden flex flex-col">
            <div class="card-header flex justify-between items-center">
              <span>Error de reproyección por varilla</span>
              <div class="flex items-center space-x-2">
                <label class="text-[9px] text-slate-400 uppercase font-bold">Umbral (px)</label>
                <input type="number" step="0.1" min="0.1" v-model.number="threshold"
                       class="input-standard w-20 py-1 text-xs font-mono text-right">
              </div>
            </div>
            <div class="overflow-x-auto flex-1">
              <table class="w-full text-left text-sm">
                <thead class="bg-slate-50/60 text-slate-500 font-semibold border-b border-slate-100">
                  <tr>
                    <th class="px-4 py-3 uppercase tracking-widest text-[10px]">#</th>
                    <th class="px-4 py-3 uppercase tracking-widest text-[10px]">Varilla</th>
                    <th class="px-4 py-3 uppercase tracking-widest text-[10px] text-right">Error (px)</th>
                    <th class="px-4 py-3 uppercase tracking-widest text-[10px] text-right">Error (m)</th>
                    <th class="px-4 py-3 uppercase tracking-widest text-[10px] text-center">Estado</th>
                    <th class="px-4 py-3 uppercase tracking-widest text-[10px] text-center">Excluir</th>
                  </tr>
                </thead>
                <tbody class="divide-y divide-slate-100">
                  <tr v-for="r in calibResult.residuals" :key="r.idx"
                      :class="r.excluded ? 'opacity-40 bg-slate-50' : (r.above_threshold ? 'bg-red-50' : 'hover:bg-slate-50')"
                      class="transition-colors text-slate-700">
                    <td class="px-4 py-3 text-[10px] font-bold text-slate-400">{{ r.idx + 1 }}</td>
                    <td class="px-4 py-3 text-[11px] font-bold uppercase">{{ r.label }}</td>
                    <td class="px-4 py-3 text-right font-mono text-[11px]"
                        :class="r.above_threshold ? 'text-red-600 font-bold' : 'text-slate-600'">
                      {{ r.error_px.toFixed(2) }}
                    </td>
                    <td class="px-4 py-3 text-right font-mono text-[11px] text-slate-500">{{ r.error_m.toFixed(3) }}</td>
                    <td class="px-4 py-3 text-center">
                      <span v-if="r.excluded" class="px-2 py-0.5 rounded text-[9px] font-bold uppercase bg-slate-100 text-slate-500 border border-slate-200">Excluida</span>
                      <span v-else-if="r.above_threshold" class="px-2 py-0.5 rounded text-[9px] font-bold uppercase bg-red-100 text-red-700 border border-red-200">⚠ Sobre umbral</span>
                      <span v-else class="px-2 py-0.5 rounded text-[9px] font-bold uppercase bg-emerald-100 text-emerald-700 border border-emerald-200">OK</span>
                    </td>
                    <td class="px-4 py-3 text-center">
                      <input type="checkbox" :checked="excludedIdx.includes(r.idx)" @change="toggleExcluded(r.idx)"
                             class="w-3.5 h-3.5 accent-blue-600 cursor-pointer">
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
            <div class="p-4 border-t border-slate-100 bg-slate-50 flex justify-between items-center">
              <button v-if="flaggedCount" @click="excludeFlagged" :disabled="calculating"
                      class="text-red-600 hover:underline text-[10px] font-bold uppercase">
                Excluir {{ flaggedCount }} sobre umbral y recalcular
              </button>
              <span v-else class="text-[10px] text-slate-400 uppercase font-bold">Todas las varillas activas dentro de tolerancia</span>
              <button @click="recalculate" :disabled="calculating" class="btn-standard py-1.5 text-[10px] uppercase">
                {{ calculating ? 'Recalculando…' : 'Recalcular' }}
              </button>
            </div>
          </div>

          <!-- Vista rectificada + acciones -->
          <div class="space-y-6">
            <div class="card-standard overflow-hidden">
              <div class="card-header uppercase tracking-wider text-[10px]">Vista rectificada (UTM)</div>
              <div class="aspect-video bg-slate-900 relative">
                <img v-if="rectifiedUrl && !rectifiedFailed" :src="rectifiedUrl" @error="rectifiedFailed = true"
                     class="w-full h-full object-contain">
                <div v-else class="w-full h-full flex items-center justify-center text-slate-500 text-[10px] font-bold uppercase tracking-widest">
                  Vista previa no disponible
                </div>
              </div>
            </div>
            <div class="card-standard p-4 space-y-2">
              <button @click="currentStep = 5" class="btn-secondary w-full text-xs uppercase">Reajustar Puntos</button>
              <button @click="currentStep = 1; fetchCameras()" class="btn-standard w-full text-xs uppercase">Finalizar Proceso</button>
            </div>
          </div>
        </div>
      </template>
    </div>
  </div>
</template>

<style scoped>
.custom-scrollbar::-webkit-scrollbar { width: 4px; }
.custom-scrollbar::-webkit-scrollbar-track { background: transparent; }
.custom-scrollbar::-webkit-scrollbar-thumb { background: #cbd5e1; border-radius: 10px; }

.animate-fade-in { animation: fadeIn 0.3s ease-out; }
@keyframes fadeIn { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }

.cursor-crosshair { cursor: crosshair; }
</style>
