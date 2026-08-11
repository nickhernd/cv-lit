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

BACKEND_DIR = os.path.abspath(SPECPATH)  # SPECPATH ya es la carpeta que contiene el .spec
PROJECT_ROOT = os.path.dirname(BACKEND_DIR)
PROCES_DIR = os.path.join(PROJECT_ROOT, "proces_images")
ACCES_API_DIR = os.path.join(PROJECT_ROOT, "acces_api")
FRONTEND_DIST = os.path.join(PROJECT_ROOT, "frontend", "dist")

if not os.path.isdir(FRONTEND_DIST):
    raise SystemExit(
        f"No existe {FRONTEND_DIST} — ejecuta 'npm run build' en frontend/ antes de empaquetar."
    )

a = Analysis(
    [os.path.join(BACKEND_DIR, "desktop_launcher.py")],
    pathex=[BACKEND_DIR, PROCES_DIR, ACCES_API_DIR],
    binaries=[],
    datas=[
        (FRONTEND_DIST, "frontend_dist"),
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
