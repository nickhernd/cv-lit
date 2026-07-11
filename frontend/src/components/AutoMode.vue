<script setup>
import { ref, onMounted, onUnmounted } from 'vue'

const emit = defineEmits(['notify'])
const API = 'http://localhost:8000'

const running = ref(false)
const watchDir = ref('/data/camaras/')
const interval = ref(60)
const priorityHour = ref('11:30-12:30')
const notifyEmail = ref('iel@ua.es')
const filterGxGy = ref(true)
const autoExportGeojson = ref(true)
const logs = ref([])
const cameras = ref([])
let poller = null

async function fetchLogs() {
  try {
    const res = await fetch(`${API}/api/logs`)
    logs.value = await res.json()
  } catch (e) { /* noop */ }
}

async function fetchCameras() {
  try {
    const res = await fetch(`${API}/api/dashboard`)
    const data = await res.json()
    cameras.value = data.cameras
  } catch (e) { /* noop */ }
}

function toggleRunning() {
  running.value = !running.value
  emit('notify', running.value ? 'Modo automático iniciado' : 'Modo automático detenido', running.value ? 'success' : 'info')
}

onMounted(() => {
  fetchLogs()
  fetchCameras()
  poller = setInterval(fetchLogs, 3000)
})
onUnmounted(() => clearInterval(poller))
</script>

<template>
  <div class="space-y-6">
    <div class="flex justify-between items-center border-b border-slate-200 pb-4">
      <div>
        <h1 class="text-xl font-semibold text-slate-900 tracking-tight">Modo Automático</h1>
        <p class="text-xs text-slate-400 font-medium">Procesamiento periódico · Directorio vigilado</p>
      </div>
      <div class="flex items-center space-x-3">
        <span class="inline-flex items-center space-x-1.5 text-[10px] font-bold uppercase">
          <span :class="running ? 'bg-emerald-500 animate-pulse' : 'bg-slate-300'" class="w-2 h-2 rounded-full"></span>
          <span>{{ running ? 'En ejecución' : 'Detenido' }}</span>
        </span>
        <button v-if="!running" @click="toggleRunning" class="btn-standard uppercase text-xs">▶ Iniciar</button>
        <button v-else @click="toggleRunning" class="px-4 py-2 bg-red-600 text-white rounded-lg text-xs font-semibold uppercase hover:bg-red-700 transition-colors">■ Detener</button>
      </div>
    </div>

    <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
      <div class="card-standard p-6 space-y-4">
        <div class="text-[10px] font-bold text-slate-400 uppercase tracking-widest">Configuración</div>
        <div class="space-y-1">
          <label class="text-[10px] font-bold text-slate-500 uppercase">Directorio vigilado</label>
          <input v-model="watchDir" class="w-full input-standard font-mono text-xs">
        </div>
        <div class="grid grid-cols-2 gap-4">
          <div class="space-y-1">
            <label class="text-[10px] font-bold text-slate-500 uppercase">Intervalo (min)</label>
            <input type="number" v-model.number="interval" class="w-full input-standard text-xs">
          </div>
          <div class="space-y-1">
            <label class="text-[10px] font-bold text-slate-500 uppercase">Hora prioritaria</label>
            <input v-model="priorityHour" class="w-full input-standard text-xs">
          </div>
        </div>
        <div class="space-y-1">
          <label class="text-[10px] font-bold text-slate-500 uppercase">Notificaciones de fallo</label>
          <input v-model="notifyEmail" type="email" class="w-full input-standard text-xs">
        </div>
        <div class="pt-2 border-t border-slate-100 space-y-3">
          <label class="flex items-center justify-between text-xs font-medium text-slate-700">
            <span>Filtro Gx/Gy (descartar imgs ruidosas)</span>
            <input type="checkbox" v-model="filterGxGy" class="rounded">
          </label>
          <label class="flex items-center justify-between text-xs font-medium text-slate-700">
            <span>Exportar GeoJSON automáticamente</span>
            <input type="checkbox" v-model="autoExportGeojson" class="rounded">
          </label>
        </div>
      </div>

      <div class="card-standard p-6 space-y-4">
        <div class="text-[10px] font-bold text-slate-400 uppercase tracking-widest">Estado por cámara</div>
        <div v-for="cam in cameras" :key="cam.idx" class="flex items-center justify-between text-xs">
          <span class="font-medium text-slate-700">{{ cam.name }}</span>
          <span :class="cam.status === 'Sin calibrar' ? 'bg-red-500' : 'bg-emerald-500'" class="w-2 h-2 rounded-full"></span>
        </div>
      </div>
    </div>

    <div class="card-standard overflow-hidden">
      <div class="card-header uppercase tracking-wider text-[10px]">Log en tiempo real</div>
      <div class="bg-slate-900 text-slate-300 font-mono text-[10px] p-4 h-64 overflow-y-auto space-y-1">
        <div v-for="(log, idx) in logs.slice().reverse()" :key="idx" class="flex space-x-3">
          <span class="text-slate-600">[{{ log.time }}]</span>
          <span :class="log.type === 'error' ? 'text-red-400' : (log.type === 'success' ? 'text-emerald-400' : 'text-blue-400')" class="font-bold uppercase">{{ log.type }}</span>
          <span class="text-slate-300">{{ log.msg }}</span>
        </div>
        <p v-if="!logs.length" class="text-slate-500 italic">Sin eventos recientes</p>
      </div>
    </div>
  </div>
</template>
