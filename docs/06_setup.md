# Setup Técnico

← [Volver al índice](README.md)

---

## Stack

| Elemento | Versión / detalle |
|----------|-------------------|
| OS | Windows + Conda/Mamba |
| Python | 3.10 / 3.11 |
| Gestor entornos | [Miniforge](https://github.com/conda-forge/miniforge) / [Mambaforge](https://github.com/conda-forge/miniforge#mambaforge) |
| IDE | [VS Code](https://code.visualstudio.com) |
| GIS | [QGIS](https://qgis.org) — validación EPSG:25830 |
| Deep Learning | [PyTorch](https://pytorch.org) (SAM) |
| Visión | [OpenCV](https://docs.opencv.org) (`opencv-python`) |
| Geo | [GDAL](https://gdal.org), [pyproj](https://pyproj4.github.io/pyproj) |

**Proyección de salida:** EPSG:25830 (ETRS89 / UTM zona 30N)  
**Fase horaria prioritaria:** 12:00h solar local

## Instalación del entorno

```bash
conda create -n cv-lit python=3.11
conda activate cv-lit

pip install torch torchvision           # SAM (backend)
pip install git+https://github.com/facebookresearch/segment-anything.git
pip install opencv-python numpy         # visión + álgebra
pip install gdal pyproj shapely         # geo
pip install requests                    # API Obscape
```

## Estructura de directorios

```text
cv-lit/
├── .gitignore               # Archivos y carpetas excluidos de Git
├── environment.yml          # Configuración del entorno Conda
├── acces_api/               # Módulo de comunicación con Obscape
│   └── obscape_api.py       # Cliente API para descarga de imágenes
├── calibration/             # Parámetros de calibración por cámara
│   ├── cam_1_params.json    # Parámetros intrínsecos/extrínsecos
│   ├── cam_1_H.npy          # Matriz de homografía calculada
│   └── ...
├── data/                    # Almacenamiento de datos (excluido de Git)
│   ├── raw/                 # Imágenes originales descargadas
│   │   ├── CAM_1/           # Imágenes por cámara y timestamp
│   │   └── ...
│   ├── processed/           # Resultados del pipeline
│   │   ├── masks/           # Máscaras binarias de segmentación (SAM)
│   │   ├── rectified/       # Imágenes proyectadas a plano planta
│   │   └── lines/           # Líneas de costa en formato GeoJSON
│   └── logs/                # Registro de operaciones y errores
├── docs/                    # Documentación técnica (Markdown)
└── proces_images/           # Lógica de procesamiento y algoritmos
    ├── segmentation/        # Scripts de segmentación con SAM
    ├── extraction/          # Extracción de línea de la máscara
    └── projection/      # Proyección de píxel a coordenadas UTM
    ```

    ## Convenciones de Git (Issue 108)

    Para mantener un flujo de trabajo organizado, se seguirán las siguientes convenciones:

    *   **Rama principal:** `main` (código estable y validado).
    *   **Ramas de desarrollo:**
    *   `feature/nombre-modulo` (ej: `feature/sam-segmentation`)
    *   `fix/descripcion-error` (ej: `fix/api-timeout`)
    *   `docs/nombre-doc` (ej: `docs/update-pipeline`)
    *   **Pull Requests:** Todo cambio debe pasar por PR y ser revisado antes de integrarse en `main`.


