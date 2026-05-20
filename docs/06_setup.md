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

```
cv-lit/
+-- obscape_api.py           # cliente API Obscape
+-- map_ubication.png        # mapa proyecto Ketel Haven
+-- docs/                    # esta documentación
|   +-- README.md
|   +-- 01_overview.md
|   +-- 02_api.md
|   +-- 03_pipeline.md
|   +-- 04_cameras.md
|   +-- 05_calibration.md
|   +-- 06_setup.md
|   +-- 07_plan.md
|   +-- 08_validation.md
|   \-- 09_estado.md
+-- calibration/             # (pendiente) perfiles de calibración
|   +-- cam_1_H.npy
|   +-- cam_1_params.json
|   \-- ...
\-- proces_images/
    +-- images/              # ~90 JPG estación PTM61474
    \-- horizon_correct.py   # corrección curvatura de horizonte
```
