<script setup>
import { ref, onMounted, computed, watch } from 'vue'

const emit = defineEmits(['notify'])

const cameras = ref([])
const availableImages = ref([])
const selectedCamId = ref(null)
const selectedImage = ref('')
const analyzing = ref(false)
const result = ref(null)
const viewMode = ref('result') // 'original', 'result', or 'split'

async function fetchCameras() {
  try {
    const res = await fetch('http://localhost:8000/api/dashboard')
    const data = await res.json()
    cameras.value = data.cameras
  } catch (err) { console.error(err) }
}

async function fetchImages() {
  if (!selectedCamId.value) {
    availableImages.value = []
    selectedImage.value = ''
    return
  }
  try {
    const res = await fetch(`http://localhost:8000/api/cameras/${selectedCamId.value}/images`)
    availableImages.value = await res.json()
    if (availableImages.value.length > 0) {
      selectedImage.value = availableImages.value[0]
    }
  } catch (err) { console.error(err) }
}

async function runAnalysis() {
  if (!selectedCamId.value) return
  analyzing.value = true
  result.value = null
  try {
    const url = `http://localhost:8000/api/cameras/${selectedCamId.value}/analyze-roi` + (selectedImage.value ? `?filename=${selectedImage.value}` : '')
    const res = await fetch(url, { method: 'POST' })
    if (res.ok) {
      result.value = await res.json()
      emit('notify', 'Análisis completado con éxito', 'success')
    } else {
      const err = await res.json()
      emit('notify', err.detail, 'error')
    }
  } catch (err) {
    emit('notify', 'Error crítico en el procesamiento', 'error')
  } finally {
    analyzing.value = false
  }
}

function exportGeoJSON() {
  window.open('http://localhost:8000/api/geojson', '_blank')
}

watch(selectedCamId, fetchImages)

onMounted(fetchCameras)

const displayImageUrl = computed(() => {
  if (!selectedCamId.value) return null
  const endpoint = viewMode.value === 'result' ? 'analysis-result' : 'image'
  const fileQuery = selectedImage.value ? `file=${selectedImage.value}&` : ''
  return `http://localhost:8000/api/cameras/${selectedCamId.value}/${endpoint}?${fileQuery}t=${Date.now()}`
})
</script>

<template>
  <div class="space-y-6">
    <div class="flex justify-between items-center border-b border-slate-200 pb-4">
      <h1 class="text-2xl font-semibold text-slate-900">Análisis Geoespacial de Costa</h1>
      <div class="flex items-center space-x-2">
        <select v-model="selectedCamId" class="input-standard py-1">
          <option :value="null">-- Seleccionar Estación --</option>
          <option v-for="cam in cameras" :key="cam.idx" :value="cam.idx">{{ cam.name }}</option>
        </select>
        <button @click="runAnalysis" :disabled="!selectedCamId || analyzing" class="btn-standard py-1 flex items-center">
          <svg v-if="analyzing" class="animate-spin -ml-1 mr-2 h-4 w-4 text-white" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path></svg>
          {{ analyzing ? 'Ejecutando...' : 'Ejecutar Análisis' }}
        </button>
      </div>
    </div>

    <div class="grid grid-cols-1 lg:grid-cols-4 gap-6">
      <!-- Image Display Area -->
      <div class="lg:col-span-3 space-y-4">
        <div class="card-standard overflow-hidden bg-slate-100 flex flex-col min-h-[600px] relative">
           <!-- Split View Layout -->
           <div v-if="viewMode === 'split' && result" class="flex w-full h-full divide-x divide-white border-x-4 border-white">
              <div class="flex-1 relative overflow-hidden bg-black">
                 <img :src="`http://localhost:8000/api/cameras/${selectedCamId}/image?file=${selectedImage}`" class="w-full h-full object-contain">
                 <div class="absolute top-2 left-2 bg-black/50 text-white text-[8px] px-2 py-0.5 rounded uppercase font-semibold">Original</div>
              </div>
              <div class="flex-1 relative overflow-hidden bg-black">
                 <img :src="`http://localhost:8000/api/cameras/${selectedCamId}/analysis-result?file=${selectedImage}`" class="w-full h-full object-contain">
                 <div class="absolute top-2 left-2 bg-blue-600/80 text-white text-[8px] px-2 py-0.5 rounded uppercase font-semibold">Segmentado</div>
              </div>
           </div>

           <img v-else-if="displayImageUrl" :src="displayImageUrl" class="w-full h-full object-contain">
           
           <div v-else class="flex-1 flex flex-col items-center justify-center text-slate-400">
              <svg class="w-12 h-12 mb-2" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" stroke-width="2"/></svg>
              <p class="text-sm font-semibold uppercase tracking-wider">Esperando Selección de Imagen</p>
           </div>

           <!-- View Controls -->
           <div v-if="result" class="absolute top-4 left-4 flex bg-white border border-slate-200 rounded shadow-md overflow-hidden z-10">
              <button @click="viewMode = 'original'" 
                      :class="viewMode === 'original' ? 'bg-slate-800 text-white' : 'text-slate-600 hover:bg-slate-50'"
                      class="px-4 py-1.5 text-xs font-semibold uppercase border-r border-slate-200 transition-colors">Original</button>
              <button @click="viewMode = 'result'" 
                      :class="viewMode === 'result' ? 'bg-slate-800 text-white' : 'text-slate-600 hover:bg-slate-50'"
                      class="px-4 py-1.5 text-xs font-semibold uppercase border-r border-slate-200 transition-colors">Resultado</button>
              <button @click="viewMode = 'split'" 
                      :class="viewMode === 'split' ? 'bg-slate-800 text-white' : 'text-slate-600 hover:bg-slate-50'"
                      class="px-4 py-1.5 text-xs font-semibold uppercase transition-colors">Lado a Lado</button>
           </div>

           <div v-if="result" class="absolute bottom-4 left-1/2 -translate-x-1/2 bg-emerald-600 text-white text-[10px] px-3 py-1 rounded font-semibold uppercase shadow-lg">Segmentación Activa: Shoreline</div>
        </div>
        
        <div v-if="selectedCamId" class="card-standard p-4 bg-slate-50 flex items-center space-x-4">
           <label class="text-xs font-semibold text-slate-500 uppercase">Seleccionar Fotograma:</label>
           <select v-model="selectedImage" class="input-standard flex-1">
              <option value="">-- Automático (Último) --</option>
              <option v-for="img in availableImages" :key="img" :value="img">{{ img }}</option>
           </select>
        </div>
      </div>

      <!-- Metrics Sidebar -->
      <aside class="space-y-6">
        <div v-if="result" class="card-standard overflow-hidden">
           <div class="card-header uppercase tracking-wider">Cuantificación</div>
           <div class="p-6 space-y-6">
              <div>
                <p class="text-[10px] font-semibold text-slate-400 uppercase mb-2">Área Seca Estimada</p>
                <div class="flex items-baseline space-x-1">
                  <p class="text-4xl font-semibold text-slate-900">{{ result.dry_area_m2.toLocaleString() }}</p>
                  <span class="text-lg font-semibold text-slate-400">m²</span>
                </div>
              </div>

              <div class="pt-4 border-t border-slate-100 grid grid-cols-1 gap-4">
                <div>
                  <p class="text-[10px] font-semibold text-slate-400 uppercase mb-1">Confianza AI</p>
                  <p class="text-lg font-semibold text-blue-600">{{ (result.confidence * 100).toFixed(1) }}%</p>
                </div>
                <div>
                  <p class="text-[10px] font-semibold text-slate-400 uppercase mb-1">Timestamp</p>
                  <p class="text-xs font-semibold text-slate-700">{{ result.timestamp.replace('T', ' ') }}</p>
                </div>
              </div>

              <button @click="exportGeoJSON" class="btn-standard w-full flex items-center justify-center">
                <svg class="w-4 h-4 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M4 16v1a2 2 0 002 2h12a2 2 0 002-2v-1m-4-4l-4 4m0 0l-4-4m4 4V4" stroke-width="2"/></svg>
                Exportar GeoJSON
              </button>
           </div>
        </div>

        <div v-else class="card-standard p-8 text-center bg-slate-50 border-dashed">
           <svg class="w-10 h-10 mx-auto text-slate-200 mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" stroke-width="2"/></svg>
           <p class="text-[10px] font-semibold text-slate-400 uppercase tracking-wider leading-relaxed">Ejecute el análisis para obtener métricas geoespaciales</p>
        </div>
      </aside>
    </div>

    <!-- Simple Loading State -->
    <div v-if="analyzing" class="fixed inset-0 z-[200] bg-slate-900/10 flex flex-col items-center justify-center">
       <div class="bg-white border border-slate-200 p-6 rounded shadow-xl flex items-center space-x-4">
          <div class="animate-spin rounded-full h-5 w-5 border-2 border-slate-200 border-t-blue-600"></div>
          <p class="text-sm font-semibold text-slate-700 uppercase tracking-wider">Procesando Segmentación...</p>
       </div>
    </div>
  </div>
</template>
