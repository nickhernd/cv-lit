<script setup>
import { ref, onMounted, computed, watch } from 'vue'

const props = defineProps({
  initialCamId: {
    type: Number,
    default: null
  }
})

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

const steps = [
  { id: 1, name: 'Configuración', desc: 'Cámara y Referencia' },
  { id: 2, name: 'Marcación', desc: 'GCPs y Varillas' },
  { id: 3, name: 'Validación', desc: 'Homografía Rectificada' }
]

const imageUrl = computed(() => {
  if (!selectedCamId.value) return null
  const base = `http://localhost:8000/api/cameras/${selectedCamId.value}/image`
  const query = selectedImage.value ? `?file=${selectedImage.value}&t=${Date.now()}` : `?t=${Date.now()}`
  return base + query
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
  } catch (err) { console.error(err) }
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

async function handleFileUpload(event) {
  const files = event.target.files
  const formData = new FormData()
  for (let f of files) formData.append('files', f)
  try {
    const res = await fetch(`http://localhost:8000/api/cameras/${selectedCamId.value}/upload-images`, {
      method: 'POST', body: formData
    })
    if (res.ok) {
      alert("Imágenes subidas")
      fetchImages()
    }
  } catch (err) { alert("Error al subir") }
}

async function handleRodImport(event) {
  const formData = new FormData()
  formData.append('file', event.target.files[0])
  try {
    const res = await fetch(`http://localhost:8000/api/cameras/${selectedCamId.value}/import-rods`, {
      method: 'POST', body: formData
    })
    if (res.ok) { alert("Varillas importadas"); fetchProfile() }
  } catch (err) { alert("Error al importar") }
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
      currentStep.value = 3
    } else { alert("Error: " + data.detail) }
  } catch (err) { alert("Error de conexión") }
  finally { calculating.value = false }
}

function handleImageClick(event) {
  if (currentStep.value !== 2) return
  const rect = event.target.getBoundingClientRect()
  const x = event.clientX - rect.left
  const y = event.clientY - rect.top
  const relX = (x / event.target.clientWidth) * 100
  const relY = (y / event.target.clientHeight) * 100
  const type = confirm("¿Es una varilla?") ? 'rod' : 'calib'
  const label = prompt("Etiqueta:", type === 'rod' ? 'Varilla_X' : `GCP_${currentProfile.value.gcps.length + 1}`)
  let utmX = 0, utmY = 0
  if (type === 'calib') {
    utmX = parseFloat(prompt("UTM X:", "707000.0"))
    utmY = parseFloat(prompt("UTM Y:", "4222000.0"))
  }
  if (label) {
    currentProfile.value.gcps.push({
      pixel: [x, y], utm: [utmX, utmY], label: label, type: type, rel: [relX, relY]
    })
  }
}

async function saveCalibration() {
  saving.value = true
  try {
    await fetch(`http://localhost:8000/api/cameras/${selectedCamId.value}/calibrate`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ cam_id: selectedCamId.value, gcps: currentProfile.value.gcps })
    })
    alert("GCPs guardados")
  } catch (err) { alert("Error") }
  finally { saving.value = false }
}

watch(selectedCamId, () => {
  if (selectedCamId.value) {
    fetchProfile()
    fetchImages()
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
  <div class="p-12 max-w-7xl mx-auto animate-fade-in">
    <!-- Stepper -->
    <div class="mb-12 flex items-center justify-between max-w-2xl mx-auto relative">
      <div v-for="step in steps" :key="step.id" class="z-10 flex flex-col items-center">
        <div @click="currentStep = step.id" 
             :class="currentStep >= step.id ? 'bg-slate-900 text-white cursor-pointer' : 'bg-white border-2 border-slate-100 text-slate-300'"
             class="w-10 h-10 rounded-full flex items-center justify-center text-xs font-bold transition-all">
          {{ step.id }}
        </div>
        <span class="text-[9px] font-bold uppercase tracking-widest mt-3" :class="currentStep >= step.id ? 'text-slate-900' : 'text-slate-300'">{{ step.name }}</span>
      </div>
      <div class="absolute top-5 left-0 w-full h-px bg-slate-100 -z-0">
        <div class="h-full bg-slate-900 transition-all duration-500" :style="{ width: ((currentStep - 1) / (steps.length - 1)) * 100 + '%' }"></div>
      </div>
    </div>

    <!-- Content -->
    <div v-if="currentStep === 1" class="max-w-4xl mx-auto grid grid-cols-1 md:grid-cols-2 gap-8">
      <div class="p-8 border border-slate-100 rounded-3xl bg-slate-50/50 space-y-6">
        <h3 class="text-xs font-bold text-slate-900 uppercase tracking-widest">1. Selección de Dispositivo</h3>
        <select v-model="selectedCamId" class="w-full bg-white border border-slate-200 rounded-xl px-4 py-3 text-sm outline-none">
          <option :value="null">Seleccionar Cámara...</option>
          <option v-for="cam in cameras" :key="cam.idx" :value="cam.idx">{{ cam.name }}</option>
        </select>
        <div v-if="selectedCamId && availableImages.length" class="space-y-3">
          <p class="text-[10px] font-bold text-slate-400 uppercase tracking-widest">Imagen de Referencia</p>
          <select v-model="selectedImage" class="w-full bg-white border border-slate-200 rounded-xl px-4 py-2 text-xs outline-none">
            <option v-for="img in availableImages" :key="img" :value="img">{{ img }}</option>
          </select>
        </div>
      </div>
      <div class="p-8 border border-slate-100 rounded-3xl bg-slate-50/50 flex flex-col justify-between">
        <div>
          <h3 class="text-xs font-bold text-slate-900 uppercase tracking-widest mb-6">2. Gestión de Archivos</h3>
          <label class="block w-full cursor-pointer group">
            <input type="file" multiple @change="handleFileUpload" class="hidden">
            <div class="border-2 border-dashed border-slate-200 rounded-2xl p-8 text-center group-hover:border-slate-900 transition-colors">
              <svg class="w-8 h-8 text-slate-200 mx-auto mb-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M4 16v1a2 2 0 002 2h12a2 2 0 002-2v-1m-4-8l-4-4m0 0L8 8m4-4v12" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>
              <span class="text-[10px] font-bold text-slate-400 uppercase tracking-[0.2em]">Cargar Imágenes</span>
            </div>
          </label>
        </div>
        <button @click="currentStep = 2" :disabled="!selectedCamId || !selectedImage" 
                class="mt-8 w-full py-4 bg-slate-900 text-white rounded-xl text-xs font-bold uppercase tracking-widest disabled:opacity-20 hover:bg-slate-800 transition-all">
          Continuar a Marcación
        </button>
      </div>
    </div>

    <div v-if="currentStep === 2" class="grid grid-cols-1 lg:grid-cols-4 gap-12">
      <div class="lg:col-span-3 space-y-6">
        <div class="relative rounded-[2.5rem] overflow-hidden border border-slate-100 bg-slate-50 shadow-inner group">
          <img :src="imageUrl" @click="handleImageClick" class="w-full h-auto block select-none cursor-crosshair">
          <div v-for="(gcp, idx) in currentProfile.gcps" :key="idx" 
               class="absolute -translate-x-1/2 -translate-y-1/2"
               :style="{ left: gcp.rel[0] + '%', top: gcp.rel[1] + '%' }">
            <div class="w-3.5 h-3.5 rounded-full border-2 border-white shadow-lg"
                 :class="gcp.type === 'rod' ? 'bg-amber-500' : 'bg-blue-600'"></div>
          </div>
          <div class="absolute top-6 left-6 px-4 py-2 bg-black/40 backdrop-blur rounded-full text-[9px] text-white font-bold uppercase tracking-widest">
            {{ selectedImage }}
          </div>
        </div>
        <div class="flex justify-between items-center bg-slate-50/50 p-4 rounded-2xl border border-slate-100">
           <div class="flex space-x-6">
              <div class="flex items-center space-x-2">
                <div class="w-2.5 h-2.5 rounded-full bg-blue-600"></div>
                <span class="text-[9px] font-bold uppercase tracking-widest text-slate-500">Punto GCP</span>
              </div>
              <div class="flex items-center space-x-2">
                <div class="w-2.5 h-2.5 rounded-full bg-amber-500"></div>
                <span class="text-[9px] font-bold uppercase tracking-widest text-slate-500">Varilla</span>
              </div>
           </div>
           <div class="flex space-x-3">
              <label class="px-4 py-2 bg-white border border-slate-200 rounded-lg text-[9px] font-bold uppercase tracking-widest cursor-pointer hover:bg-slate-50">
                Importar CSV
                <input type="file" @change="handleRodImport" class="hidden">
              </label>
              <button @click="saveCalibration" class="px-6 py-2 bg-slate-900 text-white rounded-lg text-[9px] font-bold uppercase tracking-widest hover:bg-slate-800">Guardar Puntos</button>
           </div>
        </div>
      </div>
      <aside class="space-y-6">
        <div class="p-6 border border-slate-100 rounded-3xl bg-white shadow-sm">
           <h4 class="text-[10px] font-bold text-slate-400 uppercase tracking-widest mb-4">Listado de Puntos</h4>
           <div class="space-y-2 max-h-[40vh] overflow-y-auto pr-2 custom-scrollbar">
              <div v-for="(gcp, idx) in currentProfile.gcps" :key="idx" 
                   class="flex items-center justify-between p-3 bg-slate-50 rounded-xl group transition-all">
                <div class="flex items-center space-x-3 min-w-0">
                  <div class="w-1.5 h-1.5 rounded-full shrink-0" :class="gcp.type === 'rod' ? 'bg-amber-500' : 'bg-blue-600'"></div>
                  <div class="truncate">
                    <p class="text-[10px] font-bold text-slate-900">{{ gcp.label }}</p>
                    <p class="text-[8px] text-slate-400 font-mono">{{ gcp.utm[0].toFixed(0) }}, {{ gcp.utm[1].toFixed(0) }}</p>
                  </div>
                </div>
                <button @click="currentProfile.gcps.splice(idx, 1)" class="opacity-0 group-hover:opacity-100 text-slate-300 hover:text-red-500">
                  <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M6 18L18 6M6 6l12 12" stroke-width="2" stroke-linecap="round"/></svg>
                </button>
              </div>
           </div>
        </div>
        <button @click="calculateHomography" :disabled="currentProfile.gcps.length < 4 || calculating"
                class="w-full py-4 bg-blue-600 text-white rounded-2xl text-[10px] font-bold uppercase tracking-widest shadow-lg shadow-blue-600/20 hover:bg-blue-700 disabled:opacity-20 transition-all">
          {{ calculating ? 'Procesando...' : 'Calcular Homografía' }}
        </button>
      </aside>
    </div>

    <div v-if="currentStep === 3" class="max-w-5xl mx-auto space-y-12 animate-scale-in">
      <header class="text-center">
        <div class="inline-flex items-center px-4 py-1.5 bg-emerald-50 text-emerald-600 rounded-full text-[9px] font-bold uppercase tracking-widest mb-4">Validación Exitosa</div>
        <h2 class="text-3xl font-bold text-slate-900">Vista Rectificada</h2>
        <p class="text-sm text-slate-400 mt-2">Error medio de reproyección: <span class="font-bold text-slate-900 tabular-nums">{{ rmse?.toFixed(4) }} m</span></p>
      </header>
      
      <div class="relative rounded-[3rem] overflow-hidden border-8 border-slate-50 bg-slate-100 shadow-2xl mx-auto max-w-3xl">
        <img :src="rectifiedUrl" class="w-full h-auto block" alt="Rectified View">
        <div class="absolute inset-0 bg-gradient-to-t from-black/20 to-transparent pointer-events-none"></div>
      </div>

      <div class="flex justify-center space-x-4">
        <button @click="currentStep = 2" class="px-8 py-3 border border-slate-200 rounded-xl text-xs font-bold text-slate-600 hover:bg-slate-50 transition-all">Re-ajustar Puntos</button>
        <button @click="alert('Calibración completada y guardada.')" class="px-8 py-3 bg-slate-900 text-white rounded-xl text-xs font-bold hover:bg-slate-800 transition-all shadow-xl shadow-slate-900/10">Finalizar Proceso</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.custom-scrollbar::-webkit-scrollbar { width: 3px; }
.custom-scrollbar::-webkit-scrollbar-track { background: transparent; }
.custom-scrollbar::-webkit-scrollbar-thumb { background: #e2e8f0; border-radius: 10px; }
</style>
