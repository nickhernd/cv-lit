<script setup>
import { ref, reactive, watch, onMounted } from 'vue'

const emit = defineEmits(['notify', 'calibrate-camera'])
const API = 'http://localhost:8000'

const cameras = ref([])
const loading = ref(true)
const viewingIdx = ref(null)
const saving = ref(false)

const hardwareForm = reactive({ utm_x: null, utm_y: null, height_m: null, azimuth_deg: null })
const roiForm = reactive({ x_min: 0, y_min: 0, x_max: 0, y_max: 0, description: '' })

async function fetchCameras() {
  loading.value = true
  try {
    const res = await fetch(`${API}/api/cameras`)
    cameras.value = await res.json()
  } catch (e) { emit('notify', 'Error al cargar cámaras', 'error') }
  finally { loading.value = false }
}

function fmtDate(ts) {
  if (!ts) return '—'
  return new Date(ts * 1000).toLocaleString('es-ES', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' })
}

const viewing = () => cameras.value.find(c => c.idx === viewingIdx.value)

function toggleView(idx) {
  viewingIdx.value = viewingIdx.value === idx ? null : idx
}

watch(viewingIdx, () => {
  const cam = viewing()
  if (!cam) return
  hardwareForm.utm_x = cam.utm_x
  hardwareForm.utm_y = cam.utm_y
  hardwareForm.height_m = cam.height_m
  hardwareForm.azimuth_deg = cam.azimuth_deg
  roiForm.x_min = cam.roi?.x_min ?? 0
  roiForm.y_min = cam.roi?.y_min ?? 0
  roiForm.x_max = cam.roi?.x_max ?? 0
  roiForm.y_max = cam.roi?.y_max ?? 0
  roiForm.description = cam.roi?.description ?? ''
})

async function saveChanges() {
  if (!viewingIdx.value) return
  saving.value = true
  try {
    const [hwRes, roiRes] = await Promise.all([
      fetch(`${API}/api/cameras/${viewingIdx.value}/hardware`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(hardwareForm)
      }),
      fetch(`${API}/api/cameras/${viewingIdx.value}/roi`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(roiForm)
      })
    ])
    if (!hwRes.ok || !roiRes.ok) throw new Error('HTTP error')
    await fetchCameras()
    emit('notify', 'Cambios guardados', 'success')
  } catch (e) { emit('notify', 'Error al guardar cambios: ' + e.message, 'error') }
  finally { saving.value = false }
}

onMounted(fetchCameras)
</script>

<template>
  <div class="space-y-6">
    <div class="flex justify-between items-center border-b border-slate-200 pb-4">
      <div>
        <h1 class="text-xl font-semibold text-slate-900 tracking-tight">Configuración de Cámaras</h1>
        <p class="text-xs text-slate-400 font-medium">{{ cameras.length }} estaciones · Guardamar del Segura</p>
      </div>
    </div>

    <div class="card-standard overflow-hidden">
      <div class="overflow-x-auto">
        <table class="w-full text-left text-sm">
          <thead class="bg-slate-50/60 text-slate-500 font-semibold border-b border-slate-100">
            <tr>
              <th class="px-6 py-3 uppercase tracking-widest text-[10px]">ID</th>
              <th class="px-6 py-3 uppercase tracking-widest text-[10px]">Nombre</th>
              <th class="px-6 py-3 uppercase tracking-widest text-[10px]">Estado</th>
              <th class="px-6 py-3 uppercase tracking-widest text-[10px]">Calibración</th>
              <th class="px-6 py-3 uppercase tracking-widest text-[10px]">RMSE</th>
              <th class="px-6 py-3 uppercase tracking-widest text-[10px]">GCPs</th>
              <th class="px-6 py-3 uppercase tracking-widest text-[10px]">Última img.</th>
              <th class="px-6 py-3 text-right uppercase tracking-widest text-[10px]">Acciones</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-slate-100">
            <tr v-for="cam in cameras" :key="cam.idx" class="hover:bg-slate-50 transition-colors text-slate-700">
              <td class="px-6 py-4 font-mono text-[10px] text-slate-500">{{ cam.id }}</td>
              <td class="px-6 py-4 font-bold uppercase text-[11px]">{{ cam.name }}</td>
              <td class="px-6 py-4">
                <span class="inline-flex items-center space-x-1.5">
                  <span :class="cam.calibrated ? 'bg-emerald-500' : 'bg-red-500'" class="w-1.5 h-1.5 rounded-full"></span>
                  <span class="text-[10px] font-bold uppercase">{{ cam.calibrated ? 'Activa' : 'Sin calibrar' }}</span>
                </span>
              </td>
              <td class="px-6 py-4 text-[10px] font-mono text-slate-500">{{ cam.last_calibration_date || '—' }}</td>
              <td class="px-6 py-4 text-[10px] font-mono" :class="cam.rmse_m > 1 ? 'text-amber-600' : 'text-slate-600'">{{ cam.rmse_m ? cam.rmse_m.toFixed(2) + ' m' : '—' }}</td>
              <td class="px-6 py-4 text-[10px] font-mono text-slate-500">{{ cam.gcps_count ?? '—' }}</td>
              <td class="px-6 py-4 text-[10px] font-mono text-slate-500">{{ fmtDate(cam.last_image_ts) }}</td>
              <td class="px-6 py-4 text-right space-x-2">
                <button @click="emit('calibrate-camera', cam.idx)" class="btn-secondary py-1 px-3 text-[10px]">Calibrar</button>
                <button @click="toggleView(cam.idx)" class="btn-standard py-1 px-3 text-[10px]">{{ viewingIdx === cam.idx ? 'Cerrar' : 'Ver' }}</button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <div v-if="viewing()" class="card-standard animate-fade-in">
      <div class="card-header flex justify-between items-center">
        <span>{{ viewing().name }} — Configuración hardware</span>
        <button @click="saveChanges" :disabled="saving" class="btn-standard py-1.5 px-4 text-[10px] uppercase">
          {{ saving ? 'Guardando…' : 'Guardar cambios' }}
        </button>
      </div>
      <div class="p-6 grid grid-cols-1 md:grid-cols-2 gap-8">
        <div class="space-y-4">
          <div class="text-[10px] font-bold text-slate-400 uppercase tracking-widest">Información general</div>
          <div class="grid grid-cols-2 gap-4 text-xs">
            <div><p class="text-[9px] font-bold text-slate-400 uppercase mb-0.5">ID</p><p class="font-mono font-bold">{{ viewing().id }}</p></div>
            <div><p class="text-[9px] font-bold text-slate-400 uppercase mb-0.5">Nº Serie</p><p class="font-mono">{{ viewing().serial }}</p></div>
            <div class="space-y-1">
              <label class="text-[9px] font-bold text-slate-400 uppercase">UTM X (m)</label>
              <input type="number" step="0.01" v-model.number="hardwareForm.utm_x" class="w-full input-standard font-mono text-xs">
            </div>
            <div class="space-y-1">
              <label class="text-[9px] font-bold text-slate-400 uppercase">UTM Y (m)</label>
              <input type="number" step="0.01" v-model.number="hardwareForm.utm_y" class="w-full input-standard font-mono text-xs">
            </div>
            <div class="space-y-1">
              <label class="text-[9px] font-bold text-slate-400 uppercase">Altura (m)</label>
              <input type="number" step="0.1" v-model.number="hardwareForm.height_m" class="w-full input-standard font-mono text-xs">
            </div>
            <div class="space-y-1">
              <label class="text-[9px] font-bold text-slate-400 uppercase">Acimut (°)</label>
              <input type="number" step="0.1" v-model.number="hardwareForm.azimuth_deg" class="w-full input-standard font-mono text-xs">
            </div>
            <div><p class="text-[9px] font-bold text-slate-400 uppercase mb-0.5">Imágenes almacenadas</p><p class="font-mono">{{ viewing().images_count }}</p></div>
          </div>
        </div>
        <div class="space-y-4">
          <div class="text-[10px] font-bold text-slate-400 uppercase tracking-widest">Región de interés (ROI)</div>
          <div class="grid grid-cols-2 gap-4 text-xs">
            <div class="space-y-1">
              <label class="text-[9px] font-bold text-slate-400 uppercase">X min (px)</label>
              <input type="number" v-model.number="roiForm.x_min" class="w-full input-standard font-mono text-xs">
            </div>
            <div class="space-y-1">
              <label class="text-[9px] font-bold text-slate-400 uppercase">X max (px)</label>
              <input type="number" v-model.number="roiForm.x_max" class="w-full input-standard font-mono text-xs">
            </div>
            <div class="space-y-1">
              <label class="text-[9px] font-bold text-slate-400 uppercase">Y min (px)</label>
              <input type="number" v-model.number="roiForm.y_min" class="w-full input-standard font-mono text-xs">
            </div>
            <div class="space-y-1">
              <label class="text-[9px] font-bold text-slate-400 uppercase">Y max (px)</label>
              <input type="number" v-model.number="roiForm.y_max" class="w-full input-standard font-mono text-xs">
            </div>
            <div class="col-span-2 space-y-1">
              <label class="text-[9px] font-bold text-slate-400 uppercase">Descripción</label>
              <input v-model="roiForm.description" class="w-full input-standard text-xs">
            </div>
          </div>
        </div>
      </div>
    </div>

    <p v-if="!loading && !cameras.length" class="text-center text-sm text-slate-400 py-12">No se encontraron cámaras</p>
  </div>
</template>

<style scoped>
.animate-fade-in { animation: fadeIn 0.2s ease-out; }
@keyframes fadeIn { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: translateY(0); } }
</style>
