# align_images.py

Alineación temporal de imágenes de cámara costera fija.  
Calcula la homografía entre cada imagen de una secuencia y una imagen de referencia usando SIFT + FLANN + RANSAC, guarda las imágenes transformadas y exporta las matrices H a CSV.

Desarrollado en **Tech4D Lab · Universidad de Alicante**.

---

## Dependencias

```bash
pip install opencv-python-headless numpy pandas
```

---

## Uso

```bash
# Referencia automática (primera imagen cronológicamente)
python align_images.py --input /ruta/imagenes --output /ruta/salida

# Referencia manual
python align_images.py --input /ruta/imagenes --output /ruta/salida \
                       --ref /ruta/imagenes/20260506_ref.jpg
```

| Argumento | Abrev. | Descripción |
|-----------|--------|-------------|
| `--input` | `-i` | Directorio con los JPGs de entrada |
| `--output` | `-o` | Directorio de salida (se crea si no existe) |
| `--ref` | `-r` | Imagen de referencia opcional; si se omite, se usa la primera imagen por fecha |

---

## Formato de nombres de archivo

El script extrae el timestamp del nombre para ordenar la secuencia cronológicamente. Soporta dos formatos:

```
UNIX_YYYYMMDD_HHMMSS_CAMID.jpg        ← formato principal
1778079600_20260506_150000_PTM61474.jpg

cualquier_cosa_YYYYMMDD_cualquier_cosa.jpg   ← fallback
```

Si ningún formato encaja, usa la fecha de modificación del archivo.

---

## Salida

```
output/
├── aligned/               ← Imágenes transformadas (mismo nombre que el original)
└── homographies.csv       ← Matriz H y métricas de calidad por imagen
```

### homographies.csv

| Columna | Descripción |
|---------|-------------|
| `datetime` | Timestamp ISO 8601 extraído del nombre de archivo |
| `filename` | Nombre del archivo original |
| `status` | `reference` · `ok` · `low_matches` · `no_features` · `ransac_failed` |
| `inliers` | Número de inliers RANSAC (indicador de calidad de la alineación) |
| `H00`…`H22` | Los 9 elementos de la matriz de homografía 3×3 |

Para imágenes con `status != ok` (alineación fallida), la imagen guardada en `aligned/` es una copia sin transformar y los valores `H` son `None`.

### Reutilizar la homografía guardada

```python
import pandas as pd
import numpy as np
import cv2

df = pd.read_csv("output/homographies.csv")
row = df[df["filename"] == "20260506_150000.jpg"].iloc[0]

H = np.array([[row.H00, row.H01, row.H02],
              [row.H10, row.H11, row.H12],
              [row.H20, row.H21, row.H22]])

img = cv2.imread("20260506_150000.jpg")
aligned = cv2.warpPerspective(img, H, (img.shape[1], img.shape[0]))
```

---

## Parámetros internos

Editables al inicio del script:

| Constante | Valor por defecto | Descripción |
|-----------|-------------------|-------------|
| `MIN_INLIERS` | `50` | Mínimo de inliers para aceptar la alineación |
| `RANSAC_THRESH` | `5.0` | Umbral de reproyección RANSAC (píxeles) |
| `SIFT_FEATURES` | `3000` | Número máximo de keypoints SIFT por imagen |
| `LOWE_RATIO` | `0.75` | Umbral del ratio test de Lowe para filtrar matches |

Para secuencias con mucho movimiento de cámara, reducir `RANSAC_THRESH` a `3.0` o aumentar `SIFT_FEATURES`.

---

## Método

1. **Detección de features** — SIFT sobre imagen en escala de grises. Los keypoints de la referencia se calculan una sola vez.
2. **Matching** — FLANN KD-tree (k=2) con ratio test de Lowe (`d₁ < 0.75·d₂`).
3. **Homografía** — `cv2.findHomography` con RANSAC. Se rechaza si los inliers son menores que `MIN_INLIERS`.
4. **Transformación** — `cv2.warpPerspective` al tamaño exacto de la imagen de referencia.

La homografía cubre traslación, rotación, escala y perspectiva. Para cámaras bien fijas con deriva mínima, los valores fuera de la diagonal serán cercanos a cero y la escala próxima a 1.
