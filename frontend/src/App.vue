<script setup>
import { ref, onMounted } from 'vue'
import Dashboard from './components/Dashboard.vue'
import Calibration from './components/Calibration.vue'
import ROIAnalysis from './components/ROIAnalysis.vue'

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


onMounted(() => {
  fetchLogs()
  setInterval(fetchLogs, 3000)
})
</script>

<template>
  <div class="flex flex-col h-screen bg-[#f1f5f9] font-sans text-slate-800">
    <!-- Top Header Bar -->
    <header class="h-14 bg-slate-900 text-white flex items-center justify-between px-6 shrink-0 shadow-md z-[60]">
      <div class="flex items-center space-x-3">
        <div class="w-8 h-8 bg-blue-600 rounded flex items-center justify-center">
          <svg class="w-5 h-5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M13 10V3L4 14h7v7l9-11h-7z"></path></svg>
        </div>
        <span class="text-lg font-bold tracking-tight uppercase">CV-LIT <span class="text-blue-400 font-normal text-sm ml-2">UA Engineering</span></span>
      </div>
      <div class="flex items-center space-x-6 text-xs font-medium">
        <button @click="showLogs = !showLogs" 
                :class="showLogs ? 'text-blue-400 font-bold' : 'text-slate-400 hover:text-white'"
                class="transition-colors flex items-center space-x-2">
          <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" stroke-width="2"/></svg>
          <span>Logs Sistema</span>
        </button>
        <div class="h-4 w-px bg-slate-700"></div>
        <div class="flex items-center space-x-2">
          <div class="w-2 h-2 rounded-full bg-emerald-500"></div>
          <span>Sistema Online</span>
        </div>
      </div>
    </header>

    <div class="flex flex-1 overflow-hidden relative">
      <!-- Sidebar -->
      <aside class="w-64 bg-slate-800 text-slate-300 flex flex-col shrink-0 z-50">
        <nav class="flex-1 py-6">
          <div class="px-6 mb-6 text-[10px] font-bold text-slate-500 uppercase tracking-widest">Navegación</div>
          <div class="space-y-1">
            <button @click="goToDashboard" 
                    :class="currentView === 'dashboard' ? 'bg-blue-600 text-white' : 'hover:bg-slate-700 hover:text-white'"
                    class="w-full flex items-center space-x-3 px-6 py-3 transition-colors text-sm font-medium">
              <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-width="2" d="M4 6h16M4 12h16M4 18h16"></path></svg>
              <span>Vista General</span>
            </button>
            <button @click="currentView = 'roi'" 
                    :class="currentView === 'roi' ? 'bg-blue-600 text-white' : 'hover:bg-slate-700 hover:text-white'"
                    class="w-full flex items-center space-x-3 px-6 py-3 transition-colors text-sm font-medium">
              <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-width="2" d="M9 20l-5.447-2.724A2 2 0 013 15.483V6.517a2 2 0 011.553-1.793L9 3.5l5.447 1.224A2 2 0 0116 6.517v8.966a2 2 0 01-1.553 1.793L9 18.5z"></path></svg>
              <span>Análisis ROI</span>
            </button>
            <button @click="goToCalibration()"
                    :class="currentView === 'calibration' ? 'bg-blue-600 text-white' : 'hover:bg-slate-700 hover:text-white'"
                    class="w-full flex items-center space-x-3 px-6 py-3 transition-colors text-sm font-medium">
              <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-width="2" d="M12 6V4m0 2a2 2 0 100 4m0-4a2 2 0 110 4m-6 8a2 2 0 100-4m0 4a2 2 0 110-4m10 4a2 2 0 100-4m0 4a2 2 0 110-4m-4 2a2 2 0 100-4m0 4a2 2 0 110-4"></path></svg>
              <span>Calibración</span>
            </button>
          </div>
        </nav>
        
        <div class="p-4 bg-slate-900/50">
          <div class="flex items-center space-x-3">
            <div class="w-8 h-8 rounded bg-slate-700 flex items-center justify-center font-bold text-xs">UA</div>
            <div class="text-[10px] min-w-0">
              <p class="font-bold text-white truncate">Administrador</p>
              <p class="text-slate-500 truncate">Ingeniería UA</p>
            </div>
          </div>
        </div>
      </aside>

      <!-- Main Content Area -->
      <main class="flex-1 overflow-hidden flex flex-col relative">
        <div class="flex-1 overflow-y-auto p-8 relative">
          <Transition name="fade" mode="out-in">
            <Dashboard v-if="currentView === 'dashboard'" 
                      @select-camera="goToCalibration" 
                      @notify="notify" />
            <Calibration v-else-if="currentView === 'calibration'" 
                       :initial-cam-id="selectedCamId" 
                       @notify="notify" />
            <ROIAnalysis v-else-if="currentView === 'roi'"
                        @notify="notify" />
          </Transition>
        </div>

        <!-- Log Console Panel -->
        <div v-if="showLogs" class="h-48 bg-slate-900 border-t border-slate-700 text-slate-300 font-mono text-[10px] overflow-hidden flex flex-col shrink-0 shadow-2xl">
          <div class="px-4 py-2 bg-slate-800 flex justify-between items-center shrink-0">
            <div class="flex items-center space-x-4">
               <span class="font-bold uppercase tracking-widest text-slate-400">Consola de Eventos Backend</span>
               <button @click="logs = []" class="text-blue-400 hover:text-blue-300 font-bold uppercase tracking-tighter">[Limpiar]</button>
            </div>
            <button @click="showLogs = false" class="text-slate-500 hover:text-white font-bold text-sm">×</button>
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
             class="px-4 py-3 bg-white border border-slate-200 rounded shadow-lg flex items-center justify-between min-w-[300px]">
          <div class="flex items-center space-x-3 text-sm font-medium">
             <div :class="n.type === 'error' ? 'bg-red-500' : (n.type === 'success' ? 'bg-emerald-500' : 'bg-blue-600')"
                  class="w-1.5 h-1.5 rounded-full"></div>
             <span>{{ n.message }}</span>
          </div>
          <button @click="notifications = notifications.filter(x => x.id !== n.id)" class="ml-4 text-slate-400 hover:text-slate-600">
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
