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
const currentProfile = ref({ gcps: [], reference_image: null })
const loading = ref(false)
const saving = ref(false)
const calculating = ref(false)
const rmse = ref(null)

// UX State
const selectedGcpIdx = ref(null)
const isDragging = ref(false)

const steps = [
  { id: 1, name: 'Varillas', desc: 'Importar Coordenadas' },
  { id: 2, name: 'Imágenes', desc: 'Carga de Fotogramas' },
  { id: 3, name: 'Alineación', desc: 'Transformar a Ref.' },
  { id: 4, name: 'Marcación', desc: 'Etiquetado Varillas' },
  { id: 5, name: 'Validación', desc: 'Cálculo y Perfil' }
]

// Cargar anotaciones especificas de la imagen
async function fetchImageAnnotations() {
  if (!selectedCamId.value || !selectedImage.value) return
  try {
    const res = await fetch(`http://localhost:8000/api/cameras/${selectedCamId.value}/images/${selectedImage.value}/annotations`)
    const data = await res.json()
    currentProfile.value.gcps = data.points || []
  } catch (err) { console.error(err) }
}

async function saveAnnotations() {
  if (!selectedCamId.value || !selectedImage.value) return
  saving.value = true
  try {
    await fetch(`http://localhost:8000/api/cameras/${selectedCamId.value}/images/${selectedImage.value}/annotations`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ points: currentProfile.value.gcps })
    })
    emit('notify', 'Estado guardado para esta sesión', 'success')
  } catch (err) { emit('notify', 'Error al guardar estado', 'error') }
  finally { saving.value = false }
}

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
  } catch (err) { emit('notify', 'Error al cargar estaciones', 'error') }
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

async function setAsReference(filename) {
  try {
    const res = await fetch(`http://localhost:8000/api/cameras/${selectedCamId.value}/set-reference?filename=${filename}`, {
      method: 'POST'
    })
    if (res.ok) {
      currentProfile.value.reference_image = filename
      emit('notify', 'Imagen establecida como referencia base', 'success')
    }
  } catch (err) { emit('notify', 'Error al establecer referencia', 'error') }
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
      emit('notify', `Subidos ${data.uploaded.length} archivos con éxito`, 'success')
      fetchImages()
    }
  } catch (err) { emit('notify', 'Error al subir imágenes', 'error') }
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
      emit('notify', 'Geometría validada correctamente', 'success')
      currentStep.value = 5
    } else { emit('notify', data.detail, 'error') }
  } catch (err) { emit('notify', 'Error de conexión', 'error') }
  finally { calculating.value = false }
}

function handleImageClick(event) {
  if (currentStep.value !== 4) return
  const rect = event.target.getBoundingClientRect()
  const x = event.clientX - rect.left
  const y = event.clientY - rect.top
  const relX = (x / event.target.clientWidth) * 100
  const relY = (y / event.target.clientHeight) * 100
  
  const newGcp = {
    pixel: [x, y],
    utm: [0, 0],
    label: `VARILLA_${currentProfile.value.gcps.length + 1}`,
    type: 'calib',
    rel: [relX, relY]
  }
  
  currentProfile.value.gcps.push(newGcp)
  selectedGcpIdx.value = currentProfile.value.gcps.length - 1
  saveAnnotations()
}

watch(selectedCamId, () => {
  if (selectedCamId.value) {
    fetchProfile()
    fetchImages()
    selectedGcpIdx.value = null
  }
})

watch(selectedImage, () => {
  if (selectedImage.value) {
    fetchImageAnnotations()
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
  <div class="space-y-6">
    <div class="flex justify-between items-center border-b border-slate-200 pb-4">
      <h1 class="text-2xl font-bold text-slate-900">Configuración de Estación de Visión</h1>
      <div v-if="selectedCamId" class="flex items-center space-x-2 text-xs font-bold text-blue-600 uppercase">
        <span>Cámara Activa:</span>
        <span class="bg-blue-600 text-white px-2 py-0.5 rounded">ESTACIÓN {{ selectedCamId }}</span>
      </div>
    </div>

    <!-- TABS (Traditional Stepper) -->
    <div class="flex border-b border-slate-200 bg-white rounded-t-md overflow-hidden">
      <button v-for="step in steps" :key="step.id" 
              @click="currentStep = step.id"
              :class="currentStep === step.id ? 'bg-white border-b-2 border-blue-600 text-blue-600' : 'bg-slate-50 text-slate-500 hover:bg-slate-100 border-b border-transparent'"
              class="px-6 py-4 text-xs font-bold uppercase tracking-wider transition-all flex-1 text-center">
        {{ step.id }}. {{ step.name }}
      </button>
    </div>

    <!-- PASO 1: IMPORTAR VARILLAS -->
    <div v-if="currentStep === 1" class="card-standard p-8 space-y-8">
       <div class="max-w-2xl mx-auto space-y-8">
          <div class="space-y-4">
            <label class="block text-xs font-bold text-slate-500 uppercase">1. Seleccionar Estación</label>
            <select v-model="selectedCamId" class="w-full input-standard">
              <option :value="null">-- Seleccionar --</option>
              <option v-for="cam in cameras" :key="cam.idx" :value="cam.idx">{{ cam.name }}</option>
            </select>
          </div>
          
          <div class="p-12 border-2 border-dashed border-slate-200 rounded-md bg-slate-50 flex flex-col items-center">
             <p class="text-sm font-bold text-slate-600 mb-4">Importar coordenadas de varillas</p>
             <button class="btn-secondary">Seleccionar CSV / XLSX</button>
          </div>

          <div class="flex justify-end">
            <button @click="currentStep = 2" :disabled="!selectedCamId" class="btn-standard">Siguiente Paso: Imágenes</button>
          </div>
       </div>
    </div>

    <!-- PASO 2: CARGAR FOTOS -->
    <div v-if="currentStep === 2" class="space-y-6">
       <div class="card-standard p-6 bg-slate-50 flex justify-between items-center">
          <p class="text-sm font-medium text-slate-600">Subir nuevos fotogramas para la estación</p>
          <input type="file" multiple @change="handleFiles($event.target.files)" class="text-sm">
       </div>

       <div class="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-4">
           <div v-for="img in availableImages" :key="img" 
                class="card-standard overflow-hidden cursor-pointer group"
                :class="selectedImage === img ? 'ring-2 ring-blue-600' : ''"
                @click="selectedImage = img">
              <div class="aspect-video relative bg-slate-200">
                <img :src="`http://localhost:8000/api/cameras/${selectedCamId}/image?file=${img}&thumb=1`" class="w-full h-full object-cover">
                <div v-if="currentProfile.reference_image === img" class="absolute top-2 left-2 bg-emerald-600 text-white text-[8px] font-bold px-1.5 py-0.5 rounded shadow">BASE</div>
              </div>
              <div class="p-2 text-[10px] truncate font-mono text-slate-500 bg-white">{{ img }}</div>
           </div>
       </div>

       <div class="flex justify-end pt-4">
         <button @click="currentStep = 3" :disabled="!selectedImage" class="btn-standard">Configurar Alineación</button>
       </div>
    </div>

    <!-- PASO 3: ALINEACION -->
    <div v-if="currentStep === 3" class="card-standard p-8">
       <div class="grid grid-cols-1 lg:grid-cols-2 gap-8">
          <div class="space-y-4">
            <h4 class="text-xs font-bold text-slate-500 uppercase border-b border-slate-100 pb-2">Referencia Base</h4>
            <div class="aspect-video bg-slate-100 rounded border border-slate-200 overflow-hidden">
              <img v-if="currentProfile.reference_image" :src="`http://localhost:8000/api/cameras/${selectedCamId}/image?file=${currentProfile.reference_image}`" class="w-full h-full object-contain">
            </div>
            <button @click="setAsReference(selectedImage)" class="btn-secondary w-full">Establecer actual como base</button>
          </div>
          <div class="space-y-4">
            <h4 class="text-xs font-bold text-slate-500 uppercase border-b border-slate-100 pb-2">Fotograma Actual</h4>
            <div class="aspect-video bg-slate-100 rounded border border-slate-200 overflow-hidden">
              <img :src="imageUrl" class="w-full h-full object-contain">
            </div>
            <button @click="currentStep = 4" class="btn-standard w-full">Continuar a Marcación</button>
          </div>
       </div>
    </div>

    <!-- PASO 4: MARCACION -->
    <div v-if="currentStep === 4" class="grid grid-cols-1 lg:grid-cols-4 gap-6">
       <div class="lg:col-span-3 card-standard overflow-hidden bg-slate-900 flex flex-col relative min-h-[600px]">
          <img :src="imageUrl" @click="handleImageClick" class="w-full h-full object-contain cursor-crosshair select-none">
          
          <div v-for="(gcp, idx) in currentProfile.gcps" :key="idx" 
               class="absolute -translate-x-1/2 -translate-y-1/2"
               :style="{ left: gcp.rel[0] + '%', top: gcp.rel[1] + '%' }">
            <div @click.stop="selectedGcpIdx = idx"
                 :class="selectedGcpIdx === idx ? 'bg-yellow-400 ring-4 ring-white' : 'bg-blue-600'"
                 class="w-4 h-4 rounded-full border-2 border-white shadow-md cursor-pointer transition-transform hover:scale-125">
            </div>
          </div>

          <div class="absolute bottom-4 left-4 bg-black/50 text-white text-[10px] px-3 py-1 rounded font-bold uppercase tracking-wider">Modo Edición: Varillas GCP</div>
       </div>

       <aside class="space-y-6">
          <div v-if="selectedGcpIdx !== null" class="card-standard">
            <div class="card-header flex justify-between">
              <span>Editar Punto</span>
              <button @click="selectedGcpIdx = null" class="text-slate-400">×</button>
            </div>
            <div class="p-4 space-y-4">
              <div class="space-y-1">
                <label class="text-[10px] font-bold text-slate-500 uppercase">ID Varilla</label>
                <input v-model="currentProfile.gcps[selectedGcpIdx].label" class="w-full input-standard">
              </div>
              <div class="grid grid-cols-2 gap-2">
                <div class="space-y-1">
                  <label class="text-[10px] font-bold text-slate-500 uppercase">UTM X</label>
                  <input type="number" v-model.number="currentProfile.gcps[selectedGcpIdx].utm[0]" class="w-full input-standard font-mono text-xs">
                </div>
                <div class="space-y-1">
                  <label class="text-[10px] font-bold text-slate-500 uppercase">UTM Y</label>
                  <input type="number" v-model.number="currentProfile.gcps[selectedGcpIdx].utm[1]" class="w-full input-standard font-mono text-xs">
                </div>
              </div>
              <button @click="currentProfile.gcps.splice(selectedGcpIdx, 1); selectedGcpIdx = null; saveAnnotations()" class="w-full text-red-600 text-xs font-bold hover:underline">Eliminar Punto</button>
            </div>
          </div>

          <div class="card-standard flex flex-col max-h-[400px]">
            <div class="card-header">Registro de Varillas ({{ currentProfile.gcps.length }})</div>
            <div class="flex-1 overflow-y-auto divide-y divide-slate-100">
               <div v-for="(gcp, idx) in currentProfile.gcps" :key="idx" 
                    @click="selectedGcpIdx = idx"
                    class="p-3 text-xs flex justify-between items-center cursor-pointer hover:bg-slate-50"
                    :class="selectedGcpIdx === idx ? 'bg-blue-50' : ''">
                  <span class="font-bold text-slate-700">{{ gcp.label }}</span>
                  <span class="text-slate-400 font-mono text-[10px]">{{ gcp.utm[0].toFixed(0) }}, {{ gcp.utm[1].toFixed(0) }}</span>
               </div>
            </div>
            <div class="p-4 border-t border-slate-100 bg-slate-50">
              <button @click="calculateHomography" :disabled="currentProfile.gcps.length < 4 || calculating" class="btn-standard w-full uppercase text-xs">Calcular Geometría</button>
            </div>
          </div>
       </aside>
    </div>

    <!-- PASO 5: VALIDACION -->
    <div v-if="currentStep === 5" class="card-standard p-12 text-center space-y-10">
       <div class="inline-block bg-emerald-100 text-emerald-800 px-4 py-2 rounded text-sm font-bold uppercase tracking-widest border border-emerald-200">Perfil de Estación Generado</div>
       
       <div class="max-w-4xl mx-auto space-y-6">
          <p class="text-slate-600 font-medium">Validación proyectiva completada con éxito.</p>
          <div class="grid grid-cols-2 gap-4 max-w-sm mx-auto">
            <div class="p-4 bg-slate-50 rounded border border-slate-100">
              <p class="text-[10px] font-bold text-slate-400 uppercase">RMSE</p>
              <p class="text-2xl font-bold text-slate-900 font-mono">{{ rmse?.toFixed(4) }} m</p>
            </div>
            <div class="p-4 bg-slate-50 rounded border border-slate-100">
              <p class="text-[10px] font-bold text-slate-400 uppercase">Puntos</p>
              <p class="text-2xl font-bold text-slate-900 font-mono">{{ currentProfile.gcps.length }}</p>
            </div>
          </div>
          
          <div class="aspect-video bg-slate-100 rounded border border-slate-200 overflow-hidden shadow-inner">
            <img :src="rectifiedUrl" class="w-full h-full object-contain">
          </div>
       </div>

       <div class="flex justify-center space-x-4">
          <button @click="currentStep = 4" class="btn-secondary">Ajustar Marcación</button>
          <button @click="currentStep = 1" class="btn-standard uppercase tracking-widest">Finalizar y Guardar</button>
       </div>
    </div>
  </div>
</template>

<style scoped>
.custom-scrollbar::-webkit-scrollbar { width: 3px; }
.custom-scrollbar::-webkit-scrollbar-track { background: transparent; }
.custom-scrollbar::-webkit-scrollbar-thumb { background: #e2e8f0; border-radius: 20px; }

.animate-glow {
  box-shadow: 0 0 0 0 rgba(37, 99, 235, 0.4);
  animation: pulse-glow 2s infinite;
}

@keyframes pulse-glow {
  0% { box-shadow: 0 0 0 0 rgba(37, 99, 235, 0.4); }
  70% { box-shadow: 0 0 0 10px rgba(37, 99, 235, 0); }
  100% { box-shadow: 0 0 0 0 rgba(37, 99, 235, 0); }
}

.cursor-crosshair { cursor: crosshair; }
</style>
