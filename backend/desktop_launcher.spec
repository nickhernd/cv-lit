# -*- mode: python ; coding: utf-8 -*-
# Construye la app de escritorio (ver docs/desktop-app.md): un onedir con
# desktop_launcher.py como punto de entrada, el frontend ya compilado
# (`npm run build`) empaquetado como datos, y el checkpoint de SAM
# deliberadamente EXCLUIDO (se descarga aparte, ver download_sam.py — así el
# instalador no arrastra los 2.4 GB del modelo para quien no lo quiera).
#
# Onedir (no onefile) a propósito: con dependencias tan pesadas (PyTorch,
# OpenCV) descomprimir todo en un temporal en cada arranque sería lento e
# innecesario. En onedir, sys._MEIPASS es la propia carpeta de instalación,
# estable entre ejecuciones — ahí es donde main.py busca frontend_dist/ y el
# checkpoint SAM opcional (ver BASE_DIR en backend/main.py).
#
# Construir con:  pyinstaller desktop_launcher.spec

import os
import glob
from PyInstaller.utils.hooks import collect_dynamic_libs

BACKEND_DIR = os.path.abspath(SPECPATH)  # SPECPATH ya es la carpeta que contiene el .spec
PROJECT_ROOT = os.path.dirname(BACKEND_DIR)
PROCES_DIR = os.path.join(PROJECT_ROOT, "proces_images")
ACCES_API_DIR = os.path.join(PROJECT_ROOT, "acces_api")
FRONTEND_DIST = os.path.join(PROJECT_ROOT, "frontend", "dist")
CALIBRATION_DIR = os.path.join(PROJECT_ROOT, "calibration")

if not os.path.isdir(FRONTEND_DIST):
    raise SystemExit(
        f"No existe {FRONTEND_DIST} — ejecuta 'npm run build' en frontend/ antes de empaquetar."
    )

# Config de referencia (ROI recortado y máscaras de zonas estables por cámara):
# valores fijos del encuadre físico real de las 6 cámaras, no algo que cada
# usuario deba generar al abrir la app por primera vez. Se empaquetan aparte
# como "semilla" (config.py los copia a CALIBRATION_DIR solo si aún no existen
# ahí) — a propósito NO se empaqueta la carpeta calibration/ completa, porque
# cam_N_H.npy/cam_N_profile.json son la calibración YA CALCULADA de este
# despliegue de desarrollo, no una plantilla universal para cualquier instalación.
_SEED_FILES = ("roi_config.json", "alignment_masks.json")
_calibration_seed_datas = []
for _seed_name in _SEED_FILES:
    _seed_path = os.path.join(CALIBRATION_DIR, _seed_name)
    if not os.path.isfile(_seed_path):
        raise SystemExit(
            f"No existe {_seed_path} — necesario para empaquetar la config de referencia."
        )
    _calibration_seed_datas.append((_seed_path, "calibration_seed"))

# Bug real detectado y verificado 2026-09-03: torchvision NO importa su
# extensión nativa (_C_stable.pyd, que registra operadores como
# "torchvision::nms") con un `import` normal — la carga en tiempo de
# ejecución con torch.ops.load_library() (ver
# torchvision/extension.py::_load_library), así que el análisis estático de
# PyInstaller nunca la detecta como dependencia y NO la empaqueta. El fallo
# es silencioso en torchvision (excepción capturada, _has_ops() se queda en
# False) pero revienta un poco más tarde, al importar
# torchvision/_meta_registrations.py, con "RuntimeError: operator
# torchvision::nms does not exist" — reproducido en local ejecutando
# directamente el .exe recién compilado, no solo reportado por el usuario en
# otra máquina. collect_dynamic_libs('torchvision') sí encuentra los .dll
# (libpng16.dll, etc.) pero NO los .pyd (mismo motivo: no son "dynamic libs"
# para PyInstaller, son módulos de extensión que se esperaría importar,
# cosa que aquí tampoco ocurre) — se añaden a mano los dos .pyd de
# torchvision (_C_stable y image_stable) junto al resto de binarios.
_torchvision_pyd = [
    (p, "torchvision")
    for p in glob.glob(os.path.join(BACKEND_DIR, "..", "venv", "Lib", "site-packages", "torchvision", "*.pyd"))
]
if not _torchvision_pyd:
    raise SystemExit(
        "No se encontraron los .pyd de torchvision en venv/Lib/site-packages/torchvision — "
        "revisa que el venv esté activo y torchvision instalado antes de empaquetar."
    )

a = Analysis(
    [os.path.join(BACKEND_DIR, "desktop_launcher.py")],
    pathex=[BACKEND_DIR, PROCES_DIR, ACCES_API_DIR],
    binaries=[*collect_dynamic_libs("torchvision"), *_torchvision_pyd],
    datas=[
        (FRONTEND_DIST, "frontend_dist"),
        *_calibration_seed_datas,
    ],
    hiddenimports=[
        # Importados dinámicamente en main.py con try/except ImportError —
        # se declaran explícitos para que PyInstaller no los pierda.
        "segmentation_sam",
        "extract_coastline",
        "test_mes3_pipeline",
        "cam_thresholds",
        "georef_export",
        # Importado en tiempo de ejecución (dentro de una función, no como
        # import de módulo) por backend/auto_mode.py para descargar
        # imágenes de Obscape — el análisis estático de PyInstaller no lo
        # ve, así que hay que declararlo a mano o Auto Mode falla al
        # empaquetar (ModuleNotFoundError en el .exe, aunque funcione en dev).
        "obscape_api",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="LineaDeCosta",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="LineaDeCosta",
)
