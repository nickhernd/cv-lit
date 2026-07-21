<script setup>
import { onMounted, ref, watch } from 'vue'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import proj4 from 'proj4'

// El backend genera las líneas de costa en EPSG:25830 (ETRS89 / UTM 30N, metros).
// Leaflet trabaja en WGS84 (grados), así que hay que reproyectar antes de pintar.
const EPSG_25830 = '+proj=utm +zone=30 +ellps=GRS80 +towgs84=0,0,0,0,0,0,0 +units=m +no_defs'

function toWgs84(coord) {
  // Coordenadas UTM tienen magnitudes de cientos de miles / millones;
  // si ya vienen en grados (|x|<=180, |y|<=90) se dejan tal cual.
  const [x, y] = coord
  if (Math.abs(x) <= 180 && Math.abs(y) <= 90) return coord
  return proj4(EPSG_25830, 'EPSG:4326', [x, y])
}

function reprojectCoords(coords) {
  if (!Array.isArray(coords)) return coords
  if (typeof coords[0] === 'number') return toWgs84(coords)
  return coords.map(reprojectCoords)
}

// Suavizado de esquinas de Chaikin: redondea la polilínea sin desviarla,
// conservando los extremos. Dos pasadas bastan para que se vea continua.
function chaikin(pts, iterations = 2) {
  if (!Array.isArray(pts) || pts.length < 3) return pts
  for (let it = 0; it < iterations; it++) {
    const out = [pts[0]]
    for (let i = 0; i < pts.length - 1; i++) {
      const a = pts[i], b = pts[i + 1]
      out.push([0.75 * a[0] + 0.25 * b[0], 0.75 * a[1] + 0.25 * b[1]])
      out.push([0.25 * a[0] + 0.75 * b[0], 0.25 * a[1] + 0.75 * b[1]])
    }
    out.push(pts[pts.length - 1])
    pts = out
  }
  return pts
}

function smoothGeometry(geometry) {
  if (!geometry) return geometry
  if (geometry.type === 'LineString') {
    return { ...geometry, coordinates: chaikin(geometry.coordinates) }
  }
  if (geometry.type === 'MultiLineString') {
    return { ...geometry, coordinates: geometry.coordinates.map(l => chaikin(l)) }
  }
  return geometry
}

function reprojectGeoJson(data) {
  if (!data?.features) return data
  return {
    ...data,
    features: data.features.map(f => ({
      ...f,
      geometry: f.geometry
        ? smoothGeometry({ ...f.geometry, coordinates: reprojectCoords(f.geometry.coordinates) })
        : f.geometry,
    })),
  }
}

const mapContainer = ref(null)
let map = null
let geoJsonLayer = null
const currentLayer = ref('vector')

const props = defineProps({
  geojsonData: {
    type: Object,
    default: null
  },
  // Incrementar este contador fuerza un reencuadre en el siguiente render
  // (p.ej. al cambiar de cámara en la evolución temporal)
  fitSignal: {
    type: Number,
    default: 0
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

let hasFitted = false

function updateGeoJson(data) {
  if (geoJsonLayer) {
    map.removeLayer(geoJsonLayer)
    geoJsonLayer = null
  }
  const projected = reprojectGeoJson(data)
  if (!projected?.features?.length) return
  geoJsonLayer = L.geoJSON(projected, {
    // Cada feature puede traer su propio estilo en properties._style
    // (lo usa el modo de evolución temporal para atenuar las líneas antiguas)
    style: f => ({
      color: f?.properties?._style?.color ?? '#2563eb',
      weight: f?.properties?._style?.weight ?? 3,
      opacity: f?.properties?._style?.opacity ?? 0.8,
    }),
    // Puntos (p.ej. varillas GCP) como círculos propios en vez del icono por
    // defecto de Leaflet, que no resuelve sus imágenes con el bundler.
    pointToLayer: (feature, latlng) => L.circleMarker(latlng, {
      radius: 7,
      weight: 2,
      color: '#fff',
      fillColor: feature?.properties?._style?.color ?? '#2f6690',
      fillOpacity: 0.9,
    }),
    onEachFeature: (feature, layer) => {
      const p = feature.properties || {}
      if (p.ID_Camara != null) {
        layer.bindPopup(
          `<b>Cámara ${p.ID_Camara}</b><br>` +
          (p.Timestamp ? `${String(p.Timestamp).replace('T', ' ').slice(0, 16)}<br>` : '') +
          (p.Area_Seca_m2 != null ? `Área seca: ${p.Area_Seca_m2} m²<br>` : '') +
          (p.Confianza_IA != null ? `Confianza: ${(p.Confianza_IA * 100).toFixed(0)}%` : '')
        )
      } else if (p.label != null) {
        layer.bindPopup(`<b>${p.label}</b>`)
        if (p.idx != null) layer.bindTooltip(String(p.idx + 1), { permanent: true, direction: 'top', offset: [0, -8], className: 'gcp-tooltip' })
      }
    }
  }).addTo(map)

  // Encajar la vista solo la primera vez: al animar la línea temporal o
  // alternar capas el mapa no debe estar saltando de encuadre.
  if (!hasFitted) {
    const bounds = geoJsonLayer.getBounds()
    if (bounds.isValid()) {
      map.fitBounds(bounds, { maxZoom: 17, padding: [20, 20] })
      hasFitted = true
    }
  }
}

watch(() => props.geojsonData, (newData) => {
  if (newData && map) {
    updateGeoJson(newData)
  }
}, { deep: true })

watch(() => props.fitSignal, () => {
  hasFitted = false
  if (props.geojsonData && map) updateGeoJson(props.geojsonData)
})
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

.gcp-tooltip {
  background: rgba(15, 23, 42, 0.75);
  border: none;
  color: #fff;
  font-size: 9px;
  font-weight: 700;
  padding: 1px 5px;
  border-radius: 999px;
  box-shadow: none;
}
.gcp-tooltip::before { display: none; }
</style>
