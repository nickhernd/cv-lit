<script setup>
import { ref, onMounted, computed } from 'vue'

const cameras = ref([])
const selectedCamId = ref(null)
const analyzing = ref(false)
const result = ref(null)

async function fetchCameras() {
  const res = await fetch('http://localhost:8000/api/dashboard')
  const data = await res.json()
  cameras.value = data.cameras
}

async function runAnalysis() {
  if (!selectedCamId.value) return
  analyzing.value = true
  result.value = null
  try {
    const res = await fetch(`http://localhost:8000/api/cameras/${selectedCamId.value}/analyze-roi`, {
      method: 'POST'
    })
    if (res.ok) {
      result.value = await res.json()
    } else {
      const err = await res.json()
      alert("Error: " + err.detail)
    }
  } catch (err) {
    alert("Error de conexión")
  } finally {
    analyzing.value = false
  }
}

function exportGeoJSON() {
  window.open('http://localhost:8000/api/geojson', '_blank')
}

onMounted(fetchCameras)

const resultImageUrl = computed(() => {
  if (!result.value) return null
  return `http://localhost:8000/api/cameras/${selectedCamId.value}/analysis-result?t=${Date.now()}`
})
</script>

<template>
  <div class="p-12 max-w-7xl mx-auto animate-fade-in">
    <header class="mb-12 flex justify-between items-end">
      <div>
        <h1 class="text-2xl font-bold text-slate-900 tracking-tight">Análisis ROI</h1>
        <p class="text-sm text-slate-500 mt-1">Detección de Línea de Costa y Cálculo de Área</p>
      </div>
      <div class="flex space-x-3">
        <select v-model="selectedCamId" class="bg-white border border-slate-200 text-sm rounded-xl px-4 py-2 font-medium outline-none">
          <option :value="null">Seleccionar Cámara</option>
          <option v-for="cam in cameras" :key="cam.idx" :value="cam.idx">{{ cam.name }}</option>
        </select>
        <button @click="runAnalysis" 
                :disabled="!selectedCamId || analyzing"
                class="px-6 py-2 bg-blue-600 text-white rounded-xl text-sm font-bold hover:bg-blue-700 disabled:opacity-30 flex items-center shadow-lg shadow-blue-600/20 transition-all">
          <svg v-if="analyzing" class="animate-spin -ml-1 mr-2 h-4 w-4 text-white" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path></svg>
          {{ analyzing ? 'Procesando...' : 'Ejecutar Análisis' }}
        </button>
      </div>
    </header>

    <div v-if="result" class="grid grid-cols-1 lg:grid-cols-4 gap-12 animate-scale-in">
      <div class="lg:col-span-3">
        <div class="relative rounded-[3rem] overflow-hidden border border-slate-100 bg-slate-50 shadow-inner group">
          <img :src="resultImageUrl" class="w-full h-auto block" alt="Analysis Result">
          <div class="absolute bottom-8 left-8 px-5 py-2.5 bg-black/60 backdrop-blur text-white text-[10px] font-bold uppercase tracking-widest rounded-full flex items-center space-x-2">
            <div class="w-2 h-2 rounded-full bg-blue-400 animate-pulse"></div>
            <span>Capa: Línea de Costa Detectada</span>
          </div>
        </div>
      </div>

      <aside class="space-y-8 flex flex-col">
        <div class="p-8 border border-slate-100 rounded-[2.5rem] bg-slate-50/50 space-y-8 flex-1">
          <h3 class="text-[10px] font-bold text-slate-400 uppercase tracking-[0.2em]">Resultados del Lote</h3>
          <div class="space-y-8">
            <div>
              <p class="text-[10px] font-bold text-slate-500 uppercase mb-1 tracking-widest">Área Seca Detectada</p>
              <p class="text-4xl font-bold text-slate-900 leading-none tabular-nums">{{ result.dry_area_m2.toLocaleString() }} <span class="text-base font-medium text-slate-300 ml-1">m²</span></p>
            </div>
            <div>
              <p class="text-[10px] font-bold text-slate-500 uppercase mb-1 tracking-widest">Confianza Detección</p>
              <div class="flex items-end space-x-2">
                <p class="text-2xl font-bold text-emerald-600 leading-none">{{ (result.confidence * 100).toFixed(1) }}%</p>
                <div class="flex-1 h-1 bg-slate-100 rounded-full mb-1">
                   <div class="h-full bg-emerald-500 rounded-full" :style="{ width: result.confidence * 100 + '%' }"></div>
                </div>
              </div>
            </div>
          </div>
        </div>

        <div class="space-y-4">
          <button @click="exportGeoJSON" class="w-full px-4 py-4 bg-slate-900 text-white rounded-2xl text-[10px] font-bold uppercase tracking-widest hover:bg-slate-800 transition-all shadow-xl shadow-slate-900/10 flex items-center justify-center">
            <svg class="w-4 h-4 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a2 2 0 002 2h12a2 2 0 002-2v-1m-4-4l-4 4m0 0l-4-4m4 4V4"></path></svg>
            Exportar GeoJSON
          </button>
          <p class="text-[9px] text-slate-400 text-center leading-relaxed px-4">Genera un archivo MultiLineString en EPSG:25830 compatible con QGIS.</p>
        </div>
      </aside>
    </div>

    <div v-else-if="!analyzing" class="h-[65vh] flex flex-col items-center justify-center border-2 border-dashed border-slate-100 rounded-[4rem] text-center p-12 bg-slate-50/20">
      <div class="w-20 h-20 bg-white rounded-full flex items-center justify-center text-slate-100 mb-8 shadow-sm">
        <svg class="w-10 h-10" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z"></path></svg>
      </div>
      <p class="text-slate-400 font-bold uppercase tracking-widest text-[11px] mb-2">Análisis de Costa</p>
      <p class="text-slate-300 text-[11px] max-w-xs leading-relaxed font-medium">Selecciona una cámara para ejecutar el procesamiento del lote y detectar la línea de marea.</p>
    </div>
  </div>
</template>
