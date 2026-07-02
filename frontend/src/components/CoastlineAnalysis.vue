<script setup>
import { ref, computed, watch } from 'vue'

const emit = defineEmits(['notify'])
const API = 'http://localhost:8000'

// ── Estado ───────────────────────────────────────────────────────────────────
const camId        = ref(1)
const imageList    = ref([])
const selectedFile = ref('')
const loading      = ref(false)
const result       = ref(null)   // respuesta de analyze-roi
const imgTs        = ref(Date.now())  // cache-buster para la imagen resultado

// ── Cargar lista de imágenes cuando cambia la cámara ─────────────────────────
async function fetchImages() {
  imageList.value = []
  selectedFile.value = ''
  try {
    const r = await fetch(`${API}/api/cameras/${camId.value}/images`)
    if (!r.ok) return
    const data = await r.json()
    imageList.value = data
    if (data.length > 0) selectedFile.value = data[0].filename
  } catch (e) {
    emit('notify', 'Error cargando imágenes: ' + e.message, 'error')
  }
}

watch(camId, fetchImages, { immediate: true })

// ── Análisis ─────────────────────────────────────────────────────────────────
async function analyze() {
  if (!selectedFile.value) {
    emit('notify', 'Selecciona una imagen primero', 'error')
    return
  }
  loading.value = true
  result.value  = null
  try {
    const r = await fetch(
      `${API}/api/cameras/${camId.value}/analyze-roi?filename=${encodeURIComponent(selectedFile.value)}`,
      { method: 'POST' }
    )
    if (!r.ok) throw new Error(`HTTP ${r.status}`)
    const data = await r.json()
    result.value = data
    imgTs.value  = Date.now()

    if (data.rejected) {
      emit('notify', `Imagen rechazada: ${data.reject_reason}`, 'error')
    } else {
      emit('notify', `Análisis completado — ${data.points_utm} puntos UTM`, 'success')
    }
  } catch (e) {
    emit('notify', 'Error en análisis: ' + e.message, 'error')
  } finally {
    loading.value = false
  }
}

// ── Exportar GeoJSON ─────────────────────────────────────────────────────────
async function exportGeoJSON() {
  try {
    const r = await fetch(`${API}/api/cameras/${camId.value}/geojson`)
    if (!r.ok) throw new Error(`HTTP ${r.status}`)
    const data = await r.json()
    if (!data.features || data.features.length === 0) {
      emit('notify', 'No hay resultados para exportar. Ejecuta el análisis primero.', 'error')
      return
    }
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
    const url  = URL.createObjectURL(blob)
    const a    = document.createElement('a')
    a.href     = url
    a.download = `cv-lit_cam${camId.value}_costa.geojson`
    a.click()
    URL.revokeObjectURL(url)
    emit('notify', 'GeoJSON exportado', 'success')
  } catch (e) {
    emit('notify', 'Error exportando GeoJSON: ' + e.message, 'error')
  }
}

// ── Helpers ──────────────────────────────────────────────────────────────────
const resultImageUrl = computed(() => {
  if (!result.value || result.value.rejected) return ''
  return `${API}/api/cameras/${camId.value}/analysis-result?t=${imgTs.value}`
})

const confidenceColor = computed(() => {
  if (!result.value || result.value.confidence == null) return 'bg-slate-300'
  const c = result.value.confidence
  if (c >= 0.7) return 'bg-emerald-500'
  if (c >= 0.5) return 'bg-amber-400'
  return 'bg-red-500'
})

const confidencePct = computed(() => {
  if (!result.value || result.value.confidence == null) return 0
  return Math.round(result.value.confidence * 100)
})

const CAMS = [1, 2, 3, 4, 5, 6]
</script>

<template>
  <div class="flex h-full gap-6">

    <!-- ── Panel izquierdo: controles ──────────────────────────────────────── -->
    <aside class="w-72 shrink-0 flex flex-col gap-4">

      <!-- Selector de cámara -->
      <div class="bg-white rounded-xl border border-slate-200 p-5 shadow-sm">
        <h3 class="text-xs font-bold text-slate-500 uppercase tracking-widest mb-3">Cámara</h3>
        <div class="grid grid-cols-3 gap-2">
          <button
            v-for="c in CAMS" :key="c"
            @click="camId = c"
            :class="camId === c
              ? 'bg-blue-600 text-white shadow-md'
              : 'bg-slate-100 text-slate-600 hover:bg-slate-200'"
            class="rounded-lg py-2 text-sm font-bold transition-all">
            CAM {{ c }}
          </button>
        </div>
      </div>

      <!-- Selector de imagen -->
      <div class="bg-white rounded-xl border border-slate-200 p-5 shadow-sm">
        <h3 class="text-xs font-bold text-slate-500 uppercase tracking-widest mb-3">Imagen</h3>
        <select
          v-model="selectedFile"
          class="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm text-slate-700 bg-white focus:outline-none focus:ring-2 focus:ring-blue-500">
          <option v-if="imageList.length === 0" value="">Sin imágenes</option>
          <option v-for="img in imageList" :key="img.filename" :value="img.filename">
            {{ img.filename }}
          </option>
        </select>
        <p class="text-[10px] text-slate-400 mt-2">{{ imageList.length }} imágenes disponibles</p>
      </div>

      <!-- Botón analizar -->
      <button
        @click="analyze"
        :disabled="loading || !selectedFile"
        class="w-full flex items-center justify-center gap-2 bg-blue-600 hover:bg-blue-700 disabled:opacity-40 text-white font-bold py-3 rounded-xl transition-all shadow-sm text-sm">
        <svg v-if="!loading" class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-width="2" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2"/>
        </svg>
        <svg v-else class="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
          <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"/>
          <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/>
        </svg>
        {{ loading ? 'Analizando…' : 'Analizar imagen' }}
      </button>

      <!-- Métricas (#86) -->
      <div v-if="result" class="bg-white rounded-xl border border-slate-200 p-5 shadow-sm space-y-4">
        <h3 class="text-xs font-bold text-slate-500 uppercase tracking-widest">Métricas</h3>

        <!-- Alerta rechazo -->
        <div v-if="result.rejected" class="bg-red-50 border border-red-200 rounded-lg p-3">
          <p class="text-xs font-bold text-red-600 mb-1">Imagen rechazada</p>
          <p class="text-[10px] text-red-500 font-mono">{{ result.reject_reason }}</p>
        </div>

        <template v-else>
          <!-- Confianza IA con barra -->
          <div>
            <div class="flex justify-between text-xs mb-1">
              <span class="text-slate-500 font-medium">Confianza IA</span>
              <span class="font-bold" :class="result.confidence >= 0.7 ? 'text-emerald-600' : result.confidence >= 0.5 ? 'text-amber-500' : 'text-red-500'">
                {{ confidencePct }}%
              </span>
            </div>
            <div class="w-full bg-slate-100 rounded-full h-2">
              <div :class="confidenceColor" class="h-2 rounded-full transition-all duration-500"
                   :style="`width:${confidencePct}%`"></div>
            </div>
          </div>

          <!-- Área seca -->
          <div class="flex justify-between items-center">
            <span class="text-xs text-slate-500">Área seca</span>
            <span class="text-sm font-bold text-slate-800">{{ result.dry_area_m2?.toLocaleString('es-ES') }} m²</span>
          </div>

          <!-- Puntos UTM -->
          <div class="flex justify-between items-center">
            <span class="text-xs text-slate-500">Puntos UTM</span>
            <span class="text-sm font-bold text-slate-800">{{ result.points_utm }}</span>
          </div>

          <!-- Timestamp -->
          <div>
            <span class="text-xs text-slate-500">Timestamp</span>
            <p class="text-[10px] font-mono text-slate-600 mt-0.5 break-all">{{ result.timestamp }}</p>
          </div>
        </template>
      </div>

      <!-- Botón GeoJSON (#87) -->
      <button
        @click="exportGeoJSON"
        class="w-full flex items-center justify-center gap-2 border border-emerald-500 text-emerald-600 hover:bg-emerald-50 font-bold py-2.5 rounded-xl transition-all text-sm">
        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"/>
        </svg>
        Exportar GeoJSON
      </button>

    </aside>

    <!-- ── Panel central: imagen con overlay de segmentación y línea de costa (#84, #85) ── -->
    <main class="flex-1 bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden flex flex-col">
      <div class="px-5 py-3 border-b border-slate-100 flex items-center justify-between shrink-0">
        <h2 class="text-sm font-bold text-slate-700">
          Línea de costa — CAM {{ camId }}
          <span v-if="selectedFile" class="font-normal text-slate-400 ml-2 text-xs">{{ selectedFile }}</span>
        </h2>
        <div v-if="result && !result.rejected" class="flex items-center gap-2 text-xs text-emerald-600 font-medium">
          <div class="w-2 h-2 rounded-full bg-emerald-500"></div>
          Segmentación activa
        </div>
      </div>

      <div class="flex-1 flex items-center justify-center bg-slate-50 p-4">
        <!-- Estado inicial -->
        <div v-if="!result && !loading" class="text-center text-slate-400">
          <svg class="w-16 h-16 mx-auto mb-4 opacity-30" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-width="1.5" d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z"/>
          </svg>
          <p class="text-sm font-medium">Selecciona una imagen y pulsa "Analizar"</p>
          <p class="text-xs mt-1">La línea de costa y segmentación se mostrarán aquí</p>
        </div>

        <!-- Spinner -->
        <div v-else-if="loading" class="text-center text-slate-500">
          <svg class="w-12 h-12 mx-auto mb-4 animate-spin text-blue-500" fill="none" viewBox="0 0 24 24">
            <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"/>
            <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/>
          </svg>
          <p class="text-sm font-medium">Ejecutando segmentación SAM…</p>
          <p class="text-xs text-slate-400 mt-1">Puede tardar unos segundos</p>
        </div>

        <!-- Rechazo -->
        <div v-else-if="result && result.rejected" class="text-center">
          <div class="w-16 h-16 rounded-full bg-red-100 flex items-center justify-center mx-auto mb-4">
            <svg class="w-8 h-8 text-red-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"/>
            </svg>
          </div>
          <p class="text-sm font-bold text-red-600">Imagen rechazada</p>
          <p class="text-xs text-red-400 mt-1 font-mono">{{ result.reject_reason }}</p>
        </div>

        <!-- Imagen resultado con segmentación + línea de costa superpuesta (#84, #85) -->
        <img v-else-if="resultImageUrl"
             :src="resultImageUrl"
             :key="imgTs"
             class="max-w-full max-h-full object-contain rounded-lg shadow"
             alt="Línea de costa detectada" />
      </div>

      <!-- Leyenda -->
      <div v-if="result && !result.rejected" class="px-5 py-3 border-t border-slate-100 flex items-center gap-6 text-xs text-slate-500 shrink-0">
        <div class="flex items-center gap-1.5">
          <div class="w-3 h-0.5 bg-red-500"></div>
          <span>Línea de costa</span>
        </div>
        <div class="flex items-center gap-1.5">
          <div class="w-3 h-3 rounded-sm bg-amber-300 opacity-70"></div>
          <span>Zona baja confianza</span>
        </div>
        <span class="ml-auto text-slate-400">EPSG:25830 · UTM zona 30N</span>
      </div>
    </main>

  </div>
</template>
