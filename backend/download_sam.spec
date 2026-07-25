# -*- mode: python ; coding: utf-8 -*-
# Exe aparte y ligero (solo librería estándar) para el modelo SAM opcional —
# deliberadamente separado de desktop_launcher.spec para no arrastrar
# PyTorch/OpenCV a algo que solo descarga un archivo. Lo invoca el instalador
# (ver installer/cv-lit.iss) como tarea opcional tras la instalación, y
# también puede ejecutarse a mano más tarde si el usuario cambia de opinión.
#
# Construir con:  pyinstaller download_sam.spec

import os

BACKEND_DIR = os.path.abspath(SPECPATH)

a = Analysis(
    [os.path.join(BACKEND_DIR, "download_sam.py")],
    pathex=[BACKEND_DIR],
    binaries=[],
    datas=[],
    hiddenimports=[],
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
    a.binaries,
    a.datas,
    [],
    name="download_sam",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,  # sí lleva consola: es una descarga con progreso en texto
)
