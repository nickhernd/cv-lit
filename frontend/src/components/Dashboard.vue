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
    emit('notify', 'Fallo en la sincronización con el servidor', 'error')
  }
}

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
  
  <div v-else-if="data" class="space-y-8">
    <div class="flex justify-between items-center border-b border-slate-200 pb-4">
      <h1 class="text-2xl font-bold text-slate-900">Vista General del Sistema</h1>
      <div class="flex items-center space-x-2 text-xs font-bold text-slate-500 uppercase tracking-widest">
        <span>Guardamar del Segura</span>
        <span class="text-slate-300">/</span>
        <span class="text-blue-600 font-bold">Red Obscape</span>
      </div>
    </div>

    <!-- TELEMETRY GRID -->
    <div class="grid grid-cols-1 md:grid-cols-4 gap-6">
      <div v-for="(val, label) in { 'Carga CPU': '24.2%', 'RAM': '4.8 GB', 'Almacén': '1.2 TB', 'Latencia': 'Estable' }" :key="label"
           class="card-standard p-4 flex flex-col justify-center">
        <p class="text-[10px] font-bold text-slate-400 uppercase mb-1">{{ label }}</p>
        <p class="text-xl font-bold text-slate-900">{{ val }}</p>
      </div>
    </div>

    <!-- MAIN METRICS -->
    <div class="grid grid-cols-1 lg:grid-cols-3 gap-8">
      <div class="lg:col-span-1 space-y-6">
        <div class="card-standard overflow-hidden">
          <div class="card-header">Estado de Calibración</div>
          <div class="p-6">
            <div class="flex items-baseline space-x-2 mb-4">
              <span class="text-4xl font-bold text-slate-900">{{ data.cameras_calibrated }}</span>
              <span class="text-slate-400 font-bold">/ {{ data.total_cameras }}</span>
            </div>
            <div class="h-2 w-full bg-slate-100 rounded-full overflow-hidden">
              <div class="h-full bg-blue-600" :style="{ width: (data.cameras_calibrated / data.total_cameras) * 100 + '%' }"></div>
            </div>
            <p class="text-xs text-slate-500 mt-4">Estaciones calibradas y operativas en red.</p>
          </div>
        </div>

        <div class="card-standard overflow-hidden">
          <div class="card-header">Métricas de Procesamiento</div>
          <div class="p-6 space-y-6">
            <div>
              <p class="text-[10px] font-bold text-slate-400 uppercase mb-1">Fotogramas Hoy</p>
              <p class="text-2xl font-bold text-slate-900">{{ data.images_processed.toLocaleString() }}</p>
            </div>
            <div class="pt-4 border-t border-slate-100">
              <p class="text-[10px] font-bold text-slate-400 uppercase mb-1">Área Seca Promedio</p>
              <div class="flex items-baseline space-x-1">
                <span class="text-2xl font-bold text-slate-900">{{ data.avg_dry_area }}</span>
                <span class="text-sm font-bold text-slate-400">m²</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div class="lg:col-span-2">
        <div class="card-standard h-full flex flex-col overflow-hidden">
          <div class="card-header flex justify-between items-center">
            <span>Localización ROI</span>
            <button @click="fetchData" class="text-blue-600 hover:text-blue-800 text-xs font-bold">Actualizar Mapa</button>
          </div>
          <div class="flex-1 min-h-[400px]">
            <Map :geojsonData="geojson" />
          </div>
        </div>
      </div>
    </div>

    <!-- STATIONS TABLE -->
    <div class="card-standard overflow-hidden">
      <div class="card-header">Estaciones de Visión</div>
      <div class="overflow-x-auto">
        <table class="w-full text-left text-sm">
          <thead class="bg-slate-50 text-slate-500 font-bold border-b border-slate-200">
            <tr>
              <th class="px-6 py-3">Nombre Estación</th>
              <th class="px-6 py-3">ID</th>
              <th class="px-6 py-3">Estado</th>
              <th class="px-6 py-3 text-right">Acciones</th>
            </tr>
          </thead>
          <tbody class="divide-y border-slate-100">
            <tr v-for="cam in data.cameras" :key="cam.id" class="hover:bg-slate-50 transition-colors text-slate-700">
              <td class="px-6 py-4 font-bold">{{ cam.name }}</td>
              <td class="px-6 py-4 text-slate-500 font-mono text-xs">{{ cam.id }}</td>
              <td class="px-6 py-4">
                <span :class="cam.status === 'Sin calibrar' ? 'bg-slate-100 text-slate-600' : 'bg-emerald-100 text-emerald-800'"
                      class="px-2 py-0.5 rounded text-[10px] font-bold uppercase">
                  {{ cam.status }}
                </span>
              </td>
              <td class="px-6 py-4 text-right">
                <button @click="emit('select-camera', cam.idx)" class="text-blue-600 hover:underline font-bold text-xs uppercase tracking-tight">Gestionar</button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>

  <div v-else class="h-64 flex flex-col items-center justify-center text-slate-400">
    <div class="animate-spin rounded-full h-8 w-8 border-2 border-slate-200 border-t-blue-600 mb-4"></div>
    <p class="text-sm font-medium uppercase tracking-widest">Sincronizando Sistema...</p>
  </div>
</template>
