# API Obscape

← [Volver al índice](README.md)

---

## Credenciales

| Parámetro | Valor |
|-----------|-------|
| Base URL | `https://obscape.com/portal/api/v3/api` |
| Portal | https://obscape.com/portal |
| Username | `fuster` |
| Password portal | `Delfos17*` |
| API Key | `c1RyHhP6aJBPRHwIUrpz9eEPHPGhlbuMZIujEUvWTJaJPXJO0x` |

> **Nota:** password del portal y API key son cosas distintas. La API key se obtiene en Portal → usuario → *User Settings*.

El patrón base de cualquier llamada:
```
https://obscape.com/portal/api/v3/api?username=fuster&key=<API_KEY>&...
```

## Endpoints

| Propósito | Parámetros adicionales |
|-----------|----------------------|
| Listar proyectos | (ninguno) |
| Listar estaciones del proyecto | `&project=<nombre>` |
| Datos últimas 24h | `&project=<p>&station=<id>` |
| Datos entre fechas | `&station=<id>&from=yyyy-mm-ddThh:mm:ss&to=...` |
| Últimas N horas | `&station=<id>&latest=<N>` |
| Últimos N minutos | `&station=<id>&latestMinutes=<N>` |
| Solo datos (sin metadatos) | `&dataonly` |
| Imagen por timestamp unix | `&station=<id>&image=<unix_ts>` |
| Última imagen disponible | `&station=<id>&image=latest` |
| Timezone local | `&tz=local` |

### Formato de nombre de imagen descargada

```
{unix_timestamp}_{YYYYMMDD}_{HHMMSS}_{station_id}.jpg
```

Ejemplo: `1777550400_20260430_120000_PTM61474.jpg`

## Estado actual (verificado 2026-05-19)

La API key funciona pero devuelve el proyecto **"Ketel Haven"** (Países Bajos), sin cámaras vinculadas:

```json
[{
  "id":        "5866",
  "name":      "Ketel Haven",
  "devices":   [],
  "latitude":  "51.82553",
  "longitude": "4.727377"
}]
```

**Problema:** las 6 cámaras de Guardamar no están bajo esta cuenta. Todas las consultas de estación devuelven `400`.

**Acción pendiente:** confirmar con Obscape / Ayuntamiento el nombre del proyecto correcto.

## Script cliente — `obscape_api.py`

```bash
# Listar proyectos y estaciones
python obscape_api.py

# Descargar última imagen
python obscape_api.py --download

# Rango de fechas (solo 12:00h por defecto)
python obscape_api.py --from 2026-04-30 --to 2026-05-01 --download

# Rango de fechas, todas las horas
python obscape_api.py --from 2026-04-30 --to 2026-05-01 --download --all-hours

# Estación concreta, últimas 24h
python obscape_api.py --station PTM61474 --latest 24

# Directorio de salida personalizado
python obscape_api.py --download --out /ruta/salida
```

Métodos disponibles en `ObscapeClient`:  
`list_projects()` · `list_stations()` · `get_station_data()` · `download_image()` · `download_range()`

El método `download_range()` filtra por `hour_filter=12` por defecto (prioridad 12:00h).

## Dataset manual disponible

Estación **PTM61474** (CAM 2) → `proces_images/images/`  
~90 imágenes horarias (04:00–18:00h) · 29/04/2026 – 06/05/2026  
Origen: fichero ZIP `camera_8214_from20260429_174800.zip` facilitado manualmente.
