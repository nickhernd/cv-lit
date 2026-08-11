# Línea de Costa — Frontend

Interfaz web (Vue 3 + Vite + Tailwind) del sistema de monitorización de línea de
costa. Dashboard, calibración interactiva, alineación masiva, análisis de línea
de costa, mapa GeoJSON y modo automático. Ver el `README.md` de la raíz del
repo para la descripción completa del proyecto.

## Desarrollo

```bash
npm install
npm run dev       # http://localhost:5173, con el backend en http://localhost:8000
```

## Configuración

La URL del backend es configurable vía `VITE_API_URL` (ver `.env.example`).
Sin definir, usa `http://localhost:8000`.

## Build de producción

```bash
npm run build      # genera frontend/dist/
```

`frontend/dist/` es lo que sirve `backend/main.py` (modo web) o lo que empaqueta
el instalador de escritorio (ver `installer/cv-lit.iss` y el README de la raíz).
