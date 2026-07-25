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

<!-- TODO (opcional): captura de pantalla del Dashboard o de la Calibracion aqui -->

## Aplicacion de escritorio (Windows)

Ademas de usarse como web (backend + frontend por separado), el sistema se puede empaquetar como una app de Windows normal: un `.exe` con icono, ventana propia y acceso directo, sin terminal ni navegador de por medio.

<!-- TODO (opcional): captura de pantalla de la ventana de la app o del asistente de instalacion aqui -->

### Como esta hecho
- **`backend/desktop_launcher.py`**: arranca el backend (FastAPI/uvicorn) en segundo plano y abre una ventana nativa ([pywebview](https://pywebview.flowrl.com/)) apuntando a el. El backend sirve el frontend ya compilado desde el mismo proceso (`app.mount(...)` en `backend/main.py`), asi que todo va en una sola app, un solo puerto (8000).
- **PyInstaller** (`backend/desktop_launcher.spec`) empaqueta ese lanzador junto con Python, PyTorch, OpenCV y el frontend compilado en una carpeta autocontenida — no hace falta tener Python instalado en el ordenador de destino.
- El modelo de segmentacion por IA (**SAM**, checkpoint `sam_vit_h_4b8939.pth`, ~2.4 GB) se queda **fuera** del paquete a proposito: el sistema funciona sin el (cae a un metodo de segmentacion por color/Otsu, ver `get_segmenter()` en `backend/main.py`). Se descarga aparte con `backend/download_sam.py` / `download_sam.exe`, opcionalmente, para no obligar a nadie a bajarse 2.4 GB si no los necesita.
- **Inno Setup** (`installer/cv-lit.iss`) genera el instalador final: crea accesos directos, y en la pantalla de tareas deja marcar (desmarcado por defecto) si se quiere descargar el modelo SAM justo despues de instalar.
- Los datos del usuario (calibracion, imagenes, logs) se guardan en `%LOCALAPPDATA%\LineaDeCosta\`, nunca dentro de la carpeta de instalacion — asi funciona aunque se instale en Program Files, sin permisos de administrador.

### Construir el instalador
Requisitos: Node.js, el `venv` de Python con `backend/requirements.txt` instalado (incluye `pyinstaller` y `pywebview`), e [Inno Setup](https://jrsoftware.org/isinfo.php) (gratuito).

```bash
# 1. Compilar el frontend
cd frontend && npm run build && cd ..

# 2. Congelar el backend + lanzador de escritorio
cd backend
pyinstaller desktop_launcher.spec
pyinstaller download_sam.spec
cd ..

# 3. Compilar el instalador (genera installer/output/LineaDeCosta-Setup.exe)
"C:\Program Files\Inno Setup 7\ISCC.exe" installer\cv-lit.iss
```

El instalador resultante pesa ~185 MB. Si en algun momento quieres migrar una calibracion real ya hecha (la de `calibration/` y `proces_images/data/` de este repo) a una instalacion empaquetada, basta con copiar esas carpetas dentro de `%LOCALAPPDATA%\LineaDeCosta\calibration\` y `...\data\` tras instalar.

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
