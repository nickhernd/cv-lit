<script setup>
import { ref, reactive, computed, watch, onUnmounted } from 'vue'

const props = defineProps({
  camId:       { type: Number, required: true },
  imageList:   { type: Array,  default: () => [] }, // [{filename, ...}]
  initialBase: { type: String, default: '' },       // imagen de referencia preseleccionada
})
const emit = defineEmits(['notify', 'committed', 'discard'])

const API = 'http://localhost:8000'

// ── Máquina de estados ───────────────────────────────────────────────────────
// idle → configuring → processing → reviewing → committed
const phase = ref('idle')

// ── Estado de configuración ─────────────────────────────────────────────────
const baseFilename  = ref('')
const selectedFiles = ref(new Set()) // Set de filenames a incluir en el lote

// ── Estado del job en curso ─────────────────────────────────────────────────
const jobId      = ref(null)
const jobSummary = reactive({ progress: { current: 0, total: 0 }, counts: {}, status: '' })
let pollInterval = null

// ── Estado de revisión ──────────────────────────────────────────────────────
const results       = ref([])   // array de { filename, status, inliers, mean_shift_px, approved }
const selected      = ref(null) // filename actualmente en detalle
const viewMode      = ref('diff') // 'original' | 'aligned' | 'diff' | 'blend'

// ── URLs de previsualización ────────────────────────────────────────────────
const imgTs = ref(Date.now()) // cache-buster

function previewUrl(mode, filename) {
  if (!jobId.value || !filename) return ''
  return `${API}/api/batch/${jobId.value}/preview/${mode}/${encodeURIComponent(filename)}?t=${imgTs.value}`
}

const selectedResult = computed(() => results.value.find(r => r.filename === selected.value))

const leftUrl = computed(() => {
  if (!selected.value) return ''
  return previewUrl('original', selected.value)
})

const rightUrl = computed(() => {
  if (!selected.value) return ''
  const modeMap = { aligned: 'aligned', diff: 'diff', blend: 'blend' }
  return previewUrl(modeMap[viewMode.value] || 'diff', selected.value)
})

// ── Helpers de estado ───────────────────────────────────────────────────────
function statusColor(r) {
  if (!r) return 'bg-slate-600'
  if (r.status === 'reference') return 'bg-blue-500'
  if (r.status === 'failed')    return 'bg-red-500'
  if (!r.approved)              return 'bg-amber-500'
  if (r.mean_shift_px > 3)      return 'bg-yellow-500'
  return 'bg-emerald-500'
}

function statusLabel(r) {
  if (!r) return '—'
  if (r.status === 'reference') return 'REF'
  if (r.status === 'failed') {
    const reasons = { no_features: 'SIN FT', low_matches: 'MATCHES', ransac_failed: 'RANSAC' }
    return reasons[r.fail_reason] || 'FAIL'
  }
  if (!r.approved)         return 'SKIP'
  if (r.mean_shift_px > 3) return `~${r.mean_shift_px}px`
  return r.used_mask ? 'OK·M' : 'OK'
}

function statusTooltip(r) {
  if (!r) return ''
  if (r.status === 'reference') return 'Imagen base de referencia'
  if (r.status === 'failed') {
    const msgs = {
      no_features:   'Sin suficientes features detectables en las zonas estables',
      low_matches:   `Pocos matches encontrados (${r.inliers}) — zonas muy distintas`,
      ransac_failed: `RANSAC no convergió (${r.inliers} inliers)`,
    }
    return msgs[r.fail_reason] || 'Alineación fallida'
  }
  const maskInfo = r.used_mask ? ' (zonas estables)' : ' (imagen completa)'
  return `${r.inliers} inliers · delta ${r.mean_shift_px}px${maskInfo}`
}

const approvedCount = computed(() =>
  results.value.filter(r => r.status !== 'failed' && r.approved).length
)
const failedCount = computed(() =>
  results.value.filter(r => r.status === 'failed').length
)
const skippedCount = computed(() =>
  results.value.filter(r => r.status !== 'failed' && !r.approved).length
)

// ── Fase: configuring ───────────────────────────────────────────────────────
function startConfiguring() {
  baseFilename.value  = props.initialBase || ''
  selectedFiles.value = new Set(props.imageList.map(i => i.filename))
  phase.value = 'configuring'
}

function toggleFile(fn) {
  const s = new Set(selectedFiles.value)
  s.has(fn) ? s.delete(fn) : s.add(fn)
  selectedFiles.value = s
}

function selectAll()   { selectedFiles.value = new Set(props.imageList.map(i => i.filename)) }
function deselectAll() { selectedFiles.value = new Set() }

// ── Fase: processing ────────────────────────────────────────────────────────
async function startBatch() {
  if (!baseFilename.value) {
    emit('notify', 'Selecciona una imagen base de referencia', 'error')
    return
  }
  if (selectedFiles.value.size < 2) {
    emit('notify', 'Selecciona al menos 2 imágenes', 'error')
    return
  }

  phase.value = 'processing'

  try {
    const res = await fetch(`${API}/api/batch/start`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        cam_id:           props.camId,
        base_filename:    baseFilename.value,
        image_filenames:  [...selectedFiles.value],
      }),
    })
    if (!res.ok) {
      const err = await res.json()
      throw new Error(err.detail || 'Error al iniciar batch')
    }
    const data = await res.json()
    jobId.value = data.job_id
    Object.assign(jobSummary, { progress: { current: 0, total: data.total }, status: 'processing' })
    _startPolling()
  } catch (e) {
    emit('notify', e.message, 'error')
    phase.value = 'configuring'
  }
}

function _startPolling() {
  pollInterval = setInterval(_poll, 800)
}

async function _poll() {
  if (!jobId.value) return
  try {
    const res  = await fetch(`${API}/api/batch/${jobId.value}/status`)
    const data = await res.json()
    Object.assign(jobSummary, data)

    if (data.status === 'ready') {
      clearInterval(pollInterval)
      await _loadResults()
      phase.value = 'reviewing'
    } else if (data.status === 'failed') {
      clearInterval(pollInterval)
      emit('notify', `Error en batch: ${data.error}`, 'error')
      phase.value = 'configuring'
    }
  } catch (e) { /* red intermitente, seguir intentando */ }
}

async function _loadResults() {
  const res  = await fetch(`${API}/api/batch/${jobId.value}/results`)
  const data = await res.json()
  results.value = data.items
  if (results.value.length > 0) {
    selected.value = results.value[0].filename
  }
  imgTs.value = Date.now()
}

// ── Fase: reviewing ─────────────────────────────────────────────────────────
async function toggleApproval(filename) {
  const r = results.value.find(r => r.filename === filename)
  if (!r || r.status === 'reference') return
  const newVal = !r.approved
  try {
    await fetch(`${API}/api/batch/${jobId.value}/approve/${encodeURIComponent(filename)}?approved=${newVal}`, {
      method: 'PATCH',
    })
    r.approved = newVal
  } catch (e) { emit('notify', 'Error al actualizar aprobación', 'error') }
}

// ── Commit ──────────────────────────────────────────────────────────────────
const committing = ref(false)

async function commitBatch() {
  if (approvedCount.value === 0) {
    emit('notify', 'No hay imágenes aprobadas para confirmar', 'error')
    return
  }
  committing.value = true
  try {
    const res  = await fetch(`${API}/api/batch/${jobId.value}/commit`, { method: 'POST' })
    const data = await res.json()
    if (!res.ok) throw new Error(data.detail)
    phase.value = 'committed'
    emit('notify', `Lote confirmado: ${data.committed} imágenes enviadas al módulo de marcación`, 'success')
    emit('committed', { jobId: jobId.value, committed: data.committed })
  } catch (e) {
    emit('notify', e.message, 'error')
  } finally {
    committing.value = false
  }
}

// ── Descartar ────────────────────────────────────────────────────────────────
async function discardJob() {
  if (jobId.value) {
    try {
      await fetch(`${API}/api/batch/${jobId.value}`, { method: 'DELETE' })
    } catch (_) { /* best effort */ }
  }
  _reset()
  emit('discard')
}

function _reset() {
  clearInterval(pollInterval)
  phase.value     = 'idle'
  jobId.value     = null
  results.value   = []
  selected.value  = null
  baseFilename.value = ''
}

onUnmounted(() => clearInterval(pollInterval))
</script>

<template>
  <!-- ════════════════════════════════════════════════════════════════
       IDLE — punto de entrada
  ════════════════════════════════════════════════════════════════ -->
  <div v-if="phase === 'idle'" class="flex flex-col items-center justify-center h-64 space-y-4">
    <div class="text-slate-400 text-sm">Alineación masiva de fotogramas</div>
    <button @click="startConfiguring"
            class="px-6 py-3 bg-blue-600 hover:bg-blue-700 text-white rounded-lg font-semibold text-sm transition-colors shadow">
      Iniciar lote de alineación
    </button>
  </div>

  <!-- ════════════════════════════════════════════════════════════════
       CONFIGURING — selección de base + imágenes
  ════════════════════════════════════════════════════════════════ -->
  <div v-else-if="phase === 'configuring'" class="flex flex-col h-full space-y-4">
    <!-- Header -->
    <div class="flex items-center justify-between">
      <h2 class="text-base font-bold text-slate-800">Configurar lote · CAM {{ camId }}</h2>
      <button @click="discardJob" class="text-xs text-slate-400 hover:text-red-500 transition-colors">
        Cancelar
      </button>
    </div>

    <!-- Imagen base -->
    <div class="bg-white rounded-lg border border-slate-200 p-4 space-y-2">
      <label class="text-xs font-bold text-slate-600 uppercase tracking-widest block">
        Imagen base de referencia
      </label>
      <select v-model="baseFilename"
              class="w-full text-sm border border-slate-200 rounded px-3 py-2 bg-slate-50 focus:outline-none focus:ring-2 focus:ring-blue-500">
        <option value="" disabled>— Seleccionar —</option>
        <option v-for="img in imageList" :key="img.filename" :value="img.filename">
          {{ img.filename }}
        </option>
      </select>
      <p class="text-[10px] text-slate-400">
        Todas las demás imágenes se alinearán respecto a esta referencia.
      </p>
    </div>

    <!-- Selección de imágenes -->
    <div class="bg-white rounded-lg border border-slate-200 p-4 flex-1 flex flex-col min-h-0 space-y-2">
      <div class="flex items-center justify-between">
        <label class="text-xs font-bold text-slate-600 uppercase tracking-widest">
          Imágenes en el lote ({{ selectedFiles.size }} / {{ imageList.length }})
        </label>
        <div class="flex space-x-2 text-[10px]">
          <button @click="selectAll"   class="text-blue-500 hover:underline">Todas</button>
          <button @click="deselectAll" class="text-slate-400 hover:underline">Ninguna</button>
        </div>
      </div>
      <div class="flex-1 overflow-y-auto space-y-1 pr-1 scrollbar-thin">
        <label v-for="img in imageList" :key="img.filename"
               class="flex items-center space-x-3 px-2 py-1.5 rounded hover:bg-slate-50 cursor-pointer text-sm"
               :class="img.filename === baseFilename ? 'bg-blue-50 border border-blue-200' : ''">
          <input type="checkbox"
                 :checked="selectedFiles.has(img.filename)"
                 @change="toggleFile(img.filename)"
                 class="rounded accent-blue-600" />
          <span class="flex-1 font-mono text-xs truncate text-slate-700">{{ img.filename }}</span>
          <span v-if="img.filename === baseFilename"
                class="text-[9px] font-bold bg-blue-600 text-white px-1.5 py-0.5 rounded">BASE</span>
        </label>
      </div>
    </div>

    <button @click="startBatch"
            :disabled="!baseFilename || selectedFiles.size < 2"
            class="w-full py-3 bg-blue-600 hover:bg-blue-700 disabled:bg-slate-300 disabled:cursor-not-allowed text-white rounded-lg font-semibold text-sm transition-colors shadow">
      Alinear {{ selectedFiles.size }} imágenes
    </button>
  </div>

  <!-- ════════════════════════════════════════════════════════════════
       PROCESSING — barra de progreso
  ════════════════════════════════════════════════════════════════ -->
  <div v-else-if="phase === 'processing'" class="flex flex-col items-center justify-center h-64 space-y-6 p-8">
    <div class="text-sm font-semibold text-slate-700">Alineando fotogramas…</div>

    <div class="w-full bg-slate-100 rounded-full h-3 overflow-hidden">
      <div class="h-3 bg-blue-600 rounded-full transition-all duration-500"
           :style="{ width: jobSummary.progress.total > 0
             ? `${(jobSummary.progress.current / jobSummary.progress.total * 100).toFixed(1)}%`
             : '0%' }">
      </div>
    </div>

    <div class="text-xs text-slate-500 font-mono">
      {{ jobSummary.progress.current }} / {{ jobSummary.progress.total }} imágenes
    </div>

    <div class="text-[10px] text-slate-400 text-center max-w-xs">
      SIFT + FLANN + RANSAC — los originales permanecen intactos hasta la confirmación del lote
    </div>
  </div>

  <!-- ════════════════════════════════════════════════════════════════
       REVIEWING — interfaz principal de validación
  ════════════════════════════════════════════════════════════════ -->
  <div v-else-if="phase === 'reviewing'" class="flex h-full min-h-0 gap-3">

    <!-- ── Panel izquierdo: filmstrip + métricas ─────────────────── -->
    <div class="w-56 flex flex-col min-h-0 space-y-3 shrink-0">
      <!-- Resumen del lote -->
      <div class="bg-white rounded-lg border border-slate-200 p-3 text-xs space-y-1.5">
        <div class="font-bold text-slate-700 uppercase tracking-widest text-[10px] mb-1">Resumen lote</div>
        <div class="flex justify-between">
          <span class="text-slate-500">Aprobadas</span>
          <span class="font-bold text-emerald-600">{{ approvedCount }}</span>
        </div>
        <div class="flex justify-between">
          <span class="text-slate-500">Omitidas</span>
          <span class="font-bold text-amber-600">{{ skippedCount }}</span>
        </div>
        <div class="flex justify-between">
          <span class="text-slate-500">Fallidas</span>
          <span class="font-bold text-red-600">{{ failedCount }}</span>
        </div>
      </div>

      <!-- Filmstrip -->
      <div class="flex-1 overflow-y-auto space-y-1 scrollbar-thin min-h-0">
        <button v-for="r in results" :key="r.filename"
                @click="selected = r.filename"
                :title="statusTooltip(r)"
                class="w-full flex items-center space-x-2 px-2 py-1.5 rounded text-left transition-colors"
                :class="selected === r.filename
                  ? 'bg-blue-600 text-white'
                  : 'hover:bg-slate-100 text-slate-700'">

          <!-- Indicador de estado -->
          <div class="w-2 h-2 rounded-full shrink-0" :class="statusColor(r)"></div>

          <!-- Nombre de archivo truncado -->
          <span class="flex-1 text-[10px] font-mono truncate min-w-0">{{ r.filename }}</span>

          <!-- Etiqueta compacta -->
          <span class="text-[9px] font-bold shrink-0" :class="selected === r.filename ? 'text-blue-200' : 'text-slate-400'">
            {{ statusLabel(r) }}
          </span>
        </button>
      </div>

      <!-- Botones de acción -->
      <div class="space-y-2 shrink-0">
        <button @click="commitBatch" :disabled="committing || approvedCount === 0"
                class="w-full py-2.5 bg-emerald-600 hover:bg-emerald-700 disabled:bg-slate-300 disabled:cursor-not-allowed text-white rounded-lg font-semibold text-xs transition-colors shadow">
          {{ committing ? 'Confirmando…' : `Confirmar lote (${approvedCount})` }}
        </button>
        <button @click="discardJob"
                class="w-full py-2 text-xs text-slate-400 hover:text-red-500 transition-colors">
          Descartar sin guardar
        </button>
      </div>
    </div>

    <!-- ── Panel derecho: visor de detalle ──────────────────────── -->
    <div class="flex-1 flex flex-col min-h-0 min-w-0 space-y-3">

      <!-- Toolbar del visor -->
      <div class="bg-white rounded-lg border border-slate-200 p-3 flex items-center justify-between shrink-0">
        <!-- Selector de modo -->
        <div class="flex space-x-1">
          <button v-for="m in [
              { key: 'diff',    label: 'Mapa delta' },
              { key: 'blend',   label: 'Blend 50/50' },
              { key: 'aligned', label: 'Alineada' },
            ]"
            :key="m.key"
            @click="viewMode = m.key"
            class="px-3 py-1.5 rounded text-xs font-semibold transition-colors"
            :class="viewMode === m.key
              ? 'bg-blue-600 text-white'
              : 'text-slate-500 hover:bg-slate-100'">
            {{ m.label }}
          </button>
        </div>

        <!-- Métricas de la imagen seleccionada -->
        <div v-if="selectedResult" class="flex items-center space-x-4 text-xs">
          <span class="font-mono text-slate-500 truncate max-w-[180px]">{{ selectedResult.filename }}</span>
          <div class="flex space-x-3">
            <div class="text-slate-500">
              Inliers: <span class="font-bold text-slate-800">{{ selectedResult.inliers }}</span>
            </div>
            <div class="text-slate-500">
              Delta:
              <span class="font-bold"
                    :class="selectedResult.mean_shift_px > 3 ? 'text-amber-600' : 'text-emerald-600'">
                {{ selectedResult.mean_shift_px === -1 ? 'N/A' : `${selectedResult.mean_shift_px} px` }}
              </span>
            </div>
            <div v-if="selectedResult.status !== 'reference'" class="flex items-center space-x-1">
              <button @click="toggleApproval(selectedResult.filename)"
                      class="px-2 py-0.5 rounded text-[10px] font-bold transition-colors"
                      :class="selectedResult.approved
                        ? 'bg-emerald-100 text-emerald-700 hover:bg-red-100 hover:text-red-700'
                        : 'bg-red-100 text-red-700 hover:bg-emerald-100 hover:text-emerald-700'">
                {{ selectedResult.approved ? '✓ Aprobada' : '✗ Omitida' }}
              </button>
            </div>
            <span v-else class="text-[10px] font-bold bg-blue-100 text-blue-700 px-2 py-0.5 rounded">
              REFERENCIA BASE
            </span>
          </div>
        </div>
      </div>

      <!-- Visor de imágenes -->
      <div v-if="selected" class="flex-1 min-h-0 bg-slate-900 rounded-lg overflow-hidden flex gap-px">

        <!-- Izquierda: siempre original -->
        <div class="flex-1 flex flex-col min-h-0">
          <div class="text-[9px] font-bold text-slate-400 uppercase tracking-widest px-2 py-1 bg-slate-800 shrink-0">
            Original
          </div>
          <div class="flex-1 overflow-hidden flex items-center justify-center bg-slate-900">
            <img :src="leftUrl" alt="original"
                 class="max-w-full max-h-full object-contain"
                 loading="lazy" />
          </div>
        </div>

        <!-- Divisor -->
        <div class="w-px bg-slate-700 shrink-0"></div>

        <!-- Derecha: modo seleccionado -->
        <div class="flex-1 flex flex-col min-h-0">
          <div class="text-[9px] font-bold uppercase tracking-widest px-2 py-1 bg-slate-800 shrink-0 flex items-center space-x-2">
            <span :class="{
              'text-red-400':    viewMode === 'diff',
              'text-blue-400':   viewMode === 'blend',
              'text-emerald-400': viewMode === 'aligned',
            }">
              {{ viewMode === 'diff' ? 'Mapa de delta (negro=OK · rojo=error · cian=bordes)' :
                 viewMode === 'blend' ? 'Blend 50/50 escala de grises' :
                 'Imagen alineada (staging)' }}
            </span>
          </div>
          <div class="flex-1 overflow-hidden flex items-center justify-center bg-slate-900">
            <img :src="rightUrl" alt="comparison"
                 class="max-w-full max-h-full object-contain"
                 loading="lazy" />
          </div>
        </div>
      </div>

      <!-- Leyenda del mapa delta -->
      <div v-if="viewMode === 'diff'" class="bg-slate-800 rounded-lg px-4 py-2 flex items-center space-x-6 text-[10px] text-slate-300 shrink-0">
        <span class="font-bold text-slate-400 uppercase tracking-widest">Leyenda delta:</span>
        <div class="flex items-center space-x-1.5">
          <div class="w-3 h-3 rounded bg-black border border-slate-600"></div>
          <span>Alineación perfecta</span>
        </div>
        <div class="flex items-center space-x-1.5">
          <div class="w-3 h-3 rounded" style="background:#ff4400"></div>
          <span>Error de intensidad</span>
        </div>
        <div class="flex items-center space-x-1.5">
          <div class="w-3 h-3 rounded" style="background:#ffffff"></div>
          <span>Error severo</span>
        </div>
        <div class="flex items-center space-x-1.5">
          <div class="w-3 h-3 rounded" style="background:#00ffff"></div>
          <span>Bordes divergentes</span>
        </div>
      </div>
    </div>
  </div>

  <!-- ════════════════════════════════════════════════════════════════
       COMMITTED — confirmación final
  ════════════════════════════════════════════════════════════════ -->
  <div v-else-if="phase === 'committed'" class="flex flex-col items-center justify-center h-64 space-y-4">
    <div class="w-12 h-12 bg-emerald-100 rounded-full flex items-center justify-center">
      <svg class="w-6 h-6 text-emerald-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M5 13l4 4L19 7"/>
      </svg>
    </div>
    <div class="text-sm font-semibold text-slate-700">Lote enviado al módulo de marcación</div>
    <div class="text-xs text-slate-400">Las imágenes alineadas están disponibles en la carpeta <code>aligned/</code> de la cámara.</div>
    <button @click="_reset(); emit('discard')"
            class="px-5 py-2 bg-slate-200 hover:bg-slate-300 text-slate-700 rounded-lg text-sm font-medium transition-colors">
      Nuevo lote
    </button>
  </div>
</template>

<style scoped>
.scrollbar-thin::-webkit-scrollbar { width: 3px; }
.scrollbar-thin::-webkit-scrollbar-track { background: transparent; }
.scrollbar-thin::-webkit-scrollbar-thumb { background: #cbd5e1; border-radius: 4px; }
</style>
