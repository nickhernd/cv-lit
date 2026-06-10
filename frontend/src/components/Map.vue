<script setup>
import { onMounted, ref, watch } from 'vue'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'

const mapContainer = ref(null)
let map = null
let geoJsonLayer = null

const props = defineProps({
  geojsonData: {
    type: Object,
    default: null
  }
})

onMounted(() => {
  map = L.map(mapContainer.value).setView([38.085, -0.648], 15)
  
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '&copy; OpenStreetMap contributors'
  }).addTo(map)

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
  
  if (data.features.length > 0) {
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
  <div ref="mapContainer" class="w-full h-full rounded-2xl overflow-hidden border border-slate-100 shadow-sm"></div>
</template>

<style>
/* Ensure the map container has a height */
.leaflet-container {
  background: #f8fafc;
}
</style>
