<script setup>
import { ref, computed, watch } from 'vue'
import { API_BASE } from '../api.js'

const emit = defineEmits(['notify'])
const API = API_BASE

// ── Transectos: anchura de playa (#nuevo 2026-09-14) ──────────────────────────
// Pedido en la reunión de equipo (11/09/2026): el área en m² no es fiable
// ("olvidaros de la cuestión de los cálculos de áreas"); en su lugar, un
// punto de referencia FIJO (p.ej. la valla de la duna) + la distancia hasta
// la línea de costa detectada da un indicador de "anchura de playa" mucho
// más estable y fácil de entender. Se marca UNA VEZ por cámara — el propio
// backend recalcula la distancia con la homografía vigente en CADA análisis
// (ver _compute_transect_distances en main.py), así que un mismo transecto
// sigue siendo válido aunque la cámara se recalibre más adelante.

const camId = ref(1)
const CAMS = [1, 2, 3, 4, 5, 6]

const imageList = ref([])
const selectedFile = ref('')
const transects = ref([])   // [{label, pixel:[x,y]}]
const saving = ref(false)
const dirty = ref(false)
const selectedIdx = ref(null)

const imgEl = ref(null)
const naturalW = ref(0)
const naturalH = ref(0)

const imageUrl = computed(() => {
  if (!camId.value || !selectedFile.value) return ''
  return `${API}/api/cameras/${camId.value}/image?file=${encodeURIComponent(selectedFile.value)}`
})

async function fetchImages() {
  imageList.value = []
  selectedFile.value = ''
  try {
    const r = await fetch(`${API}/api/cameras/${camId.value}/images`)
    if (!r.ok) return
    const data = await r.json()
    imageList.value = data
    if (data.length) selectedFile.value = data[data.length - 1].filename  // la más reciente
  } catch (e) {
    emit('notify', 'Error cargando imágenes: ' + e.message, 'error')
  }
}

async function fetchTransects() {
  transects.value = []
  selectedIdx.value = null
  dirty.value = false
  try {
    const r = await fetch(`${API}/api/cameras/${camId.value}/transects`)
    if (!r.ok) return
    const data = await r.json()
    transects.value = data.transects || []
  } catch (e) {
    emit('notify', 'Error cargando transectos: ' + e.message, 'error')
  }
}

watch(camId, () => { fetchImages(); fetchTransects() }, { immediate: true })

function onImgLoad() {
  naturalW.value = imgEl.value?.naturalWidth || 0
  naturalH.value = imgEl.value?.naturalHeight || 0
}

function onStageClick(event) {
  if (!imgEl.value || !naturalW.value) return
  const rect = imgEl.value.getBoundingClientRect()
  const x = ((event.clientX - rect.left) / rect.width) * naturalW.value
  const y = ((event.clientY - rect.top) / rect.height) * naturalH.value
  transects.value.push({ label: `Transecto ${transects.value.length + 1}`, pixel: [Math.round(x), Math.round(y)] })
  selectedIdx.value = transects.value.length - 1
  dirty.value = true
}

function removeTransect(idx) {
  transects.value.splice(idx, 1)
  selectedIdx.value = null
  dirty.value = true
}

function selectTransect(idx) {
  selectedIdx.value = selectedIdx.value === idx ? null : idx
}

async function saveTransects() {
  if (transects.value.some(t => !t.label.trim())) {
    emit('notify', 'Todos los transectos necesitan una etiqueta', 'error')
    return
  }
  saving.value = true
  try {
    const r = await fetch(`${API}/api/cameras/${camId.value}/transects`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ transects: transects.value }),
    })
    if (!r.ok) throw new Error(`HTTP ${r.status}`)
    dirty.value = false
    emit('notify', 'Transectos guardados', 'success')
  } catch (e) {
    emit('notify', 'Error guardando transectos: ' + e.message, 'error')
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <div class="flex h-full gap-4">

    <aside class="w-80 shrink-0 flex flex-col gap-4">
      <div class="bg-blue-50 border border-blue-200 rounded-md p-3">
        <p class="text-xs font-semibold text-blue-700">Anchura de playa por transectos</p>
        <p class="text-[10px] text-blue-600 mt-1 leading-relaxed">
          Marca un punto de referencia fijo (p.ej. la valla de la duna). Cada
          vez que se analice una imagen de esta cámara, se calculará la
          distancia desde ese punto hasta la línea de costa detectada —
          reemplaza al área en m² como indicador principal.
        </p>
      </div>

      <div class="card-standard p-4">
        <h3 class="text-[10px] font-semibold text-slate-400 uppercase tracking-wider mb-3">Cámara</h3>
        <div class="grid grid-cols-3 gap-2">
          <button v-for="c in CAMS" :key="c" @click="camId = c"
                  :class="camId === c ? 'chip active' : 'chip'" class="text-center">
            CAM {{ c }}
          </button>
        </div>
      </div>

      <div class="card-standard p-4">
        <h3 class="text-[10px] font-semibold text-slate-400 uppercase tracking-wider mb-3">Imagen de referencia</h3>
        <select v-model="selectedFile" class="input-standard w-full">
          <option v-if="imageList.length === 0" value="">Sin imágenes</option>
          <option v-for="img in imageList" :key="img.filename" :value="img.filename">{{ img.filename }}</option>
        </select>
        <p class="text-[10px] text-slate-400 mt-2">Solo para marcar el punto — la distancia se recalcula con cada imagen que se analice.</p>
      </div>

      <div class="card-standard overflow-hidden flex-1 flex flex-col min-h-0">
        <div class="card-header flex items-center justify-between">
          <span>Transectos ({{ transects.length }})</span>
        </div>
        <div class="flex-1 overflow-y-auto divide-y divide-slate-100">
          <div v-for="(t, idx) in transects" :key="idx" @click="selectTransect(idx)"
               :class="selectedIdx === idx ? 'bg-blue-50' : 'hover:bg-slate-50'"
               class="flex items-center gap-2 px-3 py-2 cursor-pointer">
            <span class="w-5 h-5 rounded-full bg-emerald-500 text-white text-[9px] font-bold flex items-center justify-center shrink-0">{{ idx + 1 }}</span>
            <input v-model="t.label" @click.stop @input="dirty = true" class="input-standard text-xs flex-1 py-1">
            <button @click.stop="removeTransect(idx)" class="text-red-400 hover:text-red-600 shrink-0">
              <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-width="2" d="M6 18L18 6M6 6l12 12"/></svg>
            </button>
          </div>
          <p v-if="!transects.length" class="text-center text-xs text-slate-400 py-8">Clic en la imagen para añadir el primer transecto</p>
        </div>
        <div class="p-3 border-t border-slate-100">
          <button @click="saveTransects" :disabled="saving || !dirty" class="btn-standard w-full justify-center py-2 text-sm disabled:opacity-40 disabled:cursor-not-allowed">
            {{ saving ? 'Guardando…' : dirty ? 'Guardar cambios' : 'Guardado' }}
          </button>
        </div>
      </div>
    </aside>

    <main class="flex-1 card-standard overflow-hidden flex flex-col">
      <div class="card-header normal-case text-[13px] font-semibold text-slate-700">
        Marcar transectos — CAM {{ camId }}
      </div>
      <div class="flex-1 flex items-center justify-center bg-slate-50 p-4 overflow-auto">
        <div v-if="!selectedFile" class="text-center text-slate-400">
          <p class="text-sm font-medium">Selecciona una cámara con imágenes</p>
        </div>
        <div v-else class="relative inline-block" style="cursor: crosshair;">
          <img ref="imgEl" :src="imageUrl" @load="onImgLoad" @click="onStageClick" draggable="false"
               class="max-w-full max-h-[70vh] object-contain rounded-md block select-none" alt="Imagen de referencia para marcar transectos" />
          <svg v-if="naturalW" class="absolute top-0 left-0 w-full h-full" style="pointer-events:none"
               :viewBox="`0 0 ${naturalW} ${naturalH}`" preserveAspectRatio="none">
            <g v-for="(t, idx) in transects" :key="idx" @click.stop="selectTransect(idx)" style="pointer-events:auto; cursor:pointer">
              <circle :cx="t.pixel[0]" :cy="t.pixel[1]" :r="selectedIdx === idx ? 18 : 13"
                      :fill="selectedIdx === idx ? '#10b981' : '#3b82f6'" stroke="white" stroke-width="4" />
              <text :x="t.pixel[0]" :y="t.pixel[1]" font-size="16" font-weight="bold" fill="white"
                    text-anchor="middle" dominant-baseline="central">{{ idx + 1 }}</text>
            </g>
          </svg>
        </div>
      </div>
    </main>

  </div>
</template>
