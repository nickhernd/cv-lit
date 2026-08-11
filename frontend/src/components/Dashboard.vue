<script setup>
import { ref, onMounted, computed, watch } from 'vue'
import { API_BASE } from '../api.js'
import Map from './Map.vue'

const emit = defineEmits(['select-camera', 'notify'])
const API = API_BASE

const data = ref(null)
const error = ref(null)
const geojson = ref(null)
const historicalData = ref([])
const cameraDetails = ref([])   // /api/cameras — trae rmse_m, para derivar tareas reales
const logs = ref([])            // /api/logs — para "Actividad reciente"
const histCam = ref(null)       // null = todas las cámaras combinadas (media diaria)

async function fetchHistorical() {
  const url = `${API}/api/historical-data` + (histCam.value ? `?cam_id=${histCam.value}` : '')
  try {
    const res = await fetch(url)
    historicalData.value = res.ok ? await res.json() : []
  } catch (err) { historicalData.value = [] }
}
watch(histCam, fetchHistorical)

async function fetchData() {
  try {
    const [dashRes, geoRes, camRes, logRes] = await Promise.all([
      fetch(`${API}/api/dashboard`),
      fetch(`${API}/api/geojson`),
      fetch(`${API}/api/cameras`),
      fetch(`${API}/api/logs`)
    ])

    if (!dashRes.ok || !geoRes.ok) throw new Error('Error al conectar con el servidor')

    data.value = await dashRes.json()
    geojson.value = await geoRes.json()
    cameraDetails.value = camRes.ok ? await camRes.json() : []
    logs.value = logRes.ok ? await logRes.json() : []
    await fetchHistorical()
  } catch (err) {
    error.value = err.message
    emit('notify', 'Fallo en la sincronización con el servidor', 'error')
  }
}

// Últimos eventos reales del sistema, más recientes primero.
const recentActivity = computed(() => logs.value.slice(-6).reverse())

// Tareas derivadas del estado real de las cámaras — nunca inventadas: solo
// "hay que calibrar" (sin calibrar), "revisar" (RMSE por encima de umbral) o
// "sin capturas recientes" (frescura de datos, a partir de last_image_ts que
// ya devuelve /api/cameras — sin inventar ningún dato nuevo).
const RMSE_REVIEW_THRESHOLD_M = 1.0
const STALE_HOURS_THRESHOLD = 48
const upcomingTasks = computed(() => {
  const tasks = []
  const nowSec = Date.now() / 1000
  for (const cam of cameraDetails.value) {
    if (!cam.calibrated) tasks.push({ label: `Calibrar ${cam.id}`, severity: 'warn' })
    else if (cam.rmse_m != null && cam.rmse_m > RMSE_REVIEW_THRESHOLD_M) {
      tasks.push({ label: `Revisar ${cam.id} — RMSE ${cam.rmse_m.toFixed(2)} m`, severity: 'err' })
    }
    if (cam.last_image_ts != null) {
      const hoursSince = (nowSec - cam.last_image_ts) / 3600
      if (hoursSince > STALE_HOURS_THRESHOLD) {
        tasks.push({ label: `${cam.id} sin capturas hace ${Math.floor(hoursSince / 24)} día(s)`, severity: 'warn' })
      }
    }
  }
  return tasks
})

function printReport() {
  window.print()
}

function downloadCSV() {
  const headers = ['Fecha', 'Area_m2']
  const rows = historicalData.value.map(d => `${d.date},${d.area}`)
  const csvContent = "data:text/csv;charset=utf-8," + [headers.join(','), ...rows].join("\n")
  const link = document.createElement("a")
  link.setAttribute("href", encodeURI(csvContent))
  link.setAttribute("download", "historico_costa_ua.csv")
  document.body.appendChild(link)
  link.click()
  link.remove()
  emit('notify', 'Archivo CSV generado con éxito', 'success')
}

// Informe completo (backend): una fila por análisis aceptado, con cámara,
// imagen y confianza — a diferencia de downloadCSV() arriba, que solo exporta
// la media diaria global que alimenta el gráfico.
function downloadReportCSV() {
  window.open(`${API}/api/report?format=csv`, '_blank')
}
async function downloadReportJSON() {
  try {
    const res = await fetch(`${API}/api/report?format=json`)
    if (!res.ok) throw new Error('HTTP ' + res.status)
    const data = await res.json()
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = 'cv-lit_informe_completo.json'
    link.click()
    URL.revokeObjectURL(url)
    emit('notify', 'Informe JSON descargado', 'success')
  } catch (err) {
    emit('notify', 'Error al descargar el informe', 'error')
  }
}

// El backend ya no genera una fila por día fijo (era relleno aleatorio) —
// ahora devuelve solo los días con captura real, que pueden ser muchos más
// de 30 según lo que lleve acumulado el histórico. Para el gráfico "(30
// días)" nos quedamos con los últimos 30 puntos reales; el CSV exporta el
// histórico completo.
const chartData = computed(() => historicalData.value.slice(-30))

// SVG Chart Helpers
const chartPoints = computed(() => {
  if (!chartData.value.length) return ""
  const width = 800
  const height = 150
  const max = Math.max(...chartData.value.map(d => d.area))
  const min = Math.min(...chartData.value.map(d => d.area))
  const range = (max - min) || 1

  return chartData.value.map((d, i) => {
    const x = chartData.value.length > 1 ? (i / (chartData.value.length - 1)) * width : width / 2
    const y = height - ((d.area - min) / range) * height
    return `${x},${y}`
  }).join(" ")
})

// Punto final destacado del sparkline: el dato más reciente es el que
// importa de un vistazo, así que se resalta en vez de dejarlo perdido
// en la línea (mismo cuidado que se le pone a la tipografía).
const lastPoint = computed(() => {
  if (!chartPoints.value) return null
  const parts = chartPoints.value.trim().split(' ')
  const [x, y] = parts[parts.length - 1].split(',').map(Number)
  return { x, y }
})

// Variación dentro de la ventana visible (primer punto vs. último): sube =
// más arena seca (acreción), baja = menos (erosión). Con menos de 2 puntos
// no hay variación que mostrar todavía.
const trend = computed(() => {
  if (chartData.value.length < 2) return null
  const first = chartData.value[0].area
  const last = chartData.value[chartData.value.length - 1].area
  const delta = last - first
  const pct = first !== 0 ? (delta / first) * 100 : 0
  return { delta, pct, up: delta >= 0 }
})

onMounted(fetchData)
</script>

<template>
  <div v-if="error" class="p-5">
    <div class="card-standard border-red-200 bg-red-50 p-4 text-red-700">
      <h2 class="text-lg font-semibold mb-2 text-red-800">Error de Conexión</h2>
      <p class="text-sm mb-4">{{ error }}</p>
      <button @click="fetchData" class="btn-standard bg-red-600 hover:bg-red-700">Reintentar</button>
    </div>
  </div>
  
  <div v-else-if="data" class="space-y-4 animate-fade-in">
    <div class="flex justify-end items-center gap-3 no-print">
      <span class="text-[11px] font-medium text-slate-400">Guardamar del Segura · Red Obscape</span>
      <button @click="downloadReportCSV" class="btn-secondary" title="Un análisis por fila: cámara, imagen, área seca, confianza">
        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M12 4v12m0 0l-4-4m4 4l4-4M4 20h16" stroke-width="2"/></svg>
        <span>Informe CSV</span>
      </button>
      <button @click="downloadReportJSON" class="btn-secondary" title="Mismo informe completo en JSON">
        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M12 4v12m0 0l-4-4m4 4l4-4M4 20h16" stroke-width="2"/></svg>
        <span>Informe JSON</span>
      </button>
      <button @click="printReport" class="btn-secondary">
        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M17 17h2a2 2 0 002-2v-4a2 2 0 00-2-2H5a2 2 0 00-2 2v4a2 2 0 00-2 2h2m2 4h10a2 2 0 002-2v-4H5v4a2 2 0 002 2z" stroke-width="2"/><path d="M17 9V5a2 2 0 00-2-2H9a2 2 0 00-2 2v4" stroke-width="2"/></svg>
        <span>Imprimir Reporte</span>
      </button>
    </div>

    <!-- Print-only Header -->
    <div class="print-only text-center border-b-2 border-slate-900 pb-4 mb-8">
       <h1 class="text-3xl font-semibold uppercase tracking-tighter">Reporte Operativo de Litoral</h1>
       <p class="text-sm font-semibold text-slate-500 uppercase tracking-wider">Generado el {{ new Date().toLocaleDateString() }} - CV-LIT UA Engineering</p>
    </div>

    <!-- Resumen: igual patrón que el mock — 3 cifras clave de un vistazo -->
    <div class="grid grid-cols-3 gap-4">
      <div class="card-standard p-4">
        <p class="text-[10px] font-semibold text-slate-400 uppercase tracking-wider mb-1">Cámaras calibradas</p>
        <p class="text-xl font-mono font-medium text-slate-900 tabular-nums">{{ data.cameras_calibrated }} / {{ data.total_cameras }}</p>
      </div>
      <div class="card-standard p-4">
        <p class="text-[10px] font-semibold text-slate-400 uppercase tracking-wider mb-1">Imágenes procesadas</p>
        <p class="text-xl font-mono font-medium text-slate-900 tabular-nums">{{ data.images_processed.toLocaleString() }}</p>
      </div>
      <div class="card-standard p-4">
        <p class="text-[10px] font-semibold text-slate-400 uppercase tracking-wider mb-1">Área seca media</p>
        <p class="text-xl font-mono font-medium text-slate-900 tabular-nums">{{ data.avg_dry_area }} <span class="text-sm text-slate-400">m²</span></p>
      </div>
    </div>

    <!-- Estado de cámaras: rejilla escaneable, cada tarjeta lleva a su calibración -->
    <div class="card-standard overflow-hidden">
      <div class="card-header uppercase tracking-wider text-[10px]">Estado de cámaras</div>
      <div class="p-4 grid grid-cols-2 md:grid-cols-3 gap-3">
        <button v-for="cam in data.cameras" :key="cam.idx" @click="emit('select-camera', cam.idx)"
                class="text-left border border-slate-200 rounded-md p-3 hover:border-blue-300 hover:bg-slate-50 transition-colors">
          <div class="flex items-center justify-between mb-2">
            <span class="text-[11px] font-semibold uppercase text-slate-700">{{ cam.name }}</span>
            <span class="w-1.5 h-1.5 rounded-full shrink-0" :class="cam.status === 'Sin calibrar' ? 'bg-slate-300' : 'bg-emerald-500'"></span>
          </div>
          <div class="flex items-center gap-2">
            <span class="badge" :class="cam.status === 'Sin calibrar' ? 'badge-neutral' : 'badge-ok'">{{ cam.status }}</span>
            <span class="text-[10px] text-slate-400 font-mono">{{ cam.images }} imgs</span>
          </div>
        </button>
      </div>
    </div>

    <!-- Actividad reciente + Próximas tareas, como en el mock -->
    <div class="grid grid-cols-1 lg:grid-cols-2 gap-4">
      <div class="card-standard overflow-hidden">
        <div class="card-header uppercase tracking-wider text-[10px]">Actividad reciente</div>
        <div class="divide-y divide-slate-100">
          <div v-for="(log, i) in recentActivity" :key="i" class="px-3.5 py-2 flex items-start gap-2.5">
            <span class="w-1.5 h-1.5 rounded-full mt-1.5 shrink-0"
                  :class="log.type === 'error' ? 'bg-red-500' : (log.type === 'success' ? 'bg-emerald-500' : 'bg-blue-500')"></span>
            <div class="min-w-0">
              <p class="text-[10px] font-mono text-slate-400">{{ log.time }}</p>
              <p class="text-xs text-slate-700">{{ log.msg }}</p>
            </div>
          </div>
          <p v-if="!recentActivity.length" class="px-3.5 py-6 text-xs text-slate-400 text-center">Sin actividad reciente</p>
        </div>
      </div>
      <div class="card-standard overflow-hidden">
        <div class="card-header uppercase tracking-wider text-[10px]">Próximas tareas</div>
        <div class="divide-y divide-slate-100">
          <div v-for="(task, i) in upcomingTasks" :key="i" class="px-3.5 py-2.5 flex items-center justify-between">
            <span class="text-xs text-slate-700">{{ task.label }}</span>
            <span class="w-1.5 h-1.5 rounded-full shrink-0" :class="task.severity === 'err' ? 'bg-red-500' : 'bg-amber-500'"></span>
          </div>
          <p v-if="!upcomingTasks.length" class="px-3.5 py-6 text-xs text-slate-400 text-center">Todo al día — sin tareas pendientes</p>
        </div>
      </div>
    </div>

    <!-- Localización ROI -->
    <div class="card-standard overflow-hidden">
      <div class="card-header flex justify-between items-center uppercase tracking-wider text-[10px]">
        <span>Localización ROI</span>
        <button @click="fetchData" class="text-blue-600 hover:text-blue-800 text-[10px] font-semibold uppercase no-print">Sincronizar</button>
      </div>
      <!-- Altura FIJA, no min-height: Leaflet necesita que su contenedor tenga
           una altura ya resuelta al montarse — con solo min-height (altura
           auto por defecto) el mapa medía 0px y quedaba en blanco. -->
      <div class="h-[320px]">
        <Map :geojsonData="geojson" @select-camera="emit('select-camera', $event)" />
      </div>
    </div>

    <!-- HISTORICAL CHART -->
    <div class="card-standard overflow-hidden">
       <div class="card-header flex justify-between items-center uppercase tracking-wider text-[10px] gap-3 flex-wrap">
          <div class="flex items-center gap-3">
            <span>Tendencia Histórica: Área Seca (30 días)</span>
            <select v-model="histCam" class="input-standard py-0.5 text-[10px] normal-case font-medium no-print">
              <option :value="null">Todas las cámaras (media)</option>
              <option v-for="cam in cameraDetails" :key="cam.idx" :value="cam.idx">{{ cam.name }}</option>
            </select>
            <span v-if="trend" class="badge no-print" :class="trend.up ? 'badge-ok' : 'badge-err'">
              {{ trend.up ? '▲' : '▼' }} {{ Math.abs(trend.pct).toFixed(1) }}% en la ventana
            </span>
          </div>
          <button @click="downloadCSV" class="text-blue-600 hover:text-blue-800 text-[10px] font-semibold no-print uppercase">Descargar CSV</button>
       </div>
       <div v-if="chartData.length" class="p-4 bg-white">
          <div class="relative h-[180px] w-full flex flex-col justify-end">
             <svg viewBox="0 0 800 150" class="w-full h-full overflow-visible" preserveAspectRatio="none">
                <defs>
                   <linearGradient id="chartGradient" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stop-color="#c98f3e" stop-opacity="0.18" />
                      <stop offset="100%" stop-color="#c98f3e" stop-opacity="0" />
                   </linearGradient>
                </defs>
                <!-- Rejilla horizontal tenue: da referencia de escala sin competir con la línea -->
                <line v-for="gy in [0, 50, 100, 150]" :key="gy" x1="0" :y1="gy" x2="800" :y2="gy" stroke="#e2e8f0" stroke-width="1" vector-effect="non-scaling-stroke" />
                <path v-if="chartPoints" :d="`M0,150 L${chartPoints} L800,150 Z`" fill="url(#chartGradient)" />
                <polyline v-if="chartPoints" fill="none" stroke="#c98f3e" stroke-width="2" :points="chartPoints" stroke-linejoin="round" stroke-linecap="round" vector-effect="non-scaling-stroke" />
                <circle v-if="lastPoint" :cx="lastPoint.x" :cy="lastPoint.y" r="4" fill="#c98f3e" stroke="white" stroke-width="1.5" vector-effect="non-scaling-stroke" />
             </svg>
             <div class="flex justify-between text-[9px] font-semibold text-slate-400 pt-4 uppercase border-t border-slate-100 mt-2">
                <span>{{ chartData[0]?.date }}</span>
                <span>{{ chartData[Math.floor(chartData.length/2)]?.date }}</span>
                <span>{{ chartData[chartData.length - 1]?.date }}</span>
             </div>
          </div>
       </div>
       <p v-else class="px-4 py-8 text-xs text-slate-400 text-center">
         Todavía no hay histórico real de área seca — se irá llenando con cada análisis (paso "Resultados").
       </p>
    </div>

  </div>

  <div v-else class="h-64 flex flex-col items-center justify-center text-slate-400">
    <div class="animate-spin rounded-full h-8 w-8 border-2 border-slate-200 border-t-blue-600 mb-4"></div>
    <p class="text-sm font-semibold uppercase tracking-wider">Sincronizando Sistema...</p>
  </div>
</template>
