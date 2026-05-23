#!/usr/bin/env bash
# ============================================================
# create_github_issues.sh — cv-lit (Guardamar del Segura)
# Crea labels, milestones e issues en nickhernd/cv-lit
# Uso: bash create_github_issues.sh
# ============================================================
set -euo pipefail

REPO="nickhernd/cv-lit"
BOLD='\033[1m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RESET='\033[0m'

log()  { echo -e "${BOLD}>>> $1${RESET}"; }
ok()   { echo -e "  ${GREEN}✓${RESET} $1"; }
warn() { echo -e "  ${YELLOW}!${RESET} $1"; }

# ------------------------------------------------------------------
# Helper: crea issue y opcionalmente lo cierra
# $1=título  $2=labels(coma)  $3=milestone  $4=body  $5=close|open
# ------------------------------------------------------------------
iss() {
  local title="$1" labels="$2" milestone="$3" body="${4:-}" state="${5:-open}"
  local url
  url=$(gh issue create \
    --repo  "$REPO" \
    --title "$title" \
    --label "$labels" \
    --milestone "$milestone" \
    --body  "$body" 2>&1 | tail -1)
  if [[ "$state" == "close" ]]; then
    local num; num=$(echo "$url" | grep -oP '/issues/\K[0-9]+')
    gh issue close "$num" --repo "$REPO" --comment "Completado antes del inicio del seguimiento." 2>/dev/null || true
  fi
  ok "$title"
}

# ==================================================================
log "1/4 — Creando etiquetas"
# ==================================================================
lbl() { gh label create "$1" --color "$2" --description "$3" --repo "$REPO" --force 2>/dev/null || true; }

lbl "mes-1"           "0075ca" "Mes 1: Preparación de datos y diseño"
lbl "mes-2"           "cfd3d7" "Mes 2: Calibración geométrica"
lbl "mes-3"           "e4e669" "Mes 3: Segmentación semántica (SAM)"
lbl "mes-4"           "0e8a16" "Mes 4: Extracción y georreferenciación"
lbl "mes-5"           "5319e7" "Mes 5: Validación y robustez"
lbl "mes-6"           "b60205" "Mes 6: Integración y entrega"
lbl "transversal"     "f9d0c4" "Tarea transversal (cualquier momento)"
lbl "bloqueado"       "ee0701" "Bloqueado por dependencia externa"
lbl "completado"      "006b75" "Tarea ya completada"
lbl "datos"           "bfd4f2" "Adquisición y gestión de datos"
lbl "calibración"     "c5def5" "Calibración geométrica / homografía"
lbl "segmentación"    "fef2c0" "Segmentación semántica / SAM"
lbl "validación"      "e99695" "Validación y control de calidad"
lbl "interfaz"        "fbca04" "Interfaz de usuario / despliegue"
lbl "infraestructura" "d4c5f9" "Entorno, CI, infraestructura"
lbl "coordinación"    "c2e0c6" "Coordinación externa (IEL, UA)"
ok "Labels creados"

# ==================================================================
log "2/4 — Creando milestones"
# ==================================================================
ms() {
  gh api "repos/$REPO/milestones" --method POST \
    -f title="$1" -f description="$2" \
    --jq '.number' 2>/dev/null || \
  gh api "repos/$REPO/milestones" --jq ".[] | select(.title==\"$1\") | .number"
}

MS1=$(ms "Mes 1 — Preparación de datos y diseño"   "Adquisición de imágenes, GNSS, ROI, entorno")
MS2=$(ms "Mes 2 — Calibración geométrica"           "Homografía por cámara, módulo calibración, criterios")
MS3=$(ms "Mes 3 — Segmentación semántica"           "SAM, preprocesado, post-procesado de máscaras")
MS4=$(ms "Mes 4 — Extracción y georreferenciación"  "Línea de costa, proyección H, GeoJSON")
MS5=$(ms "Mes 5 — Validación y robustez"            "Comparación GNSS, robustez, ajuste fino")
MS6=$(ms "Mes 6 — Integración y entrega"            "Interfaz, despliegue, entregables finales")
ok "Milestones creados: $MS1 $MS2 $MS3 $MS4 $MS5 $MS6"

# ==================================================================
log "3/4 — Creando issues"
# ==================================================================

# ------ MES 1 · Adquisición y organización de imágenes -----------
echo "  -- Mes 1: Adquisición de imágenes (completadas)"
iss "Verificar acceso a la API de Obscape (usuario fuster)" \
    "mes-1,datos,completado" "$MS1" \
    "Acceso verificado. Script \`obscape_api.py\` operativo." close

iss "Estructurar carpetas por cámara (CAM_X/fecha_hora_id.jpg)" \
    "mes-1,datos,completado" "$MS1" \
    "Estructura de carpetas por cámara con metadatos JSON junto a cada imagen." close

iss "Descargar histórico completo de las 6 cámaras" \
    "mes-1,datos,completado" "$MS1" \
    "Descarga de imágenes + metadatos JSON de CAM 1–6 desde Obscape API." close

echo "  -- Mes 1: Adquisición de imágenes (pendientes)"
iss "Hacer puntos de características y esquema del pipeline" \
    "mes-1,datos" "$MS1" \
    "## Subtareas
- [ ] Superponer las imágenes de cada cámara
- [ ] Calibrarlas para que los puntos coincidan (puntos de control visuales)
- [ ] Hacer esquema de ruta para visualizar el pipeline completo"

iss "Verificar cobertura temporal: huecos e imágenes inválidas" \
    "mes-1,datos" "$MS1" \
    "Identificar fechas sin imágenes y registros con \`invalid=1\` en los metadatos JSON por cámara."

iss "Script de inventario por cámara (fechas e imágenes disponibles)" \
    "mes-1,datos" "$MS1" \
    "Generar informe: número de imágenes por cámara, rango de fechas, estadísticas de huecos."

iss "Filtrar automáticamente imágenes nocturnas y de baja visibilidad" \
    "mes-1,datos" "$MS1" \
    "Clasificador ligero (umbral de brillo, histograma) que separe imágenes utilizables de las descartables."

iss "Organizar dataset de imágenes a las 12:00h (fase horaria prioritaria)" \
    "mes-1,datos" "$MS1" \
    "## Subtareas
- [ ] Filtrar imágenes con timestamp ~12:00 UTC
- [ ] Organizar carpetas por cámara con sus JSON de metadatos
- [ ] Verificar continuidad temporal del subconjunto"

# ------ MES 1 · Datos GNSS del IEL -------------------------------
echo "  -- Mes 1: Datos GNSS"
iss "[BLOQUEADO] Solicitar transectos GNSS al IEL (GCPs en EPSG:25830)" \
    "mes-1,coordinación,bloqueado,datos" "$MS1" \
    "> **Bloqueado:** depende de respuesta del Instituto de Ecología Litoral.
> Bloquea toda la calibración (Mes 2).

GCPs con GPS diferencial en sistema ETRS89 / UTM zona 30N (EPSG:25830)."

iss "Verificar formato de entrega de los GCPs del IEL" \
    "mes-1,coordinación,datos" "$MS1" \
    "Confirmar si los GCPs llegan en CSV, shapefile u otro formato. Preparar scripts de importación."

iss "Convertir/importar GCPs a EPSG:25830 si llegan en otro SRC" \
    "mes-1,datos,calibración" "$MS1" \
    "Usar \`pyproj\` o GDAL para reproyectar si el IEL entrega en ED50, WGS84 u otro sistema."

iss "Validar que los GCPs son visibles en las imágenes de cada cámara" \
    "mes-1,datos,calibración" "$MS1" \
    "Superposición visual: marcar GCPs en imágenes de referencia de cada CAM para confirmar visibilidad."

# ------ MES 1 · Definición de ROI --------------------------------
echo "  -- Mes 1: ROI"
iss "Definir ROI para cada una de las 6 cámaras" \
    "mes-1,datos" "$MS1" \
    "Delimitar la región de interés (píxeles) para CAM 1–6. Excluir cielo, infraestructura y mar profundo."

iss "Documentar ROI con coordenadas de píxel y justificación visual" \
    "mes-1,datos" "$MS1" \
    "Guardar en \`docs/\` con capturas anotadas. Formato: JSON con \`{cam_id, x_min, y_min, x_max, y_max}\`."

iss "Verificar que la ROI excluye cielo, infraestructura y mar profundo" \
    "mes-1,validación" "$MS1" \
    "Revisión visual sistemática con imágenes representativas (marea alta, baja, cielo despejado, nublado)."

# ------ MES 1 · Estructura y entorno -----------------------------
echo "  -- Mes 1: Estructura y entorno"
iss "Definir estructura de directorios definitiva para datos procesados" \
    "mes-1,infraestructura" "$MS1" \
    "Documentar en \`docs/06_setup.md\`. Incluir rutas para imágenes crudas, máscaras, GeoJSON, calibración."

iss "Crear entorno Conda reproducible (environment.yml)" \
    "mes-1,infraestructura" "$MS1" \
    "Fijar versiones: Python 3.11, PyTorch, OpenCV, GDAL, SAM/SAM2, pyproj, shapely, geopandas."

iss "Confirmar versiones: Python 3.11, PyTorch, OpenCV, GDAL, SAM" \
    "mes-1,infraestructura" "$MS1" \
    "Tabla de compatibilidad de versiones. Probar importación en entorno limpio."

iss "Configurar QGIS para validación visual en EPSG:25830" \
    "mes-1,infraestructura,validación" "$MS1" \
    "Proyecto QGIS base con capa de referencia de Guardamar del Segura en UTM 30N. Listo para cargar GeoJSON."

# ------ MES 1 · Especificación de interfaces ---------------------
echo "  -- Mes 1: Interfaces"
iss "Especificar interfaz de entrada: selección de imágenes y perfiles de calibración" \
    "mes-1,interfaz" "$MS1" \
    "Definir UX: selector de directorio, lista de cámaras disponibles, carga de perfiles \`.json\`/\`.yaml\`."

iss "Especificar interfaz de salida: segmentación + línea de costa + área" \
    "mes-1,interfaz" "$MS1" \
    "Wireframe de la pantalla de resultados: imagen segmentada, línea superpuesta, panel de métricas."

iss "Especificar botón de exportación GeoJSON desde la interfaz" \
    "mes-1,interfaz" "$MS1" \
    "Definir flujo: selección de rango temporal → exportar MultiLineString con atributos estándar."

# ------ MES 2 · Calibración por cámara --------------------------
echo "  -- Mes 2: Calibración por cámara"
for CAM in \
    "CAM 1 (id=8213, PTM61471)" \
    "CAM 2 (id=8214, PTM61474)" \
    "CAM 3 (id=8212, PTM61473)" \
    "CAM 4 (id=8211, PTM61475)" \
    "CAM 5 (id=8209, PTM61472)" \
    "CAM 6 (id=8210, PTM61470)"
do
  iss "Marcar correspondencias píxel–UTM: $CAM" \
      "mes-2,calibración" "$MS2" \
      "Seleccionar mínimo 8–12 GCPs visibles en la imagen. Guardar pares (u,v) ↔ (X,Y) UTM en EPSG:25830."
done

# ------ MES 2 · Módulo de calibración ---------------------------
echo "  -- Mes 2: Módulo de calibración"
iss "Módulo de corrección de distorsión de lente (parámetros intrínsecos, OpenCV)" \
    "mes-2,calibración" "$MS2" \
    "Usar \`cv2.calibrateCamera\` con tablero de ajedrez o puntos de control. Guardar \`K\`, \`dist\` por cámara."

iss "Estimación de homografía con RANSAC (cv2.findHomography)" \
    "mes-2,calibración" "$MS2" \
    "Pipeline: undistort → findHomography con RANSAC. Umbral inlier configurable. Guardar matriz H (3×3)."

iss "Validación de homografía con GCPs independientes (no usados en ajuste)" \
    "mes-2,calibración,validación" "$MS2" \
    "Separar GCPs en set de ajuste (≥8 puntos) y set de validación independiente (≥4 puntos)."

iss "Guardar perfil de calibración por cámara (H + parámetros + metadatos)" \
    "mes-2,calibración" "$MS2" \
    "Formato propuesto: YAML con campos \`cam_id\`, \`timestamp_calib\`, \`H\`, \`K\`, \`dist\`, \`rmse_px\`, \`rmse_m\`."

iss "Script de recalibración si la cámara se mueve o cambia la óptica" \
    "mes-2,calibración" "$MS2" \
    "Detectar cambio de posición (comparando GCPs reproyectados). Disparar recalibración automática o manual."

iss "Visualización de la reproyección: GCP real vs proyectado" \
    "mes-2,calibración,validación" "$MS2" \
    "Generar imagen con puntos GCP reales (verde) y proyectados (rojo) superpuestos. Guardar en \`docs/calib/\`."

iss "Criterio: error de reproyección < 2 px en GCPs de validación" \
    "mes-2,calibración,validación" "$MS2" \
    "Test de aceptación: si RMSE_px ≥ 2 en set independiente, recalibrar antes de continuar."

iss "Criterio: RMSE geométrico < 1.5 m en coordenadas UTM" \
    "mes-2,calibración,validación" "$MS2" \
    "Calcular RMSE en metros para los GCPs de validación proyectados a UTM. Documentar por cámara."

iss "Documentar precisión de calibración alcanzada por cámara" \
    "mes-2,calibración" "$MS2" \
    "Tabla resumen: \`cam_id | rmse_px | rmse_m | n_gcps_ajuste | n_gcps_val | fecha_calib\`."

# ------ MES 3 · Datos de entrenamiento ---------------------------
echo "  -- Mes 3: Datos de entrenamiento SAM"
iss "Seleccionar imágenes representativas por cámara (mínimo 20 por CAM)" \
    "mes-3,segmentación,datos" "$MS3" \
    "Criterios: distribución de mareas, condiciones lumínicas variadas, distintas estaciones. 20+ por cámara."

iss "Anotar manualmente arena seca / arena húmeda / agua en imágenes de referencia" \
    "mes-3,segmentación,datos" "$MS3" \
    "Usar herramienta de anotación (LabelMe, CVAT). Exportar máscaras PNG por clase."

iss "Cubrir condiciones variables en anotaciones: cielo despejado, nublado, amanecer, mareas" \
    "mes-3,segmentación,datos" "$MS3" \
    "Checklist por cámara: cielo despejado ✓, nublado ✓, amanecer/ocaso ✓, marea alta ✓, marea baja ✓."

# ------ MES 3 · Integración SAM ----------------------------------
echo "  -- Mes 3: Integración SAM"
iss "Instalar y configurar SAM (Meta, segment-anything)" \
    "mes-3,segmentación,infraestructura" "$MS3" \
    "Instalar \`segment-anything\`, descargar checkpoints ViT-H/L/B. Verificar inferencia en GPU/CPU."

iss "Integrar SAM con el pipeline de entrada de imágenes" \
    "mes-3,segmentación" "$MS3" \
    "Módulo \`sam_inference.py\`: recibe imagen + ROI, devuelve mapa de probabilidad por píxel."

iss "Ajustar prompts/seeds de SAM para focalizar en la zona de playa" \
    "mes-3,segmentación" "$MS3" \
    "Evaluar prompts de punto, caja y automático. Documentar cuál da mejor resultado por cámara."

iss "Generar mapa de probabilidad por píxel: arena seca / húmeda / agua" \
    "mes-3,segmentación" "$MS3" \
    "Salida: tensor float32 (H, W, 3) con probabilidades suavizadas por clase. Base para umbralizado adaptativo."

iss "Evaluar SAM base vs SAM2 y seleccionar mejor opción" \
    "mes-3,segmentación,validación" "$MS3" \
    "Métricas: IoU, F1, tiempo de inferencia. Probar ambos sobre el set de anotaciones de referencia."

# ------ MES 3 · Post-procesado -----------------------------------
echo "  -- Mes 3: Post-procesado"
iss "Implementar umbral adaptativo sobre el mapa de probabilidad de SAM" \
    "mes-3,segmentación" "$MS3" \
    "Otsu o umbral por percentil. Ajustable por cámara. Aplicar tras la inferencia SAM."

iss "Filtrado morfológico: eliminar regiones pequeñas y rellenar huecos" \
    "mes-3,segmentación" "$MS3" \
    "Operaciones: erosión + dilatación, \`remove_small_objects\`, \`binary_fill_holes\`. Parámetros por ROI."

iss "Eliminar falsas detecciones: espuma, reflejos y sombras" \
    "mes-3,segmentación" "$MS3" \
    "Post-filtros: análisis de textura, posición vertical en ROI, consistencia temporal."

iss "Generar máscara binaria estable: arena seca vs resto" \
    "mes-3,segmentación" "$MS3" \
    "Máscara final uint8 (0/255). Guardar junto a la imagen procesada en \`processed/masks/\`."

iss "Evaluar consistencia de segmentación entre frames consecutivos" \
    "mes-3,segmentación,validación" "$MS3" \
    "Comparar máscaras de horas consecutivas. Detectar saltos bruscos como anomalías."

# ------ MES 3 · Preprocesado de imagen ---------------------------
echo "  -- Mes 3: Preprocesado"
iss "Normalización de iluminación antes de segmentar" \
    "mes-3,segmentación" "$MS3" \
    "CLAHE o corrección por canal en LAB. Reducir variabilidad entre horas y condiciones climáticas."

iss "Corrección suave de contraste y balance de blancos" \
    "mes-3,segmentación" "$MS3" \
    "Parámetros por cámara almacenados en el perfil. No destructivo: se aplica en memoria antes de SAM."

iss "Recorte automático de ROI por cámara antes de segmentar" \
    "mes-3,segmentación" "$MS3" \
    "Leer ROI del perfil de cámara y recortar antes de pasar a SAM. Restaurar coordenadas después."

iss "Evaluar si la corrección de horizonte (horizon_correct.py) es necesaria en el pipeline" \
    "mes-3,segmentación" "$MS3" \
    "Probar imágenes con y sin corrección. Si el impacto en IoU es < 1%, descartar el módulo."

# ------ MES 4 · Extracción de línea ------------------------------
echo "  -- Mes 4: Extracción de línea"
iss "Calcular contornos sobre la máscara binaria" \
    "mes-4,segmentación" "$MS4" \
    "Usar \`cv2.findContours\` sobre la máscara de arena seca. Conservar solo contornos externos."

iss "Seleccionar borde principal: límite húmedo–seco más largo y continuo" \
    "mes-4,segmentación" "$MS4" \
    "Criterio: contorno más largo dentro del ROI con posición coherente (banda horizontal central)."

iss "Descartar bordes secundarios (longitud mínima, continuidad, posición relativa)" \
    "mes-4,segmentación" "$MS4" \
    "Filtros: longitud mínima configurable, distancia al borde ROI, posición vertical relativa."

iss "Suavizar la polilínea en píxeles antes de proyectar" \
    "mes-4,segmentación" "$MS4" \
    "Usar \`cv2.approxPolyDP\` + spline suavizado. Equilibrio entre fidelidad y ruido."

# ------ MES 4 · Proyección homografía ----------------------------
echo "  -- Mes 4: Proyección"
iss "Aplicar matriz H de cada cámara sobre la polilínea en píxeles" \
    "mes-4,calibración" "$MS4" \
    "Usar \`cv2.perspectiveTransform\` con la matriz H guardada en el perfil de calibración."

iss "Transformar vértices (u,v) → (X,Y) en metros EPSG:25830" \
    "mes-4,calibración" "$MS4" \
    "Verificar que las coordenadas resultantes caen dentro del dominio costero esperado (bbox Guardamar)."

iss "Manejar zonas de baja confianza en bordes del área visible de la cámara" \
    "mes-4,calibración,validación" "$MS4" \
    "Definir máscara de confianza espacial. Marcar vértices proyectados en zonas periféricas como \`low_conf\`."

# ------ MES 4 · GeoJSON ------------------------------------------
echo "  -- Mes 4: GeoJSON"
iss "Exportar línea de costa como GeoJSON (LineString / MultiLineString)" \
    "mes-4" "$MS4" \
    "Módulo \`geojson_export.py\`. Salida: \`.geojson\` con geometría y atributos estándar."

iss "Atributos obligatorios por feature: ID_Camara, Timestamp, Confianza_IA, Area_Seca_m2" \
    "mes-4" "$MS4" \
    '```json
{
  "ID_Camara": "CAM_1",
  "Timestamp": "2025-07-15T12:00:00Z",
  "Confianza_IA": 0.87,
  "Area_Seca_m2": 4320.5
}
```'

iss "Proyección de salida: EPSG:25830 (ETRS89 / UTM zone 30N)" \
    "mes-4" "$MS4" \
    "Usar \`pyproj\` o \`geopandas\` para asegurar CRS correcto. Validar con \`gpd.GeoDataFrame.crs\`."

iss "Calcular área seca (Area_Seca_m2) integrando la región delimitada por la línea" \
    "mes-4" "$MS4" \
    "Proyectar máscara binaria a UTM con resolución métrica. Contar píxeles × área de píxel."

iss "Calcular índice de confianza por imagen (probabilidad SAM media)" \
    "mes-4,validación" "$MS4" \
    "Confianza = media de probabilidad SAM en la región de la línea extraída. Rango [0,1]."

iss "Validar GeoJSON resultante en QGIS manualmente" \
    "mes-4,validación" "$MS4" \
    "Checklist: geometría válida, CRS correcto, atributos completos, posición coherente sobre ortofoto."

iss "Verificar unidades de Area_Seca_m2 (metros cuadrados, EPSG:25830)" \
    "mes-4,validación" "$MS4" \
    "Comparar área calculada con estimación visual para detectar errores de escala o unidades."

# ------ MES 5 · Validación cuantitativa -------------------------
echo "  -- Mes 5: Validación cuantitativa"
iss "Comparar líneas de costa generadas vs transectos GNSS del IEL" \
    "mes-5,validación" "$MS5" \
    "Calcular distancia perpendicular entre la línea extraída y los transectos de referencia GNSS."

iss "Calcular RMSE por cámara y global" \
    "mes-5,validación" "$MS5" \
    "RMSE en metros sobre el set de validación. Desglosar por cámara, condición lumínica y nivel de marea."

iss "Calcular Error Medio Absoluto (MAE) por cámara y global" \
    "mes-5,validación" "$MS5" \
    "MAE complementa el RMSE (menos sensible a outliers). Tabla comparativa por cámara."

iss "Objetivo: RMSE < 1.5 m en condiciones normales" \
    "mes-5,validación" "$MS5" \
    "Test de aceptación del sistema. Si no se alcanza, revisar calibración y/o post-procesado SAM."

iss "Documentar resultados de validación por cámara y condición de iluminación" \
    "mes-5,validación" "$MS5" \
    "Informe en \`docs/validacion.md\`: tablas RMSE/MAE, gráficas de dispersión, mapas de error."

# ------ MES 5 · Robustez ----------------------------------------
echo "  -- Mes 5: Robustez"
iss "Probar con imágenes nocturnas o de muy baja luz → rechazar o marcar" \
    "mes-5,validación" "$MS5" \
    "Definir umbral de brillo mínimo. Las imágenes bajo umbral se marcan \`low_quality=true\` y se descartan."

iss "Probar con presencia de personas en la playa" \
    "mes-5,validación" "$MS5" \
    "Evaluar impacto en la línea extraída. Si es significativo, añadir filtro de detección de personas."

iss "Probar con lluvia, niebla y spray marino" \
    "mes-5,validación" "$MS5" \
    "Evaluar degradación de la segmentación. Definir criterio de rechazo por visibilidad reducida."

iss "Probar con marea alta y baja (variación del dominio visible de arena)" \
    "mes-5,validación" "$MS5" \
    "Verificar que la línea se extrae correctamente en ambos extremos del ciclo mareal."

iss "Implementar filtros temporales: comparar con hora anterior, detectar anomalías" \
    "mes-5,validación" "$MS5" \
    "Si el área seca varía > X% respecto al frame anterior, marcar como posible anomalía para revisión."

iss "Definir criterio de rechazo automático de imagen (confianza < umbral)" \
    "mes-5,validación" "$MS5" \
    "Umbral de confianza por cámara. Imágenes rechazadas se registran en log con motivo."

iss "Ajustar umbrales de segmentación por cámara si es necesario" \
    "mes-5,segmentación,validación" "$MS5" \
    "Tras validación, revisar si alguna cámara necesita ajuste fino de umbral, ROI o parámetros SAM."

iss "Revisar casos donde SAM falla sistemáticamente y proponer alternativa" \
    "mes-5,segmentación" "$MS5" \
    "Identificar patrones de fallo (tipo de imagen, condición). Proponer: prompt alternativo, modelo diferente, regla heurística."

# ------ MES 6 · Interfaz ----------------------------------------
echo "  -- Mes 6: Interfaz"
iss "Implementar interfaz de entrada: selección de directorio de imágenes" \
    "mes-6,interfaz" "$MS6" \
    "UI: selector de carpeta, lista de imágenes disponibles con fecha/cámara, vista previa."

iss "Carga e inspección de perfiles de calibración por cámara" \
    "mes-6,interfaz" "$MS6" \
    "Panel lateral: mostrar perfil activo por cámara, RMSE, fecha de calibración. Botón para recargar."

iss "Visualización de la segmentación sobre la imagen original" \
    "mes-6,interfaz" "$MS6" \
    "Overlay semitransparente de la máscara SAM sobre la imagen. Modo toggle para comparar."

iss "Visualización de la línea de costa extraída superpuesta" \
    "mes-6,interfaz" "$MS6" \
    "Línea de costa en color llamativo sobre la imagen. Opción de ver en píxeles o proyectada."

iss "Panel de métricas: área seca (m²), confianza IA, timestamp" \
    "mes-6,interfaz" "$MS6" \
    "Sidebar con valores numéricos. Incluir indicador visual de confianza (semáforo verde/amarillo/rojo)."

iss "Botón de exportación a GeoJSON" \
    "mes-6,interfaz" "$MS6" \
    "Exportar línea(s) seleccionadas con todos los atributos. Nombre de archivo con timestamp automático."

# ------ MES 6 · Despliegue --------------------------------------
echo "  -- Mes 6: Despliegue"
iss "Instalar sistema en el servidor designado (configuración inicial)" \
    "mes-6,infraestructura" "$MS6" \
    "Clonar repo, instalar entorno Conda, configurar rutas de datos y modelos SAM."

iss "Configurar rutas de datos y cámaras en el servidor" \
    "mes-6,infraestructura" "$MS6" \
    "Archivo de configuración \`config.yaml\` con rutas absolutas, IDs de cámara y perfiles activos."

iss "Prueba de procesamiento end-to-end en el servidor" \
    "mes-6,infraestructura,validación" "$MS6" \
    "Ejecutar pipeline completo sobre muestra representativa. Verificar GeoJSON de salida en QGIS."

iss "Configurar ejecución automática para imágenes de las 12:00h" \
    "mes-6,infraestructura" "$MS6" \
    "Cron job o systemd timer diario. Trigger: llegada de imágenes ~12:00 UTC de las 6 cámaras."

# ------ MES 6 · Entregables -------------------------------------
echo "  -- Mes 6: Entregables"
iss "Aplicación ejecutable configurada y documentada" \
    "mes-6" "$MS6" \
    "README de despliegue, \`run.sh\`, \`config.yaml.example\`. Probado en entorno limpio."

iss "Perfiles de calibración por cámara (6 ficheros YAML)" \
    "mes-6,calibración" "$MS6" \
    "Entrega: \`calib/cam_1.yaml\` … \`calib/cam_6.yaml\` con H, K, dist, RMSE y metadatos."

iss "Manual breve de uso (usuario final)" \
    "mes-6" "$MS6" \
    "PDF de 4–6 páginas: arranque, carga de imágenes, interpretación de resultados, exportación."

iss "Informe inicial de validación con RMSE/MAE por cámara" \
    "mes-6,validación" "$MS6" \
    "Documento técnico: metodología, métricas por cámara, casos de fallo detectados, recomendaciones."

iss "Presentación de resultados al Ayuntamiento / IEL" \
    "mes-6,coordinación" "$MS6" \
    "Preparar slides: objetivos, metodología, demo en vivo, métricas de validación, próximos pasos."

# ------ TRANSVERSAL · API y adquisición -------------------------
echo "  -- Transversal: API"
iss "Script de descarga programada (cron diario 12:00h, todas las cámaras)" \
    "transversal,datos,infraestructura" "$MS1" \
    "Cron diario que llama a \`obscape_api.py\` para CAM 1–6. Registra OK/ERROR por cámara."

iss "Control de duplicados: no redescargar imágenes ya existentes" \
    "transversal,datos" "$MS1" \
    "Comparar ID de imagen con inventario local antes de descargar. Hash MD5 opcional para integridad."

iss "Manejo de errores de red y reintentos automáticos en descarga" \
    "transversal,infraestructura" "$MS1" \
    "Reintentar hasta 3 veces con backoff exponencial. Registrar fallos en log."

iss "Log de descargas con estado (OK / ERROR / inválida)" \
    "transversal,datos" "$MS1" \
    "CSV o SQLite: \`timestamp | cam_id | img_id | estado | motivo\`. Consultable para auditoría."

iss "Monitorización del estado de las cámaras (batería, señal, inclinación)" \
    "transversal,datos" "$MS1" \
    "Leer campos de metadatos Obscape: batería, RSSI, ángulo. Alertar si algún valor sale de rango."

# ------ TRANSVERSAL · Control de calidad -------------------------
echo "  -- Transversal: QC"
iss "Detector automático de imágenes oscuras (noche, obstrucción)" \
    "transversal,datos,validación" "$MS1" \
    "Umbral de brillo medio < X → marcar como descartable. Parámetro ajustable por cámara."

iss "Detector de imágenes borrosas o con artefactos" \
    "transversal,datos,validación" "$MS1" \
    "Varianza del Laplaciano < umbral → blur. Detección de píxeles saturados > 5% → artefacto."

iss "Marcar imágenes con invalid=1 en metadatos Obscape" \
    "transversal,datos" "$MS1" \
    "Decidir si usar flag de la API o metadatos locales. Coherencia con JSON descargado."

iss "Informe periódico de disponibilidad de datos por cámara" \
    "transversal,datos" "$MS1" \
    "Generado semanal/mensual: % imágenes válidas, huecos > 24h, tendencia de batería."

# ------ TRANSVERSAL · Infraestructura y código ------------------
echo "  -- Transversal: Infraestructura"
iss "Tests unitarios para módulos de calibración y proyección" \
    "transversal,infraestructura,calibración" "$MS2" \
    "pytest: calibración con GCPs sintéticos conocidos, proyección con homografía de identidad, etc."

iss "Tests de integración del pipeline completo sobre imágenes conocidas" \
    "transversal,infraestructura" "$MS4" \
    "Imagen de test con máscara ground-truth. El pipeline debe producir GeoJSON con RMSE < umbral."

iss "Control de versiones Git con ramas por módulo" \
    "transversal,infraestructura" "$MS1" \
    "Convención: \`feature/calibracion\`, \`feature/sam\`, \`feature/geojson\`. PRs con revisión."

iss "Estructura de directorios definitiva documentada en docs/06_setup.md" \
    "transversal,infraestructura" "$MS1" \
    "Árbol de directorios con descripción de cada carpeta. Actualizar tras cada sprint."

iss "environment.yml reproducible con todas las dependencias" \
    "transversal,infraestructura" "$MS1" \
    "Fijar versiones exactas. Probar \`conda env create -f environment.yml\` en máquina limpia."

# ------ TRANSVERSAL · Coordinación externa ----------------------
echo "  -- Transversal: Coordinación"
iss "[BLOQUEADO] Recibir GCPs GNSS del IEL (transectos con GPS diferencial)" \
    "transversal,coordinación,bloqueado" "$MS2" \
    "> **Bloqueado:** depende del Instituto de Ecología Litoral.
> Desbloquea: calibración (Mes 2) y validación cuantitativa (Mes 5)."

iss "Confirmar con IEL qué GCPs son para calibración y cuáles para validación independiente" \
    "transversal,coordinación" "$MS2" \
    "Separación obligatoria: los GCPs de validación NO deben usarse en el ajuste de homografía."

iss "Reunión de seguimiento mensual con supervisores de la Universidad de Alicante" \
    "transversal,coordinación" "$MS1" \
    "Orden del día tipo: avance del mes, bloqueos, decisiones pendientes, plan próximo mes."

iss "Confirmar servidor de despliegue y acceso remoto" \
    "transversal,infraestructura,coordinación" "$MS6" \
    "Confirmar IP/hostname, credenciales SSH, recursos (RAM/GPU/disco). Probar acceso antes del Mes 6."

# ==================================================================
log "4/4 — Creando proyecto GitHub"
# ==================================================================
PROJECT_URL=$(gh project create \
  --owner nickhernd \
  --title "cv-lit — Detección de línea de costa" \
  --format json 2>/dev/null | jq -r '.url' || echo "")

if [[ -n "$PROJECT_URL" ]]; then
  ok "Proyecto creado: $PROJECT_URL"
  warn "Vincula las issues al proyecto manualmente desde GitHub Projects o con 'gh project item-add'."
else
  warn "No se pudo crear el proyecto automáticamente. Créalo manualmente en github.com/nickhernd."
fi

echo ""
echo -e "${BOLD}============================================================${RESET}"
echo -e "${GREEN}  Listo. Issues, labels y milestones creados en:${RESET}"
echo -e "  https://github.com/$REPO/issues"
echo -e "${BOLD}============================================================${RESET}"
