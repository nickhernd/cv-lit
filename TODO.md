# TODO — cv-lit (Detección de línea de costa, Guardamar del Segura)

> Leyenda: `[ ]` pendiente · `[~]` en progreso · `[x]` completado · `[!]` bloqueado por dependencia externa

---

## MES 1 — Preparación de datos y diseño

### Adquisición y organización de imágenes
- [x] Acceso a la API de Obscape verificado (usuario `fuster`)
- [x] Script de descarga `obscape_api.py` operativo
- [x] Estructura de carpetas por cámara (`CAM_X/fecha_hora_id.jpg`)
- [x] Descarga de metadatos JSON junto a cada imagen
- [ ] Descargar histórico completo disponible de las 6 cámaras
- [ ] Verificar cobertura temporal: identificar huecos o imágenes inválidas (`invalid=1`)
- [ ] Script de inventario: listar por cámara cuántas imágenes hay y en qué fechas
- [ ] Filtrar y separar imágenes nocturnas / de baja visibilidad automáticamente
- [ ] Organizar dataset de imágenes a las 12:00h (fase horaria prioritaria)

### Datos GNSS del IEL
- [!] Solicitar transectos GNSS al IEL (GCPs en EPSG:25830) — **bloquea calibración**
- [ ] Verificar formato de entrega de los GCPs (CSV, shapefile, etc.)
- [ ] Convertir/importar GCPs a EPSG:25830 si llegan en otro sistema
- [ ] Validar que los GCPs son visibles en las imágenes de cada cámara

### Definición de ROI
- [ ] Definir ROI (región de interés) para cada una de las 6 cámaras
- [ ] Documentar ROI con coordenadas de píxel y justificación visual
- [ ] Verificar que la ROI excluye cielo, infraestructura y mar profundo

### Estructura del proyecto
- [x] Documentación base creada (`docs/`)
- [x] `important_data.json` con metadatos de cámaras y boyas
- [ ] Definir estructura de directorios definitiva para datos procesados
- [ ] Crear entorno Conda reproducible (`environment.yml`)
- [ ] Confirmar versiones: Python 3.11, PyTorch, OpenCV, GDAL, SAM
- [ ] Configurar QGIS para validación visual de resultados en EPSG:25830

### Especificación de interfaces
- [ ] Especificar interfaz de entrada: selección de imágenes + carga de perfiles de calibración
- [ ] Especificar interfaz de salida: visualización segmentación + línea de costa + área
- [ ] Especificar botón de exportación GeoJSON desde la interfaz

---

## MES 2 — Calibración geométrica (homografía)

### Por cada cámara (×6: CAM 1–6)
- [ ] **CAM 1** (id=8213, PTM61471) — marcar correspondencias píxel–UTM
- [ ] **CAM 2** (id=8214, PTM61474) — marcar correspondencias píxel–UTM
- [ ] **CAM 3** (id=8212, PTM61473) — marcar correspondencias píxel–UTM
- [ ] **CAM 4** (id=8211, PTM61475) — marcar correspondencias píxel–UTM
- [ ] **CAM 5** (id=8209, PTM61472) — marcar correspondencias píxel–UTM
- [ ] **CAM 6** (id=8210, PTM61470) — marcar correspondencias píxel–UTM

### Implementación módulo calibración
- [ ] Módulo de corrección de distorsión de lente (parámetros intrínsecos, OpenCV)
- [ ] Estimación de homografía con RANSAC (OpenCV `findHomography`)
- [ ] Validación de homografía con GCPs independientes (no usados en ajuste)
- [ ] Guardar perfil de calibración por cámara (matriz H + params + metadatos)
- [ ] Formato del perfil: JSON o YAML con versionado
- [ ] Script de recalibración si la cámara se mueve o cambia la óptica
- [ ] Visualización de la reproyección: superposición GCP real vs proyectado

### Criterios de aceptación (calibración)
- [ ] Error de reproyección < 2 píxeles en GCPs de validación
- [ ] RMSE geométrico < 1.5 m en coordenadas UTM
- [ ] Documentar precisión alcanzada por cámara

---

## MES 3 — Segmentación semántica (SAM)

### Preparación de datos de entrenamiento/ajuste
- [ ] Seleccionar conjunto de imágenes representativas por cámara (mínimo 20 por CAM)
- [ ] Anotar manualmente arena seca / arena húmeda / agua en imágenes de referencia
- [ ] Cubrir condiciones variables: cielo despejado, nublado, amanecer, marea alta/baja

### Integración de SAM
- [ ] Instalar y configurar SAM (Meta, `segment-anything`)
- [ ] Integrar SAM con pipeline de entrada de imágenes
- [ ] Ajustar prompts o seeds para focalizar la segmentación en la zona de playa
- [ ] Generar mapa de probabilidad por píxel: arena seca / húmeda / agua
- [ ] Probar modelo base SAM vs SAM2 — evaluar cuál se adapta mejor

### Post-procesado de segmentación
- [ ] Implementar umbral adaptativo sobre el mapa de probabilidad
- [ ] Filtrado morfológico: eliminar regiones pequeñas, rellenar huecos
- [ ] Eliminar falsas detecciones: espuma, reflejos, sombras
- [ ] Generar máscara binaria estable arena seca / resto
- [ ] Evaluar consistencia entre frames consecutivos de la misma cámara

### Preprocesado de imagen (módulo 3.1)
- [ ] Normalización de iluminación (evitar variabilidad entre horas/días)
- [ ] Corrección suave de contraste y balance de blancos
- [ ] Recorte automático de ROI por cámara antes de segmentar
- [ ] Evaluar si la corrección de horizonte (`horizon_correct.py`) es necesaria en pipeline

---

## MES 4 — Extracción de línea y georreferenciación

### Extracción de línea (módulo 3.3)
- [ ] Calcular contornos sobre la máscara binaria
- [ ] Seleccionar el borde principal: límite continuo húmedo–seco más largo
- [ ] Descartar bordes secundarios (longitud mínima, continuidad, posición relativa)
- [ ] Suavizar la polilínea en píxeles antes de proyectar

### Proyección homografía (módulo 3.4)
- [ ] Aplicar matriz H de cada cámara sobre la polilínea en píxeles
- [ ] Transformar vértices (u,v) → (X,Y) en metros EPSG:25830
- [ ] Manejar zonas de baja confianza (bordes del área visible de la cámara)

### Generación de GeoJSON (módulo 3.5)
- [ ] Exportar línea de costa como GeoJSON (geometría LineString o MultiLineString)
- [ ] Atributos obligatorios por feature: `ID_Camara`, `Timestamp`, `Confianza_IA`, `Area_Seca_m2`
- [ ] Proyección de salida: EPSG:25830 (ETRS89 / UTM zone 30N)
- [ ] Calcular área seca integrando la región delimitada por la línea dentro del dominio visible
- [ ] Calcular índice de confianza por imagen (basado en probabilidad SAM media)
- [ ] Validar GeoJSON resultante en QGIS manualmente

### Cálculo de área
- [ ] Implementar cálculo de `Area_Seca_m2` a partir de la máscara proyectada
- [ ] Verificar unidades (metros cuadrados, EPSG:25830)

---

## MES 5 — Validación y robustez

### Validación cuantitativa
- [ ] Comparar líneas de costa generadas vs transectos GNSS independientes del IEL
- [ ] Calcular RMSE por cámara y global
- [ ] Calcular Error Medio Absoluto (MAE) por cámara y global
- [ ] Objetivo: RMSE < 1.5 m en condiciones normales
- [ ] Documentar resultados por cámara y condición de iluminación

### Robustez del sistema
- [ ] Probar con imágenes nocturnas o de muy baja luz → debe rechazarlas o marcarlas
- [ ] Probar con presencia de personas en la playa
- [ ] Probar con lluvia, niebla o spray marino
- [ ] Probar con marea alta y baja (variación del dominio visible de arena)
- [ ] Implementar filtros temporales: comparar con hora anterior, detectar anomalías
- [ ] Definir criterio de rechazo automático de imagen (confianza < umbral)

### Ajustes finales de segmentación
- [ ] Ajustar umbrales por cámara si es necesario
- [ ] Revisar casos donde SAM falla sistemáticamente y proponer alternativa

---

## MES 6 — Integración y entrega

### Interfaz de usuario
- [ ] Implementar interfaz de entrada: selección de directorio de imágenes
- [ ] Carga e inspección de perfiles de calibración por cámara
- [ ] Visualización de la segmentación sobre la imagen original
- [ ] Visualización de la línea de costa extraída superpuesta
- [ ] Panel con métricas: área seca (m²), confianza IA, timestamp
- [ ] Botón de exportación a GeoJSON

### Despliegue
- [ ] Instalar sistema en el servidor designado (configuración inicial)
- [ ] Configurar rutas de datos y cámaras en el servidor
- [ ] Prueba de procesamiento end-to-end en el servidor
- [ ] Configurar ejecución automática para imágenes de las 12:00h

### Entregables
- [ ] Aplicación ejecutable configurada y documentada
- [ ] Perfiles de calibración por cámara (6 ficheros)
- [ ] Manual breve de uso (usuario final)
- [ ] Informe inicial de validación con RMSE/MAE por cámara
- [ ] Presentación de resultados al Ayuntamiento / IEL

---

## TRANSVERSAL — En cualquier momento

### API y adquisición de datos
- [ ] Script de descarga programada (cron diario a las 12:00h para todas las cámaras)
- [ ] Control de duplicados: no redescargar imágenes ya existentes
- [ ] Manejo de errores de red y reintentos automáticos
- [ ] Log de descargas con estado (OK / ERROR / inválida)
- [ ] Monitorización del estado de las cámaras (batería, señal, inclinación)

### Control de calidad de imágenes
- [ ] Detector automático de imágenes oscuras (noche, obstrucción)
- [ ] Detector de imágenes borrosas o con artefactos
- [ ] Marcar imágenes con `invalid=1` en los metadatos Obscape
- [ ] Informe periódico de disponibilidad de datos por cámara

### Infraestructura y código
- [ ] Tests unitarios para módulos de calibración y proyección
- [ ] Tests de integración del pipeline completo sobre imágenes conocidas
- [ ] Control de versiones Git con ramas por módulo
- [ ] Estructura de directorios definitiva documentada en `docs/06_setup.md`
- [ ] `environment.yml` reproducible con todas las dependencias

### Coordinación externa
- [!] Recibir GCPs GNSS del IEL (transectos con GPS diferencial)
- [ ] Confirmar con IEL qué GCPs se usan para calibración y cuáles para validación independiente
- [ ] Reunión de seguimiento mensual con supervisores de la Universidad de Alicante
- [ ] Confirmar servidor de despliegue y acceso remoto
