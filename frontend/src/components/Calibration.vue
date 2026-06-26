<script setup>
import { ref, onMounted, computed, watch } from 'vue'
import BatchAlignment from './BatchAlignment.vue'

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
const isDraggingOver = ref(false)

const steps = [
  { id: 1, name: 'Estación', desc: 'Seleccionar Cámara' },
  { id: 2, name: 'Imágenes', desc: 'Gestionar Fotogramas' },
  { id: 3, name: 'Alineación', desc: 'Configurar Referencia' },
  { id: 4, name: 'Marcación', desc: 'Etiquetado Varillas' },
  { id: 5, name: 'Validación', desc: 'Perfil Final' }
]

// API Helpers
async function fetchCameras() {
  try {
    const res = await fetch('http://localhost:8000/api/dashboard')
    const data = await res.json()
    cameras.value = data.cameras
  } catch (err) { emit('notify', 'Error al cargar estaciones', 'error') }
}

async function fetchImages() {
  if (!selectedCamId.value) return
  // Limpiar inmediatamente para evitar que imágenes de la cámara anterior
  // aparezcan en el contexto de la nueva (race condition entre fetches)
  availableImages.value = []
  selectedImage.value   = ''
  const camSnapshot = selectedCamId.value
  try {
    const res = await fetch(`http://localhost:8000/api/cameras/${camSnapshot}/images`)
    const imgs = await res.json()
    // Descartar la respuesta si el usuario ya cambió de cámara mientras esperábamos
    if (camSnapshot !== selectedCamId.value) return
    availableImages.value = imgs
    if (imgs.length > 0) selectedImage.value = imgs[0].filename
  } catch (err) { console.error(err) }
}

async function runAlignment() {
  alignState.value = 'loading'
  blendUrl.value   = ''
  alignError.value = ''

  try {
    // Obtener la imagen target como Blob desde su URL del backend
    const tgtResp = await fetch(imageUrl.value)  // URL de la imagen seleccionada en paso 2
    if (!tgtResp.ok) throw new Error('No se pudo cargar la imagen target')
    const tgtBlob = await tgtResp.blob()

    const form = new FormData()
    form.append('target', tgtBlob, 'target.jpg')
    // No enviamos 'reference' → el backend la lee del perfil JSON automáticamente

    const resp = await fetch(
      `http://localhost:8000/api/cameras/${selectedCamId.value}/align-preview`,
      { method: 'POST', body: form }
    )

    if (!resp.ok) {
      const err = await resp.json()
      throw new Error(err.detail ?? 'Error desconocido')
    }

    if (blendUrl.value) URL.revokeObjectURL(blendUrl.value) // limpiar anterior
    blendUrl.value   = URL.createObjectURL(await resp.blob())
    alignState.value = 'done'

  } catch (e) {
    alignError.value = e.message
    alignState.value = 'error'
  }
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
    emit('notify', 'Anotaciones guardadas', 'success')
  } catch (err) { emit('notify', 'Error al guardar anotaciones', 'error') }
  finally { saving.value = false }
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

async function deleteImage(filename) {
  if (!confirm(`¿Seguro que quieres eliminar ${filename}?`)) return
  try {
    const res = await fetch(`http://localhost:8000/api/cameras/${selectedCamId.value}/images/${filename}`, {
      method: 'DELETE'
    })
    if (res.ok) {
      emit('notify', 'Imagen eliminada', 'success')
      if (selectedImage.value === filename) selectedImage.value = ''
      fetchImages()
    }
  } catch (err) { emit('notify', 'Error al eliminar imagen', 'error') }
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
      emit('notify', `Subidos ${data.uploaded.length} archivos`, 'success')
      fetchImages()
    }
  } catch (err) { emit('notify', 'Error al subir imágenes', 'error') }
}

function onDrop(e) {
  isDraggingOver.value = false
  const files = e.dataTransfer.files
  if (files.length > 0) handleFiles(files)
}

// Computed
const imageUrl = computed(() => {
  if (!selectedCamId.value || !selectedImage.value) return null
  return `http://localhost:8000/api/cameras/${selectedCamId.value}/image?file=${selectedImage.value}&t=${Date.now()}`
})

const rectifiedUrl = computed(() => {
  if (!selectedCamId.value || !rmse.value) return null
  return `http://localhost:8000/api/cameras/${selectedCamId.value}/rectified-preview?t=${Date.now()}`
})

// Handlers
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

// Watches
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
      <h1 class="text-2xl font-bold text-slate-900 uppercase tracking-tight">Calibración Geométrica</h1>
      <div v-if="selectedCamId" class="flex items-center space-x-2 text-xs font-bold text-blue-600 uppercase">
        <span>Cámara Activa:</span>
        <span class="bg-blue-600 text-white px-2 py-0.5 rounded shadow-sm">{{ cameras.find(c => c.idx === selectedCamId)?.name }}</span>
      </div>
    </div>

    <!-- TABS -->
    <div class="flex bg-white rounded-md shadow-sm border border-slate-200 overflow-hidden">
      <button v-for="step in steps" :key="step.id"
              @click="currentStep = step.id"
              :disabled="!selectedCamId && step.id > 1"
              :class="[
                currentStep === step.id ? 'bg-slate-900 text-white' : 'text-slate-500 hover:bg-slate-50',
                !selectedCamId && step.id > 1 ? 'opacity-50 cursor-not-allowed' : ''
              ]"
              class="px-4 py-3 text-[10px] font-bold uppercase tracking-widest transition-all flex-1 text-center border-r last:border-r-0 border-slate-200">
        {{ step.id }}. {{ step.name }}
      </button>
    </div>

    <!-- PASO 1: SELECCION -->
    <div v-if="currentStep === 1" class="card-standard p-12 flex flex-col items-center justify-center space-y-8 min-h-[400px]">
       <div class="w-full max-w-md space-y-4">
          <label class="block text-xs font-bold text-slate-400 uppercase tracking-widest text-center">Seleccionar Estación para Calibrar</label>
          <div class="grid grid-cols-2 gap-4">
            <button v-for="cam in cameras" :key="cam.idx"
                    @click="selectedCamId = cam.idx; currentStep = 2"
                    :class="selectedCamId === cam.idx ? 'border-blue-600 bg-blue-50 text-blue-700 ring-2 ring-blue-600 ring-inset' : 'border-slate-200 hover:border-blue-400'"
                    class="p-4 border rounded-lg text-left transition-all group">
              <p class="text-[10px] font-bold text-slate-400 uppercase mb-1 group-hover:text-blue-500">Estación {{ cam.idx }}</p>
              <p class="text-sm font-bold truncate">{{ cam.name }}</p>
            </button>
          </div>
       </div>
    </div>

    <!-- PASO 2: GESTION DE IMAGENES -->
    <div v-if="currentStep === 2" class="grid grid-cols-1 lg:grid-cols-4 gap-6">
       <!-- Upload & List -->
       <div class="lg:col-span-1 space-y-4">
          <div @dragover.prevent="isDraggingOver = true"
               @dragleave.prevent="isDraggingOver = false"
               @drop.prevent="onDrop"
               :class="isDraggingOver ? 'border-blue-600 bg-blue-50' : 'border-slate-200 bg-white'"
               class="p-6 border-2 border-dashed rounded-lg text-center transition-colors relative">
            <input type="file" multiple @change="handleFiles($event.target.files)" class="absolute inset-0 opacity-0 cursor-pointer">
            <svg class="w-8 h-8 mx-auto text-slate-400 mb-2" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M12 4v16m8-8H4" stroke-width="2"/></svg>
            <p class="text-xs font-bold text-slate-600 uppercase">Añadir Imágenes</p>
            <p class="text-[9px] text-slate-400 uppercase mt-1">Arrastra o haz click</p>
          </div>

          <div class="card-standard flex flex-col h-[500px]">
            <div class="card-header flex justify-between">
              <span>Fotogramas ({{ availableImages.length }})</span>
              <button @click="fetchImages" class="text-blue-600 hover:underline">↻</button>
            </div>
            <div class="flex-1 overflow-y-auto divide-y divide-slate-100">
               <div v-for="img in availableImages" :key="img.filename"
                    @click="selectedImage = img.filename"
                    :class="selectedImage === img.filename ? 'bg-blue-50' : 'hover:bg-slate-50'"
                    class="p-3 cursor-pointer flex items-center space-x-3 transition-colors group">
                  <div class="w-12 h-8 bg-slate-200 rounded overflow-hidden shrink-0">
                    <img :src="`http://localhost:8000/api/cameras/${selectedCamId}/image?file=${img.filename}&thumb=1`" class="w-full h-full object-cover">
                  </div>
                  <div class="flex-1 min-w-0">
                    <p class="text-[10px] font-bold truncate" :class="selectedImage === img.filename ? 'text-blue-700' : 'text-slate-700'">{{ img.filename }}</p>
                    <p class="text-[9px] text-slate-400 uppercase">{{ (img.size / 1024 / 1024).toFixed(1) }} MB</p>
                  </div>
                  <button @click.stop="deleteImage(img.filename)" class="opacity-0 group-hover:opacity-100 p-1 text-red-500 hover:bg-red-50 rounded transition-all">
                    <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" stroke-width="2"/></svg>
                  </button>
               </div>
            </div>
          </div>
       </div>

       <!-- Preview -->
       <div class="lg:col-span-3 card-standard flex flex-col overflow-hidden bg-slate-900 relative">
          <div v-if="selectedImage" class="h-full flex flex-col">
            <div class="flex-1 flex items-center justify-center p-4">
              <img :src="imageUrl" class="max-w-full max-h-full object-contain shadow-2xl">
            </div>
            <div class="p-4 bg-white/5 backdrop-blur border-t border-white/10 flex justify-between items-center">
              <div class="flex space-x-4 items-center">
                <span class="text-xs font-bold text-white uppercase">{{ selectedImage }}</span>
                <span v-if="currentProfile.reference_image === selectedImage" class="bg-emerald-600 text-white text-[9px] font-bold px-2 py-0.5 rounded shadow-sm">REFERENCIA BASE</span>
              </div>
              <div class="space-x-2">
                <button v-if="currentProfile.reference_image !== selectedImage" @click="setAsReference(selectedImage)" class="btn-secondary py-1 text-[10px]">Set como Referencia</button>
                <button @click="currentStep = 3" :disabled="!currentProfile.reference_image" class="btn-standard py-1 text-[10px] disabled:opacity-40 disabled:cursor-not-allowed" :title="!currentProfile.reference_image ? 'Primero establece una imagen de referencia' : ''">Alinear lote completo →</button>
              </div>
            </div>
          </div>
          <div v-else class="flex-1 flex flex-col items-center justify-center text-slate-500 space-y-4">
            <svg class="w-16 h-16 opacity-20" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" stroke-width="1.5"/></svg>
            <p class="text-sm font-bold uppercase tracking-widest">Selecciona o sube un fotograma</p>
          </div>
       </div>
    </div>

    <!-- PASO 3: ALINEACION MASIVA POR LOTES -->
    <div v-if="currentStep === 3" class="card-standard p-4 flex flex-col min-h-[600px]">
      <BatchAlignment
        :cam-id="selectedCamId"
        :image-list="availableImages"
        :initial-base="currentProfile.reference_image || ''"
        @notify="(msg, type) => emit('notify', msg, type)"
        @committed="currentStep = 4"
        @discard="currentStep = 2"
      />
    </div>

    <!-- PASO 4: MARCACION (GCPs) -->
    <div v-if="currentStep === 4" class="grid grid-cols-1 lg:grid-cols-4 gap-6">
       <div class="lg:col-span-3 card-standard overflow-hidden bg-slate-900 flex flex-col relative min-h-[600px]">
          <img :src="imageUrl" @click="handleImageClick" class="w-full h-full object-contain cursor-crosshair select-none">

          <div v-for="(gcp, idx) in currentProfile.gcps" :key="idx"
               class="absolute -translate-x-1/2 -translate-y-1/2"
               :style="{ left: gcp.rel[0] + '%', top: gcp.rel[1] + '%' }">
            <div @click.stop="selectedGcpIdx = idx"
                 :class="selectedGcpIdx === idx ? 'bg-yellow-400 scale-150 ring-4 ring-white' : 'bg-blue-600 scale-100'"
                 class="w-4 h-4 rounded-full border-2 border-white shadow-lg cursor-pointer transition-all hover:scale-125 z-10 flex items-center justify-center">
                 <span class="text-[8px] font-bold text-white">{{ idx + 1 }}</span>
            </div>
          </div>
          <div class="absolute bottom-4 left-4 bg-black/60 text-white text-[10px] px-3 py-1.5 rounded-full font-bold uppercase tracking-widest backdrop-blur-sm border border-white/20 shadow-xl">Modo Marcación: Varillas GCP</div>
       </div>

       <aside class="space-y-6">
          <div v-if="selectedGcpIdx !== null" class="card-standard border-blue-200 shadow-xl animate-fade-in">
            <div class="card-header bg-blue-600 text-white flex justify-between items-center py-2">
              <span class="text-[10px] font-bold uppercase tracking-widest">Editar Punto {{ selectedGcpIdx + 1 }}</span>
              <button @click="selectedGcpIdx = null" class="hover:bg-blue-700 rounded px-1">×</button>
            </div>
            <div class="p-4 space-y-4">
              <div class="space-y-1">
                <label class="text-[10px] font-bold text-slate-500 uppercase">Etiqueta</label>
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
              <button @click="currentProfile.gcps.splice(selectedGcpIdx, 1); selectedGcpIdx = null; saveAnnotations()" class="w-full bg-red-50 text-red-600 text-[10px] font-bold py-2 rounded uppercase border border-red-100 hover:bg-red-100 transition-colors">Eliminar Punto</button>
            </div>
          </div>

          <div class="card-standard flex flex-col h-[500px]">
            <div class="card-header uppercase tracking-wider text-[10px]">Listado de Varillas ({{ currentProfile.gcps.length }})</div>
            <div class="flex-1 overflow-y-auto divide-y divide-slate-100 custom-scrollbar">
               <div v-for="(gcp, idx) in currentProfile.gcps" :key="idx"
                    @click="selectedGcpIdx = idx"
                    class="p-3 text-xs flex justify-between items-center cursor-pointer hover:bg-slate-50 transition-colors"
                    :class="selectedGcpIdx === idx ? 'bg-blue-50 border-l-4 border-blue-600' : ''">
                  <div>
                    <p class="font-bold text-slate-700 uppercase text-[10px]">{{ gcp.label }}</p>
                    <p class="text-[9px] text-slate-400 font-mono">{{ gcp.utm[0].toFixed(1) }}, {{ gcp.utm[1].toFixed(1) }}</p>
                  </div>
                  <span class="text-[9px] font-bold text-slate-300">#{{ idx + 1 }}</span>
               </div>
            </div>
            <div class="p-4 border-t border-slate-100 bg-slate-50">
              <button @click="calculateHomography" :disabled="currentProfile.gcps.length < 4 || calculating"
                      class="btn-standard w-full uppercase text-xs shadow-md">
                {{ calculating ? 'Calculando...' : 'Generar Perfil' }}
              </button>
            </div>
          </div>
       </aside>
    </div>

    <!-- PASO 5: VALIDACION -->
    <div v-if="currentStep === 5" class="card-standard p-12 text-center space-y-10 min-h-[600px] flex flex-col justify-center">
       <div class="inline-block bg-emerald-100 text-emerald-800 px-6 py-2 rounded-full text-xs font-bold uppercase tracking-widest border border-emerald-200 shadow-sm">Estación Calibrada con Éxito</div>

       <div class="max-w-4xl mx-auto space-y-8">
          <div class="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div class="p-4 bg-white rounded-lg border border-slate-100 shadow-sm">
              <p class="text-[9px] font-bold text-slate-400 uppercase tracking-widest mb-1">Error RMSE</p>
              <p class="text-xl font-bold text-slate-900 font-mono">{{ rmse?.toFixed(4) }} m</p>
            </div>
            <div class="p-4 bg-white rounded-lg border border-slate-100 shadow-sm">
              <p class="text-[9px] font-bold text-slate-400 uppercase tracking-widest mb-1">GCPs Usados</p>
              <p class="text-xl font-bold text-slate-900 font-mono">{{ currentProfile.gcps.length }}</p>
            </div>
            <div class="p-4 bg-white rounded-lg border border-slate-100 shadow-sm">
              <p class="text-[9px] font-bold text-slate-400 uppercase tracking-widest mb-1">Proyección</p>
              <p class="text-xl font-bold text-slate-900 font-mono">EPSG:25830</p>
            </div>
            <div class="p-4 bg-white rounded-lg border border-slate-100 shadow-sm">
              <p class="text-[9px] font-bold text-slate-400 uppercase tracking-widest mb-1">Estado</p>
              <div class="flex items-center justify-center space-x-2">
                <div class="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></div>
                <p class="text-sm font-bold text-slate-700 uppercase">Óptimo</p>
              </div>
            </div>
          </div>

          <div class="aspect-video bg-slate-900 rounded-lg border border-slate-800 overflow-hidden shadow-2xl relative">
            <img :src="rectifiedUrl" class="w-full h-full object-contain">
            <div class="absolute top-4 left-4 bg-black/50 text-white text-[9px] font-bold px-3 py-1 rounded-full uppercase tracking-widest">Vista Rectificada (UTM)</div>
          </div>
       </div>

       <div class="flex justify-center space-x-4">
          <button @click="currentStep = 4" class="btn-secondary px-8">Reajustar Puntos</button>
          <button @click="currentView = 'dashboard'" class="btn-standard uppercase px-8 shadow-lg">Finalizar Proceso</button>
       </div>
    </div>
  </div>
</template>

<style scoped>
.custom-scrollbar::-webkit-scrollbar { width: 4px; }
.custom-scrollbar::-webkit-scrollbar-track { background: transparent; }
.custom-scrollbar::-webkit-scrollbar-thumb { background: #cbd5e1; border-radius: 10px; }

.animate-fade-in { animation: fadeIn 0.3s ease-out; }
@keyframes fadeIn { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }

.cursor-crosshair { cursor: crosshair; }
</style>
