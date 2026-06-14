<script setup>
import { ref, onMounted } from 'vue'
import Dashboard from './components/Dashboard.vue'
import Calibration from './components/Calibration.vue'
import ROIAnalysis from './components/ROIAnalysis.vue'

const currentView = ref('dashboard')
const selectedCamId = ref(null)
const notifications = ref([])

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
</script>

<template>
  <div class="flex h-screen bg-white font-sans text-slate-900 overflow-hidden">
    <!-- Notifications (Toasts) -->
    <div class="fixed top-6 right-6 z-[100] space-y-3 w-80">
      <TransitionGroup name="list">
        <div v-for="n in notifications" :key="n.id" 
             :class="n.type === 'error' ? 'bg-red-600' : (n.type === 'success' ? 'bg-emerald-600' : 'bg-slate-900')"
             class="p-4 rounded-2xl text-white text-[11px] font-bold shadow-2xl flex items-center justify-between pointer-events-auto border border-white/10 backdrop-blur-md">
          <div class="flex items-center space-x-3">
             <div v-if="n.type === 'success'" class="w-1.5 h-1.5 rounded-full bg-white animate-pulse"></div>
             <span>{{ n.message }}</span>
          </div>
          <button @click="notifications = notifications.filter(x => x.id !== n.id)" class="ml-4 opacity-50 hover:opacity-100 transition-opacity">
            <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M6 18L18 6M6 6l12 12" stroke-width="2" stroke-linecap="round"/></svg>
          </button>
        </div>
      </TransitionGroup>
    </div>

    <!-- Sidebar -->
    <aside class="w-64 border-r border-slate-100 flex flex-col bg-slate-50/50 flex-shrink-0">
      <div class="p-8">
        <div class="flex items-center space-x-3 mb-12">
          <div class="w-8 h-8 bg-slate-900 rounded-lg flex items-center justify-center">
            <svg class="w-5 h-5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z"></path></svg>
          </div>
          <span class="text-lg font-bold tracking-tight">CV-LIT</span>
        </div>

        <nav class="space-y-1">
          <button @click="goToDashboard" 
                  :class="currentView === 'dashboard' ? 'bg-white border-slate-200 text-slate-900 shadow-sm' : 'text-slate-500 hover:text-slate-900'"
                  class="w-full flex items-center space-x-3 p-3 rounded-xl border border-transparent transition-all duration-200 group">
            <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2V6zM14 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2V6zM4 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2v-2zM14 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2v-2z"></path></svg>
            <span class="text-sm font-semibold">Dashboard</span>
          </button>

          <button @click="goToCalibration()" 
                  :class="currentView === 'calibration' ? 'bg-white border-slate-200 text-slate-900 shadow-sm' : 'text-slate-500 hover:text-slate-900'"
                  class="w-full flex items-center space-x-3 p-3 rounded-xl border border-transparent transition-all duration-200 group">
            <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 15l-2 5L9 9l11 4-5 2zm0 0l5 5M7.188 2.239l.777 2.897M5.136 7.965l-2.898-.777M13.95 4.05l-2.122 2.122m-5.657 5.656l-2.12 2.122"></path></svg>
            <span class="text-sm font-semibold">Calibracion</span>
          </button>

          <div class="h-px bg-slate-100 my-4"></div>

          <button @click="currentView = 'roi'" 
                  :class="currentView === 'roi' ? 'bg-white border-slate-200 text-slate-900 shadow-sm' : 'text-slate-500 hover:text-slate-900'"
                  class="w-full flex items-center space-x-3 p-3 rounded-xl border border-transparent transition-all duration-200 group">
            <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z"></path></svg>
            <span class="text-sm font-semibold">Analisis ROI</span>
          </button>
        </nav>
      </div>

      <div class="mt-auto p-8 text-[10px] font-medium text-slate-400 uppercase tracking-widest">
        v1.1.0-ux-pulido
      </div>
    </aside>

    <!-- Main Content -->
    <main class="flex-1 overflow-y-auto bg-white relative">
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
    </main>
  </div>
</template>

<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
body {
  font-family: 'Inter', sans-serif;
  -webkit-font-smoothing: antialiased;
}

.fade-enter-active, .fade-leave-active { transition: opacity 0.2s ease; }
.fade-enter-from, .fade-leave-to { opacity: 0; }

.list-enter-active, .list-leave-active { transition: all 0.4s ease; }
.list-enter-from { opacity: 0; transform: translateX(30px); }
.list-leave-to { opacity: 0; transform: scale(0.9); }

/* Custom Scrollbar */
::-webkit-scrollbar { width: 5px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: #f1f5f9; border-radius: 10px; }
::-webkit-scrollbar-thumb:hover { background: #e2e8f0; }

.cursor-crosshair { cursor: crosshair; }
</style>
