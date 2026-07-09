# cv-lit - Monitorizacion de Linea de Costa

Sistema de monitorizacion automatica mediante camaras fijas (Obscape) en Guardamar del Segura.

## Interfaz Web (Dashboard & Calibracion)

El sistema cuenta con una interfaz moderna en Vue para monitorizar el estado y realizar calibraciones interactivas.

### Ejecucion (Entorno de Desarrollo)
Puedes iniciar tanto el backend (FastAPI) como el frontend (Vite) con un solo comando:
```bash
./scripts/start_dev.sh
```

Esto levantara:
- **Backend:** `http://localhost:8000`
- **Frontend:** `http://localhost:5173`

### Calibracion Interactiva
Desde la interfaz web, puedes seleccionar una camara, cargar su ultima imagen, marcar los puntos GCP con clicks y calcular la homografia instantaneamente.

## Inicio Rapido (Scripts de Python)

### 1. Diagnostico Inicial
Verifica la conexion con la API y el estado de las camaras:
```bash
python3 verify_setup.py
```

### 2. Descarga de Imagenes
El sistema descarga imagenes automaticamente evitando duplicados.
```bash
# Descarga estandar (ultimos 14 dias, 12:00h)
python3 acces_api/scheduled_download.py
```

### 3. Calibracion y Mantenimiento
Para calibrar una camara desde cero o realizar ajustes si se ha movido:
```bash
# Lanzador rapido para CAM 1
python3 visualizar_calibracion.py

# Ajuste rapido (arrastrar puntos) en una imagen nueva
python3 proces_images/recalibrate.py --cam 1 --image ruta/foto.jpg
```

### 4. Segmentacion y Extraccion (Mes 3)
Prueba el pipeline de extraccion de linea de costa:
```bash
# Ejecuta el flujo: ROI -> Segmentacion -> Linea de Costa
python3 proces_images/test_mes3_pipeline.py --cam 1
```

## Estado del Proyecto (Mes 3)
- [OK] **Hito 1 & 2**: Acceso API Obscape, Herramientas de Calibracion y ROI completados.
- [OK] **Hito 3**: Prototipo de segmentacion (SAM) y extraccion de linea de costa funcional.
- [BLOQUEO] **Bloqueo**: Pendiente de recibir GCPs reales del IEL para calibracion final de precision.

## Documentacion completa
Para mas detalles, consulta la carpeta `docs/`:
- [Guia de Comandos](docs/13_guia_comandos.md) - Lista completa de herramientas.
- [Mejoras del Sistema](docs/12_mejoras_sistema.md) - Detalles sobre las ultimas actualizaciones.
- [Estado del Proyecto](docs/09_estado.md) - Progreso de los hitos.
