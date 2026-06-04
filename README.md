# cv-lit — Monitorización de Línea de Costa

Sistema de monitorización automática mediante cámaras fijas (Obscape) en Guardamar del Segura.

## Inicio Rápido

### 1. Instalación
Asegúrate de tener las dependencias instaladas:
```bash
pip install opencv-python numpy requests pyproj
```

### 2. Descarga de Imágenes
El sistema descarga imágenes automáticamente evitando duplicados.
```bash
# Descarga estándar (últimos 14 días, 12:00h)
python3 acces_api/scheduled_download.py

# Descarga masiva (últimos 30 días, todas las horas)
python3 acces_api/scheduled_download.py --days 30 --hour all
```

### 3. Calibración y Mantenimiento
Para calibrar una cámara desde cero o realizar ajustes si se ha movido:
```bash
# Lanzador rápido para CAM 1
python3 visualizar_calibracion.py

# Ajuste rápido (arrastrar puntos) en una imagen nueva
python3 proces_images/recalibrate.py --cam 1 --image ruta/foto.jpg
```

## Estado del Proyecto (Mes 2)
- ✅ **Calibración técnica**: Motor de homografía, RANSAC y corrección de distorsión completados.
- ✅ **Automatización**: Sistema de descarga con control de duplicados y ventana de 14 días operativo.
- 🔴 **Bloqueo**: Pendiente de recibir GCPs reales del IEL para calibración definitiva.

## Documentación completa
Para más detalles, consulta la carpeta `docs/`:
- [Guía de Comandos](docs/13_guia_comandos.md) — Lista completa de herramientas.
- [Mejoras del Sistema](docs/12_mejoras_sistema.md) — Detalles sobre las últimas actualizaciones.
- [Estado del Proyecto](docs/09_estado.md) — Progreso de los hitos.
