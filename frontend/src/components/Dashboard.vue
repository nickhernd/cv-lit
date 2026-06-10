<script setup>
import { ref, onMounted } from 'vue'

const data = ref(null)
const error = ref(null)

onMounted(async () => {
  try {
    const response = await fetch('http://localhost:8000/api/dashboard')
    if (!response.ok) throw new Error('Error al conectar con el servidor')
    data.value = await response.json()
  } catch (err) {
    error.value = err.message
    console.error('Fetch error:', err)
  }
})
</script>

<template>
  <div v-if="error" class="p-6 text-red-600 font-bold">
    Error: {{ error }}
  </div>
  <div v-else-if="data" class="p-6 bg-gray-50 min-h-screen">
    <!-- ... tu contenido actual ... -->
    <h1 class="text-2xl font-bold mb-6 text-gray-800">Dashboard</h1>
    <!-- (Mantén el resto del template igual) -->
    <div class="grid grid-cols-1 md:grid-cols-3 gap-4 mb-8">
      <div class="bg-white p-4 rounded-lg shadow">
        <p class="text-sm text-gray-500">Cámaras Calibradas</p>
        <p class="text-xl font-semibold">{{ data.cameras_calibrated }} / {{ data.total_cameras }}</p>
      </div>
      <div class="bg-white p-4 rounded-lg shadow">
        <p class="text-sm text-gray-500">Imágenes Procesadas</p>
        <p class="text-xl font-semibold">{{ data.images_processed }}</p>
      </div>
      <div class="bg-white p-4 rounded-lg shadow">
        <p class="text-sm text-gray-500">Área Seca Media</p>
        <p class="text-xl font-semibold">{{ data.avg_dry_area }}</p>
      </div>
    </div>
    
    <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
      <div v-for="cam in data.cameras" :key="cam.id" 
           class="p-4 rounded-lg shadow border-l-4"
           :class="cam.status === 'Sin calibrar' ? 'bg-red-50 border-red-500' : 'bg-white border-green-500'">
        <h3 class="font-bold text-lg">{{ cam.id }} - {{ cam.name }}</h3>
        <p class="text-sm" :class="cam.status === 'Sin calibrar' ? 'text-red-700' : 'text-green-700'">
          Estado: {{ cam.status }}
        </p>
        <p class="text-sm text-gray-600">Imágenes: {{ cam.images }}</p>
      </div>
    </div>
  </div>
  <div v-else class="p-6 text-gray-600">Cargando datos del dashboard...</div>
</template>
