import os
import shutil
import sys

from fastapi import HTTPException

# DEBUG (INIT): config.py se importa al arrancar main.py y batch_alignment.py.
# Calcula las rutas base del proyecto a partir de la ubicación de este archivo
# (backend/config.py -> sube dos niveles -> raíz del proyecto). Solo aplica
# fuera de la app empaquetada: congelada, "la ubicación de este archivo" no es
# una ruta real en disco (vive dentro del bundle de PyInstaller).
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROCES_IMAGES_DIR = os.path.join(BASE_DIR, "proces_images")

# Los directorios de trabajo se pueden redirigir por variables de entorno para
# aislar entornos (start_dev.ps1 -> workspace vacío, start_demo.ps1 -> workspace
# demo sembrado). Sin variables se usan los directorios reales de siempre —
# EXCEPTO en la app empaquetada, donde el valor por defecto no puede ser
# "junto al ejecutable": si se instaló en Program Files, un usuario normal no
# tiene permiso de escritura ahí. Ahí los datos van a la carpeta de perfil del
# usuario (%LOCALAPPDATA%), como cualquier app de escritorio de Windows.
if getattr(sys, "frozen", False):
    _APPDATA = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    _DEFAULT_DATA_DIR = os.path.join(_APPDATA, "LineaDeCosta", "data")
    _DEFAULT_CALIBRATION_DIR = os.path.join(_APPDATA, "LineaDeCosta", "calibration")
else:
    _DEFAULT_DATA_DIR = os.path.join(PROCES_IMAGES_DIR, "data")
    _DEFAULT_CALIBRATION_DIR = os.path.join(BASE_DIR, "calibration")

DATA_DIR = os.environ.get("CVLIT_DATA_DIR") or _DEFAULT_DATA_DIR
CALIBRATION_DIR = os.environ.get("CVLIT_CALIBRATION_DIR") or _DEFAULT_CALIBRATION_DIR
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(CALIBRATION_DIR, exist_ok=True)

# Sembrar configuración de referencia (ROI y máscaras de zonas estables) en
# una instalación nueva: son valores FIJOS del despliegue real de las 6
# cámaras de Guardamar del Segura (encuadre físico de cada cámara), no algo
# que cada usuario deba crear desde cero al abrir la app por primera vez.
# Bug real detectado 2026-08-31: sin esto, un CALIBRATION_DIR nuevo (p.ej.
# %LOCALAPPDATA% recién creado) nunca tiene roi_config.json — SAM coloca sus
# puntos de referencia sobre la imagen sin recortar, y TODAS las imágenes de
# esa cámara salen con confianza baja, sin ningún error visible que lo delate.
# Solo copia si el archivo aún no existe — nunca pisa un roi_config.json que
# el usuario ya haya editado desde la interfaz (paso "Cámaras").
if getattr(sys, "frozen", False):
    _SEED_DIR = os.path.join(sys._MEIPASS, "calibration_seed")
    for _seed_name in ("roi_config.json", "alignment_masks.json"):
        _dst = os.path.join(CALIBRATION_DIR, _seed_name)
        _src = os.path.join(_SEED_DIR, _seed_name)
        if not os.path.exists(_dst) and os.path.exists(_src):
            try:
                shutil.copy2(_src, _dst)
            except OSError:
                pass

# DEBUG (INIT): diccionario global de cámaras (id -> nombre, carpeta, imagen por defecto).
# Es la fuente de verdad que usan casi todos los endpoints de main.py y batch_alignment.py
# para resolver rutas de imágenes y perfiles de calibración por cámara.
CAMERAS = {
    1: {"name": "CAM 1 (Norte)", "id": "8213", "serial": "PTM61471",
        "folder": "camera1", "file": "1779787800_20260526_093000_PTM61471.jpg"},
    2: {"name": "CAM 2 (Norte Centro)", "id": "8214", "serial": "PTM61474",
        "folder": "camera2", "file": "1778580900_20260512_101500_PTM61474.jpg"},
    3: {"name": "CAM 3 (Centro)", "id": "8212", "serial": "PTM61473",
        "folder": "camera3", "file": "1777896000_20260504_120000_PTM61473.jpg"},
    4: {"name": "CAM 4 (Centro Sur)", "id": "8211", "serial": "PTM61475",
        "folder": "camera4", "file": "1777896000_20260504_120000_PTM61475.jpg"},
    5: {"name": "CAM 5 (Sur)", "id": "8209", "serial": "PTM61472",
        "folder": "camera5", "file": "1777893600_20260504_112000_PTM61472.jpg"},
    6: {"name": "CAM 6 (Sur Punta)", "id": "8210", "serial": "PTM61470",
        "folder": "camera6", "file": "1777891200_20260504_104000_PTM61470.jpg"},
}


def _safe_filename(filename):
    """Reduce cualquier nombre de archivo recibido del cliente a un nombre
    "plano" sin componentes de directorio (os.path.basename), para que un
    '../../../etc/passwd' o una ruta absoluta no puedan escapar de la carpeta
    de datos de la cámara. Se usa en TODO endpoint (de main.py o
    batch_alignment.py) que recibe un filename del cliente y lo mete en un
    os.path.join/Path (lectura, borrado o escritura) — compartido aquí para
    que ambos módulos apliquen exactamente la misma sanitización."""
    name = os.path.basename((filename or "").strip().replace("\\", "/"))
    if not name or name in (".", ".."):
        raise HTTPException(status_code=400, detail="Nombre de archivo inválido")
    return name
