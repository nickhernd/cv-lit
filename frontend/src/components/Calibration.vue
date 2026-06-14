<script setup>
import { ref, onMounted, computed, watch } from 'vue'

const props = defineProps({
  initialCamId: { type: Number, default: null }
})

const emit = defineEmits(['notify'])

const currentStep = ref(1)
const selectedCamId = ref(props.initialCamId)
const cameras = ref([])
const availableImages = ref([])
const selectedImage = ref('')
const currentProfile = ref({ gcps: [] })
const loading = ref(false)
const saving = ref(false)
const calculating = ref(false)
const rmse = ref(null)

// UX State
const selectedGcpIdx = ref(null)
const isDragging = ref(false)

const steps = [
  { id: 1, name: 'Entrada', desc: 'Gestion de Archivos' },
  { id: 2, name: 'Calibracion', desc: 'Marcacion GCP' },
  { id: 3, name: 'Validacion', desc: 'Vista Rectificada' }
]

const imageUrl = computed(() => {
  if (!selectedCamId.value || !selectedImage.value) return null
  return `http://localhost:8000/api/cameras/${selectedCamId.value}/image?file=${selectedImage.value}&t=${Date.now()}`
})

const rectifiedUrl = computed(() => {
  if (!selectedCamId.value || !rmse.value) return null
  return `http://localhost:8000/api/cameras/${selectedCamId.value}/rectified-preview?t=${Date.now()}`
})

async function fetchCameras() {
  try {
    const res = await fetch('http://localhost:8000/api/dashboard')
    const data = await res.json()
    cameras.value = data.cameras
  } catch (err) { emit('notify', 'Error al cargar camaras', 'error') }
}

async function fetchImages() {
  if (!selectedCamId.value) return
  try {
    const res = await fetch(`http://localhost:8000/api/cameras/${selectedCamId.value}/images`)
    availableImages.value = await res.json()
    if (availableImages.value.length > 0 && !selectedImage.value) {
      selectedImage.value = availableImages.value[0]
    }
  } catch (err) { console.error(err) }
}

async function fetchProfile() {
  if (!selectedCamId.value) return
  loading.value = true
  try {
    const res = await fetch(`http://localhost:8000/api/cameras/${selectedCamId.value}/profile`)
    currentProfile.value = await res.json()
    if (!currentProfile.value.gcps) currentProfile.value.gcps = []
    rmse.value = currentProfile.value.rmse_m || null
  } catch (err) { console.error(err) }
  finally { loading.value = false }
}

async function handleFiles(files) {
  const formData = new FormData()
  for (let f of files) formData.append('files', f)
  try {
    const res = await fetch(`http://localhost:8000/api/cameras/${selectedCamId.value}/upload-images`, {
      method: 'POST', body: formData
    })
    const data = await res.json()
    if (res.ok) {
      if (data.skipped.length > 0) {
        emit('notify', `Subidos ${data.uploaded.length} archivos. ${data.skipped.length} omitidos por duplicados.`, 'info')
      } else {
        emit('notify', 'Imagenes subidas con exito', 'success')
      }
      fetchImages()
    }
  } catch (err) { emit('notify', 'Error al subir imagenes', 'error') }
}

async function deleteImage(filename) {
  if (!confirm(`¿Borrar imagen ${filename}?`)) return
  try {
    const res = await fetch(`http://localhost:8000/api/cameras/${selectedCamId.value}/images/${filename}`, {
      method: 'DELETE'
    })
    if (res.ok) {
      emit('notify', 'Imagen eliminada', 'success')
      if (selectedImage.value === filename) selectedImage.value = ''
      fetchImages()
    } else {
      const err = await res.json()
      emit('notify', err.detail, 'error')
    }
  } catch (err) { emit('notify', 'Error de red', 'error') }
}

async function calculateHomography() {
  calculating.value = true
  try {
    const res = await fetch(`http://localhost:8000/api/cameras/${selectedCamId.value}/calculate-homography?image_name=${selectedImage.value}`, {
      method: 'POST'
    })
    const data = await res.json()
    if (res.ok) {
      rmse.value = data.rmse_m
      emit('notify', 'Homografia calculada correctamente', 'success')
      currentStep.value = 3
    } else { emit('notify', data.detail, 'error') }
  } catch (err) { emit('notify', 'Error de conexion', 'error') }
  finally { calculating.value = false }
}

function handleImageClick(event) {
  if (currentStep.value !== 2) return
  const rect = event.target.getBoundingClientRect()
  const x = event.clientX - rect.left
  const y = event.clientY - rect.top
  const relX = (x / event.target.clientWidth) * 100
  const relY = (y / event.target.clientHeight) * 100
  
  const newGcp = {
    pixel: [x, y],
    utm: [0, 0],
    label: `GCP_${currentProfile.value.gcps.length + 1}`,
    type: 'calib',
    rel: [relX, relY]
  }
  
  currentProfile.value.gcps.push(newGcp)
  selectedGcpIdx.value = currentProfile.value.gcps.length - 1
}

async function saveCalibration() {
  saving.value = true
  try {
    await fetch(`http://localhost:8000/api/cameras/${selectedCamId.value}/calibrate`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ cam_id: selectedCamId.value, gcps: currentProfile.value.gcps })
    })
    emit('notify', 'Configuracion guardada', 'success')
  } catch (err) { emit('notify', 'Error al guardar', 'error') }
  finally { saving.value = false }
}

watch(selectedCamId, () => {
  if (selectedCamId.value) {
    fetchProfile()
    fetchImages()
    selectedGcpIdx.value = null
  }
})

onMounted(() => {
  fetchCameras()
  if (selectedCamId.value) {
    fetchProfile()
    fetchImages()
  }
})
</script>

<template>
  <div class="p-12 max-w-7xl mx-auto flex flex-col h-full">
    <!-- Stepper -->
    <div class="mb-12 flex items-center justify-between max-w-2xl mx-auto w-full relative">
      <div v-for="step in steps" :key="step.id" class="z-10 flex flex-col items-center">
        <div @click="currentStep = step.id" 
             :class="currentStep >= step.id ? 'bg-slate-900 text-white cursor-pointer shadow-lg' : 'bg-white border-2 border-slate-100 text-slate-300 pointer-events-none'"
             class="w-10 h-10 rounded-full flex items-center justify-center text-xs font-bold transition-all duration-300">
          <svg v-if="currentStep > step.id" class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M5 13l4 4L19 7" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/></svg>
          <span v-else>{{ step.id }}</span>
        </div>
        <span class="text-[10px] font-bold uppercase tracking-widest mt-3" :class="currentStep >= step.id ? 'text-slate-900' : 'text-slate-300'">{{ step.name }}</span>
      </div>
      <div class="absolute top-5 left-0 w-full h-[2px] bg-slate-100 -z-0">
        <div class="h-full bg-slate-900 transition-all duration-500" :style="{ width: ((currentStep - 1) / (steps.length - 1)) * 100 + '%' }"></div>
      </div>
    </div>

    <!-- STEP 1: GESTION -->
    <div v-if="currentStep === 1" class="flex-1 animate-fade-in space-y-12">
      <div class="grid grid-cols-1 md:grid-cols-2 gap-12">
        <div class="p-10 border border-slate-100 rounded-[3rem] bg-slate-50/50 space-y-8">
          <div>
            <h3 class="text-sm font-bold text-slate-900 uppercase tracking-widest mb-2">1. Seleccionar Camara</h3>
            <p class="text-xs text-slate-400">Elige el dispositivo que deseas calibrar.</p>
          </div>
          <select v-model="selectedCamId" class="w-full bg-white border border-slate-200 rounded-2xl px-6 py-4 text-sm font-semibold outline-none shadow-sm focus:border-slate-900 transition-all">
            <option :value="null">Seleccionar Dispositivo...</option>
            <option v-for="cam in cameras" :key="cam.idx" :value="cam.idx">{{ cam.name }}</option>
          </select>
        </div>

        <div class="p-1 border border-slate-100 rounded-[3rem] bg-white shadow-xl relative group">
          <div @dragover.prevent="isDragging = true" 
               @dragleave.prevent="isDragging = false"
               @drop.prevent="isDragging = false; handleFiles($event.dataTransfer.files)"
               :class="isDragging ? 'bg-slate-900 border-slate-900 text-white' : 'bg-slate-50/50 border-slate-100 text-slate-400'"
               class="h-full w-full rounded-[2.8rem] border-2 border-dashed flex flex-col items-center justify-center p-12 transition-all cursor-pointer">
            <input type="file" multiple @change="handleFiles($event.target.files)" class="absolute inset-0 opacity-0 cursor-pointer">
            <svg class="w-12 h-12 mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>
            <span class="text-xs font-bold uppercase tracking-[0.2em]">{{ isDragging ? 'Soltar para subir' : 'Arrastrar imagenes aqui' }}</span>
          </div>
        </div>
      </div>

      <div v-if="selectedCamId" class="space-y-6">
        <h3 class="text-xs font-bold text-slate-900 uppercase tracking-widest">Galeria de Referencias ({{ availableImages.length }})</h3>
        <div class="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-4">
           <div v-for="img in availableImages" :key="img" 
                class="group relative aspect-video rounded-2xl overflow-hidden border-2 transition-all cursor-pointer"
                :class="selectedImage === img ? 'border-slate-900 scale-[0.98]' : 'border-transparent hover:border-slate-200'"
                @click="selectedImage = img">
              <img :src="`http://localhost:8000/api/cameras/${selectedCamId}/image?file=${img}&thumb=1`" class="w-full h-full object-cover grayscale group-hover:grayscale-0 transition-all">
              <div class="absolute inset-0 bg-black/40 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center">
                 <button @click.stop="deleteImage(img)" class="p-2 bg-red-600 text-white rounded-full hover:scale-110 transition-transform">
                   <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>
                 </button>
              </div>
           </div>
        </div>
        <div class="flex justify-center pt-8">
           <button @click="currentStep = 2" :disabled="!selectedImage" 
                   class="px-12 py-4 bg-slate-900 text-white rounded-2xl text-sm font-bold uppercase tracking-widest hover:scale-105 active:scale-95 disabled:opacity-20 transition-all shadow-xl shadow-slate-900/20">
             Iniciar Marcacion
           </button>
        </div>
      </div>
    </div>

    <!-- STEP 2: MARCACION -->
    <div v-if="currentStep === 2" class="flex-1 grid grid-cols-1 lg:grid-cols-4 gap-12 animate-fade-in overflow-hidden">
      <div class="lg:col-span-3 flex flex-col min-h-0">
        <div class="relative flex-1 rounded-[3rem] overflow-hidden border border-slate-100 bg-slate-50 shadow-inner group">
          <img :src="imageUrl" @click="handleImageClick" class="w-full h-full object-contain select-none cursor-crosshair">
          
          <div v-for="(gcp, idx) in currentProfile.gcps" :key="idx" 
               class="absolute -translate-x-1/2 -translate-y-1/2 group/pt"
               :style="{ left: gcp.rel[0] + '%', top: gcp.rel[1] + '%' }">
            <div @click.stop="selectedGcpIdx = idx"
                 :class="[
                   gcp.type === 'rod' ? 'bg-amber-500' : 'bg-blue-600',
                   selectedGcpIdx === idx ? 'scale-150 ring-4 ring-white shadow-2xl' : 'hover:scale-125'
                 ]"
                 class="w-4 h-4 rounded-full border-2 border-white shadow-lg transition-all cursor-pointer">
            </div>
            <div v-if="selectedGcpIdx === idx" class="absolute top-6 left-1/2 -translate-x-1/2 px-2 py-1 bg-slate-900 text-white text-[8px] font-bold rounded shadow-xl whitespace-nowrap z-50">
              {{ gcp.label }}
            </div>
          </div>
        </div>

        <div class="mt-6 flex justify-between items-center bg-slate-50/50 p-6 rounded-[2rem] border border-slate-100">
           <div class="flex space-x-8">
              <div class="flex items-center space-x-3">
                <div class="w-3 h-3 rounded-full bg-blue-600"></div>
                <span class="text-[10px] font-bold uppercase tracking-[0.1em] text-slate-500">Arena (GCP)</span>
              </div>
              <div class="flex items-center space-x-3">
                <div class="w-3 h-3 rounded-full bg-amber-500"></div>
                <span class="text-[10px] font-bold uppercase tracking-[0.1em] text-slate-500">Varilla</span>
              </div>
           </div>
           <div class="flex space-x-4">
              <button @click="saveCalibration" class="px-8 py-3 bg-white border border-slate-200 text-slate-900 rounded-xl text-[10px] font-bold uppercase tracking-widest hover:bg-slate-100 transition-all">Guardar Progreso</button>
              <button @click="calculateHomography" :disabled="currentProfile.gcps.filter(g=>g.type==='calib').length < 4 || calculating"
                      class="px-10 py-3 bg-blue-600 text-white rounded-xl text-[10px] font-bold uppercase tracking-widest shadow-lg shadow-blue-600/20 hover:bg-blue-700 disabled:opacity-20 transition-all">
                {{ calculating ? 'Calculando...' : 'Generar Homografia' }}
              </button>
           </div>
        </div>
      </div>

      <aside class="space-y-6 flex flex-col min-h-0">
        <!-- Edit Panel -->
        <div v-if="selectedGcpIdx !== null" class="p-8 border border-slate-200 rounded-[2.5rem] bg-white shadow-2xl animate-scale-in">
           <div class="flex justify-between items-center mb-6">
              <h4 class="text-xs font-bold text-slate-900 uppercase tracking-widest">Editar Punto</h4>
              <button @click="selectedGcpIdx = null" class="text-slate-300 hover:text-slate-900">
                 <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M6 18L18 6M6 6l12 12" stroke-width="2" stroke-linecap="round"/></svg>
              </button>
           </div>
           <div class="space-y-5">
              <div>
                <label class="text-[9px] font-bold text-slate-400 uppercase tracking-widest block mb-1.5">Identificador</label>
                <input v-model="currentProfile.gcps[selectedGcpIdx].label" class="w-full bg-slate-50 border-none rounded-xl px-4 py-2.5 text-xs font-bold focus:ring-2 focus:ring-slate-200">
              </div>
              <div class="grid grid-cols-2 gap-3">
                <div>
                  <label class="text-[9px] font-bold text-slate-400 uppercase tracking-widest block mb-1.5">UTM X</label>
                  <input type="number" v-model.number="currentProfile.gcps[selectedGcpIdx].utm[0]" class="w-full bg-slate-50 border-none rounded-xl px-4 py-2.5 text-xs font-mono focus:ring-2 focus:ring-slate-200">
                </div>
                <div>
                  <label class="text-[9px] font-bold text-slate-400 uppercase tracking-widest block mb-1.5">UTM Y</label>
                  <input type="number" v-model.number="currentProfile.gcps[selectedGcpIdx].utm[1]" class="w-full bg-slate-50 border-none rounded-xl px-4 py-2.5 text-xs font-mono focus:ring-2 focus:ring-slate-200">
                </div>
              </div>
              <div>
                <label class="text-[9px] font-bold text-slate-400 uppercase tracking-widest block mb-1.5">Tipo</label>
                <div class="flex bg-slate-50 p-1 rounded-xl">
                  <button @click="currentProfile.gcps[selectedGcpIdx].type = 'calib'" 
                          :class="currentProfile.gcps[selectedGcpIdx].type === 'calib' ? 'bg-white shadow text-slate-900' : 'text-slate-400'"
                          class="flex-1 py-2 text-[9px] font-bold uppercase rounded-lg transition-all">GCP</button>
                  <button @click="currentProfile.gcps[selectedGcpIdx].type = 'rod'"
                          :class="currentProfile.gcps[selectedGcpIdx].type === 'rod' ? 'bg-white shadow text-slate-900' : 'text-slate-400'"
                          class="flex-1 py-2 text-[9px] font-bold uppercase rounded-lg transition-all">Varilla</button>
                </div>
              </div>
              <button @click="currentProfile.gcps.splice(selectedGcpIdx, 1); selectedGcpIdx = null" 
                      class="w-full py-3 mt-4 text-red-500 text-[10px] font-bold uppercase tracking-widest hover:bg-red-50 rounded-xl transition-colors">Eliminar Punto</button>
           </div>
        </div>

        <div v-else class="flex-1 border border-slate-100 rounded-[2.5rem] bg-slate-50/50 p-8 overflow-hidden flex flex-col">
           <h4 class="text-[10px] font-bold text-slate-400 uppercase tracking-widest mb-6">Puntos Marcados ({{ currentProfile.gcps.length }})</h4>
           <div class="flex-1 overflow-y-auto custom-scrollbar pr-2 space-y-2">
              <div v-for="(gcp, idx) in currentProfile.gcps" :key="idx" 
                   @click="selectedGcpIdx = idx"
                   class="flex items-center justify-between p-4 bg-white rounded-2xl hover:border-slate-300 border border-transparent transition-all cursor-pointer group">
                <div class="flex items-center space-x-3 min-w-0">
                  <div class="w-2 h-2 rounded-full shrink-0" :class="gcp.type === 'rod' ? 'bg-amber-500' : 'bg-blue-600'"></div>
                  <div class="truncate">
                    <p class="text-[10px] font-bold text-slate-900">{{ gcp.label }}</p>
                    <p class="text-[8px] text-slate-400 font-mono">{{ gcp.utm[0].toFixed(0) }}, {{ gcp.utm[1].toFixed(0) }}</p>
                  </div>
                </div>
                <svg class="w-3 h-3 text-slate-200 group-hover:text-slate-400 transition-colors" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M9 5l7 7-7 7" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/></svg>
              </div>
              <div v-if="!currentProfile.gcps.length" class="h-full flex flex-col items-center justify-center text-center opacity-30 p-4 pt-12">
                 <svg class="w-8 h-8 mb-2" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M15 15l-2 5L9 9l11 4-5 2zm0 0l5 5M7.188 2.239l.777 2.897M5.136 7.965l-2.898-.777M13.95 4.05l-2.122 2.122m-5.657 5.656l-2.12 2.122" stroke-width="1.5"/></svg>
                 <p class="text-[9px] font-bold uppercase tracking-widest">Haz click en la imagen para marcar un punto</p>
              </div>
           </div>
        </div>
      </aside>
    </div>

    <!-- STEP 3: VALIDACION -->
    <div v-if="currentStep === 3" class="max-w-5xl mx-auto flex-1 animate-scale-in flex flex-col justify-center py-12">
      <header class="text-center mb-12">
        <div class="inline-flex items-center px-5 py-2 bg-emerald-50 text-emerald-600 rounded-full text-[10px] font-bold uppercase tracking-widest mb-6 border border-emerald-100 shadow-sm">
           <div class="w-1.5 h-1.5 rounded-full bg-emerald-500 mr-3 animate-pulse"></div>
           Homografia Generada
        </div>
        <h2 class="text-4xl font-bold text-slate-900 tracking-tight">Vista Rectificada</h2>
        <p class="text-slate-400 mt-4 text-sm max-w-md mx-auto leading-relaxed">Precision geometrica validada. Error medio residual: <span class="font-bold text-slate-900 tabular-nums">{{ rmse?.toFixed(4) }} m</span></p>
      </header>
      
      <div class="relative rounded-[4rem] overflow-hidden border-[12px] border-slate-50 bg-slate-100 shadow-2xl mx-auto max-w-3xl transform hover:scale-[1.01] transition-transform duration-500">
        <img :src="rectifiedUrl" class="w-full h-auto block" alt="Rectified View">
        <div class="absolute inset-0 bg-gradient-to-t from-black/20 to-transparent pointer-events-none"></div>
      </div>

      <div class="flex justify-center space-x-6 mt-16">
        <button @click="currentStep = 2" class="px-10 py-4 border-2 border-slate-100 rounded-2xl text-xs font-bold text-slate-500 hover:bg-slate-50 transition-all uppercase tracking-widest">Ajustar Marcacion</button>
        <button @click="currentStep = 1" class="px-12 py-4 bg-slate-900 text-white rounded-2xl text-xs font-bold hover:bg-slate-800 transition-all shadow-2xl shadow-slate-900/20 uppercase tracking-widest">Finalizar Calibracion</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.custom-scrollbar::-webkit-scrollbar { width: 4px; }
.custom-scrollbar::-webkit-scrollbar-track { background: transparent; }
.custom-scrollbar::-webkit-scrollbar-thumb { background: #f1f5f9; border-radius: 20px; }

.animate-scale-in { animation: scaleIn 0.4s cubic-bezier(0.16, 1, 0.3, 1); }
@keyframes scaleIn {
  from { opacity: 0; transform: scale(0.98) translateY(10px); }
  to { opacity: 1; transform: scale(1) translateY(0); }
}

.animate-fade-in { animation: fadeIn 0.5s ease-out; }
@keyframes fadeIn {
  from { opacity: 0; }
  to { opacity: 1; }
}
</style>
