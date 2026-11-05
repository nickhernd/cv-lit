# cv-lit — Monitorización de Línea de Costa

Sistema de monitorización automática de la línea de costa mediante 6 cámaras fijas (Obscape) en Guardamar del Segura (SensoMar).

## Ejecución (desarrollo)

```bash
./scripts/start_dev.sh
```

Levanta el backend (FastAPI) en `http://localhost:8000` y el frontend (Vite) en `http://localhost:5173`.

## Aplicación de escritorio (Windows)

El sistema también se distribuye como app de escritorio empaquetada: `installer/output/LineaDeCosta-Setup.exe`. Para generarla desde cero:

```bash
cd frontend && npm run build && cd ..
cd backend && pyinstaller desktop_launcher.spec && pyinstaller download_sam.spec && cd ..
"C:\Program Files\Inno Setup 7\ISCC.exe" installer\cv-lit.iss
```

## Documentación

- [`docs/uso.pdf`](docs/uso.pdf) — manual de uso de la aplicación, pantalla por pantalla.
- [`docs/memoria.pdf`](docs/memoria.pdf) — memoria técnica completa (arquitectura, calibración, segmentación).
