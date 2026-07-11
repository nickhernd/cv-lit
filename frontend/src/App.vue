<script setup>
import { ref, onMounted } from 'vue'
import Dashboard from './components/Dashboard.vue'
import Calibration from './components/Calibration.vue'
import CoastlineAnalysis from './components/CoastlineAnalysis.vue'
import ImageIngest from './components/ImageIngest.vue'
import GeoJSONMap from './components/GeoJSONMap.vue'
import Cameras from './components/Cameras.vue'
import AutoMode from './components/AutoMode.vue'

const currentView = ref('dashboard')
const selectedCamId = ref(null)
const notifications = ref([])
const logs = ref([])
const showLogs = ref(false)

async function fetchLogs() {
  try {
    const res = await fetch('http://localhost:8000/api/logs')
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
  <div class="flex flex-col h-screen bg-[#f1f5f9] font-sans text-slate-800">
    <!-- Top Header Bar -->
    <header class="h-14 bg-slate-900 text-white flex items-center justify-between px-6 shrink-0 z-[60]">
      <div class="flex items-center space-x-3">
        <div class="w-7 h-7 bg-blue-600 rounded-lg flex items-center justify-center">
          <svg class="w-4 h-4 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M13 10V3L4 14h7v7l9-11h-7z"></path></svg>
        </div>
        <span class="text-[15px] font-semibold tracking-tight">CV-LIT <span class="text-slate-500 font-normal text-xs ml-1.5">UA Engineering</span></span>
      </div>
      <div class="flex items-center space-x-5 text-xs font-medium">
        <button @click="showLogs = !showLogs"
                :class="showLogs ? 'text-blue-400' : 'text-slate-400 hover:text-slate-100'"
                class="transition-colors flex items-center space-x-2">
          <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" stroke-width="2"/></svg>
          <span>Logs</span>
        </button>
        <div class="h-4 w-px bg-slate-800"></div>
        <div class="flex items-center space-x-2 text-slate-400">
          <div class="w-1.5 h-1.5 rounded-full bg-emerald-500"></div>
          <span>Sistema online</span>
        </div>
      </div>
    </header>

    <div class="flex flex-1 overflow-hidden relative">
      <!-- Sidebar -->
      <aside class="w-60 bg-slate-800 text-slate-300 flex flex-col shrink-0 z-50">
        <nav class="flex-1 py-6 px-3">
          <div class="px-3 mb-2 text-[10px] font-semibold text-slate-500 uppercase tracking-widest">Proceso</div>
          <div class="space-y-0.5 mb-6">
            <button @click="goToDashboard"
                    :class="currentView === 'dashboard' ? 'bg-blue-600/15 text-blue-300' : 'text-slate-400 hover:bg-white/5 hover:text-slate-100'"
                    class="w-full flex items-center space-x-2.5 px-3 py-2 rounded-lg transition-colors text-sm font-medium">
              <svg class="w-4 h-4 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-width="1.75" d="M4 6h16M4 12h16M4 18h16"></path></svg>
              <span>Dashboard</span>
            </button>
            <button @click="currentView = 'ingest'"
                    :class="currentView === 'ingest' ? 'bg-blue-600/15 text-blue-300' : 'text-slate-400 hover:bg-white/5 hover:text-slate-100'"
                    class="w-full flex items-center space-x-2.5 px-3 py-2 rounded-lg transition-colors text-sm font-medium">
              <svg class="w-4 h-4 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-width="1.75" d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z"/></svg>
              <span>Carga de imágenes</span>
            </button>
            <button @click="goToResultados()"
                    :class="currentView === 'resultados' ? 'bg-blue-600/15 text-blue-300' : 'text-slate-400 hover:bg-white/5 hover:text-slate-100'"
                    class="w-full flex items-center space-x-2.5 px-3 py-2 rounded-lg transition-colors text-sm font-medium">
              <svg class="w-4 h-4 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-width="1.75" d="M3 17c2-2 4-3 6-1s4 3 6 1 4-2 6-1M3 12c2-2 4-3 6-1s4 3 6 1 4-2 6-1"/></svg>
              <span>Resultados</span>
            </button>
            <button @click="currentView = 'geomap'"
                    :class="currentView === 'geomap' ? 'bg-blue-600/15 text-blue-300' : 'text-slate-400 hover:bg-white/5 hover:text-slate-100'"
                    class="w-full flex items-center space-x-2.5 px-3 py-2 rounded-lg transition-colors text-sm font-medium">
              <svg class="w-4 h-4 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-width="1.75" d="M9 20l-5.447-2.724A2 2 0 013 15.483V6.517a2 2 0 011.553-1.793L9 3.5l5.447 1.224A2 2 0 0116 6.517v8.966a2 2 0 01-1.553 1.793L9 18.5z"/></svg>
              <span>Mapa GeoJSON</span>
            </button>
          </div>

          <div class="px-3 mb-2 text-[10px] font-semibold text-slate-500 uppercase tracking-widest">Sistema</div>
          <div class="space-y-0.5">
            <button @click="goToCalibration()"
                    :class="currentView === 'calibration' ? 'bg-blue-600/15 text-blue-300' : 'text-slate-400 hover:bg-white/5 hover:text-slate-100'"
                    class="w-full flex items-center space-x-2.5 px-3 py-2 rounded-lg transition-colors text-sm font-medium">
              <svg class="w-4 h-4 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-width="1.75" d="M12 6V4m0 2a2 2 0 100 4m0-4a2 2 0 110 4m-6 8a2 2 0 100-4m0 4a2 2 0 110-4m10 4a2 2 0 100-4m0 4a2 2 0 110-4m-4 2a2 2 0 100-4m0 4a2 2 0 110-4"></path></svg>
              <span>Calibración</span>
            </button>
            <button @click="currentView = 'cameras'"
                    :class="currentView === 'cameras' ? 'bg-blue-600/15 text-blue-300' : 'text-slate-400 hover:bg-white/5 hover:text-slate-100'"
                    class="w-full flex items-center space-x-2.5 px-3 py-2 rounded-lg transition-colors text-sm font-medium">
              <svg class="w-4 h-4 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-width="1.75" d="M3 9a2 2 0 012-2h.93a2 2 0 001.664-.89l.812-1.22A2 2 0 0110.07 4h3.86a2 2 0 011.664.89l.812 1.22A2 2 0 0018.07 7H19a2 2 0 012 2v9a2 2 0 01-2 2H5a2 2 0 01-2-2V9z"/><circle cx="12" cy="13" r="3" stroke-width="1.75"/></svg>
              <span>Cámaras</span>
            </button>
            <button @click="currentView = 'automode'"
                    :class="currentView === 'automode' ? 'bg-blue-600/15 text-blue-300' : 'text-slate-400 hover:bg-white/5 hover:text-slate-100'"
                    class="w-full flex items-center space-x-2.5 px-3 py-2 rounded-lg transition-colors text-sm font-medium">
              <svg class="w-4 h-4 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-width="1.75" d="M13 10V3L4 14h7v7l9-11h-7z"/></svg>
              <span>Modo automático</span>
            </button>
          </div>
        </nav>

        <div class="px-4 py-4 border-t border-white/5 flex items-center justify-between">
          <div class="flex items-center space-x-2.5 min-w-0">
            <div class="w-7 h-7 rounded-lg bg-slate-700 flex items-center justify-center font-semibold text-[10px] shrink-0">UA</div>
            <div class="text-[11px] min-w-0">
              <p class="font-medium text-slate-200 truncate">Administrador</p>
              <p class="text-slate-500 truncate">Ingeniería UA</p>
            </div>
          </div>
          <span class="text-[9px] font-medium text-slate-600 shrink-0">v0.1.0</span>
        </div>
      </aside>

      <!-- Main Content Area -->
      <main class="flex-1 overflow-hidden flex flex-col relative">
        <div class="flex-1 overflow-y-auto p-8 relative">
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
          </Transition>
        </div>

        <!-- Log Console Panel -->
        <div v-if="showLogs" class="h-48 bg-slate-900 border-t border-slate-800 text-slate-300 font-mono text-[10px] overflow-hidden flex flex-col shrink-0">
          <div class="px-4 py-2.5 border-b border-slate-800 flex justify-between items-center shrink-0">
            <div class="flex items-center space-x-4">
               <span class="font-semibold uppercase tracking-widest text-slate-500">Consola de eventos</span>
               <button @click="logs = []" class="text-blue-400 hover:text-blue-300 font-medium uppercase">Limpiar</button>
            </div>
            <button @click="showLogs = false" class="text-slate-500 hover:text-white font-medium text-sm">×</button>
          </div>
          <div class="flex-1 overflow-y-auto p-4 space-y-1 scrollbar-thin">
            <div v-for="(log, idx) in logs.slice().reverse()" :key="idx" class="flex space-x-4 border-b border-slate-800 pb-1">
              <span class="text-slate-600">[{{ log.time }}]</span>
              <span :class="log.type === 'error' ? 'text-red-400' : (log.type === 'success' ? 'text-emerald-400' : 'text-blue-400')" class="font-bold uppercase w-16">
                {{ log.type }}
              </span>
              <span class="text-slate-300 leading-relaxed">{{ log.msg }}</span>
            </div>
          </div>
        </div>
      </main>
    </div>

    <!-- Simple Notifications (Toasts) -->
    <div class="fixed bottom-6 right-6 z-[100] space-y-2">
      <TransitionGroup name="list">
        <div v-for="n in notifications" :key="n.id"
             class="px-4 py-3 bg-white border border-slate-100 rounded-xl shadow-lg flex items-center justify-between min-w-[300px]">
          <div class="flex items-center space-x-3 text-sm font-medium text-slate-700">
             <div :class="n.type === 'error' ? 'bg-red-500' : (n.type === 'success' ? 'bg-emerald-500' : 'bg-blue-600')"
                  class="w-1.5 h-1.5 rounded-full shrink-0"></div>
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
