<script setup>
import { ref, computed, onMounted } from 'vue'
import { API_BASE } from './api.js'
import Dashboard from './components/Dashboard.vue'
import Calibration from './components/Calibration.vue'
import CoastlineAnalysis from './components/CoastlineAnalysis.vue'
import ImageIngest from './components/ImageIngest.vue'
import GeoJSONMap from './components/GeoJSONMap.vue'
import Cameras from './components/Cameras.vue'
import AutoMode from './components/AutoMode.vue'
import Settings from './components/Settings.vue'

const currentView = ref('dashboard')
const selectedCamId = ref(null)
const notifications = ref([])
const logs = ref([])
const showLogs = ref(false)

const VIEW_META = {
  dashboard: { title: 'Dashboard', sub: 'Vista general del sistema' },
  ingest: { title: 'Carga de imágenes', sub: 'Selecciona cámara y directorio de imágenes' },
  resultados: { title: 'Resultados', sub: 'Segmentación y línea de costa' },
  geomap: { title: 'Mapa GeoJSON', sub: 'EPSG:25830 · Guardamar del Segura' },
  calibration: { title: 'Calibración geométrica', sub: 'Estado por cámara · Módulo offline' },
  cameras: { title: 'Cámaras', sub: 'Configuración hardware · Lente, ROI, ubicación' },
  automode: { title: 'Modo automático', sub: 'Descarga, alineación y análisis por rango de fechas' },
  settings: { title: 'Configuración', sub: 'Credenciales y ajustes de la aplicación' },
}
const viewMeta = computed(() => VIEW_META[currentView.value] || { title: '', sub: '' })

async function fetchLogs() {
  try {
    const res = await fetch(`${API_BASE}/api/logs`)
    logs.value = await res.json()
  } catch (err) { console.error('Error fetching logs:', err) }
}

function notify(message, type = 'info') {
  const id = Date.now()
  notifications.value.push({ id, message, type })
  setTimeout(() => {
    notifications.value = notifications.value.filter(n => n.id !== id)
  }, 4000)
}

function goToCalibration(camId = null) {
  selectedCamId.value = camId
  currentView.value = 'calibration'
}

function goToDashboard() {
  currentView.value = 'dashboard'
}

function goToResultados(camId = null) {
  selectedCamId.value = camId
  currentView.value = 'resultados'
}


onMounted(() => {
  fetchLogs()
  setInterval(fetchLogs, 3000)
})
</script>

<template>
  <div class="flex h-screen bg-[var(--bg2)] font-sans text-slate-800">
    <!-- Sidebar: igual estructura que Linea de costa-6/calibration (logo arriba,
         secciones Proceso/Sistema, items de texto plano con borde izq. activo) -->
    <aside class="w-[220px] bg-[var(--bg2)] border-r border-slate-200 text-slate-600 flex flex-col shrink-0">
      <div class="p-4 flex items-center gap-2.5">
        <div class="w-7 h-7 bg-blue-600 rounded-md flex items-center justify-center shrink-0">
          <span class="text-[11px] font-semibold text-white">LC</span>
        </div>
        <div class="min-w-0">
          <p class="text-[13px] font-semibold text-slate-900 leading-tight truncate">Línea de Costa</p>
          <p class="text-[10px] text-slate-400 leading-tight truncate">Guardamar del Segura</p>
        </div>
      </div>

      <nav class="flex-1 overflow-y-auto pb-4 space-y-0.5">
        <div class="px-5 pt-3.5 pb-1 text-[11px] font-semibold text-slate-400 uppercase tracking-wide">Proceso</div>
        <button @click="goToDashboard" class="nav-item" :class="{ active: currentView === 'dashboard' }">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75"><path stroke-linecap="round" stroke-linejoin="round" d="M4 6h16M4 12h16M4 18h7"/></svg>
          <span>Dashboard</span>
        </button>
        <button @click="currentView = 'ingest'" class="nav-item" :class="{ active: currentView === 'ingest' }">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75"><path stroke-linecap="round" stroke-linejoin="round" d="M4 16l4.6-4.6a2 2 0 0 1 2.8 0L16 16m-2-2 1.6-1.6a2 2 0 0 1 2.8 0L20 14M4 20h16a1 1 0 0 0 1-1V5a1 1 0 0 0-1-1H4a1 1 0 0 0-1 1v14a1 1 0 0 0 1 1Z"/></svg>
          <span>Carga de imágenes</span>
        </button>
        <button @click="goToResultados()" class="nav-item" :class="{ active: currentView === 'resultados' }">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75"><path stroke-linecap="round" stroke-linejoin="round" d="M3 17c2-2 4-3 6-1s4 3 6 1 4-2 6-1M3 12c2-2 4-3 6-1s4 3 6 1 4-2 6-1"/></svg>
          <span>Resultados</span>
        </button>
        <button @click="currentView = 'geomap'" class="nav-item" :class="{ active: currentView === 'geomap' }">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75"><path stroke-linecap="round" stroke-linejoin="round" d="M9 20 3.6 17.3A1 1 0 0 1 3 16.4V7.1a1 1 0 0 1 1.4-.9L9 4.5l6 1.7 5.4-1.9a1 1 0 0 1 1.6.9v9.3a1 1 0 0 1-.6.9L15 18Zm0-15.5v13.7M15 6.2v13.7"/></svg>
          <span>Mapa GeoJSON</span>
        </button>

        <div class="px-5 pt-3.5 pb-1 text-[11px] font-semibold text-slate-400 uppercase tracking-wide">Sistema</div>
        <button @click="goToCalibration()" class="nav-item" :class="{ active: currentView === 'calibration' }">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75"><circle cx="12" cy="12" r="8.25"/><circle cx="12" cy="12" r="3.25"/><path stroke-linecap="round" d="M12 2.75v2.5M12 18.75v2.5M21.25 12h-2.5M5.25 12h-2.5"/></svg>
          <span>Calibración</span>
        </button>
        <button @click="currentView = 'cameras'" class="nav-item" :class="{ active: currentView === 'cameras' }">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75"><path stroke-linecap="round" stroke-linejoin="round" d="M3 9a2 2 0 0 1 2-2h.9a2 2 0 0 0 1.7-.9l.8-1.2A2 2 0 0 1 10.1 4h3.8a2 2 0 0 1 1.7.9l.8 1.2a2 2 0 0 0 1.7.9H19a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2Z"/><circle cx="12" cy="13" r="3"/></svg>
          <span>Cámaras</span>
        </button>
        <button @click="currentView = 'automode'" class="nav-item" :class="{ active: currentView === 'automode' }">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75"><path stroke-linecap="round" stroke-linejoin="round" d="M13 3 4 14h7l-1 7 9-11h-7z"/></svg>
          <span>Modo automático</span>
        </button>
        <button @click="currentView = 'settings'" class="nav-item" :class="{ active: currentView === 'settings' }">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75"><path stroke-linecap="round" stroke-linejoin="round" d="M10.3 3.3a1.94 1.94 0 0 1 3.4 0l.4.7a1.94 1.94 0 0 0 2.2 1l.8-.2a1.94 1.94 0 0 1 2.4 2.4l-.2.8a1.94 1.94 0 0 0 1 2.2l.7.4a1.94 1.94 0 0 1 0 3.4l-.7.4a1.94 1.94 0 0 0-1 2.2l.2.8a1.94 1.94 0 0 1-2.4 2.4l-.8-.2a1.94 1.94 0 0 0-2.2 1l-.4.7a1.94 1.94 0 0 1-3.4 0l-.4-.7a1.94 1.94 0 0 0-2.2-1l-.8.2a1.94 1.94 0 0 1-2.4-2.4l.2-.8a1.94 1.94 0 0 0-1-2.2l-.7-.4a1.94 1.94 0 0 1 0-3.4l.7-.4a1.94 1.94 0 0 0 1-2.2l-.2-.8a1.94 1.94 0 0 1 2.4-2.4l.8.2a1.94 1.94 0 0 0 2.2-1Z"/><circle cx="12" cy="12" r="3.25"/></svg>
          <span>Configuración</span>
        </button>
      </nav>

      <div class="px-4 py-3 border-t border-slate-200 flex items-center justify-between shrink-0">
        <button @click="showLogs = !showLogs"
                :class="showLogs ? 'text-blue-600' : 'text-slate-400 hover:text-slate-700'"
                class="flex items-center gap-1.5 text-[11px] font-medium transition-colors">
          <span class="w-1.5 h-1.5 rounded-full bg-emerald-500 shrink-0"></span>
          <span>Logs</span>
        </button>
        <span class="text-[10px] font-medium text-slate-400">v0.1.0-alpha</span>
      </div>
    </aside>

    <!-- Main Content Area -->
    <main class="flex-1 overflow-hidden flex flex-col relative">
      <!-- Topbar contextual: título + subtítulo por pantalla (igual que el mock) -->
      <div class="flex items-center justify-between gap-4 px-5 py-3 border-b border-slate-200 bg-[var(--bg)] shrink-0">
        <div>
          <div class="text-base font-semibold text-slate-900 leading-tight">{{ viewMeta.title }}</div>
          <div class="text-xs text-slate-400 mt-0.5">{{ viewMeta.sub }}</div>
        </div>
      </div>

      <div class="flex-1 overflow-y-auto p-5 relative">
        <Transition name="fade" mode="out-in">
          <Dashboard v-if="currentView === 'dashboard'"
                    @select-camera="goToCalibration"
                    @notify="notify" />
          <ImageIngest v-else-if="currentView === 'ingest'"
                     @notify="notify"
                     @go-resultados="goToResultados" />
          <CoastlineAnalysis v-else-if="currentView === 'resultados'"
                             @notify="notify" />
          <GeoJSONMap v-else-if="currentView === 'geomap'"
                     @notify="notify" />
          <Calibration v-else-if="currentView === 'calibration'"
                     :initial-cam-id="selectedCamId"
                     @notify="notify" />
          <Cameras v-else-if="currentView === 'cameras'"
                     @notify="notify"
                     @calibrate-camera="goToCalibration" />
          <AutoMode v-else-if="currentView === 'automode'"
                     @notify="notify" />
          <Settings v-else-if="currentView === 'settings'"
                     @notify="notify" />
        </Transition>
      </div>

      <!-- Log Console Panel -->
      <div v-if="showLogs" class="h-48 bg-[#14181c] border-t border-slate-800 text-slate-300 font-mono text-[10px] overflow-hidden flex flex-col shrink-0">
        <div class="px-4 py-2 border-b border-slate-800 flex justify-between items-center shrink-0">
          <div class="flex items-center space-x-4">
             <span class="font-semibold uppercase tracking-wider text-slate-500">Consola de eventos</span>
             <button @click="logs = []" class="text-blue-400 hover:text-blue-300 font-medium uppercase">Limpiar</button>
          </div>
          <button @click="showLogs = false" class="text-slate-500 hover:text-white font-medium text-sm">×</button>
        </div>
        <div class="flex-1 overflow-y-auto p-3 space-y-1 scrollbar-thin">
          <div v-for="(log, idx) in logs.slice().reverse()" :key="idx" class="flex space-x-4 border-b border-slate-800/60 pb-1">
            <span class="text-slate-600">[{{ log.time }}]</span>
            <span :class="log.type === 'error' ? 'text-red-400' : (log.type === 'success' ? 'text-emerald-400' : 'text-blue-400')" class="font-semibold uppercase w-16">
              {{ log.type }}
            </span>
            <span class="text-slate-300 leading-relaxed">{{ log.msg }}</span>
          </div>
        </div>
      </div>
    </main>

    <!-- Simple Notifications (Toasts) -->
    <div class="fixed bottom-6 right-6 z-[100] space-y-2">
      <TransitionGroup name="list">
        <div v-for="n in notifications" :key="n.id"
             class="px-4 py-3 bg-white border rounded-md flex items-center justify-between min-w-[300px]"
             :class="n.type === 'error' ? 'border-red-200' : (n.type === 'success' ? 'border-emerald-200' : 'border-slate-200')">
          <div class="flex items-center gap-2.5 text-sm font-medium text-slate-700">
             <!-- Icono además de color: el estado no debe depender solo del tono -->
             <svg v-if="n.type === 'error'" class="w-4 h-4 text-red-500 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v4m0 4h.01M10.29 3.86 1.82 18a1 1 0 0 0 .87 1.5h18.62a1 1 0 0 0 .87-1.5L13.71 3.86a1 1 0 0 0-1.72 0Z"/></svg>
             <svg v-else-if="n.type === 'success'" class="w-4 h-4 text-emerald-500 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"/></svg>
             <svg v-else class="w-4 h-4 text-blue-600 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z"/></svg>
             <span>{{ n.message }}</span>
          </div>
          <button @click="notifications = notifications.filter(x => x.id !== n.id)" class="ml-4 text-slate-300 hover:text-slate-500">
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M6 18L18 6M6 6l12 12" stroke-width="2" stroke-linecap="round"/></svg>
          </button>
        </div>
      </TransitionGroup>
    </div>
  </div>
</template>

<style>
.fade-enter-active, .fade-leave-active { transition: opacity 0.1s ease; }
.fade-enter-from, .fade-leave-to { opacity: 0; }

.list-enter-active, .list-leave-active { transition: all 0.3s ease; }
.list-enter-from { opacity: 0; transform: translateY(20px); }
.list-leave-to { opacity: 0; transform: scale(0.9); }

.scrollbar-thin::-webkit-scrollbar { width: 4px; }
.scrollbar-thin::-webkit-scrollbar-track { background: #0f172a; }
.scrollbar-thin::-webkit-scrollbar-thumb { background: #334155; border-radius: 4px; }
</style>
