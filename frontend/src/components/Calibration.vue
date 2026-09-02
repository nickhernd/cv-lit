<script setup>
import { ref, onMounted, onBeforeUnmount, computed, watch } from 'vue'
import { API_BASE } from '../api.js'
import BatchAlignment from './BatchAlignment.vue'
import Map from './Map.vue'

const props = defineProps({
  initialCamId: { type: Number, default: null }
})

const emit = defineEmits(['notify'])
const API = API_BASE

const currentStep = ref(1)
const selectedCamId = ref(props.initialCamId)
const cameras = ref([])
const availableImages = ref([])
const selectedImage = ref('')
const currentProfile = ref({ gcps: [], reference_image: null })
const loading = ref(false)
const saving = ref(false)
const calculating = ref(false)

// Calibración por imagen: resultado del último cálculo (residuos por varilla)
const calibResult = ref(null)
const excludedIdx = ref([])
// Umbral por varilla individual (px) — solo una ayuda para detectar de un
// vistazo qué punto concreto podría estar mal marcado. Con fotos de varios
// miles de píxeles de ancho, exigir <1px por varilla marcada a mano es
// prácticamente inalcanzable aunque la calibración sea buena — el criterio
// real de aceptación es el RMSE en metros (ver calibOk más abajo).
const threshold = ref(5.0)

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
// Densidad visual del paso Marcación: la dropzone de importación y el panel de
// sesiones importadas ocupan mucho espacio permanentemente aunque no haya nada
// pendiente que hacer con ellos. showImportDropzone empieza oculto (se revela
// con un botón compacto); importGroupsExpanded se auto-fuerza a true mientras
// quede trabajo real por revisar (vía importGroupsNeedAttention más abajo).
const showImportDropzone = ref(false)
const importGroupsExpanded = ref(false)
// "Importadas" (guardadas como anotación) no es lo mismo que "confirmadas"
// (píxel exacto fijado por el usuario) — un grupo con savedAt puede seguir
// teniendo varillas pendientes en pendingGcps hasta que se confirman una a
// una con la lupa. Sin este chequeo, el resumen colapsado podía decir
// "confirmadas" mientras todavía quedaban varillas en ámbar por revisar.
const importGroupsNeedAttention = computed(() =>
  unmatchedGroups.value.length > 0 ||
  imageGroups.value.some(g => !g.savedAt || groupHasIssues(g.points)) ||
  pendingGcps.value.length > 0
)

// Paso 5 (Marcación): la imagen se pinta con object-contain, así que si su
// proporción no coincide con la del panel quedan bandas (letterbox) a los
// lados o arriba/abajo. Guardamos el tamaño real renderizado de la imagen
// (no el del contenedor) para dibujar cada punto sobre su píxel real y para
// recalcular en cuanto cambie el tamaño de la ventana — si no, los puntos se
// quedan flotando separados de la imagen en vez de moverse con ella.
const markImgRef = ref(null)
const imgNatural = ref({ width: 0, height: 0 })
const stageSize = ref({ width: 0, height: 0 })
let stageResizeObserver = null

// Alineación de la imagen activa (paso 5): si esta imagen viene del módulo de
// Alineación, currentAlignH guarda la H (captura original -> imagen alineada)
// que se está mostrando. Se usa para: (a) transformar el píxel "crudo" de las
// varillas importadas de un CSV de campo antes de guardarlas, y (b) dejar
// constancia en cada punto de con qué H se marcó, para poder reproyectarlo
// automáticamente si la imagen se vuelve a alinear más adelante.
const currentAlignInfo = ref(null)  // null = sin alinear (H identidad implícita)

async function fetchAlignmentInfo() {
  currentAlignInfo.value = null
  if (!selectedCamId.value || !selectedImage.value) return
  try {
    const res = await fetch(`${API}/api/cameras/${selectedCamId.value}/images/${selectedImage.value}/alignment`)
    const data = await res.json()
    currentAlignInfo.value = data.aligned ? data : null
  } catch (err) { console.error(err) }
}

// Lupa de precisión (paso 5): recorte ampliado alrededor del cursor para poder
// fijar el píxel exacto de una varilla en fotos de varios miles de píxeles,
// donde acertar a ojo sobre la imagen a escala reducida es imposible.
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

  // Cruz roja = posición del CURSOR ahora mismo (siempre en el centro, el
  // recorte está centrado en él).
  ctx.strokeStyle = 'rgba(239, 68, 68, 0.9)'
  ctx.lineWidth = 1
  ctx.beginPath()
  ctx.moveTo(LOUPE_SIZE / 2, 0); ctx.lineTo(LOUPE_SIZE / 2, LOUPE_SIZE)
  ctx.moveTo(0, LOUPE_SIZE / 2); ctx.lineTo(LOUPE_SIZE, LOUPE_SIZE / 2)
  ctx.stroke()

  // Cruz verde = posición EXACTA donde está fijado el marcador de la varilla
  // seleccionada (si cae dentro de lo que se ve ahora en la lupa). Deja
  // comparar de un vistazo, ya con el zoom aplicado, dónde está el cursor
  // frente a dónde quedó puesto el punto realmente — sin esto solo se veía
  // el cursor, nunca la posición ya fijada del marcador.
  const gcp = selectedGcpIdx.value !== null ? currentProfile.value.gcps[selectedGcpIdx.value] : null
  if (gcp) {
    const gx = (gcp.pixel[0] - sx) * zoomFactor.value
    const gy = (gcp.pixel[1] - sy) * zoomFactor.value
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

// Convierte un evento de ratón sobre la foto en (a) coordenadas de píxel
// nativas de la imagen y (b) porcentaje relativo — la misma lógica que
// necesita tanto el click (fijar un punto) como el hover (mover la lupa).
function eventToImagePixel(event) {
  const r = imageRect.value
  if (!r.width || !r.height) return null
  const box = event.currentTarget.getBoundingClientRect()
  const x = event.clientX - box.left - r.offsetX
  const y = event.clientY - box.top - r.offsetY
  if (x < 0 || y < 0 || x > r.width || y > r.height) return null
  const relX = (x / r.width) * 100
  const relY = (y / r.height) * 100
  return {
    relX, relY,
    pixelX: (relX / 100) * imgNatural.value.width,
    pixelY: (relY / 100) * imgNatural.value.height,
  }
}

function onStageMouseMove(event) {
  if (currentStep.value !== 5) return
  const p = eventToImagePixel(event)
  if (!p) { loupeVisible.value = false; return }
  loupeNaturalPos = { x: p.pixelX, y: p.pixelY }
  loupeVisible.value = true
  // Posicionar la lupa cerca del cursor pero sin taparlo, y sin salirse del panel.
  const stageBox = event.currentTarget.getBoundingClientRect()
  let left = event.clientX - stageBox.left + 24
  let top = event.clientY - stageBox.top - LOUPE_SIZE - 24
  if (left + LOUPE_SIZE > stageBox.width) left = event.clientX - stageBox.left - LOUPE_SIZE - 24
  if (top < 0) top = event.clientY - stageBox.top + 24
  loupeScreenPos.value = { left, top }
  requestAnimationFrame(drawLoupe)
}

function onStageMouseLeave() { loupeVisible.value = false }

function updateStageSize() {
  if (!markImgRef.value) return
  stageSize.value = { width: markImgRef.value.clientWidth, height: markImgRef.value.clientHeight }
}

function onMarkImageLoad(e) {
  imgNatural.value = { width: e.target.naturalWidth, height: e.target.naturalHeight }
  updateStageSize()
}

// Rectángulo que ocupa REALMENTE la imagen dentro de su contenedor (con
// object-contain puede haber bandas). Clicks, píxeles guardados y posición de
// los puntos se calculan siempre contra este rectángulo, nunca contra el
// contenedor completo.
const imageRect = computed(() => {
  const { width: natW, height: natH } = imgNatural.value
  const { width: boxW, height: boxH } = stageSize.value
  if (!natW || !natH || !boxW || !boxH) return { offsetX: 0, offsetY: 0, width: 0, height: 0 }
  const scale = Math.min(boxW / natW, boxH / natH)
  const width = natW * scale
  const height = natH * scale
  return { offsetX: (boxW - width) / 2, offsetY: (boxH - height) / 2, width, height }
})

function gcpMarkerStyle(gcp) {
  const r = imageRect.value
  if (!r.width || !r.height) return { left: gcp.rel[0] + '%', top: gcp.rel[1] + '%' }
  return {
    left: (r.offsetX + (gcp.rel[0] / 100) * r.width) + 'px',
    top: (r.offsetY + (gcp.rel[1] / 100) * r.height) + 'px'
  }
}

// El <img> del paso 5 se monta/desmonta al cambiar de paso (v-if), así que
// el ResizeObserver se (re)conecta cada vez que aparece el elemento real.
watch(markImgRef, (el) => {
  if (stageResizeObserver) { stageResizeObserver.disconnect(); stageResizeObserver = null }
  if (el) {
    updateStageSize()
    stageResizeObserver = new ResizeObserver(updateStageSize)
    stageResizeObserver.observe(el)
  }
})

onBeforeUnmount(() => {
  if (stageResizeObserver) stageResizeObserver.disconnect()
})

// Vista de mapa en el paso de Marcación: sitúa las varillas marcadas (UTM)
// sobre un mapa real para comprobar de un vistazo que las coordenadas caen
// donde tienen que caer, en vez de fiarse solo de la tabla de números.
// 'both' muestra foto y mapa en paralelo (por defecto): la selección de una
// varilla ya se sincroniza entre los dos (selectedGcpIdx), así que verlos a
// la vez es estrictamente mejor que alternar — 'photo'/'map' quedan para
// cuando se necesita el panel entero para un solo lado (pantallas estrechas).
const viewMode = ref('both')
const mapFitSignal = ref(0)
const gcpGeoJson = computed(() => ({
  type: 'FeatureCollection',
  // idx conserva la posición ORIGINAL en currentProfile.gcps (no la posición
  // tras el filtro) — si no, en cuanto hay una varilla sin UTM válida el
  // número mostrado en el mapa deja de corresponder con el de la lista/foto.
  features: (currentProfile.value.gcps || [])
    .map((g, origIdx) => ({ g, origIdx }))
    .filter(({ g }) => Array.isArray(g.utm) && g.utm.length === 2 && g.utm.every(v => v !== null && v !== '' && !Number.isNaN(Number(v))))
    .map(({ g, origIdx }) => ({
      type: 'Feature',
      geometry: { type: 'Point', coordinates: [Number(g.utm[0]), Number(g.utm[1])] },
      properties: { label: g.label, idx: origIdx }
    }))
}))
watch(viewMode, (v) => { if (v !== 'photo') mapFitSignal.value++ })

const steps = [
  { id: 1, name: 'Vista general', desc: 'Perfiles de calibración' },
  { id: 2, name: 'Imágenes', desc: 'Gestionar Fotogramas' },
  { id: 3, name: 'Alineación', desc: 'Configurar Referencia' },
  { id: 4, name: 'Catálogo', desc: 'Importar y Corregir Varillas' },
  { id: 5, name: 'Marcación', desc: 'Etiquetado Varillas' },
  { id: 6, name: 'Cálculo', desc: 'Homografía y Residuos' },
  { id: 7, name: 'Validación', desc: 'Perfil Final' },
]

// API Helpers
async function fetchCameras() {
  try {
    const res = await fetch(`${API}/api/cameras`)
    if (!res.ok) throw new Error('HTTP ' + res.status)
    cameras.value = await res.json()
  } catch (err) { emit('notify', 'Error al cargar estaciones', 'error') }
}

function editCamera(idx) {
  selectedCamId.value = idx
  currentStep.value = 2
}

function viewCamera(idx) {
  selectedCamId.value = idx
  currentStep.value = 7
}

const calibratedCount = computed(() => cameras.value.filter(c => c.calibrated).length)
const avgRmse = computed(() => {
  const vals = cameras.value.filter(c => c.rmse_m != null).map(c => c.rmse_m)
  if (!vals.length) return '—'
  return (vals.reduce((a, b) => a + b, 0) / vals.length).toFixed(2) + ' m'
})
const avgMae = computed(() => {
  const vals = cameras.value.filter(c => c.mae_m != null).map(c => c.mae_m)
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
    const res = await fetch(`${API}/api/cameras/${camSnapshot}/images`)
    if (!res.ok) throw new Error('HTTP ' + res.status)
    const imgs = await res.json()
    // Descartar la respuesta si el usuario ya cambió de cámara mientras esperábamos
    if (camSnapshot !== selectedCamId.value) return
    availableImages.value = imgs
    if (imgs.length > 0) selectedImage.value = imgs[0].filename
  } catch (err) { emit('notify', 'Error al cargar imágenes de la cámara', 'error') }
}

async function fetchProfile() {
  if (!selectedCamId.value) return
  loading.value = true
  try {
    const res = await fetch(`${API}/api/cameras/${selectedCamId.value}/profile`)
    currentProfile.value = await res.json()
    if (!currentProfile.value.gcps) currentProfile.value.gcps = []
  } catch (err) { console.error(err) }
  finally { loading.value = false }
}

async function fetchRods() {
  if (!selectedCamId.value) return
  try {
    const res = await fetch(`${API}/api/cameras/${selectedCamId.value}/rods`)
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
    const res = await fetch(`${API}/api/cameras/${selectedCamId.value}/import-rods`, {
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
      // El CSV de campo se revisa y confirma en Marcación, no aquí — si se
      // importó desde otro paso, saltamos directos a esa revisión.
      currentStep.value = 5
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
    img.src = `${API}/api/cameras/${selectedCamId.value}/image?file=${filename}`
  })
}

// El píxel de un CSV de campo se midió sobre la captura ORIGINAL de esa sesión.
// Si esa imagen ya tiene una alineación confirmada, la que se va a mostrar y
// usar de aquí en adelante es la versión alineada — hay que llevar el píxel a
// ese espacio con la misma H, si no la varilla queda marcada sobre otro sitio.
function applyHomography(H, [x, y]) {
  if (!H) return [x, y]
  const [h0, h1, h2, h3, h4, h5, h6, h7, h8] = H
  const w = h6 * x + h7 * y + h8
  return [(h0 * x + h1 * y + h2) / w, (h3 * x + h4 * y + h5) / w]
}

async function fetchAlignmentFor(filename) {
  try {
    const res = await fetch(`${API}/api/cameras/${selectedCamId.value}/images/${filename}/alignment`)
    const data = await res.json()
    return data.aligned ? data.H : null
  } catch (err) { return null }
}

// Persiste los puntos de un grupo como anotaciones de su imagen (misma ruta
// que usa la marcación manual), calculando "rel" a partir del tamaño real
// de la imagen para que el punto se pinte en el sitio correcto en el paso 5.
// El píxel del CSV es solo una APROXIMACIÓN: se guarda con confirmed=false y
// hay que confirmarlo con la lupa del paso Marcación antes de que cuente para
// calcular la homografía.
async function saveImageGroup(group, filename) {
  if (!filename || groupHasIssues(group.points)) return
  group.saving = true
  try {
    const [{ width, height }, alignedH] = await Promise.all([
      loadImageSize(filename),
      fetchAlignmentFor(filename),
    ])
    const points = group.points.map(p => {
      const rawPixel = p.pixel.map(Number)
      const pixel = applyHomography(alignedH, rawPixel)
      return {
        pixel,
        utm: p.utm.map(Number),
        label: p.label,
        type: 'calib',
        rel: [(pixel[0] / width) * 100, (pixel[1] / height) * 100],
        confirmed: false,
        aligned_H: alignedH,
        ...(p.notes ? { notes: p.notes } : {})
      }
    })
    const res = await fetch(`${API}/api/cameras/${selectedCamId.value}/images/${filename}/annotations`, {
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
    const res = await fetch(`${API}/api/cameras/${selectedCamId.value}/rods`, {
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
  gcp.z = rod.z ?? null
  saveAnnotations()
}

// Calcula la homografía de la imagen activa con sus varillas marcadas y guarda
// el resultado (residuos por varilla, RMSE, umbral) para el paso de validación.
async function calculateHomography(excluded = []) {
  if (!selectedCamId.value || !selectedImage.value) return
  calculating.value = true
  try {
    const res = await fetch(`${API}/api/cameras/${selectedCamId.value}/calculate-homography`, {
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
    // El aviso usa el mismo criterio que calibOk (RMSE terreno vs. objetivo),
    // no el recuento de varillas "sobre umbral" en píxeles — ese umbral es
    // solo una ayuda de diagnóstico por varilla (ver nota en la tabla de
    // Cálculo) y no debería disparar un toast de error por sí solo.
    const rmseOk = data.rmse_m <= (data.rmse_good_m ?? 1.5)
    if (!rmseOk) {
      emit('notify', `Homografía calculada. RMSE terreno ${data.rmse_m?.toFixed(2)} m — por encima del objetivo`, 'error')
    } else if (data.geometry_warning) {
      emit('notify', 'Homografía calculada, pero la geometría de las varillas es inestable — revisa el aviso en Cálculo', 'error')
    } else {
      emit('notify', `Homografía calculada. RMSE terreno ${data.rmse_m?.toFixed(2)} m`, 'success')
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
    const res = await fetch(`${API}/api/cameras/${selectedCamId.value}/profile`)
    const profile = await res.json()
    const img = profile.calibrated_image || profile.reference_image
    if (!img || !profile.H) return
    const annRes = await fetch(`${API}/api/cameras/${selectedCamId.value}/images/${img}/annotations`)
    const ann = await annRes.json()
    if (ann.calibration) {
      calibResult.value = ann.calibration
      excludedIdx.value = [...(ann.calibration.excluded || [])]
      threshold.value = ann.calibration.threshold_px ?? threshold.value
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
// El criterio real de aceptación es el RMSE en metros frente al umbral que
// ya usa el resto del sistema (rmse_good_m, ver calculate_homography en el
// backend) — NO que todas las varillas individuales bajen de threshold_px.
// Ese umbral por varilla es un puntero para localizar posibles misclicks,
// pero exigir que TODAS lo cumplan hacía que casi cualquier calibración
// razonable apareciera como "Revisar" solo por una varilla límite.
const calibOk = computed(() =>
  !!calibResult.value && calibResult.value.rmse_m <= (calibResult.value.rmse_good_m ?? 1.5)
)

// ── Validación: histograma de residuos + mapa de cobertura/reproyección ─────
// Dimensiones naturales de la imagen mostrada en el mapa de cobertura — propio
// de Validación (no comparte imgNatural con la lupa de Marcación, que solo se
// rellena si se ha visitado ese paso en esta sesión).
const coverageImgNatural = ref({ width: 0, height: 0 })
function onCoverageImgLoad(e) {
  coverageImgNatural.value = { width: e.target.naturalWidth, height: e.target.naturalHeight }
}

function residualColor(r) {
  if (r.excluded || r.pending) return '#94a3b8'   // slate-400
  if (r.above_threshold) return '#d97706'         // amber-600
  return '#059669'                                // emerald-600
}

// Barras del histograma de residuos (m), en coordenadas de un viewBox fijo —
// altura proporcional al error máximo del lote para que las barras siempre
// aprovechen el alto disponible.
const HIST_W = 600, HIST_H = 140, HIST_PAD = 24
const residualBars = computed(() => {
  const items = calibResult.value?.residuals || []
  if (!items.length) return []
  const maxErr = Math.max(...items.map(r => r.error_m), 0.001)
  const n = items.length
  const barGap = 6
  const barW = Math.max(4, (HIST_W - HIST_PAD * 2 - barGap * (n - 1)) / n)
  const usableH = HIST_H - HIST_PAD * 2
  return items.map((r, i) => {
    const h = Math.max(2, (r.error_m / maxErr) * usableH)
    return {
      x: HIST_PAD + i * (barW + barGap),
      y: HIST_H - HIST_PAD - h,
      width: barW,
      height: h,
      color: residualColor(r),
      label: r.label,
      error_m: r.error_m,
    }
  })
})

// ── Validación: metadatos de perfil + exportables (JSON / PDF) ──────────────
const profileMeta = ref({ profile_name: '', operator: '', notes: '' })
const savingMeta = ref(false)
watch(currentProfile, (p) => {
  profileMeta.value = {
    profile_name: p?.profile_name || '',
    operator: p?.operator || '',
    notes: p?.notes || '',
  }
}, { immediate: true })

async function saveProfileMetadata() {
  if (!selectedCamId.value) return
  savingMeta.value = true
  try {
    const res = await fetch(`${API}/api/cameras/${selectedCamId.value}/profile-metadata`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(profileMeta.value),
    })
    if (!res.ok) throw new Error()
    Object.assign(currentProfile.value, profileMeta.value)
    emit('notify', 'Metadatos de perfil guardados', 'success')
  } catch (err) {
    emit('notify', 'Error al guardar los metadatos del perfil', 'error')
  } finally { savingMeta.value = false }
}

function downloadCalibrationJson() {
  if (!calibResult.value) return
  const camInfo = cameras.value.find(c => c.idx === selectedCamId.value)
  const payload = {
    camera: { id: selectedCamId.value, name: camInfo?.name, serial: camInfo?.serial },
    profile: profileMeta.value,
    calibration: calibResult.value,
    exported_at: new Date().toISOString(),
  }
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `cv-lit_cam${selectedCamId.value}_calibracion.json`
  a.click()
  URL.revokeObjectURL(url)
}

function downloadCalibrationPdf() {
  if (!selectedCamId.value) return
  window.open(`${API}/api/cameras/${selectedCamId.value}/calibration-report.pdf`, '_blank')
}

function csvEscape(v) {
  const s = v === null || v === undefined ? '' : String(v)
  return /[";\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s
}

// CSV de las varillas con toda la info por punto (píxel/UTM medidos y
// predichos por la homografía, error, inlier) — para poder llevarlas a
// Excel y contrastarlas contra el CSV/Excel de origen de las varillas.
// Separador ';' (no ',') porque Excel en es-ES usa la coma como separador
// decimal y con ',' como delimitador todo cae en una sola columna.
function downloadCalibrationCsv() {
  if (!calibResult.value) return
  const rows = calibResult.value.residuals || []
  const headers = [
    'Varilla', 'Pixel X', 'Pixel Y', 'UTM X', 'UTM Y',
    'Pixel X predicho', 'Pixel Y predicho', 'UTM X predicho', 'UTM Y predicho',
    'Error (px)', 'Error (m)', 'Inlier RANSAC', 'Excluida', 'Pendiente',
  ]
  const lines = [headers.join(';')]
  for (const r of rows) {
    lines.push([
      r.label,
      r.pixel?.[0], r.pixel?.[1],
      r.utm?.[0], r.utm?.[1],
      r.pixel_predicted?.[0], r.pixel_predicted?.[1],
      r.utm_predicted?.[0], r.utm_predicted?.[1],
      r.error_px, r.error_m,
      r.inlier === null ? '—' : (r.inlier ? 'Sí' : 'No'),
      r.excluded ? 'Sí' : 'No',
      r.pending ? 'Sí' : 'No',
    ].map(csvEscape).join(';'))
  }
  // BOM UTF-8 para que Excel detecte bien la codificación (tildes/ñ) al abrir.
  const blob = new Blob(['﻿' + lines.join('\r\n')], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `cv-lit_cam${selectedCamId.value}_varillas.csv`
  a.click()
  URL.revokeObjectURL(url)
}

async function fetchImageAnnotations() {
  if (!selectedCamId.value || !selectedImage.value) return
  try {
    const res = await fetch(`${API}/api/cameras/${selectedCamId.value}/images/${selectedImage.value}/annotations`)
    const data = await res.json()
    currentProfile.value.gcps = data.points || []
    // La calibración es por imagen (§ memoria cap. 4) — mantener calibResult
    // sincronizado con selectedImage permite pinchar entre imágenes en el
    // paso Cálculo y ver el resultado de cada una sin volver a Marcación.
    // null si esta imagen concreta aún no tiene homografía calculada.
    calibResult.value = data.calibration || null
    if (data.calibration) {
      excludedIdx.value = [...(data.calibration.excluded || [])]
      threshold.value = data.calibration.threshold_px ?? threshold.value
    } else {
      excludedIdx.value = []
    }
  } catch (err) { console.error(err) }
}

async function saveAnnotations() {
  if (!selectedCamId.value || !selectedImage.value) return
  saving.value = true
  try {
    await fetch(`${API}/api/cameras/${selectedCamId.value}/images/${selectedImage.value}/annotations`, {
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
    const res = await fetch(`${API}/api/cameras/${selectedCamId.value}/set-reference?filename=${filename}`, {
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
    const res = await fetch(`${API}/api/cameras/${selectedCamId.value}/images/${filename}`, {
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
    const res = await fetch(`${API}/api/cameras/${selectedCamId.value}/upload-images`, {
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
  return `${API}/api/cameras/${selectedCamId.value}/image?file=${selectedImage.value}&t=${Date.now()}`
})

// Handlers
// Idx del punto recién creado por el propio flujo de "click para añadir" —
// se auto-selecciona para poder rellenar su UTM al momento, pero un click
// siguiente debe seguir añadiendo puntos nuevos, no reposicionar ese. Solo
// cuando el usuario vuelve a seleccionar explícitamente un punto ya existente
// (marcador, lista o mapa) un click sobre la foto pasa a reposicionarlo — así
// se puede corregir un punto mal colocado sin salir del modo "click = mover".
const justCreatedIdx = ref(null)

// Último reposicionamiento (confirmación de pendiente o corrección de un punto
// ya existente): guarda el estado ANTERIOR para poder deshacerlo con un click
// si el usuario acierta mal sobre la foto. Solo un nivel — se pierde en cuanto
// cambias de punto seleccionado o de imagen, para no arrastrar confusión.
const lastReposition = ref(null)

// Volver a marcar el mismo punto que ya está seleccionado lo deselecciona —
// si no, se queda "enganchado" en modo reposicionar indefinidamente y un
// click posterior en la foto (para otra cosa) lo movería sin querer.
function selectGcp(idx) {
  justCreatedIdx.value = null
  const next = selectedGcpIdx.value === idx ? null : idx
  if (lastReposition.value && lastReposition.value.idx !== next) lastReposition.value = null
  selectedGcpIdx.value = next
}

// Click directo sobre el MARCADOR de una varilla en la foto (a diferencia de
// selectGcp, que se usa desde las listas del lateral). Si la varilla está
// pendiente de confirmar, clicar justo encima significa "sí, está bien puesta
// aquí" — antes ese click lo capturaba el propio marcador (@click.stop) y solo
// alternaba la selección sin confirmar nunca nada. Si ya está confirmada,
// mantiene el comportamiento normal de selección.
function handleMarkerClick(idx) {
  const gcp = currentProfile.value.gcps[idx]
  if (gcp && gcp.confirmed === false) {
    lastReposition.value = {
      idx,
      pixel: [...gcp.pixel],
      rel: [...gcp.rel],
      confirmed: gcp.confirmed,
      aligned_H: gcp.aligned_H,
      reprojected_at: gcp.reprojected_at,
    }
    gcp.confirmed = true
    gcp.reprojected_at = null
    gcp.aligned_H = currentAlignInfo.value?.H || gcp.aligned_H
    // justCreatedIdx = idx (no null): un click siguiente en la foto debe
    // seguir añadiendo varillas nuevas, no reposicionar esta que se acaba
    // de confirmar — si no, el gesto más natural después de confirmar
    // (clicar el siguiente punto) desplazaba silenciosamente el que
    // acabábamos de fijar. Mismo criterio que ya usa handleImageClick al
    // crear un punto nuevo.
    justCreatedIdx.value = idx
    selectedGcpIdx.value = idx
    saveAnnotations()
    return
  }
  selectGcp(idx)
}

function undoReposition() {
  const la = lastReposition.value
  if (!la) return
  const gcp = currentProfile.value.gcps[la.idx]
  if (!gcp) return
  gcp.pixel = la.pixel
  gcp.rel = la.rel
  gcp.confirmed = la.confirmed
  gcp.aligned_H = la.aligned_H
  gcp.reprojected_at = la.reprojected_at
  lastReposition.value = null
  saveAnnotations()
}

function handleImageClick(event) {
  if (currentStep.value !== 5) return
  const p = eventToImagePixel(event)
  if (!p) return // click en la banda de letterbox (fuera del área real de la imagen)

  // H con la que queda "marcado" este punto — la de la imagen tal y como se
  // está mostrando ahora mismo (identidad si no está alineada). Se guarda
  // junto al punto para poder reproyectarlo si la imagen se realinea después.
  const alignedH = currentAlignInfo.value?.H || null

  const activeIdx = selectedGcpIdx.value
  const active = activeIdx !== null ? currentProfile.value.gcps[activeIdx] : null
  const repositioning = active && (active.confirmed === false || activeIdx !== justCreatedIdx.value)
  if (repositioning) {
    // Reposicionar el punto seleccionado: pendiente por confirmar, o uno ya
    // existente que el usuario ha vuelto a seleccionar para corregirlo.
    lastReposition.value = {
      idx: activeIdx,
      pixel: [...active.pixel],
      rel: [...active.rel],
      confirmed: active.confirmed,
      aligned_H: active.aligned_H,
      reprojected_at: active.reprojected_at,
    }
    active.pixel = [p.pixelX, p.pixelY]
    active.rel = [p.relX, p.relY]
    active.confirmed = true
    active.aligned_H = alignedH
    active.reprojected_at = null
    justCreatedIdx.value = null
  } else {
    lastReposition.value = null
    const newGcp = {
      pixel: [p.pixelX, p.pixelY],
      utm: [0, 0],
      z: null,
      label: `VARILLA_${currentProfile.value.gcps.length + 1}`,
      type: 'calib',
      rel: [p.relX, p.relY],
      confirmed: true,
      aligned_H: alignedH,
    }
    currentProfile.value.gcps.push(newGcp)
    selectedGcpIdx.value = currentProfile.value.gcps.length - 1
    justCreatedIdx.value = selectedGcpIdx.value
  }
  saveAnnotations()
}

const pendingGcps = computed(() =>
  currentProfile.value.gcps
    .map((g, idx) => ({ ...g, idx }))
    .filter(g => g.confirmed === false)
)
const confirmedGcpsCount = computed(() =>
  currentProfile.value.gcps.filter(g => g.confirmed !== false).length
)

// Punto de aviso sobre el número del paso en el stepper — feedback de estado
// a simple vista, sin tener que entrar en cada paso para descubrir que algo
// quedó a medias.
function stepNeedsAttention(stepId) {
  if (stepId === 4) return rodsHasIssues.value
  if (stepId === 5) return pendingGcps.value.length > 0 || (confirmedGcpsCount.value > 0 && confirmedGcpsCount.value < 4)
  if (stepId === 6 || stepId === 7) return !!calibResult.value?.geometry_warning
  return false
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
  // calibResult es estado compartido entre Cálculo (6) y Validación (7) —
  // cualquiera de los dos puede ser el punto de entrada (p.ej. "Ver" desde
  // Vista general salta directo a Validación sin pasar por Cálculo antes).
  if (step === 6 || step === 7) loadSavedCalibration()
})

watch(selectedImage, () => {
  if (selectedImage.value) {
    fetchImageAnnotations()
    fetchAlignmentInfo()
    selectedGcpIdx.value = null
    lastReposition.value = null
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
  <div class="space-y-4">
    <div v-if="selectedCamId" class="flex justify-end">
      <span class="badge badge-info">
        Cámara activa: <strong class="font-semibold">{{ cameras.find(c => c.idx === selectedCamId)?.name }}</strong>
      </span>
    </div>

    <!-- Stepper de puntos conectados, como en Calibrar · Cámara N del mock -->
    <div class="stepper">
      <template v-for="(step, i) in steps" :key="step.id">
        <div class="step" :class="[
               currentStep === step.id ? 'active' : (currentStep > step.id ? 'done' : ''),
               (!selectedCamId && step.id > 1) ? 'opacity-40 pointer-events-none' : 'cursor-pointer'
             ]"
             @click="currentStep = step.id">
          <div class="dot relative">
            {{ currentStep > step.id ? '✓' : step.id }}
            <span v-if="stepNeedsAttention(step.id)"
                  class="absolute -top-1 -right-1 w-2.5 h-2.5 rounded-full bg-red-500 ring-2 ring-white"
                  :title="`${step.name}: hay elementos pendientes de revisar`"></span>
          </div>
          <span class="label">{{ step.name }}</span>
        </div>
        <div v-if="i < steps.length - 1" class="connector"></div>
      </template>
    </div>

    <!-- PASO 1: VISTA GENERAL -->
    <div v-if="currentStep === 1" class="space-y-4">
      <div class="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div class="card-standard p-4">
          <p class="text-[9px] font-semibold text-slate-400 uppercase tracking-wider mb-1">Cámaras calibradas</p>
          <p class="text-xl font-mono font-medium text-slate-900 tabular-nums">{{ calibratedCount }} / {{ cameras.length }}</p>
        </div>
        <div class="card-standard p-4">
          <p class="text-[9px] font-semibold text-slate-400 uppercase tracking-wider mb-1">RMSE medio</p>
          <p class="text-xl font-mono font-medium text-slate-900 tabular-nums">{{ avgRmse }}</p>
        </div>
        <div class="card-standard p-4">
          <p class="text-[9px] font-semibold text-slate-400 uppercase tracking-wider mb-1">MAE medio</p>
          <p class="text-xl font-mono font-medium text-slate-900 tabular-nums">{{ avgMae }}</p>
        </div>
        <div class="card-standard p-4">
          <p class="text-[9px] font-semibold text-slate-400 uppercase tracking-wider mb-1">GCPs registrados</p>
          <p class="text-xl font-mono font-medium text-slate-900 tabular-nums">{{ totalGcps }}</p>
        </div>
      </div>

      <div class="card-standard overflow-hidden">
        <div class="card-header uppercase tracking-wider text-[10px] flex justify-between items-center">
          <span>Perfiles de calibración</span>
          <button @click="fetchCameras" class="text-blue-600 hover:underline normal-case">↻ Recargar</button>
        </div>
        <div class="overflow-x-auto">
          <table class="w-full text-left text-sm">
            <thead class="text-slate-500 font-semibold border-b border-slate-200">
              <tr>
                <th class="px-3.5 py-2 uppercase tracking-wider text-[10px]">Cám.</th>
                <th class="px-3.5 py-2 uppercase tracking-wider text-[10px]">Estado</th>
                <th class="px-3.5 py-2 uppercase tracking-wider text-[10px]">Última calibración</th>
                <th class="px-3.5 py-2 uppercase tracking-wider text-[10px]">RMSE</th>
                <th class="px-3.5 py-2 uppercase tracking-wider text-[10px]">MAE</th>
                <th class="px-3.5 py-2 uppercase tracking-wider text-[10px]">GCPs</th>
                <th class="px-3.5 py-2 uppercase tracking-wider text-[10px]">Inliers</th>
                <th class="px-3.5 py-2 text-right uppercase tracking-wider text-[10px]">Acciones</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-slate-100">
              <tr v-for="cam in cameras" :key="cam.idx" class="hover:bg-slate-50 transition-colors text-slate-700">
                <td class="px-3.5 py-2.5">
                  <p class="font-semibold uppercase text-[11px]">{{ cam.id }}</p>
                  <p class="text-[10px] text-slate-400">{{ cam.name }}</p>
                </td>
                <td class="px-3.5 py-2.5">
                  <span class="inline-flex items-center space-x-1.5">
                    <span :class="cam.calibrated ? 'bg-emerald-500' : 'bg-slate-300'" class="w-1.5 h-1.5 rounded-full"></span>
                    <span class="text-[10px] font-semibold uppercase">{{ cam.calibrated ? 'Calibrada' : 'Sin calibrar' }}</span>
                  </span>
                </td>
                <td class="px-3.5 py-2.5 text-[10px] font-mono text-slate-500">{{ cam.last_calibration_date || '—' }}</td>
                <td class="px-3.5 py-2.5 text-[10px] font-mono" :class="cam.rmse_m > 2 ? 'text-amber-600' : 'text-slate-600'">
                  <template v-if="cam.rmse_m != null">
                    {{ cam.rmse_m.toFixed(2) }} m<span v-if="cam.rmse_px != null" class="text-slate-400"> · {{ cam.rmse_px.toFixed(2) }} px</span>
                  </template>
                  <template v-else>—</template>
                </td>
                <td class="px-3.5 py-2.5 text-[10px] font-mono text-slate-500">
                  <template v-if="cam.mae_m != null">
                    {{ cam.mae_m.toFixed(2) }} m<span v-if="cam.mae_px != null" class="text-slate-400"> · {{ cam.mae_px.toFixed(2) }} px</span>
                  </template>
                  <template v-else>—</template>
                </td>
                <td class="px-3.5 py-2.5 text-[10px] font-mono text-slate-500">{{ cam.gcps_count ?? '—' }}</td>
                <td class="px-3.5 py-2.5 text-[10px] font-mono"
                    :class="cam.inliers_count != null && cam.gcps_count && cam.inliers_count < cam.gcps_count ? 'text-amber-600' : 'text-slate-500'">
                  <template v-if="cam.inliers_count != null && cam.gcps_count">{{ cam.inliers_count }} / {{ cam.gcps_count }}</template>
                  <template v-else>—</template>
                </td>
                <td class="px-3.5 py-2.5 text-right space-x-2">
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
    <div v-if="currentStep === 2" class="grid grid-cols-1 lg:grid-cols-4 gap-4">
       <!-- Upload & List -->
       <div class="lg:col-span-1 space-y-4">
          <div @dragover.prevent="isDraggingOver = true"
               @dragleave.prevent="isDraggingOver = false"
               @drop.prevent="onDrop"
               :class="isDraggingOver ? 'border-blue-600 bg-blue-50' : 'border-slate-200 bg-white'"
               class="p-4 border-2 border-dashed rounded-md text-center transition-colors relative">
            <input type="file" multiple @change="handleFiles($event.target.files)" class="absolute inset-0 opacity-0 cursor-pointer">
            <svg class="w-8 h-8 mx-auto text-slate-400 mb-2" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M12 4v16m8-8H4" stroke-width="2"/></svg>
            <p class="text-xs font-semibold text-slate-600 uppercase">Añadir Imágenes</p>
            <p class="text-[9px] text-slate-400 uppercase mt-1">Arrastra o haz click</p>
          </div>

          <div class="card-standard flex flex-col h-[500px]">
            <div class="card-header flex justify-between items-center">
              <span>Fotogramas ({{ availableImages.length }})</span>
              <div class="flex items-center gap-3 normal-case font-normal">
                <span class="flex items-center gap-1 text-[9px] text-slate-400"><span class="w-1.5 h-1.5 rounded-full bg-emerald-500"></span>Calibrada</span>
                <span class="flex items-center gap-1 text-[9px] text-slate-400"><span class="w-1.5 h-1.5 rounded-full bg-amber-400"></span>Marcada</span>
                <button @click="fetchImages" class="text-blue-600 hover:underline">↻</button>
              </div>
            </div>
            <div class="flex-1 overflow-y-auto divide-y divide-slate-100">
               <div v-for="img in availableImages" :key="img.filename"
                    @click="selectedImage = img.filename"
                    :class="selectedImage === img.filename ? 'bg-blue-50' : 'hover:bg-slate-50'"
                    class="p-3 cursor-pointer flex items-center space-x-3 transition-colors group">
                  <div class="w-12 h-8 bg-slate-200 rounded overflow-hidden shrink-0">
                    <img :src="`${API}/api/cameras/${selectedCamId}/image?file=${img.filename}&thumb=1`" class="w-full h-full object-cover">
                  </div>
                  <div class="flex-1 min-w-0">
                    <p class="text-[10px] font-semibold truncate" :class="selectedImage === img.filename ? 'text-blue-700' : 'text-slate-700'">{{ img.filename }}</p>
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
       <div class="lg:col-span-3 card-standard flex flex-col overflow-hidden bg-slate-50 relative">
          <div v-if="selectedImage" class="h-full flex flex-col">
            <div class="flex-1 flex items-center justify-center p-4">
              <img :src="imageUrl" class="max-w-full max-h-full object-contain rounded">
            </div>
            <div class="p-4 bg-white border-t border-slate-200 flex justify-between items-center">
              <div class="flex space-x-4 items-center">
                <span class="text-xs font-semibold text-slate-700 uppercase">{{ selectedImage }}</span>
                <span v-if="currentProfile.reference_image === selectedImage" class="bg-emerald-100 text-emerald-700 border border-emerald-200 text-[9px] font-semibold px-2 py-0.5 rounded">REFERENCIA BASE</span>
              </div>
              <div class="space-x-2">
                <button v-if="currentProfile.reference_image !== selectedImage" @click="setAsReference(selectedImage)" class="btn-secondary py-1 text-[10px]">Set como Referencia</button>
                <button @click="currentStep = 3" :disabled="!currentProfile.reference_image" class="btn-standard py-1 text-[10px] disabled:opacity-40 disabled:cursor-not-allowed" :title="!currentProfile.reference_image ? 'Primero establece una imagen de referencia' : ''">Alinear lote completo →</button>
              </div>
            </div>
          </div>
          <div v-else class="flex-1 flex flex-col items-center justify-center text-slate-400 space-y-4">
            <svg class="w-16 h-16 opacity-40" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" stroke-width="1.5"/></svg>
            <p class="text-sm font-semibold uppercase tracking-wider">Selecciona o sube un fotograma</p>
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

    <!-- PASO 4: CATALOGO (solo carga/gestión del catálogo UTM genérico de la cámara.
         El CSV de campo por imagen —columna FILE— se importa y confirma en Marcación). -->
    <div v-if="currentStep === 4" class="space-y-4">
      <div class="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div @dragover.prevent="isDraggingRodsCsv = true"
             @dragleave.prevent="isDraggingRodsCsv = false"
             @drop.prevent="onDropRodsCsv"
             :class="isDraggingRodsCsv ? 'border-blue-600 bg-blue-50' : 'border-slate-200 bg-white'"
             class="p-4 border-2 border-dashed rounded-md text-center transition-colors relative">
          <input type="file" accept=".csv,.txt" @change="importRodsCsv" class="absolute inset-0 opacity-0 cursor-pointer" :disabled="importingRods">
          <svg class="w-8 h-8 mx-auto text-slate-400 mb-2" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M12 4v16m8-8H4" stroke-width="2"/></svg>
          <p class="text-xs font-semibold text-slate-600 uppercase">{{ importingRods ? 'Importando…' : 'Importar CSV de Catálogo' }}</p>
          <p class="text-[9px] text-slate-400 uppercase mt-1">Arrastra el archivo o haz click</p>
        </div>

        <div class="lg:col-span-2 card-standard p-4 flex flex-col justify-center space-y-2">
          <p class="text-[10px] font-semibold text-slate-500 uppercase tracking-wider">Formato esperado</p>
          <p class="text-xs text-slate-500 leading-relaxed">
            Columnas <span class="font-mono text-slate-700">id / X / Y</span> (o equivalentes en español: <span class="font-mono text-slate-700">nombre, este, norte</span>…),
            opcionalmente <span class="font-mono text-slate-700">Z</span> y <span class="font-mono text-slate-700">notas</span>. Separador coma o punto y coma, decimales con coma o punto.
          </p>
          <p class="text-xs text-slate-500 leading-relaxed">
            ¿Tu CSV es el levantamiento de campo del proyecto (con columna <span class="font-mono text-slate-700">FILE</span>, una varilla por imagen)? Impórtalo
            desde el paso <button @click="currentStep = 5" class="text-blue-600 hover:underline font-semibold">Marcación</button> — ahí se emparejan por imagen y se confirma el píxel exacto de cada una.
          </p>
          <p v-if="rodsMeta.source_file" class="text-[10px] text-slate-400 font-mono pt-1">
            Último origen: {{ rodsMeta.source_file }}
            <span v-if="rodsMeta.edited_at"> · corregido {{ formatTs(rodsMeta.edited_at) }}</span>
            <span v-else-if="rodsMeta.imported_at"> · importado {{ formatTs(rodsMeta.imported_at) }}</span>
          </p>
        </div>
      </div>

      <div class="card-standard flex flex-col">
        <div class="card-header flex justify-between items-center">
          <span class="uppercase tracking-wider text-[10px]">Catálogo de Varillas ({{ rods.length }})</span>
          <div class="flex items-center space-x-3">
            <span v-if="rodsHasIssues" class="text-[9px] font-semibold text-red-600 uppercase">⚠ Corrige las filas resaltadas antes de guardar</span>
            <span v-else-if="rodsDirty" class="text-[9px] font-semibold text-amber-600 uppercase">Cambios sin guardar</span>
            <button @click="addRodRow" class="text-blue-600 hover:underline text-[10px] font-semibold uppercase">+ Añadir fila</button>
          </div>
        </div>

        <div v-if="!rods.length" class="p-12 text-center space-y-2">
          <p class="text-sm font-semibold uppercase tracking-wider text-slate-300">Sin varillas todavía</p>
          <p class="text-[10px] text-slate-400">Importa un CSV o añade filas manualmente para construir el catálogo.</p>
        </div>

        <div v-else class="overflow-x-auto">
          <table class="w-full text-left text-sm">
            <thead class="text-slate-500 font-semibold border-b border-slate-200">
              <tr>
                <th class="px-4 py-3 uppercase tracking-wider text-[10px]">#</th>
                <th class="px-4 py-3 uppercase tracking-wider text-[10px]">Etiqueta</th>
                <th class="px-4 py-3 uppercase tracking-wider text-[10px]">UTM X</th>
                <th class="px-4 py-3 uppercase tracking-wider text-[10px]">UTM Y</th>
                <th class="px-4 py-3 uppercase tracking-wider text-[10px]">Z</th>
                <th class="px-4 py-3 uppercase tracking-wider text-[10px]">Notas</th>
                <th class="px-4 py-3 uppercase tracking-wider text-[10px] text-center">Quitar</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-slate-100">
              <tr v-for="(rod, idx) in rods" :key="idx"
                  :class="(rodsIssues[idx]?.emptyLabel || rodsIssues[idx]?.duplicateLabel || rodsIssues[idx]?.invalidCoords) ? 'bg-red-50' : ''"
                  class="transition-colors">
                <td class="px-4 py-2 text-[10px] font-semibold text-slate-400">{{ idx + 1 }}</td>
                <td class="px-2 py-2">
                  <input v-model="rod.label" @input="markRodsDirty"
                         :class="(rodsIssues[idx]?.emptyLabel || rodsIssues[idx]?.duplicateLabel) ? 'border-red-300 focus:border-red-400' : ''"
                         class="w-full input-standard py-1 text-[11px] font-mono uppercase">
                </td>
                <td class="px-2 py-2">
                  <input type="number" step="any" v-model.number="rod.utm[0]" @input="markRodsDirty"
                         :class="rodsIssues[idx]?.invalidCoords ? 'border-red-300 focus:border-red-400' : ''"
                         class="w-32 input-standard py-1 text-[11px] font-mono text-right">
                </td>
                <td class="px-2 py-2">
                  <input type="number" step="any" v-model.number="rod.utm[1]" @input="markRodsDirty"
                         :class="rodsIssues[idx]?.invalidCoords ? 'border-red-300 focus:border-red-400' : ''"
                         class="w-32 input-standard py-1 text-[11px] font-mono text-right">
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
    <div v-if="currentStep === 5" class="grid grid-cols-1 lg:grid-cols-4 gap-4">
       <div class="lg:col-span-3 flex flex-col gap-3">
          <!-- Importar CSV de campo (columna FILE, una varilla por imagen): se
               importa y se revisa/confirma aquí mismo, sin salir de Marcación.
               Un CSV de catálogo genérico (sin FILE) también se acepta — alimenta
               el catálogo UTM que se gestiona en el paso Catálogo. Colapsada tras
               un botón compacto: en visitas repetidas al paso no compite en
               tamaño con el área de trabajo real (foto/mapa). -->
          <button v-if="!showImportDropzone" @click="showImportDropzone = true"
                  class="btn-secondary self-start shrink-0 text-[10px] py-1.5 uppercase">
            + Importar CSV de campo (por imagen)
          </button>
          <div v-else
               @dragover.prevent="isDraggingRodsCsv = true"
               @dragleave.prevent="isDraggingRodsCsv = false"
               @drop.prevent="onDropRodsCsv"
               :class="isDraggingRodsCsv ? 'border-blue-600 bg-blue-50' : 'border-slate-200 bg-white'"
               class="card-standard p-3 border-2 border-dashed text-center relative shrink-0 flex items-center justify-center gap-2">
            <input type="file" accept=".csv,.txt" @change="importRodsCsv" class="absolute inset-0 opacity-0 cursor-pointer" :disabled="importingRods">
            <svg class="w-4 h-4 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M12 4v16m8-8H4" stroke-width="2"/></svg>
            <p class="text-xs font-semibold text-slate-600 uppercase">{{ importingRods ? 'Importando…' : 'Importar CSV de varillas de campo (por imagen)' }}</p>
            <button @click.stop="showImportDropzone = false" class="absolute top-1.5 right-1.5 text-slate-400 hover:text-slate-600 text-xs leading-none p-1">×</button>
          </div>

          <!-- Sesiones del CSV sin ninguna imagen coincidente: hay que asignarlas a mano -->
          <div v-if="unmatchedGroups.length" class="card-standard border-red-200 overflow-hidden shrink-0">
            <div class="card-header bg-red-50 text-red-700 border-red-200">⚠ Sesiones sin imagen coincidente ({{ unmatchedGroups.length }})</div>
            <div class="divide-y divide-slate-100 max-h-64 overflow-y-auto">
              <div v-for="(group, gi) in unmatchedGroups" :key="'u' + gi" class="p-3 space-y-2">
                <div class="flex items-center justify-between flex-wrap gap-2">
                  <div>
                    <p class="text-xs font-semibold text-slate-700">Sesión <span class="font-mono">{{ group.file_tag || '(sin etiqueta)' }}</span></p>
                    <p class="text-[10px] text-slate-400">{{ group.points.length }} varilla(s) · sin imagen con esa fecha/hora</p>
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
              </div>
            </div>
          </div>

          <!-- Varillas importadas ya emparejadas por imagen: se guardan como
               pendientes (confirmed=false) y se confirman abajo con la lupa.
               Colapsado a un resumen de una línea en cuanto todo está guardado
               y sin incidencias — si no, se queda ocupando espacio a perpetuidad
               aunque ya no haya nada que revisar aquí. -->
          <div v-if="imageGroups.length" class="card-standard overflow-hidden shrink-0">
            <div class="card-header flex justify-between items-center">
              <span class="uppercase tracking-wider text-[10px]">Varillas importadas por imagen ({{ imageGroups.length }})</span>
              <div class="flex items-center gap-3">
                <button v-if="!importGroupsNeedAttention" @click="importGroupsExpanded = !importGroupsExpanded"
                        class="text-blue-600 hover:underline text-[10px] font-semibold uppercase">
                  {{ importGroupsExpanded ? 'Ocultar detalle' : 'Ver detalle' }}
                </button>
                <button @click="imageGroups = []; unmatchedGroups = []; importMode = null; importGroupsExpanded = false"
                        class="text-slate-400 hover:underline text-[10px] font-semibold uppercase">Descartar</button>
              </div>
            </div>
            <p v-if="!importGroupsNeedAttention && !importGroupsExpanded" class="px-3.5 py-2 text-[10px] text-emerald-600">
              ✓ Todas las sesiones importadas y confirmadas.
            </p>
            <div v-else class="divide-y divide-slate-100 max-h-72 overflow-y-auto">
              <div v-for="(group, gi) in imageGroups" :key="'m' + gi" class="p-3 space-y-2">
                <div class="flex items-center justify-between flex-wrap gap-2">
                  <div>
                    <button @click="selectedImage = group.filename" class="text-xs font-semibold uppercase text-blue-700 hover:underline">{{ group.filename }}</button>
                    <span class="text-[9px] text-slate-400 ml-2">{{ formatTs(group.captured_at) }} · {{ group.points.length }} varilla(s)</span>
                  </div>
                  <div class="flex items-center space-x-3">
                    <button @click="group.expanded = !group.expanded" class="text-slate-400 hover:underline text-[9px] font-semibold uppercase">{{ group.expanded ? 'Ocultar filas' : 'Ver/editar filas' }}</button>
                    <span v-if="groupHasIssues(group.points)" class="text-[9px] font-semibold text-red-600 uppercase">⚠ Revisa el CSV</span>
                    <span v-else-if="group.savedAt" class="text-[9px] font-semibold text-emerald-600 uppercase">Importado {{ formatTs(group.savedAt) }} — confirma abajo</span>
                    <button v-else @click="saveImageGroup(group, group.filename)" :disabled="groupHasIssues(group.points) || group.saving"
                            class="btn-standard py-1 text-[10px] uppercase disabled:opacity-40 disabled:cursor-not-allowed">
                      {{ group.saving ? 'Guardando…' : 'Importar a esta imagen' }}
                    </button>
                  </div>
                </div>
                <div v-if="group.expanded" class="overflow-x-auto border border-slate-100 rounded">
                  <table class="w-full text-left text-sm">
                    <thead class="text-slate-500 font-semibold border-b border-slate-200">
                      <tr>
                        <th class="px-3 py-2 uppercase tracking-wider text-[9px]">Etiqueta</th>
                        <th class="px-3 py-2 uppercase tracking-wider text-[9px]">Píxel X</th>
                        <th class="px-3 py-2 uppercase tracking-wider text-[9px]">Píxel Y</th>
                        <th class="px-3 py-2 uppercase tracking-wider text-[9px]">UTM X</th>
                        <th class="px-3 py-2 uppercase tracking-wider text-[9px]">UTM Y</th>
                        <th class="px-3 py-2 uppercase tracking-wider text-[9px]">Notas</th>
                        <th class="px-3 py-2 uppercase tracking-wider text-[9px] text-center">Quitar</th>
                      </tr>
                    </thead>
                    <tbody class="divide-y divide-slate-100">
                      <tr v-for="(p, pi) in group.points" :key="pi"
                          :class="Object.values(pointIssues(group.points)[pi]).some(Boolean) ? 'bg-red-50' : ''">
                        <td class="px-2 py-1.5"><input v-model="p.label" class="w-28 input-standard py-1 text-[11px] font-mono uppercase"></td>
                        <td class="px-2 py-1.5"><input type="number" step="any" v-model.number="p.pixel[0]" class="w-24 input-standard py-1 text-[11px] font-mono text-right"></td>
                        <td class="px-2 py-1.5"><input type="number" step="any" v-model.number="p.pixel[1]" class="w-24 input-standard py-1 text-[11px] font-mono text-right"></td>
                        <td class="px-2 py-1.5"><input type="number" step="any" v-model.number="p.utm[0]" class="w-32 input-standard py-1 text-[11px] font-mono text-right"></td>
                        <td class="px-2 py-1.5"><input type="number" step="any" v-model.number="p.utm[1]" class="w-32 input-standard py-1 text-[11px] font-mono text-right"></td>
                        <td class="px-2 py-1.5"><input v-model="p.notes" placeholder="—" class="w-full input-standard py-1 text-[11px]"></td>
                        <td class="px-2 py-1.5 text-center">
                          <button @click="removeGroupPoint(group.points, pi)" class="p-1 text-red-500 hover:bg-red-50 rounded transition-colors">
                            <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" stroke-width="2"/></svg>
                          </button>
                        </td>
                      </tr>
                    </tbody>
                  </table>
                  <button @click="addGroupPoint(group.points)" class="block m-2 text-blue-600 hover:underline text-[10px] font-semibold uppercase">+ Añadir varilla</button>
                </div>
              </div>
            </div>
          </div>

          <!-- Selector de imagen: cada imagen se marca por separado (las varillas
               NO se comparten entre fotos), así que hace falta poder cambiar de
               imagen sin salir del paso de Marcación para hacerlas seguidas. -->
          <div class="card-standard p-2 flex items-center gap-2 overflow-x-auto shrink-0">
            <button v-for="img in availableImages" :key="img.filename"
                    @click="selectedImage = img.filename"
                    :class="selectedImage === img.filename ? 'ring-2 ring-blue-600' : 'ring-1 ring-slate-200 hover:ring-slate-300'"
                    class="relative shrink-0 w-16 h-11 rounded overflow-hidden transition-all">
              <img :src="`${API}/api/cameras/${selectedCamId}/image?file=${img.filename}&thumb=1`" class="w-full h-full object-cover">
              <span v-if="img.calibrated" title="Calibrada" class="absolute top-0.5 right-0.5 w-1.5 h-1.5 rounded-full bg-emerald-500 ring-1 ring-white"></span>
              <span v-else-if="img.annotated" title="Varillas marcadas, sin calibrar" class="absolute top-0.5 right-0.5 w-1.5 h-1.5 rounded-full bg-amber-400 ring-1 ring-white"></span>
              <span v-if="img.aligned" :title="`Alineada · ${img.align_inliers ?? '?'} inliers`"
                    class="absolute bottom-0.5 left-0.5 text-[7px] font-bold text-white bg-blue-600/90 rounded px-1 leading-tight">
                {{ img.align_inliers ?? '?' }}
              </span>
            </button>
            <span v-if="!availableImages.length" class="text-[10px] text-slate-400 uppercase px-2">Sin fotogramas — vuelve al paso Imágenes</span>
          </div>

          <!-- Progreso de varillas confirmadas en esta imagen + zoom de la lupa -->
          <div class="card-standard p-2.5 flex items-center gap-4 shrink-0">
            <div class="flex-1 min-w-[140px]">
              <div class="flex items-center justify-between mb-1">
                <span class="text-[9px] font-semibold text-slate-400 uppercase tracking-wider">Progreso de marcación</span>
                <span class="text-[9px] font-semibold text-slate-500 font-mono">{{ confirmedGcpsCount }} / {{ currentProfile.gcps.length }}</span>
              </div>
              <div class="h-1.5 rounded-full bg-slate-100 overflow-hidden">
                <div class="h-full rounded-full transition-all"
                     :class="confirmedGcpsCount >= 4 ? 'bg-emerald-500' : 'bg-amber-400'"
                     :style="{ width: (currentProfile.gcps.length ? (confirmedGcpsCount / currentProfile.gcps.length) * 100 : 0) + '%' }"></div>
              </div>
            </div>
            <div class="flex items-center gap-1.5 shrink-0">
              <span class="text-[9px] font-semibold text-slate-400 uppercase tracking-wider">Zoom lupa</span>
              <button @click="zoomFactor = Math.max(2, zoomFactor - 1)" class="w-5 h-5 flex items-center justify-center rounded border border-slate-200 text-slate-500 hover:bg-slate-50 text-xs leading-none">−</button>
              <span class="text-[10px] font-mono text-slate-600 w-6 text-center">×{{ zoomFactor }}</span>
              <button @click="zoomFactor = Math.min(15, zoomFactor + 1)" class="w-5 h-5 flex items-center justify-center rounded border border-slate-200 text-slate-500 hover:bg-slate-50 text-xs leading-none">+</button>
            </div>
          </div>

       <div class="relative flex gap-3 min-h-[600px]">
          <!-- Panel foto: visible en modo 'photo' y 'both' -->
          <div v-if="viewMode !== 'map'" class="card-standard overflow-hidden bg-slate-900 relative flex-1"
               @mousemove="onStageMouseMove" @mouseleave="onStageMouseLeave">
            <img ref="markImgRef" :src="imageUrl" @click="handleImageClick" @load="onMarkImageLoad" class="absolute inset-0 w-full h-full object-contain cursor-crosshair select-none">

            <div v-for="(gcp, idx) in currentProfile.gcps" :key="idx"
                 class="absolute -translate-x-1/2 -translate-y-1/2"
                 :style="gcpMarkerStyle(gcp)">
              <!-- Con el punto ya seleccionado, el marcador deja de capturar clicks: si no,
                   un click de corrección cerca (o justo encima) de su posición actual vuelve
                   a caer en handleMarkerClick (@click.stop) y solo re-selecciona/deselecciona
                   el punto en vez de reposicionarlo — el gesto más habitual al corregir (un
                   ajuste fino, no un salto grande) es precisamente el que peor funcionaba. El
                   click "atraviesa" el marcador y llega a la <img> de debajo, que ya sabe
                   reposicionar el punto activo (handleImageClick). -->
              <div @click.stop="handleMarkerClick(idx)"
                   :class="[
                     gcp.confirmed === false
                       ? (selectedGcpIdx === idx ? 'bg-amber-400 scale-150 ring-4 ring-amber-400/50 border-dashed' : 'bg-amber-400/80 border-dashed animate-pulse')
                       : (selectedGcpIdx === idx ? 'bg-emerald-500 scale-150 ring-4 ring-emerald-500/50' : 'bg-emerald-500 scale-100'),
                     selectedGcpIdx === idx ? 'pointer-events-none' : 'cursor-pointer'
                   ]"
                   :title="gcp.confirmed === false ? (gcp.reprojected_at ? 'Reproyectada por alineación — revisar' : 'Aproximado — pendiente de confirmar') : ''"
                   class="w-4 h-4 rounded-full border-2 border-white transition-all hover:scale-125 z-10 flex items-center justify-center">
                   <span class="text-[8px] font-semibold text-white">{{ gcp.confirmed === false ? '~' : idx + 1 }}</span>
              </div>
            </div>

            <!-- Lupa: recorte ampliado alrededor del cursor para fijar el píxel exacto -->
            <div v-show="loupeVisible" class="absolute z-30 rounded-md overflow-hidden border-2 border-white/80 shadow-xl pointer-events-none"
                 :style="{ left: loupeScreenPos.left + 'px', top: loupeScreenPos.top + 'px', width: LOUPE_SIZE + 'px', height: LOUPE_SIZE + 'px' }">
              <canvas ref="loupeCanvasRef" :width="LOUPE_SIZE" :height="LOUPE_SIZE" class="block bg-black"></canvas>
              <div class="absolute top-1 left-1 bg-black/70 text-white text-[8px] font-semibold px-1.5 py-0.5 rounded uppercase">×{{ zoomFactor }}</div>
              <div v-if="selectedGcpIdx !== null" class="absolute bottom-1 left-1 right-1 bg-black/70 text-white text-[7px] font-semibold px-1.5 py-0.5 rounded uppercase flex items-center gap-2">
                <span class="flex items-center gap-1"><span class="w-2 h-px bg-red-500"></span>Cursor</span>
                <span class="flex items-center gap-1"><span class="w-2 h-px bg-emerald-500"></span>Punto actual</span>
              </div>
            </div>

            <div class="absolute bottom-4 left-4 bg-black/60 text-white text-[10px] px-3 py-1.5 rounded-full font-semibold uppercase tracking-wider backdrop-blur-sm border border-white/20">Modo Marcación: Varillas GCP</div>
            <div v-if="currentAlignInfo" class="absolute bottom-4 right-4 bg-emerald-900/70 text-emerald-100 text-[9px] px-3 py-1.5 rounded-full font-semibold uppercase tracking-wider backdrop-blur-sm border border-emerald-400/30">
              Alineada · {{ currentAlignInfo.inliers }} inliers
            </div>
          </div>

          <!-- Panel mapa: visible en modo 'map' y 'both' -->
          <div v-if="viewMode !== 'photo'" class="card-standard overflow-hidden bg-slate-900 relative flex-1">
            <Map :geojsonData="gcpGeoJson" :fit-signal="mapFitSignal"
                 :selected-index="selectedGcpIdx" @select-feature="selectGcp($event)" />
            <div v-if="!gcpGeoJson.features.length" class="absolute inset-0 flex items-center justify-center pointer-events-none">
              <p class="bg-black/60 text-white text-[10px] font-semibold uppercase tracking-wider px-4 py-2 rounded-full">Ninguna varilla con UTM válida todavía</p>
            </div>
            <div class="absolute bottom-4 left-4 bg-black/60 text-white text-[10px] px-3 py-1.5 rounded-full font-semibold uppercase tracking-wider backdrop-blur-sm border border-white/20 z-[401]">Vista mapa: verificación UTM · clic en un punto para seleccionarlo</div>
          </div>

          <!-- Selector de modo: flota sobre el panel foto (o el único panel visible) -->
          <div class="absolute top-4 right-4 z-20 segmented-dark" :class="viewMode === 'both' ? 'lg:right-[calc(50%+0.875rem)]' : ''">
            <button @click="viewMode = 'photo'" :class="{ active: viewMode === 'photo' }">Foto</button>
            <button @click="viewMode = 'both'" :class="{ active: viewMode === 'both' }">Ambos</button>
            <button @click="viewMode = 'map'" :class="{ active: viewMode === 'map' }">Mapa</button>
          </div>
       </div>
       </div>

       <aside class="space-y-4">
          <!-- Varillas importadas de un CSV con píxel aproximado: hay que confirmar
               cada una con la lupa antes de que cuenten para la homografía. -->
          <div v-if="pendingGcps.length" class="card-standard border-amber-300 overflow-hidden">
            <div class="card-header bg-amber-50 text-amber-800 border-amber-200">
              ⚠ {{ pendingGcps.length }} varilla(s) pendiente(s) de confirmar
            </div>
            <p class="px-3.5 pt-2 text-[10px] text-slate-500 leading-relaxed">
              Selecciónalas y haz click sobre la imagen (usa la lupa) para fijar el píxel exacto.
            </p>
            <div class="max-h-40 overflow-y-auto divide-y divide-slate-100">
              <button v-for="gcp in pendingGcps" :key="gcp.idx" @click="selectGcp(gcp.idx)"
                      :class="selectedGcpIdx === gcp.idx ? 'bg-amber-50' : 'hover:bg-slate-50'"
                      class="w-full flex items-center justify-between px-3.5 py-2 text-left transition-colors">
                <span class="text-[10px] font-semibold uppercase text-slate-700">
                  {{ gcp.label }}
                  <span class="block normal-case font-normal text-slate-400">{{ gcp.reprojected_at ? 'reproyectada por alineación' : 'importada de CSV' }}</span>
                </span>
                <span class="text-[9px] font-semibold uppercase text-amber-600">Confirmar →</span>
              </button>
            </div>
          </div>

          <div v-if="selectedGcpIdx !== null" class="card-standard border-blue-200 animate-fade-in">
            <div class="card-header bg-blue-600 text-white flex justify-between items-center py-2">
              <span class="text-[10px] font-semibold uppercase tracking-wider">Editar Punto {{ selectedGcpIdx + 1 }}</span>
              <button @click="selectedGcpIdx = null; lastReposition = null" class="hover:bg-blue-700 rounded px-1">×</button>
            </div>
            <div class="p-4 space-y-4">
              <div v-if="lastReposition && lastReposition.idx === selectedGcpIdx" class="flex items-center justify-between bg-slate-50 border border-slate-200 rounded-md p-3 text-[10px] text-slate-600">
                <span>Posición cambiada.</span>
                <button @click="undoReposition" class="text-blue-600 hover:underline font-semibold uppercase">↺ Deshacer</button>
              </div>
              <div v-if="currentProfile.gcps[selectedGcpIdx].confirmed === false && currentProfile.gcps[selectedGcpIdx].reprojected_at" class="bg-amber-50 border border-amber-200 rounded-md p-3 text-[10px] text-amber-800 leading-relaxed">
                Este punto ya estaba confirmado, pero una alineación nueva de la imagen lo ha recolocado automáticamente. Comprueba que sigue cayendo sobre la varilla correcta — haz click sobre la imagen (apóyate en la lupa) para ajustarlo y confirmarlo de nuevo.
              </div>
              <div v-else-if="currentProfile.gcps[selectedGcpIdx].confirmed === false" class="bg-amber-50 border border-amber-200 rounded-md p-3 text-[10px] text-amber-800 leading-relaxed">
                Píxel aproximado (importado de CSV). Haz click sobre la imagen — apóyate en la lupa — para fijar el punto exacto y confirmarlo.
              </div>
              <div v-else class="bg-blue-50 border border-blue-200 rounded-md p-3 text-[10px] text-blue-800 leading-relaxed flex items-start gap-2">
                <span class="mt-0.5">📍</span>
                <span>
                  <strong class="block uppercase tracking-wider text-[9px] mb-0.5">Modo reposicionar activo</strong>
                  Haz click en cualquier parte de la foto — apóyate en la lupa — para mover este punto ahí, incluso si clicas justo sobre su posición actual. Ya no hace falta acertar sobre el círculo.
                </span>
              </div>
              <div v-if="rods.length" class="space-y-1">
                <label class="text-[10px] font-semibold text-slate-500 uppercase">Varilla del catálogo</label>
                <select @change="assignRod($event.target.value)" class="w-full input-standard text-xs">
                  <option value="" selected disabled>Autocompletar desde catálogo…</option>
                  <option v-for="(rod, i) in rods" :key="i" :value="i">
                    {{ rod.label }} — {{ rod.utm[0].toFixed(1) }}, {{ rod.utm[1].toFixed(1) }}
                  </option>
                </select>
              </div>
              <div class="space-y-1">
                <label class="text-[10px] font-semibold text-slate-500 uppercase">Etiqueta</label>
                <input v-model="currentProfile.gcps[selectedGcpIdx].label" class="w-full input-standard">
              </div>
              <div class="grid grid-cols-2 gap-2">
                <div class="space-y-1">
                  <label class="text-[10px] font-semibold text-slate-500 uppercase">UTM X</label>
                  <input type="number" v-model.number="currentProfile.gcps[selectedGcpIdx].utm[0]" class="w-full input-standard font-mono text-xs">
                </div>
                <div class="space-y-1">
                  <label class="text-[10px] font-semibold text-slate-500 uppercase">UTM Y</label>
                  <input type="number" v-model.number="currentProfile.gcps[selectedGcpIdx].utm[1]" class="w-full input-standard font-mono text-xs">
                </div>
              </div>
              <div class="space-y-1">
                <label class="text-[10px] font-semibold text-slate-500 uppercase" title="Cota de la varilla — no interviene en el cálculo de la homografía (2D), es solo referencia de campo.">Z (cota, opcional)</label>
                <input type="number" step="any" v-model.number="currentProfile.gcps[selectedGcpIdx].z" placeholder="—" class="w-full input-standard font-mono text-xs">
              </div>
              <button @click="currentProfile.gcps.splice(selectedGcpIdx, 1); selectedGcpIdx = null; saveAnnotations()" class="w-full bg-red-50 text-red-600 text-[10px] font-semibold py-2 rounded uppercase border border-red-100 hover:bg-red-100 transition-colors">Eliminar Punto</button>
            </div>
          </div>

          <div class="card-standard flex flex-col h-[420px]">
            <div class="card-header flex justify-between items-center">
              <span class="uppercase tracking-wider text-[10px]">Listado de Varillas ({{ currentProfile.gcps.length }})</span>
              <button @click="currentStep = 4" class="text-blue-600 hover:underline text-[10px] font-semibold uppercase"
                      :title="rods.length ? `${rods.length} varillas disponibles para autocompletar` : 'Todavía no hay varillas topografiadas'">
                Catálogo UTM ({{ rods.length }})
              </button>
            </div>
            <div class="flex-1 overflow-y-auto divide-y divide-slate-100 custom-scrollbar">
               <div v-for="(gcp, idx) in currentProfile.gcps" :key="idx"
                    @click="selectGcp(idx)"
                    class="p-3 text-xs flex justify-between items-center cursor-pointer hover:bg-slate-50 transition-colors"
                    :class="selectedGcpIdx === idx
                      ? (gcp.confirmed === false ? 'bg-amber-50 border-l-4 border-amber-400' : 'bg-emerald-50 border-l-4 border-emerald-500')
                      : ''">
                  <div>
                    <p class="font-semibold text-slate-700 uppercase text-[10px] flex items-center gap-1.5">
                      {{ gcp.label }}
                      <span v-if="gcp.confirmed === false" class="text-[8px] font-semibold uppercase text-amber-600 bg-amber-100 px-1 py-0.5 rounded">Pendiente</span>
                    </p>
                    <p class="text-[9px] text-slate-400 font-mono">{{ gcp.utm[0].toFixed(1) }}, {{ gcp.utm[1].toFixed(1) }}</p>
                  </div>
                  <span class="text-[9px] font-semibold text-slate-300">#{{ idx + 1 }}</span>
               </div>
            </div>
            <div class="p-4 border-t border-slate-100 bg-slate-50 space-y-2">
              <button @click="currentStep = 6" :disabled="confirmedGcpsCount < 4"
                      class="btn-standard w-full uppercase text-xs disabled:opacity-40 disabled:cursor-not-allowed">
                Continuar a Cálculo →
              </button>
              <p v-if="confirmedGcpsCount < 4" class="text-[9px] text-slate-400 text-center uppercase">
                Faltan {{ 4 - confirmedGcpsCount }} varilla(s) confirmada(s) (mínimo 4)
              </p>
            </div>
          </div>
       </aside>
    </div>

    <!-- PASO 6: CALCULO (dispara el ajuste de homografía y deja iterar sobre
         los residuos por varilla — excluir, ajustar umbral, recalcular —
         antes de pasar a la validación final). -->
    <div v-if="currentStep === 6" class="space-y-4">
      <div class="card-standard p-4 text-xs text-slate-500 leading-relaxed">
        <strong class="text-slate-700">¿Qué hace este cálculo?</strong> Cada varilla que confirmaste en Marcación
        aporta dos coordenadas del mismo punto: dónde cae en la foto (píxel) y dónde está en la realidad
        (UTM, metros). Con al menos 4 de esas parejas, el sistema calcula la fórmula matemática (la
        "homografía") que convierte cualquier píxel de la foto en su coordenada real — es lo que luego
        permite medir distancias y área de playa sobre la imagen. El <strong>RMSE</strong> mide cuánto se
        desvía esa fórmula de las varillas que usaste para calcularla: cuanto más bajo, mejor encaja.
      </div>

      <!-- Selector de imagen: la calibración es por imagen (cada una tiene su
           propio cálculo), así que se puede pinchar entre imágenes para
           comparar resultados sin volver a Marcación cada vez. La que quede
           calculada en último lugar es la que se usa como activa de la
           cámara para analizar el resto de sus capturas (ver memoria, §4.2). -->
      <div v-if="availableImages.length > 1" class="card-standard p-2 flex items-center gap-2 overflow-x-auto shrink-0">
        <button v-for="img in availableImages" :key="img.filename"
                @click="selectedImage = img.filename"
                :class="selectedImage === img.filename ? 'ring-2 ring-blue-600' : 'ring-1 ring-slate-200 hover:ring-slate-300'"
                class="relative shrink-0 w-16 h-11 rounded overflow-hidden transition-all">
          <img :src="`${API}/api/cameras/${selectedCamId}/image?file=${img.filename}&thumb=1`" class="w-full h-full object-cover">
          <span v-if="img.calibrated" title="Calibrada" class="absolute top-0.5 right-0.5 w-1.5 h-1.5 rounded-full bg-emerald-500 ring-1 ring-white"></span>
          <span v-else-if="img.annotated" title="Varillas marcadas, sin calibrar" class="absolute top-0.5 right-0.5 w-1.5 h-1.5 rounded-full bg-amber-400 ring-1 ring-white"></span>
        </button>
      </div>

      <div v-if="!calibResult" class="card-standard p-16 text-center space-y-4 min-h-[400px] flex flex-col items-center justify-center">
        <svg class="w-12 h-12 text-slate-200" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" stroke-width="1.5"/></svg>
        <p class="text-sm font-semibold uppercase tracking-wider text-slate-400">
          {{ confirmedGcpsCount }} / {{ currentProfile.gcps.length }} varilla(s) confirmada(s)
        </p>
        <button @click="calculateHomography()" :disabled="confirmedGcpsCount < 4 || calculating"
                class="btn-standard uppercase text-xs disabled:opacity-40 disabled:cursor-not-allowed">
          {{ calculating ? 'Calculando…' : 'Calcular homografía' }}
        </button>
        <p v-if="confirmedGcpsCount < 4" class="text-[10px] text-slate-400 uppercase">
          Faltan {{ 4 - confirmedGcpsCount }} varilla(s) confirmada(s) (mínimo 4) — vuelve a
          <button @click="currentStep = 5" class="text-blue-600 hover:underline font-semibold">Marcación</button>
        </p>
      </div>

      <template v-else>
        <!-- Aviso de geometría inestable: explica un RMSE disparado en vez de
             dejarlo como un número grande sin más contexto — ver
             geometry_warning en calculate_homography (backend). -->
        <div v-if="calibResult.geometry_warning" class="card-standard border-red-200 bg-red-50 p-3 flex items-start gap-2.5">
          <svg class="w-4 h-4 text-red-500 shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01M5.07 19h13.86c1.54 0 2.5-1.67 1.73-3L13.73 4c-.77-1.33-2.69-1.33-3.46 0L3.34 16c-.77 1.33.19 3 1.73 3z"/></svg>
          <div>
            <p class="text-[10px] font-semibold text-red-700 uppercase tracking-wider">RMSE poco fiable — geometría de varillas inestable</p>
            <p class="text-[11px] text-red-700 leading-relaxed mt-0.5">{{ calibResult.geometry_warning }}</p>
          </div>
        </div>

        <div class="flex items-center justify-between flex-wrap gap-2">
          <p class="text-xs text-slate-500 flex items-center gap-3 flex-wrap">
            <span>RMSE reproyección <strong class="text-slate-800 font-mono">{{ calibResult.rmse_px?.toFixed(2) }} px</strong></span>
            <span>· RMSE terreno <strong class="font-mono" :class="calibOk ? 'text-slate-800' : 'text-red-600'">{{ calibResult.rmse_m?.toFixed(3) }} m</strong></span>
            <span title="Varillas usadas = las que entraron en el ajuste (confirmadas, no excluidas). Inliers RANSAC = de esas, cuántas aceptó RANSAC como mutuamente consistentes — no son lo mismo: pocos inliers sobre muchas varillas usadas es la señal de geometría inestable.">
              · Inliers RANSAC
              <strong class="font-mono" :class="calibResult.inliers_count < calibResult.gcps_used * 0.6 ? 'text-red-600' : 'text-slate-800'">
                {{ calibResult.inliers_count }} / {{ calibResult.gcps_used }}
              </strong>
            </span>
          </p>
          <p class="text-[10px] text-slate-400 font-mono">{{ calibResult.image }} · {{ formatTs(calibResult.date) }}</p>
        </div>

        <!-- Nota persistente (no solo al pasar el ratón): cuando el umbral por
             varilla está ajustado fino, es normal que varias varillas queden
             "sobre umbral" en píxeles aunque la calibración en conjunto sea
             buena — sin esto, una tabla en ámbar/rojo parece un problema real
             aunque el RMSE terreno esté perfectamente dentro de tolerancia. -->
        <div v-if="flaggedCount > 0 && calibOk" class="card-standard border-blue-200 bg-blue-50 p-3 text-[11px] text-blue-800 leading-relaxed">
          {{ flaggedCount }} varilla(s) superan el umbral de {{ threshold }}px marcado arriba, pero
          la calibración en conjunto es correcta — el RMSE terreno ({{ calibResult.rmse_m?.toFixed(3) }} m)
          es el que decide si la calibración vale, no esto. Súbelo si no necesitas tanta precisión
          por varilla, o revisa solo las filas marcadas si quieres afinar más.
        </div>

        <!-- Tabla de residuos por varilla -->
        <div class="card-standard overflow-hidden flex flex-col">
          <div class="card-header flex justify-between items-center">
            <span>Error de reproyección por varilla</span>
            <div class="flex items-center space-x-2"
                 title="Solo marca en la tabla qué varilla concreta podría estar mal puesta (útil para localizar un misclick) — no es el criterio de si la calibración es válida, eso lo decide el RMSE terreno de la Validación.">
              <label class="text-[9px] text-slate-400 uppercase font-semibold">Umbral por varilla (px)</label>
              <input type="number" step="0.1" min="0.1" v-model.number="threshold"
                     class="input-standard w-20 py-1 text-xs font-mono text-right">
            </div>
          </div>
          <div class="overflow-x-auto flex-1">
            <table class="w-full text-left text-sm">
              <thead class="text-slate-500 font-semibold border-b border-slate-200">
                <tr>
                  <th class="px-4 py-3 uppercase tracking-wider text-[10px]">#</th>
                  <th class="px-4 py-3 uppercase tracking-wider text-[10px]">Varilla</th>
                  <th class="px-4 py-3 uppercase tracking-wider text-[10px]" title="El píxel donde se marcó/importó esta varilla — compáralo con tu CSV/Excel de origen si algo no cuadra.">Píxel marcado (u, v)</th>
                  <th class="px-4 py-3 uppercase tracking-wider text-[10px]" title="La coordenada UTM asignada a esta varilla — compáralo con tu CSV/Excel de origen si algo no cuadra.">UTM marcado (X, Y)</th>
                  <th class="px-4 py-3 uppercase tracking-wider text-[10px] text-right">Error (px)</th>
                  <th class="px-4 py-3 uppercase tracking-wider text-[10px] text-right">Error (m)</th>
                  <th class="px-4 py-3 uppercase tracking-wider text-[10px] text-center">Estado</th>
                  <th class="px-4 py-3 uppercase tracking-wider text-[10px] text-center">Excluir</th>
                </tr>
              </thead>
              <tbody class="divide-y divide-slate-100">
                <tr v-for="r in calibResult.residuals" :key="r.idx"
                    :class="(r.excluded || r.pending) ? 'opacity-40 bg-slate-50' : (r.above_threshold ? 'bg-amber-50' : 'hover:bg-slate-50')"
                    class="transition-colors text-slate-700">
                  <td class="px-4 py-3 text-[10px] font-semibold text-slate-400">{{ r.idx + 1 }}</td>
                  <td class="px-4 py-3 text-[11px] font-semibold uppercase">{{ r.label }}</td>
                  <td class="px-4 py-3 font-mono text-[11px] text-slate-600 whitespace-nowrap">
                    {{ r.pixel ? `${r.pixel[0]}, ${r.pixel[1]}` : '—' }}
                  </td>
                  <td class="px-4 py-3 font-mono text-[11px] text-slate-600 whitespace-nowrap">
                    {{ r.utm ? `${r.utm[0]}, ${r.utm[1]}` : '—' }}
                  </td>
                  <td class="px-4 py-3 text-right font-mono text-[11px]"
                      :class="r.above_threshold ? 'text-amber-700 font-semibold' : 'text-slate-600'"
                      :title="r.pixel_predicted ? `Homografía predice: ${r.pixel_predicted[0]}, ${r.pixel_predicted[1]}` : ''">
                    {{ r.error_px.toFixed(2) }}
                  </td>
                  <td class="px-4 py-3 text-right font-mono text-[11px] text-slate-500"
                      :title="r.utm_predicted ? `Homografía predice: ${r.utm_predicted[0]}, ${r.utm_predicted[1]}` : ''">
                    {{ r.error_m.toFixed(3) }}
                  </td>
                  <td class="px-4 py-3 text-center">
                    <span v-if="r.pending" class="px-2 py-0.5 rounded text-[9px] font-semibold uppercase bg-amber-100 text-amber-700 border border-amber-200">Pendiente</span>
                    <span v-else-if="r.excluded" class="px-2 py-0.5 rounded text-[9px] font-semibold uppercase bg-slate-100 text-slate-500 border border-slate-200">Excluida</span>
                    <span v-else-if="r.above_threshold" class="px-2 py-0.5 rounded text-[9px] font-semibold uppercase bg-amber-100 text-amber-700 border border-amber-200" title="Ayuda de diagnóstico por varilla — no decide si la calibración es válida">⚠ Sobre umbral</span>
                    <span v-else class="px-2 py-0.5 rounded text-[9px] font-semibold uppercase bg-emerald-100 text-emerald-700 border border-emerald-200">OK</span>
                  </td>
                  <td class="px-4 py-3 text-center">
                    <input type="checkbox" :disabled="r.pending" :checked="excludedIdx.includes(r.idx)" @change="toggleExcluded(r.idx)"
                           class="w-3.5 h-3.5 accent-blue-600 cursor-pointer disabled:opacity-30">
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
          <div class="p-4 border-t border-slate-100 bg-slate-50 flex justify-between items-center">
            <button v-if="flaggedCount" @click="excludeFlagged" :disabled="calculating"
                    class="text-red-600 hover:underline text-[10px] font-semibold uppercase">
              Excluir {{ flaggedCount }} sobre umbral y recalcular
            </button>
            <span v-else class="text-[10px] text-slate-400 uppercase font-semibold">Todas las varillas activas dentro de tolerancia</span>
            <button @click="recalculate" :disabled="calculating" class="btn-standard py-1.5 text-[10px] uppercase">
              {{ calculating ? 'Recalculando…' : 'Recalcular' }}
            </button>
          </div>
        </div>

        <div class="flex justify-between items-center">
          <button @click="currentStep = 5" class="text-[10px] text-slate-400 hover:text-slate-600 font-semibold uppercase">← Volver a Marcación</button>
          <button @click="currentStep = 7" class="btn-standard py-2 text-xs uppercase">Continuar a Validación →</button>
        </div>
      </template>
    </div>

    <!-- PASO 7: VALIDACION (resumen final de la calibración de esta imagen) -->
    <div v-if="currentStep === 7" class="space-y-4">
      <div v-if="!calibResult" class="card-standard p-16 text-center space-y-4 min-h-[400px] flex flex-col items-center justify-center">
        <svg class="w-12 h-12 text-slate-200" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" stroke-width="1.5"/></svg>
        <p class="text-sm font-semibold uppercase tracking-wider text-slate-400">Esta imagen aún no tiene calibración calculada</p>
        <button @click="currentStep = 6" class="btn-standard uppercase text-xs">Ir a Cálculo</button>
      </div>

      <template v-else>
        <div class="flex items-center justify-between flex-wrap gap-2">
          <div :class="calibOk ? 'bg-emerald-100 text-emerald-800 border-emerald-200' : 'bg-red-100 text-red-800 border-red-200'"
               class="inline-flex items-center space-x-2 px-5 py-1.5 rounded-full text-xs font-semibold uppercase tracking-wider border">
            <svg v-if="!calibOk" class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M12 9v2m0 4h.01M5.07 19h13.86c1.54 0 2.5-1.67 1.73-3L13.73 4c-.77-1.33-2.69-1.33-3.46 0L3.34 16c-.77 1.33.19 3 1.73 3z" stroke-width="2"/></svg>
            <span>{{ calibOk
              ? `RMSE ${calibResult.rmse_m?.toFixed(2)} m — dentro de tolerancia`
              : `RMSE ${calibResult.rmse_m?.toFixed(2)} m — por encima de ${(calibResult.rmse_good_m ?? 1.5).toFixed(1)} m` }}</span>
          </div>
          <p class="text-[10px] text-slate-400 font-mono">{{ calibResult.image }} · {{ formatTs(calibResult.date) }}</p>
        </div>

        <div v-if="calibResult.geometry_warning" class="card-standard border-red-200 bg-red-50 p-3 flex items-start gap-2.5">
          <svg class="w-4 h-4 text-red-500 shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01M5.07 19h13.86c1.54 0 2.5-1.67 1.73-3L13.73 4c-.77-1.33-2.69-1.33-3.46 0L3.34 16c-.77 1.33.19 3 1.73 3z"/></svg>
          <div>
            <p class="text-[10px] font-semibold text-red-700 uppercase tracking-wider">RMSE poco fiable — geometría de varillas inestable</p>
            <p class="text-[11px] text-red-700 leading-relaxed mt-0.5">{{ calibResult.geometry_warning }}</p>
            <button @click="currentStep = 6" class="text-[10px] font-semibold text-red-700 hover:underline uppercase mt-1">Volver a Cálculo →</button>
          </div>
        </div>

        <div class="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-4">
          <div class="card-standard p-4">
            <p class="text-[9px] font-semibold text-slate-400 uppercase tracking-wider mb-1">RMSE reproyección</p>
            <p class="text-xl font-semibold text-slate-900 font-mono">{{ calibResult.rmse_px?.toFixed(2) }} px</p>
          </div>
          <div class="card-standard p-4" :title="`Objetivo: RMSE terreno ≤ ${(calibResult.rmse_good_m ?? 1.5).toFixed(1)} m — este es el criterio real de aceptación, no el error en píxeles por varilla.`">
            <p class="text-[9px] font-semibold text-slate-400 uppercase tracking-wider mb-1">RMSE terreno</p>
            <p class="text-xl font-semibold font-mono" :class="calibOk ? 'text-slate-900' : 'text-red-600'">{{ calibResult.rmse_m?.toFixed(3) }} m</p>
          </div>
          <div class="card-standard p-4">
            <p class="text-[9px] font-semibold text-slate-400 uppercase tracking-wider mb-1">MAE reproyección</p>
            <p class="text-xl font-semibold text-slate-900 font-mono">{{ calibResult.mae_px?.toFixed(2) }} px</p>
          </div>
          <div class="card-standard p-4">
            <p class="text-[9px] font-semibold text-slate-400 uppercase tracking-wider mb-1">MAE terreno</p>
            <p class="text-xl font-semibold text-slate-900 font-mono">{{ calibResult.mae_m?.toFixed(3) }} m</p>
          </div>
          <div class="card-standard p-4">
            <p class="text-[9px] font-semibold text-slate-400 uppercase tracking-wider mb-1">Varillas usadas</p>
            <p class="text-xl font-semibold text-slate-900 font-mono">{{ calibResult.gcps_used }} / {{ calibResult.residuals?.length }}</p>
          </div>
          <div class="card-standard p-4">
            <p class="text-[9px] font-semibold text-slate-400 uppercase tracking-wider mb-1">Estado · EPSG:25830</p>
            <div class="flex items-center space-x-2">
              <div :class="calibOk ? 'bg-emerald-500' : 'bg-red-500'" class="w-2 h-2 rounded-full animate-pulse"></div>
              <p class="text-sm font-semibold uppercase" :class="calibOk ? 'text-slate-700' : 'text-red-600'">{{ calibOk ? 'Óptimo' : 'Revisar' }}</p>
            </div>
          </div>
        </div>

        <div class="grid grid-cols-1 lg:grid-cols-3 gap-4">
          <!-- Histograma de residuos: una barra por varilla, altura ∝ error en
               metros, mismo color que su estado en la tabla de Cálculo. -->
          <div class="card-standard p-4">
            <div class="text-[10px] font-semibold text-slate-400 uppercase tracking-wider mb-3">Distribución de residuos (m)</div>
            <svg :viewBox="`0 0 ${HIST_W} ${HIST_H}`" class="w-full h-32">
              <line :x1="HIST_PAD" :y1="HIST_H - HIST_PAD" :x2="HIST_W - HIST_PAD" :y2="HIST_H - HIST_PAD" stroke="#e2e8f0" stroke-width="1"/>
              <g v-for="(b, i) in residualBars" :key="i">
                <rect :x="b.x" :y="b.y" :width="b.width" :height="b.height" :fill="b.color" rx="2">
                  <title>{{ b.label }}: {{ b.error_m.toFixed(3) }} m</title>
                </rect>
              </g>
            </svg>
            <p v-if="!residualBars.length" class="text-[10px] text-slate-400 text-center py-8">Sin residuos que mostrar</p>
          </div>

          <!-- Mapa de cobertura + reproyección: dónde caen las varillas sobre
               la foto (revela geometría casi colineal de un vistazo) y, con
               una línea corta, el vector de error hacia lo que predice la
               homografía en ese mismo punto (pixel_predicted). -->
          <div class="lg:col-span-2 card-standard overflow-hidden">
            <div class="card-header uppercase tracking-wider text-[10px]">Cobertura de varillas y reproyección</div>
            <div class="relative bg-slate-100">
              <img :src="imageUrl" @load="onCoverageImgLoad" class="w-full h-auto block" alt="Imagen calibrada">
              <svg v-if="coverageImgNatural.width" class="absolute inset-0 w-full h-full"
                   :viewBox="`0 0 ${coverageImgNatural.width} ${coverageImgNatural.height}`" preserveAspectRatio="none">
                <g v-for="r in calibResult.residuals" :key="r.idx">
                  <line v-if="r.pixel && r.pixel_predicted"
                        :x1="r.pixel[0]" :y1="r.pixel[1]" :x2="r.pixel_predicted[0]" :y2="r.pixel_predicted[1]"
                        :stroke="residualColor(r)" :stroke-width="coverageImgNatural.width / 500" opacity="0.85"/>
                  <circle v-if="r.pixel" :cx="r.pixel[0]" :cy="r.pixel[1]" :r="coverageImgNatural.width / 220"
                          :fill="residualColor(r)" stroke="white" :stroke-width="coverageImgNatural.width / 1500">
                    <title>{{ r.label }}: {{ r.error_m.toFixed(3) }} m</title>
                  </circle>
                </g>
              </svg>
            </div>
            <p class="px-4 py-2 text-[10px] text-slate-400 border-t border-slate-100">
              Punto = varilla marcada · línea = distancia hasta la posición que predice la homografía.
              Si los puntos quedan casi todos en fila, esa es la causa típica de un RMSE poco fiable
              (§ aviso de geometría inestable).
            </p>
          </div>
        </div>

        <div class="card-standard p-4">
          <div class="text-[10px] font-semibold text-slate-400 uppercase tracking-wider mb-3">Metadatos del perfil</div>
          <div class="grid grid-cols-1 md:grid-cols-3 gap-3">
            <div>
              <label class="block text-[9px] font-semibold text-slate-400 uppercase tracking-wider mb-1">Nombre de perfil</label>
              <input v-model="profileMeta.profile_name" class="w-full input-standard text-xs" placeholder="ej. Campaña verano 2026">
            </div>
            <div>
              <label class="block text-[9px] font-semibold text-slate-400 uppercase tracking-wider mb-1">Operador</label>
              <input v-model="profileMeta.operator" class="w-full input-standard text-xs" placeholder="ej. J. Pérez">
            </div>
            <div>
              <label class="block text-[9px] font-semibold text-slate-400 uppercase tracking-wider mb-1">Notas</label>
              <input v-model="profileMeta.notes" class="w-full input-standard text-xs" placeholder="observaciones opcionales">
            </div>
          </div>
          <div class="flex justify-end mt-3">
            <button @click="saveProfileMetadata" :disabled="savingMeta" class="btn-secondary text-xs uppercase disabled:opacity-40">
              {{ savingMeta ? 'Guardando…' : 'Guardar metadatos' }}
            </button>
          </div>
        </div>

        <div class="card-standard p-4 flex flex-wrap gap-3 justify-end">
          <button @click="downloadCalibrationCsv" class="btn-secondary text-xs uppercase">Descargar CSV</button>
          <button @click="downloadCalibrationJson" class="btn-secondary text-xs uppercase">Descargar JSON</button>
          <button @click="downloadCalibrationPdf" class="btn-secondary text-xs uppercase">Descargar informe PDF</button>
          <button @click="currentStep = 6" class="btn-secondary text-xs uppercase">← Volver a Cálculo</button>
          <button @click="currentStep = 5" class="btn-secondary text-xs uppercase">Reajustar Puntos</button>
          <button @click="currentStep = 1; fetchCameras()" class="btn-standard text-xs uppercase">Finalizar Proceso</button>
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
