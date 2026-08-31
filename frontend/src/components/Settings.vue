<script setup>
import { ref, onMounted } from 'vue'
import { API_BASE } from '../api.js'

const emit = defineEmits(['notify'])
const API = API_BASE

const loading = ref(true)
const saving = ref(false)
const testing = ref(false)
const configured = ref(false)
const showKey = ref(false)

const obscapeUsername = ref('')
const obscapeApiKey = ref('')

async function fetchSettings() {
  loading.value = true
  try {
    const res = await fetch(`${API}/api/settings`)
    const data = await res.json()
    obscapeUsername.value = data.obscape_username || ''
    obscapeApiKey.value = data.obscape_api_key || ''
    configured.value = data.configured
  } catch (err) {
    emit('notify', 'Error al cargar la configuración', 'error')
  } finally {
    loading.value = false
  }
}

async function saveSettings() {
  saving.value = true
  try {
    const res = await fetch(`${API}/api/settings`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        obscape_username: obscapeUsername.value.trim(),
        obscape_api_key: obscapeApiKey.value.trim(),
      }),
    })
    if (!res.ok) throw new Error('Error al guardar')
    const data = await res.json()
    configured.value = data.configured
    emit('notify', 'Configuración guardada', 'success')
  } catch (err) {
    emit('notify', 'Error al guardar la configuración', 'error')
  } finally {
    saving.value = false
  }
}

async function testConnection() {
  testing.value = true
  try {
    const res = await fetch(`${API}/api/settings/test-connection`, { method: 'POST' })
    const data = await res.json()
    if (data.status === 'success') {
      emit('notify', `Conexión correcta — ${data.stations_found} estación(es) encontrada(s)`, 'success')
    } else {
      emit('notify', `Fallo de conexión: ${data.detail}`, 'error')
    }
  } catch (err) {
    emit('notify', 'Error al probar la conexión', 'error')
  } finally {
    testing.value = false
  }
}

onMounted(fetchSettings)
</script>

<template>
  <div class="max-w-xl space-y-4">
    <div class="card-standard p-4 space-y-4">
      <div class="flex items-center justify-between">
        <div class="text-[10px] font-semibold text-slate-400 uppercase tracking-wider">
          Credenciales de Obscape
        </div>
        <span class="inline-flex items-center gap-1.5 text-[10px] font-semibold uppercase px-2 py-0.5 rounded-full"
              :class="configured ? 'bg-emerald-100 text-emerald-700' : 'bg-slate-100 text-slate-500'">
          <span class="w-1.5 h-1.5 rounded-full" :class="configured ? 'bg-emerald-500' : 'bg-slate-400'"></span>
          {{ configured ? 'Configurado' : 'Sin configurar' }}
        </span>
      </div>

      <p class="text-xs text-slate-500 leading-relaxed">
        Necesarias para descargar imágenes de las cámaras (Carga de imágenes, Modo automático).
        Cada persona que use esta aplicación tiene su propia cuenta en el portal de Obscape —
        estas claves se guardan solo en este ordenador, nunca se comparten ni se suben a ningún sitio.
      </p>

      <div v-if="!loading" class="space-y-3">
        <div class="space-y-1">
          <label class="text-[10px] font-semibold text-slate-500 uppercase">Usuario</label>
          <input v-model="obscapeUsername" class="w-full input-standard text-xs" placeholder="usuario del portal Obscape" autocomplete="off">
        </div>
        <div class="space-y-1">
          <label class="text-[10px] font-semibold text-slate-500 uppercase">API Key</label>
          <div class="relative">
            <input v-model="obscapeApiKey" :type="showKey ? 'text' : 'password'"
                   class="w-full input-standard text-xs pr-16" placeholder="clave de API" autocomplete="off">
            <button @click="showKey = !showKey" type="button"
                    class="absolute right-2 top-1/2 -translate-y-1/2 text-[10px] font-semibold text-blue-600 hover:underline uppercase">
              {{ showKey ? 'Ocultar' : 'Ver' }}
            </button>
          </div>
        </div>
      </div>
      <div v-else class="text-xs text-slate-400 italic">Cargando…</div>

      <div class="flex items-center gap-2 pt-1">
        <button @click="saveSettings" :disabled="saving || loading" class="btn-standard text-xs uppercase disabled:opacity-40">
          {{ saving ? 'Guardando…' : 'Guardar' }}
        </button>
        <button @click="testConnection" :disabled="testing || loading || !configured" class="btn-secondary text-xs uppercase disabled:opacity-40"
                :title="!configured ? 'Guarda primero unas credenciales para poder probarlas' : ''">
          {{ testing ? 'Probando…' : 'Probar conexión' }}
        </button>
      </div>
    </div>
  </div>
</template>
