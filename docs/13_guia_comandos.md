# Guía de Comandos Importantes

Este documento contiene los comandos principales para operar el sistema de monitorización de línea de costa.

---

## 1. Adquisición de Datos (API Obscape)

### Descarga Programada (Recomendado)
Descarga las imágenes de los últimos 14 días (ventana de seguridad) evitando duplicados.
```bash
python3 acces_api/scheduled_download.py
```
*   `--days N`: Cambiar el número de días a revisar.
*   `--hour H`: Cambiar la hora de descarga (por defecto 12h). Use `all` para todas las horas.

**Ejemplo: Descarga masiva (Últimos 30 días, todas las horas):**
```bash
python3 acces_api/scheduled_download.py --days 30 --hour all
```

### Descarga Manual / Listado
Acceso directo al cliente de la API.
```bash
# Listar cámaras disponibles
python3 acces_api/obscape_api.py

# Descargar última imagen de una cámara específica
python3 acces_api/obscape_api.py --station 8213 --download
```

---

## 2. Calibración Geométrica

### Lanzador Visual Rápido
Abre automáticamente la herramienta con la imagen más reciente de la CAM 1.
```bash
python3 visualizar_calibracion.py
```

### Herramienta de Calibración Completa
```bash
python3 proces_images/calibration_tool.py --cam [1-6] --image [RUTA_FOTO]
```
**Controles internos:**
*   `L-Click`: Punto de Calibración (Verde).
*   `R-Click`: Punto de Validación (Azul).
*   `h`: Calcular Homografía.
*   `s`: Guardar perfil en `calibration/`.
*   `p`: Generar imagen de diagnóstico de errores.

### Recalibración (Ajuste rápido)
Para cuando la cámara se ha movido levemente. Permite arrastrar los puntos.
```bash
python3 proces_images/recalibrate.py --cam [1-6] --image [RUTA_FOTO_NUEVA]
```

---

## 3. Mantenimiento y Automatización

### Configuración de Tarea Diaria (Cron)
Para ver o editar las tareas automáticas:
```bash
crontab -e
```
**Línea a añadir para descarga diaria a las 13:00h:**
```text
0 13 * * * cd /home/nickhernd/Desktop/cv-lit/ && /usr/bin/python3 acces_api/scheduled_download.py >> /home/nickhernd/Desktop/cv-lit/data/logs/cron_log.txt 2>&1
```

### Verificación del Motor Matemático
Verifica que los cálculos de homografía y RMSE sean correctos.
```bash
python3 proces_images/test_calibration_logic.py
```
