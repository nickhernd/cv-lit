<script setup>
import { ref, onMounted, computed } from 'vue'
import Map from './Map.vue'

const emit = defineEmits(['select-camera', 'notify'])

const data = ref(null)
const error = ref(null)
const geojson = ref(null)
const historicalData = ref([])

async function fetchData() {
  try {
    const [dashRes, geoRes, histRes] = await Promise.all([
      fetch('http://localhost:8000/api/dashboard'),
      fetch('http://localhost:8000/api/geojson'),
      fetch('http://localhost:8000/api/historical-data')
    ])
    
    if (!dashRes.ok || !geoRes.ok || !histRes.ok) throw new Error('Error al conectar con el servidor')
    
    data.value = await dashRes.json()
    geojson.value = await geoRes.json()
    historicalData.value = await histRes.json()
  } catch (err) {
    error.value = err.message
    emit('notify', 'Fallo en la sincronización con el servidor', 'error')
  }
}

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
  emit('notify', 'Archivo CSV generado con éxito', 'success')
}

// SVG Chart Helpers
const chartPoints = computed(() => {
  if (!historicalData.value.length) return ""
  const width = 800
  const height = 150
  const max = Math.max(...historicalData.value.map(d => d.area))
  const min = Math.min(...historicalData.value.map(d => d.area))
  const range = (max - min) || 1
  
  return historicalData.value.map((d, i) => {
    const x = (i / (historicalData.value.length - 1)) * width
    const y = height - ((d.area - min) / range) * height
    return `${x},${y}`
  }).join(" ")
})

onMounted(fetchData)
</script>

<template>
  <div v-if="error" class="p-8">
    <div class="card-standard border-red-200 bg-red-50 p-6 text-red-700">
      <h2 class="text-lg font-bold mb-2 text-red-800">Error de Conexión</h2>
      <p class="text-sm mb-4">{{ error }}</p>
      <button @click="fetchData" class="btn-standard bg-red-600 hover:bg-red-700">Reintentar</button>
    </div>
  </div>
  
  <div v-else-if="data" class="space-y-8 animate-fade-in">
    <div class="flex justify-between items-center border-b border-slate-200 pb-4">
      <h1 class="text-xl font-semibold text-slate-900 tracking-tight">Vista General del Sistema</h1>
      <div class="flex items-center space-x-4">
        <button @click="printReport" class="btn-secondary flex items-center space-x-2 py-1.5 no-print">
          <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M17 17h2a2 2 0 002-2v-4a2 2 0 00-2-2H5a2 2 0 00-2 2v4a2 2 0 00-2 2h2m2 4h10a2 2 0 002-2v-4H5v4a2 2 0 002 2z" stroke-width="2"/><path d="M17 9V5a2 2 0 00-2-2H9a2 2 0 00-2 2v4" stroke-width="2"/></svg>
          <span>Imprimir Reporte</span>
        </button>
        <div class="flex items-center space-x-2 text-xs font-bold text-slate-500 uppercase tracking-widest no-print">
          <span>Guardamar del Segura</span>
          <span class="text-slate-300">/</span>
          <span class="text-blue-600 font-bold">Red Obscape</span>
        </div>
      </div>
    </div>

    <!-- Print-only Header -->
    <div class="print-only text-center border-b-2 border-slate-900 pb-4 mb-8">
       <h1 class="text-3xl font-bold uppercase tracking-tighter">Reporte Operativo de Litoral</h1>
       <p class="text-sm font-bold text-slate-500 uppercase tracking-widest">Generado el {{ new Date().toLocaleDateString() }} - CV-LIT UA Engineering</p>
    </div>

    <!-- TELEMETRY GRID (Deshabilitado temporalmente)
    <div class="grid grid-cols-2 md:grid-cols-4 gap-6">
      <div v-for="(val, label) in { 'Carga CPU': '24.2%', 'RAM': '4.8 GB', 'Almacén': '1.2 TB', 'Latencia': 'Estable' }" :key="label"
           class="card-standard p-4 flex flex-col justify-center shadow-sm">
        <p class="text-[10px] font-bold text-slate-400 uppercase mb-1">{{ label }}</p>
        <p class="text-xl font-bold text-slate-900">{{ val }}</p>
      </div>
    </div>
    -->

    <!-- MAIN METRICS -->
    <div class="grid grid-cols-1 lg:grid-cols-3 gap-8">
      <div class="lg:col-span-1 space-y-6">
        <div class="card-standard overflow-hidden shadow-sm">
          <div class="card-header uppercase tracking-wider text-[10px]">Estado de Calibración</div>
          <div class="p-6">
            <div class="flex items-baseline space-x-2 mb-4">
              <span class="text-4xl font-bold text-slate-900 tabular-nums">{{ data.cameras_calibrated }}</span>
              <span class="text-slate-400 font-bold">/ {{ data.total_cameras }}</span>
            </div>
            <div class="h-2 w-full bg-slate-100 rounded-full overflow-hidden">
              <div class="h-full bg-blue-600" :style="{ width: (data.cameras_calibrated / data.total_cameras) * 100 + '%' }"></div>
            </div>
            <p class="text-xs text-slate-500 mt-4 font-medium uppercase tracking-tight">Estaciones calibradas y operativas.</p>
          </div>
        </div>

        <div class="card-standard overflow-hidden shadow-sm">
          <div class="card-header uppercase tracking-wider text-[10px]">Métricas de Procesamiento</div>
          <div class="p-6 space-y-6">
            <div>
              <p class="text-[10px] font-bold text-slate-400 uppercase mb-1">Fotogramas Hoy</p>
              <p class="text-2xl font-bold text-slate-900 tabular-nums">{{ data.images_processed.toLocaleString() }}</p>
            </div>
            <div class="pt-4 border-t border-slate-100">
              <p class="text-[10px] font-bold text-slate-400 uppercase mb-1">Área Seca Promedio</p>
              <div class="flex items-baseline space-x-1">
                <span class="text-2xl font-bold text-slate-900 tabular-nums">{{ data.avg_dry_area }}</span>
                <span class="text-sm font-bold text-slate-400 uppercase">m²</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div class="lg:col-span-2">
        <div class="card-standard h-full flex flex-col overflow-hidden shadow-sm">
          <div class="card-header flex justify-between items-center uppercase tracking-wider text-[10px]">
            <span>Localización ROI</span>
            <button @click="fetchData" class="text-blue-600 hover:text-blue-800 text-[10px] font-bold uppercase no-print">Sincronizar</button>
          </div>
          <div class="flex-1 min-h-[350px]">
            <Map :geojsonData="geojson" />
          </div>
        </div>
      </div>
    </div>

    <!-- HISTORICAL CHART -->
    <div class="card-standard overflow-hidden shadow-sm">
       <div class="card-header flex justify-between items-center uppercase tracking-wider text-[10px]">
          <span>Tendencia Histórica: Área Seca (30 días)</span>
          <button @click="downloadCSV" class="text-blue-600 hover:text-blue-800 text-[10px] font-bold no-print uppercase">Descargar CSV</button>
       </div>
       <div class="p-6 bg-white">
          <div class="relative h-[180px] w-full flex flex-col justify-end">
             <svg viewBox="0 0 800 150" class="w-full h-full overflow-visible" preserveAspectRatio="none">
                <defs>
                   <linearGradient id="chartGradient" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stop-color="#3b82f6" stop-opacity="0.2" />
                      <stop offset="100%" stop-color="#3b82f6" stop-opacity="0" />
                   </linearGradient>
                </defs>
                <polyline v-if="chartPoints" fill="none" stroke="#2563eb" stroke-width="2" :points="chartPoints" stroke-linejoin="round" stroke-linecap="round" />
                <path v-if="chartPoints" :d="`M0,150 L${chartPoints} L800,150 Z`" fill="url(#chartGradient)" />
             </svg>
             <div class="flex justify-between text-[9px] font-bold text-slate-400 pt-4 uppercase border-t border-slate-100 mt-2">
                <span>{{ historicalData[0]?.date }}</span>
                <span>{{ historicalData[Math.floor(historicalData.length/2)]?.date }}</span>
                <span>Hoy</span>
             </div>
          </div>
       </div>
    </div>

    <!-- STATIONS AND AVAILABILITY -->
    <div class="grid grid-cols-1 lg:grid-cols-3 gap-8">
      <div class="lg:col-span-2">
        <div class="card-standard overflow-hidden shadow-sm">
          <div class="card-header uppercase tracking-wider text-[10px]">Estaciones de Visión</div>
          <div class="overflow-x-auto">
            <table class="w-full text-left text-sm">
              <thead class="bg-slate-50/60 text-slate-500 font-semibold border-b border-slate-100">
                <tr>
                  <th class="px-6 py-3 uppercase tracking-widest text-[10px]">Nombre Estación</th>
                  <th class="px-6 py-3 uppercase tracking-widest text-[10px]">ID</th>
                  <th class="px-6 py-3 uppercase tracking-widest text-[10px]">Estado</th>
                  <th class="px-6 py-3 text-right uppercase tracking-widest text-[10px] no-print">Acciones</th>
                </tr>
              </thead>
              <tbody class="divide-y border-slate-100">
                <tr v-for="cam in data.cameras" :key="cam.id" class="hover:bg-slate-50 transition-colors text-slate-700">
                  <td class="px-6 py-4 font-bold uppercase text-[11px]">{{ cam.name }}</td>
                  <td class="px-6 py-4 text-slate-500 font-mono text-[10px]">{{ cam.id }}</td>
                  <td class="px-6 py-4">
                    <span :class="cam.status === 'Sin calibrar' ? 'bg-slate-100 text-slate-600 border-slate-200' : 'bg-emerald-100 text-emerald-800 border-emerald-200'"
                          class="px-2 py-0.5 rounded text-[9px] font-bold uppercase border shadow-sm">
                      {{ cam.status }}
                    </span>
                  </td>
                  <td class="px-6 py-4 text-right no-print">
                    <button @click="emit('select-camera', cam.idx)" class="text-blue-600 hover:underline font-bold text-[10px] uppercase tracking-tight">Gestionar</button>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>
      
      <div class="lg:col-span-1">
        <div class="card-standard overflow-hidden h-full shadow-sm">
           <div class="card-header uppercase tracking-wider text-[10px]">Disponibilidad Semanal</div>
           <div class="p-6 space-y-6">
              <div v-for="i in 4" :key="i" class="space-y-2">
                 <div class="flex justify-between text-[10px] font-bold uppercase tracking-tight">
                    <span class="text-slate-700">Cámara {{i}}</span>
                    <span class="text-blue-600">98.{{Math.floor(Math.random()*10)}}%</span>
                 </div>
                 <div class="flex space-x-0.5 h-6">
                    <div v-for="d in 7" :key="d" 
                         :class="Math.random() > 0.1 ? 'bg-emerald-500' : 'bg-red-500'"
                         class="flex-1 rounded shadow-inner"
                         :title="`Día -${8-d}`"></div>
                 </div>
              </div>
              <p class="text-[9px] text-slate-400 font-bold uppercase italic leading-tight">* Disponibilidad basada en fotogramas de control UA.</p>
           </div>
        </div>
      </div>
    </div>
  </div>

  <div v-else class="h-64 flex flex-col items-center justify-center text-slate-400">
    <div class="animate-spin rounded-full h-8 w-8 border-2 border-slate-200 border-t-blue-600 mb-4"></div>
    <p class="text-sm font-bold uppercase tracking-widest">Sincronizando Sistema...</p>
  </div>
</template>
