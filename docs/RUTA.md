# Ruta de Desarrollo (Roadmap) - cv-lit

Este documento detalla los pasos a seguir para completar la implementacion definitiva del sistema de monitorizacion.

## Fase 1: Consolidacion de Herramientas (Meses 1-3) [OK]
- [x] Cliente API Obscape estable.
- [x] Motor de homografia y calibracion offline.
- [x] Prototipo de segmentacion y extraccion de linea de costa.
- [x] Interfaz web base (Dashboard, Calibracion, Analisis).

## Fase 2: Georreferenciacion Definitiva (Mes 4) [EN CURSO]
1. **Datos del IEL:** Recibir y validar el archivo de transectos GNSS.
2. **Calibracion Real:** Ejecutar `calibration_tool.py` para las 6 camaras usando los datos GNSS.
3. **Conversion a UTM:** Implementar la proyeccion sistematica de todos los puntos de la linea de costa a EPSG:25830.
4. **Validacion de Error:** Calcular RMSE real comparando con los transectos.

## Fase 3: Automatizacion y Robustez (Mes 5)
1. **Procesamiento por Lotes:** Integrar el backend para procesar todas las imagenes de las 12:00h de un dia.
2. **Filtros de Calidad:** Implementar rechazo automatico de imagenes con niebla o baja confianza.
3. **Persistencia GeoJSON:** Guardar historico de lineas de costa en base de datos o sistema de archivos.

## Fase 4: Entrega e Integracion (Mes 6)
1. **Dashboard de Historico:** Graficas de evolucion del area seca en la playa.
2. **Exportacion Masiva:** Generar informes mensuales de variacion de linea de costa.
3. **Manual de Usuario:** Documentacion final para el personal del ayuntamiento.
