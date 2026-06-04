# Definición de ROI (Región de Interés)

← [Volver al índice](README.md)

---

## Criterios de delimitación

Para optimizar el procesamiento con SAM y reducir el ruido en la extracción de la línea de costa, se han definido regiones de interés (ROI) que cumplen los siguientes criterios:

1. **Exclusión del cielo:** Se eliminan los píxeles por encima del horizonte.
2. **Exclusión de infraestructura:** Se evitan paseos marítimos, edificios o espigones que no aporten información sobre la interfaz tierra-mar.
3. **Exclusión de mar profundo:** Se recorta la zona de mar abierto donde no hay rotura de onda ni información relevante para la línea de costa.

## Coordenadas por cámara

Las coordenadas se almacenan en `calibration/roi_config.json` con el formato `{x_min, y_min, x_max, y_max}`.

| Cámara | ROI (x_min, y_min, x_max, y_max) | Justificación |
|--------|-----------------------------------|---------------|
| CAM 1 | [0, 400, 1920, 1080] | Recorte superior para horizonte |
| CAM 2 | [0, 350, 1920, 1080] | Recorte superior para horizonte |
| CAM 3 | [0, 450, 1920, 1080] | Recorte superior para horizonte |
| CAM 4 | [0, 400, 1920, 1080] | Recorte superior para horizonte |
| CAM 5 | [0, 380, 1920, 1080] | Recorte superior para horizonte |
| CAM 6 | [0, 420, 1920, 1080] | Recorte superior para horizonte |

*Nota: Estos valores son preliminares y se ajustarán tras la primera recepción de imágenes de producción de las cámaras de Guardamar.*

## Verificación visual

Se recomienda realizar una superposición de la ROI sobre una imagen de referencia para confirmar que no se pierde zona de intermarea (marea alta/baja).
