<script setup>
import { ref, onMounted } from 'vue'
import Map from './Map.vue'

const emit = defineEmits(['select-camera', 'notify'])

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
    emit('notify', 'Fallo en la sincronizacion con el servidor', 'error')
  }
}

onMounted(fetchData)
</script>

<template>
  <div v-if="error" class="p-12 flex flex-col items-center justify-center h-full space-y-6">
    <div class="p-10 bg-red-50 rounded-[3rem] border border-red-100 text-center max-w-lg shadow-xl shadow-red-500/5">
       <div class="w-16 h-16 bg-white rounded-full flex items-center justify-center mx-auto mb-6 shadow-sm text-red-500">
         <svg class="w-8 h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>
       </div>
       <h2 class="text-xl font-bold text-slate-900 mb-2">Error de Sincronizacion</h2>
       <p class="text-sm text-slate-500 leading-relaxed mb-8">{{ error }}</p>
       <button @click="fetchData" class="px-8 py-3 bg-red-600 text-white rounded-2xl text-xs font-bold uppercase tracking-widest hover:bg-red-700 transition-all shadow-lg shadow-red-600/20">Reintentar Conexion</button>
    </div>
  </div>
  
  <div v-else-if="data" class="p-12 max-w-7xl mx-auto animate-fade-in space-y-12">
    <header class="flex justify-between items-end">
      <div>
        <h1 class="text-3xl font-bold text-slate-900 tracking-tight">Estado de la Red</h1>
        <p class="text-sm text-slate-400 mt-2 font-medium">Guardamar del Segura <span class="mx-2 text-slate-200">|</span> Monitorizacion de Linea de Costa</p>
      </div>
      <div class="px-5 py-2.5 bg-emerald-50 text-emerald-600 rounded-full border border-emerald-100 flex items-center space-x-3 shadow-sm">
        <div class="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse"></div>
        <span class="text-[10px] font-bold uppercase tracking-widest">Servidor Online</span>
      </div>
    </header>

    <div class="grid grid-cols-1 lg:grid-cols-3 gap-8">
      <div class="lg:col-span-1 space-y-6">
        <div class="p-10 border border-slate-100 rounded-[3rem] bg-slate-50/30 hover:bg-white transition-colors group">
          <p class="text-[10px] font-bold text-slate-400 uppercase tracking-[0.2em] mb-4">Dispositivos</p>
          <p class="text-4xl font-bold text-slate-900 tabular-nums">{{ data.cameras_calibrated }} <span class="text-lg text-slate-200 mx-1">/</span> {{ data.total_cameras }}</p>
          <p class="text-[11px] font-bold text-slate-400 uppercase mt-2">Camaras Calibradas</p>
          <div class="mt-8 h-1.5 w-full bg-slate-100 rounded-full overflow-hidden">
            <div class="h-full bg-slate-900 transition-all duration-[1.5s] ease-out shadow-[0_0_10px_rgba(0,0,0,0.1)]" :style="{ width: (data.cameras_calibrated / data.total_cameras) * 100 + '%' }"></div>
          </div>
        </div>
        
        <div class="p-10 border border-slate-100 rounded-[3rem] bg-slate-50/30 hover:bg-white transition-colors">
          <p class="text-[10px] font-bold text-slate-400 uppercase tracking-[0.2em] mb-4">Procesamiento</p>
          <p class="text-4xl font-bold text-slate-900 tabular-nums">{{ data.images_processed.toLocaleString() }}</p>
          <p class="text-[11px] font-bold text-slate-400 uppercase mt-2">Fotogramas Analizados</p>
          <div class="mt-8 flex items-center space-x-2">
             <div class="flex -space-x-2">
               <div v-for="i in 3" :key="i" class="w-6 h-6 rounded-full border-2 border-white bg-slate-200"></div>
             </div>
             <span class="text-[10px] text-slate-400 font-bold ml-2">+{{ data.images_processed - 3 }} hoy</span>
          </div>
        </div>

        <div class="p-10 rounded-[3rem] bg-slate-900 text-white shadow-2xl shadow-slate-900/20 relative overflow-hidden group">
          <div class="absolute -right-8 -top-8 w-32 h-32 bg-white/5 rounded-full blur-3xl group-hover:scale-150 transition-transform duration-1000"></div>
          <p class="text-[10px] font-bold text-slate-500 uppercase tracking-[0.2em] mb-4">Metrica de Costa</p>
          <p class="text-4xl font-bold tabular-nums tracking-tight">{{ data.avg_dry_area }}</p>
          <p class="text-[11px] font-bold text-slate-500 uppercase mt-2">Area Seca Promedio</p>
          <div class="mt-8 flex items-center space-x-3 text-emerald-400">
             <div class="w-8 h-8 rounded-xl bg-white/10 flex items-center justify-center">
               <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>
             </div>
             <span class="text-[10px] font-bold uppercase tracking-widest">+2.4% tendencia</span>
          </div>
        </div>
      </div>

      <div class="lg:col-span-2 relative min-h-[500px] rounded-[4rem] overflow-hidden border border-slate-100 shadow-inner group">
        <Map :geojsonData="geojson" />
        <div class="absolute bottom-10 left-10 right-10 p-6 bg-white/80 backdrop-blur-xl border border-white/20 rounded-[2.5rem] shadow-2xl flex items-center justify-between transform group-hover:translate-y-[-5px] transition-transform duration-500">
          <div>
            <p class="text-[10px] font-bold text-slate-900 uppercase tracking-widest mb-1">Localizacion ROI</p>
            <p class="text-[11px] text-slate-500 font-medium">Visualizacion: MultiLineString (EPSG:25830)</p>
          </div>
          <div class="flex items-center space-x-6">
             <div class="flex items-center space-x-2">
               <div class="w-4 h-1 bg-blue-600 rounded-full shadow-[0_0_8px_rgba(37,99,235,0.4)]"></div>
               <span class="text-[10px] font-bold text-slate-400 uppercase tracking-widest">Costa</span>
             </div>
             <div class="w-px h-8 bg-slate-200/50 mx-2"></div>
             <button @click="fetchData" class="p-2 hover:bg-slate-100 rounded-full transition-colors text-slate-400 hover:text-slate-900">
               <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.001 0 01-15.357-2m15.357 2H15" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>
             </button>
          </div>
        </div>
      </div>
    </div>

    <div>
      <div class="flex items-center justify-between mb-8">
        <h2 class="text-sm font-bold text-slate-900 uppercase tracking-[0.2em]">Dispositivos en Red</h2>
        <div class="h-px flex-1 bg-slate-100 mx-8"></div>
      </div>
      
      <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8">
        <div v-for="cam in data.cameras" :key="cam.id" 
             @click="emit('select-camera', cam.idx)"
             class="group p-8 border border-slate-100 rounded-[2.5rem] bg-white hover:border-slate-300 hover:shadow-2xl hover:shadow-slate-200/50 transition-all cursor-pointer relative overflow-hidden">
          <div class="absolute -right-4 -bottom-4 w-24 h-24 bg-slate-50 rounded-full opacity-0 group-hover:opacity-100 scale-0 group-hover:scale-100 transition-all duration-700"></div>
          
          <div class="flex items-center justify-between mb-6">
            <div class="w-14 h-14 rounded-2xl bg-slate-50 flex items-center justify-center text-slate-300 group-hover:bg-slate-900 group-hover:text-white transition-all duration-500 shadow-inner">
              <svg class="w-7 h-7" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>
            </div>
            <span :class="cam.status === 'Sin calibrar' ? 'bg-slate-100 text-slate-400' : 'bg-blue-50 text-blue-600'"
                  class="px-4 py-1.5 rounded-full text-[9px] font-bold uppercase tracking-widest border border-transparent group-hover:border-current transition-all">
              {{ cam.status }}
            </span>
          </div>
          
          <h3 class="text-lg font-bold text-slate-900 group-hover:translate-x-1 transition-transform">{{ cam.name }}</h3>
          <p class="text-xs text-slate-400 font-medium mt-2">{{ cam.id }} <span class="mx-1 text-slate-200">•</span> {{ cam.images }} imagenes</p>
          
          <div class="mt-10 flex items-center text-[10px] font-bold text-slate-300 group-hover:text-slate-900 transition-all uppercase tracking-widest">
            <span>Configurar Calibracion</span>
            <div class="w-8 h-px bg-slate-100 ml-4 group-hover:w-12 group-hover:bg-slate-900 transition-all"></div>
            <svg class="w-4 h-4 ml-2 opacity-0 group-hover:opacity-100 transition-all" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M17 8l4 4m0 0l-4 4m4-4H3" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>
          </div>
        </div>
      </div>
    </div>
  </div>

  <div v-else class="h-[80vh] flex flex-col items-center justify-center space-y-6">
    <div class="relative">
      <div class="w-16 h-16 border-4 border-slate-100 rounded-full"></div>
      <div class="absolute inset-0 w-16 h-16 border-4 border-t-slate-900 rounded-full animate-spin"></div>
    </div>
    <div class="text-center">
      <p class="text-slate-900 text-xs font-bold tracking-[0.3em] uppercase">Sincronizando</p>
      <p class="text-slate-300 text-[10px] font-medium mt-2">Conectando con estaciones Obscape...</p>
    </div>
  </div>
</template>
