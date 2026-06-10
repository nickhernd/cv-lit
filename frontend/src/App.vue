<script setup>
import { ref } from 'vue'
import Dashboard from './components/Dashboard.vue'
import Calibration from './components/Calibration.vue'
import ROIAnalysis from './components/ROIAnalysis.vue'

const currentView = ref('dashboard')
const selectedCamId = ref(null)

function goToCalibration(camId = null) {
  selectedCamId.value = camId
  currentView.value = 'calibration'
}

function goToDashboard() {
  currentView.value = 'dashboard'
}
</script>

<template>
  <div class="flex h-screen bg-white font-sans text-slate-900">
    <!-- Sidebar - Minimalist & Flat -->
    <aside class="w-64 border-r border-slate-100 flex flex-col bg-slate-50/50">
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
            <span class="text-sm font-semibold">Calibración</span>
          </button>

          <div class="h-px bg-slate-100 my-4"></div>

          <button @click="currentView = 'roi'" 
                  :class="currentView === 'roi' ? 'bg-white border-slate-200 text-slate-900 shadow-sm' : 'text-slate-500 hover:text-slate-900'"
                  class="w-full flex items-center space-x-3 p-3 rounded-xl border border-transparent transition-all duration-200 group">
            <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z"></path></svg>
            <span class="text-sm font-semibold">Análisis ROI</span>
          </button>
        </nav>
      </div>

      <div class="mt-auto p-8 text-[10px] font-medium text-slate-400 uppercase tracking-widest">
        v1.0.4-beta
      </div>
    </aside>

    <!-- Main Content -->
    <main class="flex-1 overflow-y-auto bg-white">
      <Dashboard v-if="currentView === 'dashboard'" @select-camera="goToCalibration" />
      <Calibration v-if="currentView === 'calibration'" :initial-cam-id="selectedCamId" />
      <ROIAnalysis v-if="currentView === 'roi'" />
    </main>
  </div>
</template>

<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
body {
  font-family: 'Inter', sans-serif;
}
</style>
