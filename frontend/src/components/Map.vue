<script setup>
import { onMounted, ref, watch } from 'vue'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'

const mapContainer = ref(null)
let map = null
let geoJsonLayer = null
const currentLayer = ref('vector')

const props = defineProps({
  geojsonData: {
    type: Object,
    default: null
  }
})

const layers = {
  vector: L.tileLayer('https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png', {
    attribution: '&copy; CARTO'
  }),
  satellite: L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', {
    attribution: 'Tiles &copy; Esri'
  })
}

function switchLayer(type) {
  if (currentLayer.value === type) return
  map.removeLayer(layers[currentLayer.value])
  layers[type].addTo(map)
  currentLayer.value = type
}

onMounted(() => {
  map = L.map(mapContainer.value).setView([38.085, -0.648], 15)
  layers.vector.addTo(map)

  if (props.geojsonData) {
    updateGeoJson(props.geojsonData)
  }
})

function updateGeoJson(data) {
  if (geoJsonLayer) {
    map.removeLayer(geoJsonLayer)
  }
  geoJsonLayer = L.geoJSON(data, {
    style: {
      color: '#2563eb',
      weight: 3,
      opacity: 0.8
    }
  }).addTo(map)
  
  if (data.features && data.features.length > 0) {
    map.fitBounds(geoJsonLayer.getBounds())
  }
}

watch(() => props.geojsonData, (newData) => {
  if (newData && map) {
    updateGeoJson(newData)
  }
}, { deep: true })
</script>

<template>
  <div class="relative w-full h-full">
    <div ref="mapContainer" class="w-full h-full bg-slate-100 rounded-md border border-slate-200 shadow-inner"></div>
    
    <!-- Simple Layer Switcher -->
    <div class="absolute top-4 right-4 z-[400] flex bg-white border border-slate-300 rounded shadow-md overflow-hidden">
       <button @click="switchLayer('vector')" 
               :class="currentLayer === 'vector' ? 'bg-slate-800 text-white' : 'text-slate-600 hover:bg-slate-50'"
               class="px-3 py-1.5 text-[10px] font-bold uppercase border-r border-slate-300 transition-colors">Vector</button>
       <button @click="switchLayer('satellite')" 
               :class="currentLayer === 'satellite' ? 'bg-slate-800 text-white' : 'text-slate-600 hover:bg-slate-50'"
               class="px-3 py-1.5 text-[10px] font-bold uppercase transition-colors">Satélite</button>
    </div>
  </div>
</template>

<style>
/* Ensure the map container has a height */
.leaflet-container {
  background: #f1f5f9;
}
</style>
