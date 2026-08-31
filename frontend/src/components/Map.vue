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
// idx (properties.idx del GeoJSON) -> capa Leaflet, para resaltar/seleccionar
// puntos sin tener que reconstruir toda la capa (p.ej. varillas GCP)
const markerLayersByIdx = {}

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
  },
  // idx del punto actualmente seleccionado (p.ej. varilla GCP elegida en la
  // lista o en la foto) — se resalta con un anillo y se agranda en el mapa
  selectedIndex: {
    type: Number,
    default: null
  }
})

const emit = defineEmits(['select-feature', 'select-camera'])

const layers = {
  // OpenStreetMap estándar: sin API key ni cuenta de terceros — CARTO empezó a
  // exigir una API key para su capa "light_all" gratuita (antes anónima), lo
  // que tumbaba este mapa en cualquier instalación sin esa clave configurada.
  vector: L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    maxZoom: 19,
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

  // El enlace "Ir a la cámara" vive dentro del HTML del popup de Leaflet
  // (fuera del árbol de Vue, reinsertado cada vez que se abre un popup) —
  // engancharlo a mano en cada popupopen no es fiable (el evento no siempre
  // llega a tiempo). Delegar el click una única vez sobre el contenedor del
  // mapa evita depender de ese timing — pero Leaflet para la propagación de
  // los clics dentro del popup (para no disparar el pan/zoom del mapa que
  // hay debajo), así que un listener normal (fase de burbuja) en el
  // contenedor nunca lo recibe. En fase de CAPTURA sí, porque se ejecuta de
  // fuera hacia dentro, antes de que Leaflet llegue a detener la propagación.
  mapContainer.value.addEventListener('click', (e) => {
    const link = e.target.closest('.map-goto-camera')
    if (!link) return
    e.preventDefault()
    emit('select-camera', Number(link.dataset.cam))
  }, true)

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
  Object.keys(markerLayersByIdx).forEach(k => delete markerLayersByIdx[k])
  const projected = reprojectGeoJson(data)
  if (!projected?.features?.length) return
  geoJsonLayer = L.geoJSON(projected, {
    // Cada feature puede traer su propio estilo en properties._style
    // (lo usa el modo de evolución temporal para atenuar las líneas antiguas).
    // El polígono de área seca (mismo análisis que la línea, geometría
    // distinta) se distingue con relleno translúcido en vez de un trazo
    // sólido, para no confundirlo visualmente con la línea de costa.
    style: f => {
      const isPolygon = f?.geometry?.type === 'Polygon'
      const color = f?.properties?._style?.color ?? (isPolygon ? '#c98f3e' : '#2563eb')
      return {
        color,
        weight: f?.properties?._style?.weight ?? (isPolygon ? 1.5 : 3),
        opacity: f?.properties?._style?.opacity ?? (isPolygon ? 0.6 : 0.8),
        fill: isPolygon,
        fillColor: color,
        fillOpacity: isPolygon ? 0.2 : 0,
      }
    },
    // Puntos (p.ej. varillas GCP) como círculos propios en vez del icono por
    // defecto de Leaflet, que no resuelve sus imágenes con el bundler.
    // Color por defecto: ámbar — es el color real de las varillas en campo
    // (naranja flúor), no un azul genérico.
    pointToLayer: (feature, latlng) => L.circleMarker(latlng, {
      radius: 7,
      weight: 2,
      color: '#fff',
      fillColor: feature?.properties?._style?.color ?? '#c98f3e',
      fillOpacity: 0.9,
    }),
    onEachFeature: (feature, layer) => {
      const p = feature.properties || {}
      if (p.ID_Camara != null) {
        layer.bindPopup(
          `<b>Cámara ${p.ID_Camara}</b><br>` +
          (p.Timestamp ? `${String(p.Timestamp).replace('T', ' ').slice(0, 16)}<br>` : '') +
          (p.Area_Seca_m2 != null ? `Área seca: ${p.Area_Seca_m2} m²<br>` : '') +
          (p.Confianza_IA != null ? `Confianza: ${(p.Confianza_IA * 100).toFixed(0)}%<br>` : '') +
          `<a href="#" class="map-goto-camera" data-cam="${p.ID_Camara}">Ir a la cámara →</a>`
        )
      } else if (p.label != null) {
        layer.bindPopup(`<b>${p.label}</b>`)
        if (p.idx != null) {
          layer.bindTooltip(String(p.idx + 1), { permanent: true, direction: 'top', offset: [0, -8], className: 'gcp-tooltip' })
          markerLayersByIdx[p.idx] = layer
          // Seleccionar la varilla desde el mapa, igual que se hace desde la
          // lista o clicando sobre la foto — la selección queda sincronizada
          // entre las tres vistas.
          layer.on('click', () => emit('select-feature', p.idx))
        }
      }
    }
  }).addTo(map)

  applySelectionStyle()

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

// Resalta en el mapa la varilla actualmente seleccionada (agrandada + anillo
// azul) sin reconstruir la capa entera, para no perder zoom/encuadre.
function applySelectionStyle() {
  Object.entries(markerLayersByIdx).forEach(([idx, layer]) => {
    const isSelected = Number(idx) === props.selectedIndex
    layer.setRadius(isSelected ? 11 : 7)
    layer.setStyle({
      color: isSelected ? '#2f6690' : '#fff',
      weight: isSelected ? 3 : 2,
    })
    if (isSelected) layer.bringToFront()
  })
}

watch(() => props.selectedIndex, applySelectionStyle)

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
    <div ref="mapContainer" class="w-full h-full bg-slate-100 rounded-md border border-slate-200"></div>
    
    <!-- Simple Layer Switcher -->
    <div class="absolute top-4 right-4 z-[400] flex bg-white border border-slate-300 rounded overflow-hidden">
       <button @click="switchLayer('vector')" 
               :class="currentLayer === 'vector' ? 'bg-slate-800 text-white' : 'text-slate-600 hover:bg-slate-50'"
               class="px-3 py-1.5 text-[10px] font-semibold uppercase border-r border-slate-300 transition-colors">Vector</button>
       <button @click="switchLayer('satellite')" 
               :class="currentLayer === 'satellite' ? 'bg-slate-800 text-white' : 'text-slate-600 hover:bg-slate-50'"
               class="px-3 py-1.5 text-[10px] font-semibold uppercase transition-colors">Satélite</button>
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

.map-goto-camera {
  display: inline-block;
  margin-top: 4px;
  color: #2f6690;
  font-weight: 600;
  font-size: 11px;
  text-decoration: none;
}
.map-goto-camera:hover { text-decoration: underline; }
</style>
