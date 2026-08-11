<script setup>
import { ref, onMounted, onUnmounted, computed } from 'vue'
import { API_BASE } from '../api.js'
import Map from './Map.vue'

const emit = defineEmits(['notify', 'calibrate-camera'])
const API = API_BASE

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
    if (!res.ok) throw new Error('HTTP ' + res.status)
    const data = await res.json()
    cameras.value = data.cameras
  } catch (e) { emit('notify', 'Error al cargar cámaras', 'error') }
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

// ── Evolución temporal ────────────────────────────────────────────────────
// Histórico de líneas de costa de una cámara con deslizador de tiempo:
// la captura seleccionada se pinta en azul y las demás como estela gris.
const historyCam = ref('')
const history = ref(null)
const timeIdx = ref(0)
const playing = ref(false)
const showTrails = ref(true)
const fitSignal = ref(0)
let playTimer = null

const historyFeatures = computed(() => history.value?.features || [])
const currentTs = computed(() => {
  const ts = historyFeatures.value[timeIdx.value]?.properties?.Timestamp
  return ts ? String(ts).replace('T', ' ').slice(0, 16) : '—'
})

async function loadHistory() {
  stopPlay()
  history.value = null
  if (!historyCam.value) { fitSignal.value++; return }
  try {
    const res = await fetch(`${API}/api/cameras/${historyCam.value}/coastline-history`)
    const data = await res.json()
    history.value = data
    timeIdx.value = Math.max(0, (data.features?.length || 1) - 1)
    fitSignal.value++
    if (!data.features?.length) emit('notify', 'Esta cámara aún no tiene histórico de línea de costa', 'info')
  } catch (e) { emit('notify', 'Error al cargar el histórico', 'error') }
}

function togglePlay() {
  if (playing.value) return stopPlay()
  if (historyFeatures.value.length < 2) return
  playing.value = true
  playTimer = setInterval(() => {
    timeIdx.value = (timeIdx.value + 1) % historyFeatures.value.length
  }, 900)
}

function stopPlay() {
  playing.value = false
  if (playTimer) { clearInterval(playTimer); playTimer = null }
}

onUnmounted(stopPlay)

const displayedGeoJson = computed(() => {
  // Modo temporal activo: solo se muestra el histórico de la cámara elegida
  if (historyCam.value && historyFeatures.value.length) {
    const features = []
    if (showTrails.value) {
      historyFeatures.value.forEach((f, i) => {
        if (i === timeIdx.value) return
        features.push({
          ...f,
          properties: { ...f.properties, _style: { color: '#94a3b8', weight: 1.5, opacity: 0.45 } },
        })
      })
    }
    const current = historyFeatures.value[timeIdx.value]
    if (current) features.push(current)
    return { type: 'FeatureCollection', features }
  }

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
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
  emit('notify', 'GeoJSON combinado exportado', 'success')
}

onMounted(() => {
  fetchCombined()
  fetchCameras()
})
</script>

<template>
  <div class="space-y-4 h-full flex flex-col">
    <div class="flex justify-end shrink-0">
      <button @click="exportCombined" class="btn-standard uppercase text-xs">↓ GeoJSON combinado</button>
    </div>

    <div class="flex-1 grid grid-cols-1 lg:grid-cols-4 gap-4 min-h-[500px]">
      <div class="lg:col-span-3 card-standard overflow-hidden">
        <Map :geojsonData="displayedGeoJson" :fit-signal="fitSignal" @select-camera="emit('calibrate-camera', $event)" />
      </div>

      <aside class="space-y-4">
        <div class="card-standard p-4 space-y-3">
          <div class="text-[10px] font-semibold text-slate-400 uppercase tracking-wider">Capas</div>
          <label class="flex items-center space-x-2 text-xs font-medium text-slate-700">
            <input type="checkbox" v-model="showCombined" class="rounded">
            <span>Línea de costa (combinada)</span>
          </label>
          <div class="pt-2 border-t border-slate-100 space-y-2">
            <p class="text-[9px] font-semibold text-slate-400 uppercase">Por estación</p>
            <label v-for="cam in cameras" :key="cam.idx" class="flex items-center space-x-2 text-xs font-medium text-slate-700">
              <input type="checkbox" :checked="selectedCams.has(cam.idx)" @change="toggleCamLayer(cam.idx)" class="rounded">
              <span>{{ cam.name }}</span>
            </label>
          </div>
        </div>

        <div class="card-standard p-4 space-y-3">
          <div class="text-[10px] font-semibold text-slate-400 uppercase tracking-wider">Evolución temporal</div>
          <select v-model="historyCam" @change="loadHistory" class="w-full input-standard text-xs">
            <option value="">Desactivada</option>
            <option v-for="cam in cameras" :key="cam.idx" :value="cam.idx">{{ cam.name }}</option>
          </select>
          <template v-if="historyCam && historyFeatures.length">
            <input type="range" min="0" :max="historyFeatures.length - 1" v-model.number="timeIdx"
                   @input="stopPlay" class="w-full accent-blue-600">
            <div class="flex items-center justify-between">
              <button @click="togglePlay" class="btn-secondary py-1 px-3 text-[10px] uppercase">
                {{ playing ? '⏸ Pausa' : '▶ Reproducir' }}
              </button>
              <span class="text-[10px] font-mono text-slate-600">{{ currentTs }}</span>
            </div>
            <label class="flex items-center space-x-2 text-xs font-medium text-slate-700">
              <input type="checkbox" v-model="showTrails" class="rounded">
              <span>Mostrar líneas anteriores</span>
            </label>
            <p class="text-[9px] text-slate-400 uppercase font-semibold">Captura {{ timeIdx + 1 }} / {{ historyFeatures.length }}</p>
          </template>
          <p v-else-if="historyCam" class="text-[10px] text-slate-400">Sin histórico para esta cámara todavía. Se irá llenando con cada análisis.</p>
        </div>

        <div class="card-standard p-4 space-y-2">
          <div class="text-[10px] font-semibold text-slate-400 uppercase tracking-wider">Resumen</div>
          <p class="text-xs text-slate-600">{{ displayedGeoJson.features.length }} feature(s) visibles</p>
        </div>
      </aside>
    </div>
  </div>
</template>
