<script setup>
import { ref, onMounted } from 'vue'
import Map from './Map.vue'

const data = ref(null)
const error = ref(null)
const geojson = ref(null)

async function fetchData() {
  try {
    const [dashRes, geoRes] = await Promise.all([
      fetch('http://localhost:8000/api/dashboard'),
      fetch('http://localhost:8000/api/geojson')
    ])
    
    if (!dashRes.ok || !geoRes.ok) throw new Error('Error al conectar con el servidor')
    
    data.value = await dashRes.json()
    geojson.value = await geoRes.json()
  } catch (err) {
    error.value = err.message
    console.error('Fetch error:', err)
  }
}

onMounted(fetchData)

const emit = defineEmits(['select-camera'])
</script>

<template>
  <div v-if="error" class="p-8 text-red-600 font-medium text-center">
    <div class="max-w-md mx-auto p-6 bg-red-50 rounded-2xl border border-red-100">
       <p class="text-sm font-bold uppercase tracking-widest mb-2">Error de Conexión</p>
       <p class="text-xs text-red-400">{{ error }}</p>
       <button @click="fetchData" class="mt-4 px-4 py-2 bg-red-600 text-white rounded-lg text-xs font-bold uppercase tracking-widest">Reintentar</button>
    </div>
  </div>
  
  <div v-else-if="data" class="p-12 max-w-7xl mx-auto animate-fade-in space-y-12">
    <header class="flex justify-between items-end">
      <div>
        <h1 class="text-2xl font-bold text-slate-900 tracking-tight">Estado del Sistema</h1>
        <p class="text-sm text-slate-500 mt-1">Guardamar del Segura · Red de Cámaras Obscape</p>
      </div>
      <div class="px-4 py-2 bg-slate-50 rounded-full border border-slate-100 flex items-center space-x-2">
        <div class="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></div>
        <span class="text-[10px] font-bold text-slate-600 uppercase tracking-widest">Servidor Online</span>
      </div>
    </header>

    <!-- Main Grid: Stats & Map -->
    <div class="grid grid-cols-1 lg:grid-cols-3 gap-8">
      <!-- Left Column: Stats -->
      <div class="lg:col-span-1 space-y-6">
        <div class="p-8 border border-slate-100 rounded-3xl bg-slate-50/30">
          <p class="text-[10px] font-bold text-slate-400 uppercase tracking-widest mb-1">Cámaras</p>
          <p class="text-3xl font-bold text-slate-900">{{ data.cameras_calibrated }} / {{ data.total_cameras }} <span class="text-xs font-medium text-slate-400 ml-1">Calibradas</span></p>
          <div class="mt-4 h-1.5 w-full bg-slate-100 rounded-full overflow-hidden">
            <div class="h-full bg-slate-900 transition-all duration-1000" :style="{ width: (data.cameras_calibrated / data.total_cameras) * 100 + '%' }"></div>
          </div>
        </div>
        
        <div class="p-8 border border-slate-100 rounded-3xl bg-slate-50/30">
          <p class="text-[10px] font-bold text-slate-400 uppercase tracking-widest mb-1">Procesamiento Total</p>
          <p class="text-3xl font-bold text-slate-900">{{ data.images_processed.toLocaleString() }} <span class="text-xs font-medium text-slate-400 ml-1">Imágenes</span></p>
          <p class="text-[11px] text-slate-400 mt-2 font-medium">Última actualización: hace 5 min</p>
        </div>

        <div class="p-8 border border-slate-100 rounded-3xl bg-slate-900 text-white">
          <p class="text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-1">Métrica Clave (Área Seca)</p>
          <p class="text-3xl font-bold">{{ data.avg_dry_area }}</p>
          <div class="mt-4 flex items-center space-x-2 text-emerald-400">
             <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6"></path></svg>
             <span class="text-[10px] font-bold uppercase tracking-widest">+2.4% vs mes anterior</span>
          </div>
        </div>
      </div>

      <!-- Right Column: Map Integration -->
      <div class="lg:col-span-2 relative min-h-[400px]">
        <Map :geojsonData="geojson" />
        <div class="absolute bottom-6 left-6 right-6 p-4 bg-white/90 backdrop-blur border border-slate-100 rounded-2xl shadow-xl flex items-center justify-between pointer-events-none">
          <div>
            <p class="text-[10px] font-bold text-slate-900 uppercase">Localización ROI</p>
            <p class="text-[11px] text-slate-500">Geometría: MultiLineString (EPSG:25830)</p>
          </div>
          <div class="flex items-center space-x-4">
             <div class="flex items-center space-x-1.5">
               <div class="w-3 h-1 bg-blue-600 rounded-full"></div>
               <span class="text-[9px] font-bold text-slate-400 uppercase">Costa</span>
             </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Camera Grid -->
    <div>
      <h2 class="text-sm font-bold text-slate-900 uppercase tracking-widest mb-6">Cámaras en Red</h2>
      <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        <div v-for="cam in data.cameras" :key="cam.id" 
             @click="emit('select-camera', cam.idx)"
             class="group p-6 border border-slate-100 rounded-2xl hover:border-slate-300 hover:bg-slate-50/50 transition-all cursor-pointer">
          <div class="flex items-center justify-between mb-4">
            <div class="w-12 h-12 rounded-2xl bg-slate-100 flex items-center justify-center text-slate-400 group-hover:text-slate-900 transition-colors">
              <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z"></path></svg>
            </div>
            <span :class="cam.status === 'Sin calibrar' ? 'bg-slate-100 text-slate-400' : 'bg-blue-50 text-blue-600'"
                  class="px-3 py-1 rounded-full text-[9px] font-bold uppercase tracking-widest">
              {{ cam.status }}
            </span>
          </div>
          <h3 class="font-bold text-slate-900">{{ cam.name }}</h3>
          <p class="text-xs text-slate-400 font-medium mt-1">{{ cam.id }} · {{ cam.images }} imágenes totales</p>
          
          <div class="mt-6 flex items-center text-[10px] font-bold text-slate-300 group-hover:text-slate-900 transition-colors uppercase tracking-widest">
            Configurar Calibración
            <svg class="w-4 h-4 ml-2 group-hover:translate-x-1 transition-transform" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 8l4 4m0 0l-4 4m4-4H3"></path></svg>
          </div>
        </div>
      </div>
    </div>
  </div>

  <div v-else class="h-[80vh] flex flex-col items-center justify-center space-y-4">
    <div class="w-12 h-12 border-4 border-slate-100 border-t-slate-900 rounded-full animate-spin"></div>
    <p class="text-slate-400 text-[10px] font-bold animate-pulse tracking-[0.2em] uppercase">Iniciando Sensores...</p>
  </div>
</template>
