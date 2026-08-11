<script setup>
import { ref, reactive, computed, onMounted, onUnmounted } from 'vue'
import { API_BASE } from '../api.js'

const emit = defineEmits(['notify'])
const API = API_BASE

// idle (formulario) -> running (polling) -> done (resultados)
const phase = ref('idle')

const cameras = ref([])
const camerasLoading = ref(true)

const selectedCamId = ref(null)
const today = new Date().toISOString().slice(0, 10)
const fromDate = ref(today)
const toDate = ref(today)

const jobId = ref(null)
const jobSummary = reactive({
  status: '', step: '', progress: { current: 0, total: 0 },
  downloaded: 0, counts: { ok: 0, rejected: 0, errors: 0, total: 0 }, error: '',
})
const results = ref([])
let pollTimer = null

// Exportar GeoJSON automáticamente en cuanto el job termina en 'done' — evita
// tener que volver a esta pantalla solo para pulsar el botón manual de siempre.
const autoExportGeojson = ref(false)

// Log de actividad en tiempo real, acotado a Auto Mode: reutiliza GET /api/logs
// (el mismo buffer que ya consume App.vue) filtrando por el prefijo real que
// usa add_log() en auto_mode.py, en vez de duplicar el mecanismo de logging.
const allLogs = ref([])
let logsTimer = null
const autoModeLogs = computed(() =>
  allLogs.value.filter(l => l.msg?.startsWith('Auto Mode')).slice(-30).reverse()
)
async function _pollLogs() {
  try {
    const res = await fetch(`${API}/api/logs`)
    if (!res.ok) return
    allLogs.value = await res.json()
  } catch (e) { /* red intermitente: se reintenta en el siguiente tick */ }
}
function logColor(type) {
  if (type === 'error') return 'text-red-600'
  if (type === 'warning') return 'text-amber-600'
  if (type === 'success') return 'text-emerald-600'
  return 'text-slate-500'
}

const STEP_LABELS = {
  pending: 'En cola',
  downloading: 'Descargando imágenes de Obscape',
  aligning: 'Alineando imágenes',
  analyzing: 'Analizando línea de costa',
  done: 'Completado',
  error: 'Error',
}

const selectedCamera = computed(() => cameras.value.find(c => c.idx === selectedCamId.value))

async function fetchCameras() {
  camerasLoading.value = true
  try {
    const res = await fetch(`${API}/api/cameras`)
    if (!res.ok) throw new Error('HTTP ' + res.status)
    cameras.value = await res.json()
    if (!selectedCamId.value) {
      const firstCalibrated = cameras.value.find(c => c.calibrated)
      selectedCamId.value = (firstCalibrated || cameras.value[0])?.idx ?? null
    }
  } catch (e) {
    emit('notify', 'Error al cargar cámaras', 'error')
  } finally {
    camerasLoading.value = false
  }
}

async function start() {
  if (!selectedCamId.value) {
    emit('notify', 'Selecciona una cámara', 'error')
    return
  }
  if (!fromDate.value || !toDate.value) {
    emit('notify', 'Selecciona un rango de fechas', 'error')
    return
  }
  if (fromDate.value > toDate.value) {
    emit('notify', 'La fecha de inicio no puede ser posterior a la de fin', 'error')
    return
  }

  try {
    const res = await fetch(`${API}/api/automode/start`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        cam_id: selectedCamId.value,
        from_date: fromDate.value,
        to_date: toDate.value,
      }),
    })
    const data = await res.json()
    if (!res.ok) throw new Error(data.detail || 'Error al iniciar Auto Mode')

    jobId.value = data.job_id
    Object.assign(jobSummary, {
      status: 'pending', step: '', progress: { current: 0, total: 0 },
      downloaded: 0, counts: { ok: 0, rejected: 0, errors: 0, total: 0 }, error: '',
    })
    phase.value = 'running'
    _startPolling()
  } catch (e) {
    emit('notify', e.message, 'error')
  }
}

function _startPolling() {
  clearInterval(pollTimer)
  pollTimer = setInterval(_poll, 1500)
  _poll()
}

async function _poll() {
  if (!jobId.value) return
  try {
    const res = await fetch(`${API}/api/automode/${jobId.value}/status`)
    if (!res.ok) throw new Error('HTTP ' + res.status)
    const data = await res.json()
    Object.assign(jobSummary, data)

    if (data.status === 'done' || data.status === 'error') {
      clearInterval(pollTimer)
      if (data.status === 'done') {
        await _loadResults()
        if (autoExportGeojson.value) exportGeoJson()
      }
      phase.value = 'done'
    }
  } catch (e) {
    // red intermitente durante el polling: se reintenta en el siguiente tick
  }
}

async function _loadResults() {
  try {
    const res = await fetch(`${API}/api/automode/${jobId.value}/results`)
    if (!res.ok) throw new Error('HTTP ' + res.status)
    const data = await res.json()
    results.value = data.items
  } catch (e) {
    emit('notify', 'Error al cargar los resultados del procesamiento', 'error')
  }
}

function exportGeoJson() {
  if (!selectedCamId.value) return
  window.open(`${API}/api/cameras/${selectedCamId.value}/geojson`, '_blank')
}

function reset() {
  clearInterval(pollTimer)
  phase.value = 'idle'
  jobId.value = null
  results.value = []
}

function rowStatus(r) {
  if (r.error) return { label: 'ERROR', color: 'bg-red-500' }
  if (r.rejected) return { label: 'RECHAZADA', color: 'bg-amber-500' }
  return { label: 'OK', color: 'bg-emerald-500' }
}

onMounted(() => {
  fetchCameras()
  _pollLogs()
  logsTimer = setInterval(_pollLogs, 3000)
})
onUnmounted(() => {
  clearInterval(pollTimer)
  clearInterval(logsTimer)
})
</script>

<template>
  <div class="grid grid-cols-1 xl:grid-cols-3 gap-4 items-start">
  <div class="xl:col-span-2 space-y-4">
    <!-- ════════════════════════════════════════════════════════════
         IDLE — formulario: cámara + rango de fechas
    ════════════════════════════════════════════════════════════ -->
    <div v-if="phase === 'idle'" class="max-w-xl space-y-4">
      <div class="card-standard p-4 space-y-4">
        <div class="text-[10px] font-semibold text-slate-400 uppercase tracking-wider">
          Procesamiento automático
        </div>
        <p class="text-xs text-slate-500">
          Elige una cámara ya calibrada y un rango de fechas: el sistema descarga las imágenes
          nuevas de Obscape, alinea el lote contra la más antigua y analiza cada imagen
          (segmentación, línea de costa, GeoJSON) — el mismo proceso que harías a mano, automático.
        </p>

        <div class="space-y-1">
          <label class="text-[10px] font-semibold text-slate-500 uppercase">Cámara</label>
          <select v-model.number="selectedCamId" class="w-full input-standard text-xs" :disabled="camerasLoading">
            <option v-for="cam in cameras" :key="cam.idx" :value="cam.idx" :disabled="!cam.calibrated">
              {{ cam.name }} {{ cam.calibrated ? '' : '— sin calibrar' }}
            </option>
          </select>
          <p v-if="selectedCamera && !selectedCamera.calibrated" class="text-[10px] text-red-500">
            Esta cámara no está calibrada todavía — calíbrala primero en "Calibración".
          </p>
        </div>

        <div class="grid grid-cols-2 gap-4">
          <div class="space-y-1">
            <label class="text-[10px] font-semibold text-slate-500 uppercase">Desde</label>
            <input type="date" v-model="fromDate" :max="toDate" class="w-full input-standard text-xs">
          </div>
          <div class="space-y-1">
            <label class="text-[10px] font-semibold text-slate-500 uppercase">Hasta</label>
            <input type="date" v-model="toDate" :min="fromDate" :max="today" class="w-full input-standard text-xs">
          </div>
        </div>

        <label class="flex items-center gap-2 text-xs text-slate-500 cursor-pointer">
          <input type="checkbox" v-model="autoExportGeojson" class="rounded border-slate-300">
          Exportar GeoJSON automáticamente al terminar
        </label>

        <button @click="start"
                :disabled="!selectedCamera?.calibrated"
                class="btn-standard w-full justify-center py-3">
          Iniciar procesamiento automático
        </button>
      </div>
    </div>

    <!-- ════════════════════════════════════════════════════════════
         RUNNING — progreso por fase
    ════════════════════════════════════════════════════════════ -->
    <div v-else-if="phase === 'running'" class="flex flex-col items-center justify-center h-64 space-y-4 p-5">
      <div class="text-sm font-semibold text-slate-700">
        {{ STEP_LABELS[jobSummary.status] || jobSummary.status }}
      </div>
      <div v-if="jobSummary.step" class="text-xs text-slate-500">{{ jobSummary.step }}</div>

      <div class="w-full max-w-md bg-slate-100 rounded-full h-3 overflow-hidden">
        <div class="h-3 bg-blue-600 rounded-full transition-all duration-500"
             :style="{ width: jobSummary.progress.total > 0
               ? `${(jobSummary.progress.current / jobSummary.progress.total * 100).toFixed(1)}%`
               : (jobSummary.status === 'downloading' ? '15%' : '0%') }">
        </div>
      </div>

      <div v-if="jobSummary.progress.total > 0" class="text-xs text-slate-500 font-mono">
        {{ jobSummary.progress.current }} / {{ jobSummary.progress.total }} imágenes
      </div>

      <div class="flex space-x-6 text-[10px] text-slate-400 uppercase tracking-wider">
        <span :class="{ 'text-blue-600 font-semibold': jobSummary.status === 'downloading' }">1. Descarga</span>
        <span :class="{ 'text-blue-600 font-semibold': jobSummary.status === 'aligning' }">2. Alineación</span>
        <span :class="{ 'text-blue-600 font-semibold': jobSummary.status === 'analyzing' }">3. Análisis</span>
      </div>
    </div>

    <!-- ════════════════════════════════════════════════════════════
         DONE — resumen + tabla de resultados
    ════════════════════════════════════════════════════════════ -->
    <div v-else-if="phase === 'done'" class="space-y-4">
      <div v-if="jobSummary.status === 'error'" class="card-standard p-4 border-red-200">
        <div class="text-sm font-semibold text-red-600">Error en el procesamiento</div>
        <div class="text-xs text-slate-500 mt-1">{{ jobSummary.error }}</div>
      </div>

      <div v-else class="card-standard p-4 space-y-1">
        <div class="text-sm font-semibold text-slate-700">{{ jobSummary.step }}</div>
        <div class="flex space-x-4 text-xs text-slate-500">
          <span>Descargadas: <strong class="text-slate-700">{{ jobSummary.downloaded }}</strong></span>
          <span>OK: <strong class="text-emerald-600">{{ jobSummary.counts.ok }}</strong></span>
          <span>Rechazadas: <strong class="text-amber-600">{{ jobSummary.counts.rejected }}</strong></span>
          <span>Errores: <strong class="text-red-600">{{ jobSummary.counts.errors }}</strong></span>
        </div>
      </div>

      <div v-if="results.length" class="card-standard overflow-hidden">
        <div class="card-header uppercase tracking-wider text-[10px] flex items-center justify-between">
          <span>Resultados por imagen</span>
          <button @click="exportGeoJson" class="text-blue-500 hover:underline normal-case font-medium">
            Exportar GeoJSON de esta cámara
          </button>
        </div>
        <table class="w-full text-xs">
          <thead>
            <tr class="text-[10px] text-slate-400 uppercase tracking-wider border-b border-slate-100">
              <th class="text-left px-4 py-2">Imagen</th>
              <th class="text-left px-4 py-2">Alineación</th>
              <th class="text-left px-4 py-2">Confianza</th>
              <th class="text-left px-4 py-2">Área seca (m²)</th>
              <th class="text-left px-4 py-2">Estado</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="r in results" :key="r.filename" class="border-b border-slate-50 last:border-0">
              <td class="px-4 py-2 font-mono text-[11px] text-slate-600 truncate max-w-[220px]">
                {{ r.filename }}<span v-if="r.is_base" class="ml-1.5 text-[9px] font-semibold bg-blue-100 text-blue-700 px-1.5 py-0.5 rounded">BASE</span>
              </td>
              <td class="px-4 py-2 text-slate-500">{{ r.align_status || '—' }}</td>
              <td class="px-4 py-2 text-slate-500">{{ r.confidence ? r.confidence.toFixed(2) : '—' }}</td>
              <td class="px-4 py-2 text-slate-500">{{ r.dry_area_m2 ? r.dry_area_m2.toLocaleString('es-ES') : '—' }}</td>
              <td class="px-4 py-2">
                <span class="inline-flex items-center gap-1.5 text-[10px] font-semibold uppercase">
                  <span class="w-1.5 h-1.5 rounded-full" :class="rowStatus(r).color"></span>
                  {{ rowStatus(r).label }}
                </span>
                <span v-if="r.reject_reason || r.error" class="block text-[10px] text-slate-400 mt-0.5">
                  {{ r.error || r.reject_reason }}
                </span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <div v-else class="card-standard p-4 text-xs text-slate-400 italic">
        No había imágenes nuevas en ese rango de fechas.
      </div>

      <button @click="reset" class="btn-secondary">Nuevo procesamiento</button>
    </div>
  </div>

  <!-- ════════════════════════════════════════════════════════════
       SIDEBAR — estado por cámara + log de actividad de Auto Mode
  ════════════════════════════════════════════════════════════ -->
  <div class="space-y-4">
    <div class="card-standard overflow-hidden">
      <div class="card-header uppercase tracking-wider text-[10px]">Estado por cámara</div>
      <div class="divide-y divide-slate-50 max-h-64 overflow-y-auto">
        <div v-for="cam in cameras" :key="cam.idx"
             class="px-4 py-2 flex items-center justify-between text-xs">
          <span class="text-slate-600 truncate">{{ cam.name }}</span>
          <span class="inline-flex items-center gap-1.5 text-[9px] font-semibold uppercase shrink-0 ml-2">
            <span class="w-1.5 h-1.5 rounded-full" :class="cam.calibrated ? 'bg-emerald-500' : 'bg-slate-300'"></span>
            {{ cam.calibrated ? `RMSE ${cam.rmse_m?.toFixed(2) ?? '—'} m` : 'Sin calibrar' }}
          </span>
        </div>
        <p v-if="!cameras.length" class="px-4 py-3 text-[10px] text-slate-400 italic">Cargando cámaras…</p>
      </div>
    </div>

    <div class="card-standard overflow-hidden">
      <div class="card-header uppercase tracking-wider text-[10px]">Actividad de Auto Mode</div>
      <div class="divide-y divide-slate-50 max-h-80 overflow-y-auto font-mono">
        <div v-for="(l, i) in autoModeLogs" :key="i" class="px-3 py-1.5 text-[10px] leading-tight">
          <span class="text-slate-300">{{ l.time }}</span>
          <span :class="logColor(l.type)">{{ l.msg }}</span>
        </div>
        <p v-if="!autoModeLogs.length" class="px-3 py-3 text-[10px] text-slate-400 italic">Sin actividad de Auto Mode todavía.</p>
      </div>
    </div>
  </div>
  </div>
</template>
