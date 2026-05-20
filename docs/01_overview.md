# Visión General del Proyecto

← [Volver al índice](README.md)

---

## Descripción

**cv-lit** es un sistema de detección automática de línea de costa a partir de imágenes oblicuas de **6 cámaras fijas** instaladas en el frente litoral de **Guardamar del Segura** (Alicante, España).

## Cliente y colaboradores

| Rol | Entidad |
|-----|---------|
| Cliente | Ayuntamiento de Guardamar del Segura |
| Colaboración técnica | Instituto de Ecología Litoral (IEL) — suministra GCPs GNSS |
| Equipo de desarrollo | 1 ingeniero a tiempo parcial, supervisado por la Universidad de Alicante |
| Duración | 6 meses |

## Objetivo

Monitorización automática de la playa seca, produciendo como producto final un **GeoJSON proyectado en EPSG:25830** (ETRS89 / UTM zona 30N).

### Atributos obligatorios del GeoJSON de salida

| Campo | Descripción |
|-------|-------------|
| `ID_Camara` | Identificador de la cámara (1–6) |
| `Timestamp` | Fecha y hora UTC de la imagen |
| `Confianza_IA` | Score de confianza del modelo SAM (0–1) |
| `Area_Seca_m2` | Superficie de playa seca en m² |

## Restricciones no negociables

- Toda implementación **debe** producir GeoJSON en **EPSG:25830**.
- Fase horaria prioritaria: **12:00h solar local**.
- Modelo de segmentación: **SAM** (Segment Anything Model, Meta AI).
- Cada cámara tiene su propio perfil de calibración independiente.

## Entregables finales

1. Aplicación ejecutable configurada y documentada.
2. Perfiles de calibración por cámara (6 ficheros `.npy` / `.json`).
3. Manual breve de uso.
4. Informe inicial de validación con métricas RMSE y MAE.
