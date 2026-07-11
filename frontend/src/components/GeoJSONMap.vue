<script setup>
import { ref, onMounted, computed } from 'vue'
import Map from './Map.vue'

const emit = defineEmits(['notify'])
const API = 'http://localhost:8000'

const combined = ref(null)
const perCamera = ref({})
const showCombined = ref(true)
const selectedCams = ref(new Set())
const cameras = ref([])

async function fetchCombined() {
  try {
    const res = await fetch(`${API}/api/geojson`)
    combined.value = await res.json()
  } catch (e) { emit('notify', 'Error al cargar GeoJSON combinado', 'error') }
}

async function fetchCameras() {
  try {
    const res = await fetch(`${API}/api/dashboard`)
    const data = await res.json()
    cameras.value = data.cameras
  } catch (e) { /* noop */ }
}

async function toggleCamLayer(idx) {
  const next = new Set(selectedCams.value)
  if (next.has(idx)) {
    next.delete(idx)
  } else {
    next.add(idx)
    if (!perCamera.value[idx]) {
      try {
        const res = await fetch(`${API}/api/cameras/${idx}/geojson`)
        perCamera.value = { ...perCamera.value, [idx]: await res.json() }
      } catch (e) { emit('notify', `Error al cargar GeoJSON de C${idx}`, 'error') }
    }
  }
  selectedCams.value = next
}

const displayedGeoJson = computed(() => {
  const features = []
  if (showCombined.value && combined.value?.features) features.push(...combined.value.features)
  for (const idx of selectedCams.value) {
    if (perCamera.value[idx]?.features) features.push(...perCamera.value[idx].features)
  }
  return { type: 'FeatureCollection', features }
})

function exportCombined() {
  if (!combined.value?.features?.length) {
    emit('notify', 'No hay datos para exportar', 'error')
    return
  }
  const blob = new Blob([JSON.stringify(combined.value, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = 'cv-lit_linea_costa_combinado.geojson'
  a.click()
  URL.revokeObjectURL(url)
  emit('notify', 'GeoJSON combinado exportado', 'success')
}

onMounted(() => {
  fetchCombined()
  fetchCameras()
})
</script>

<template>
  <div class="space-y-6 h-full flex flex-col">
    <div class="flex justify-between items-center border-b border-slate-200 pb-4 shrink-0">
      <div>
        <h1 class="text-xl font-semibold text-slate-900 tracking-tight">Mapa GeoJSON</h1>
        <p class="text-xs text-slate-400 font-medium">EPSG:25830 · Guardamar del Segura</p>
      </div>
      <button @click="exportCombined" class="btn-standard uppercase text-xs">↓ GeoJSON combinado</button>
    </div>

    <div class="flex-1 grid grid-cols-1 lg:grid-cols-4 gap-6 min-h-[500px]">
      <div class="lg:col-span-3 card-standard overflow-hidden">
        <Map :geojsonData="displayedGeoJson" />
      </div>

      <aside class="space-y-4">
        <div class="card-standard p-4 space-y-3">
          <div class="text-[10px] font-bold text-slate-400 uppercase tracking-widest">Capas</div>
          <label class="flex items-center space-x-2 text-xs font-medium text-slate-700">
            <input type="checkbox" v-model="showCombined" class="rounded">
            <span>Línea de costa (combinada)</span>
          </label>
          <div class="pt-2 border-t border-slate-100 space-y-2">
            <p class="text-[9px] font-bold text-slate-400 uppercase">Por estación</p>
            <label v-for="cam in cameras" :key="cam.idx" class="flex items-center space-x-2 text-xs font-medium text-slate-700">
              <input type="checkbox" :checked="selectedCams.has(cam.idx)" @change="toggleCamLayer(cam.idx)" class="rounded">
              <span>{{ cam.name }}</span>
            </label>
          </div>
        </div>

        <div class="card-standard p-4 space-y-2">
          <div class="text-[10px] font-bold text-slate-400 uppercase tracking-widest">Resumen</div>
          <p class="text-xs text-slate-600">{{ displayedGeoJson.features.length }} feature(s) visibles</p>
        </div>
      </aside>
    </div>
  </div>
</template>
