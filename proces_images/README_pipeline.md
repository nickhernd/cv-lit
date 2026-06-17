# Procesamiento de Imágenes - Shoreline Extraction

Este módulo contiene el pipeline para la detección y extracción de la línea de costa a partir de los fotogramas de las cámaras Obscape.

## Metodología del Pipeline (Mes 3)

El proceso de extracción sigue estos pasos:

1.  **Definición de ROI (Region of Interest):** Se delimita el área de la playa para ignorar el cielo, montañas y zonas irrelevantes.
2.  **Segmentación Semántica:**
    *   **SAM (Segment Anything Model):** Uso de IA (modelo ViT-H) para segmentar la arena seca mediante "prompts" automáticos.
    *   **Color Fallback (Detección por Color):** Algoritmo robusto basado en espacio HSV que detecta tonos de arena y **resta la espuma blanca** de las olas para mayor precisión.
3.  **Suavizado Temporal:** Se aplica una media móvil (70% actual, 30% anterior) entre fotogramas consecutivos para evitar saltos bruscos y filtrar ruidos momentáneos.
4.  **Extracción de Línea:**
    *   Cálculo de contornos sobre la máscara binaria.
    *   Selección del contorno más largo (la orilla).
    *   Simplificación de polilínea (Ramer-Douglas-Peucker) para una línea limpia.

## Archivos Generados en `/output`

*   `analisis_costa.gif`: Animación de la línea detectada sobre la imagen real.
*   `solo_mascaras.gif`: Animación de la evolución de la segmentación binaria.
*   `mask_frame_XXX.png`: Máscaras intermedias procesadas.
*   `frame_XXX.jpg`: Visualizaciones con la línea superpuesta.

## Herramientas

*   `segmentation_sam.py`: Clase principal para inferencia con SAM.
*   `extract_coastline.py`: Funciones geométricas para tratar los contornos.
*   `test_mes3_pipeline.py`: Script integrador para generar las pruebas y los GIFs.
