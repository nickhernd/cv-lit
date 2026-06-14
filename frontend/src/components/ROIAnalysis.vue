<script setup>
import { ref, onMounted, computed } from 'vue'

const emit = defineEmits(['notify'])

const cameras = ref([])
const selectedCamId = ref(null)
const analyzing = ref(false)
const result = ref(null)
const viewMode = ref('result') // 'original' or 'result'

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
      emit('notify', 'Analisis completado con exito', 'success')
    } else {
      const err = await res.json()
      emit('notify', err.detail, 'error')
    }
  } catch (err) {
    emit('notify', 'Error critico en el procesamiento', 'error')
  } finally {
    analyzing.value = false
  }
}

function exportGeoJSON() {
  window.open('http://localhost:8000/api/geojson', '_blank')
}

onMounted(fetchCameras)

const displayImageUrl = computed(() => {
  if (!selectedCamId.value) return null
  const endpoint = viewMode.value === 'result' ? 'analysis-result' : 'image'
  return `http://localhost:8000/api/cameras/${selectedCamId.value}/${endpoint}?t=${Date.now()}`
})
</script>

<template>
  <div class="p-12 max-w-7xl mx-auto animate-fade-in min-h-screen flex flex-col">
    <header class="mb-12 flex justify-between items-end">
      <div>
        <h1 class="text-3xl font-bold text-slate-900 tracking-tight">Analisis de Costa</h1>
        <p class="text-sm text-slate-400 mt-2 font-medium">Extraccion Automatica de Linea de Costa (SAM)</p>
      </div>
      <div class="flex space-x-4 bg-slate-50 p-2 rounded-2xl border border-slate-100">
        <select v-model="selectedCamId" class="bg-white border border-slate-200 text-xs rounded-xl px-5 py-2.5 font-bold outline-none shadow-sm focus:ring-2 focus:ring-slate-200 transition-all">
          <option :value="null">Seleccionar Dispositivo</option>
          <option v-for="cam in cameras" :key="cam.idx" :value="cam.idx">{{ cam.name }}</option>
        </select>
        <button @click="runAnalysis" 
                :disabled="!selectedCamId || analyzing"
                class="px-8 py-2.5 bg-blue-600 text-white rounded-xl text-xs font-bold uppercase tracking-widest hover:bg-blue-700 disabled:opacity-30 flex items-center shadow-xl shadow-blue-600/20 transition-all active:scale-95">
          <svg v-if="analyzing" class="animate-spin -ml-1 mr-3 h-4 w-4 text-white" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path></svg>
          {{ analyzing ? 'Analizando...' : 'Ejecutar Analisis' }}
        </button>
      </div>
    </header>

    <div v-if="result" class="grid grid-cols-1 lg:grid-cols-4 gap-12 flex-1 animate-scale-in">
      <div class="lg:col-span-3 space-y-6 flex flex-col">
        <div class="relative flex-1 rounded-[4rem] overflow-hidden border-8 border-slate-50 bg-slate-100 shadow-2xl group">
          <img :src="displayImageUrl" class="w-full h-full object-contain block transition-transform duration-700 group-hover:scale-[1.02]" alt="Analysis Result">
          
          <!-- View Toggle Floating -->
          <div class="absolute top-8 left-8 p-1 bg-black/40 backdrop-blur-xl rounded-2xl flex border border-white/10 shadow-2xl">
             <button @click="viewMode = 'original'" 
                     :class="viewMode === 'original' ? 'bg-white text-slate-900 shadow-lg' : 'text-white hover:bg-white/10'"
                     class="px-5 py-2 rounded-xl text-[10px] font-bold uppercase tracking-widest transition-all">Original</button>
             <button @click="viewMode = 'result'" 
                     :class="viewMode === 'result' ? 'bg-white text-slate-900 shadow-lg' : 'text-white hover:bg-white/10'"
                     class="px-5 py-2 rounded-xl text-[10px] font-bold uppercase tracking-widest transition-all">Resultado</button>
          </div>

          <div class="absolute bottom-10 left-1/2 -translate-x-1/2 px-6 py-3 bg-white/90 backdrop-blur text-slate-900 text-[10px] font-bold uppercase tracking-[0.2em] rounded-full flex items-center space-x-3 shadow-2xl border border-white">
            <div class="w-2 h-2 rounded-full bg-blue-500 animate-pulse shadow-[0_0_8px_rgba(59,130,246,0.5)]"></div>
            <span>Capa: Linea de Costa Detectada</span>
          </div>
        </div>
      </div>

      <aside class="space-y-8 flex flex-col">
        <div class="p-10 border border-slate-100 rounded-[3rem] bg-slate-50/50 space-y-12 flex-1 relative overflow-hidden">
          <div class="absolute -right-10 -bottom-10 w-40 h-40 bg-blue-500/5 rounded-full blur-3xl"></div>
          <h3 class="text-[10px] font-bold text-slate-400 uppercase tracking-[0.3em]">Métricas del Lote</h3>
          
          <div class="space-y-10">
            <div>
              <p class="text-[10px] font-bold text-slate-500 uppercase mb-3 tracking-widest">Area Seca Estimada</p>
              <p class="text-5xl font-bold text-slate-900 leading-none tabular-nums tracking-tighter">{{ result.dry_area_m2.toLocaleString() }} <span class="text-lg font-medium text-slate-300 ml-1">m2</span></p>
              <div class="mt-4 flex items-center text-[10px] text-emerald-500 font-bold uppercase tracking-widest">
                 <svg class="w-3 h-3 mr-1" fill="currentColor" viewBox="0 0 20 20"><path d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z"/></svg>
                 Calculo validado
              </div>
            </div>
            
            <div class="pt-10 border-t border-slate-100">
              <p class="text-[10px] font-bold text-slate-500 uppercase mb-4 tracking-widest">Confianza del Algoritmo</p>
              <div class="flex items-end space-x-4">
                <p class="text-3xl font-bold text-slate-900 tabular-nums leading-none">{{ (result.confidence * 100).toFixed(0) }}%</p>
                <div class="flex-1 h-2 bg-slate-100 rounded-full mb-1 relative overflow-hidden">
                   <div class="h-full bg-slate-900 rounded-full transition-all duration-[1s]" :style="{ width: result.confidence * 100 + '%' }"></div>
                </div>
              </div>
            </div>
          </div>
        </div>

        <div class="space-y-4">
          <button @click="exportGeoJSON" class="w-full py-5 bg-slate-900 text-white rounded-[2rem] text-xs font-bold uppercase tracking-widest hover:bg-slate-800 hover:scale-[1.02] active:scale-95 transition-all shadow-2xl shadow-slate-900/20 flex items-center justify-center group">
            <svg class="w-5 h-5 mr-3 group-hover:-translate-y-1 transition-transform" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M4 16v1a2 2 0 002 2h12a2 2 0 002-2v-1m-4-4l-4 4m0 0l-4-4m4 4V4" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>
            Exportar GeoJSON
          </button>
          <p class="text-[9px] text-slate-400 text-center leading-relaxed px-8 font-medium">Compatible con QGIS, ArcGIS y herramientas SIG estandar.</p>
        </div>
      </aside>
    </div>

    <div v-else-if="!analyzing" class="flex-1 flex flex-col items-center justify-center border-4 border-dashed border-slate-50 rounded-[5rem] text-center p-20 bg-slate-50/20 m-4 transition-all hover:bg-slate-50/40 group">
      <div class="w-24 h-24 bg-white rounded-[2.5rem] flex items-center justify-center text-slate-200 mb-10 shadow-xl group-hover:scale-110 group-hover:rotate-3 transition-all duration-500">
        <svg class="w-12 h-12" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" stroke-width="1.5"/></svg>
      </div>
      <h3 class="text-slate-900 font-bold uppercase tracking-[0.3em] text-xs mb-3">Motor de Analisis Listo</h3>
      <p class="text-slate-400 text-[11px] max-w-xs leading-relaxed font-medium">Selecciona una camara para iniciar la segmentacion y deteccion automatica de la marea.</p>
    </div>

    <div v-else class="flex-1 flex flex-col items-center justify-center">
       <div class="w-20 h-20 relative">
          <div class="absolute inset-0 border-4 border-slate-100 rounded-full"></div>
          <div class="absolute inset-0 border-4 border-t-blue-600 rounded-full animate-spin"></div>
       </div>
       <p class="mt-8 text-[10px] font-bold text-slate-900 uppercase tracking-[0.4em] animate-pulse">Procesando Fotogramas</p>
    </div>
  </div>
</template>

<style scoped>
.animate-scale-in { animation: scaleIn 0.5s cubic-bezier(0.16, 1, 0.3, 1); }
@keyframes scaleIn {
  from { opacity: 0; transform: scale(0.95); }
  to { opacity: 1; transform: scale(1); }
}

.animate-fade-in { animation: fadeIn 0.6s ease-out; }
@keyframes fadeIn {
  from { opacity: 0; }
  to { opacity: 1; }
}
</style>
