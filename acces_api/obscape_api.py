"""
Cliente para la API de Obscape.
Descarga imágenes y metadatos de estaciones de cámaras fijas.

Uso:
    python obscape_api.py                                             # listar cámaras
    python obscape_api.py --download                                  # última imagen de cada cámara
    python obscape_api.py --download --all                            # TODO el historial de todas las cámaras
    python obscape_api.py --station 8213 --download                   # última imagen de CAM 1
    python obscape_api.py --station 8214 --from 2026-05-01 --to 2026-05-20 --download
    python obscape_api.py --station 8214 --from 2026-05-01 --to 2026-05-20 --download --all-hours

Estructura de salida:
    proces_images/
      CAM_1/
        images/  20260520_120000_8213.jpg
        json/    20260520_120000_8213.json
      CAM_2/
        images/  ...
        json/    ...
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

# ── Configuración ──────────────────────────────────────────────────────────────
API_URL  = "https://obscape.com/portal/api/v3/api"
USERNAME = "fuster"
API_KEY  = "c1RyHhP6aJBPRHwIUrpz9eEPHPGhlbuMZIujEUvWTJaJPXJO0x"

# Fecha de inicio del proyecto (límite para --all)
PROJECT_START = "2025-01-01T00:00:00"

# Directorio de salida por defecto
OUT_DIR = Path(__file__).parent.parent / "proces_images"

# ── Cliente API ────────────────────────────────────────────────────────────────

class ObscapeClient:
    def __init__(self, username: str = USERNAME, api_key: str = API_KEY):
        self.username = username
        self.api_key  = api_key
        self.session  = requests.Session()
        self.session.headers.update({"User-Agent": "cv-lit/1.0"})

    def _get(self, params: dict, stream: bool = False) -> requests.Response:
        params = {"username": self.username, "key": self.api_key, **params}
        r = self.session.get(API_URL, params=params, stream=stream, timeout=30)
        return r

    def list_stations(self, cameras_only: bool = True) -> list[dict]:
        """Devuelve las estaciones. Si cameras_only=True filtra solo CAM*."""
        r = self._get({})
        r.raise_for_status()
        data = r.json()
        if not isinstance(data, list):
            return []
        if cameras_only:
            data = [s for s in data if s.get("name", "").upper().startswith("CAM")]
        return data

    def get_station_data(
        self,
        station: str,
        from_dt: str | None = None,
        to_dt: str | None = None,
        latest_hours: int | None = None,
        latest_minutes: int | None = None,
        parameters: list[str] | None = None,
        tz: str = "local",
    ) -> dict:
        params: dict = {"station": station, "tz": tz}
        if from_dt:
            params["from"] = from_dt
        if to_dt:
            params["to"] = to_dt
        if latest_hours:
            params["latest"] = latest_hours
        if latest_minutes:
            params["latestMinutes"] = latest_minutes
        if parameters:
            params["parameters"] = ",".join(parameters)
        r = self._get(params)
        r.raise_for_status()
        return r.json()

    def download_image(
        self,
        station_id: str,
        station_name: str,
        timestamp: int | str,
        base_out_dir: Path,
        metadata: dict | None = None,
    ) -> Path | None:
        """
        Descarga una imagen y su JSON de metadatos.
        Estructura:
            base_out_dir/CAM_X/images/{YYYYMMDD}_{HHMMSS}_{station_id}.jpg
            base_out_dir/CAM_X/json/  {YYYYMMDD}_{HHMMSS}_{station_id}.json
        """
        cam_folder  = base_out_dir / station_name.replace(" ", "_")
        img_folder  = cam_folder / "images"
        json_folder = cam_folder / "json"
        img_folder.mkdir(parents=True, exist_ok=True)
        json_folder.mkdir(parents=True, exist_ok=True)

        # Determinar nombre de fichero
        if timestamp == "latest":
            # Intentar usar el timestamp real del último punto de metadatos
            ts_from_meta = (metadata or {}).get("time")
            if ts_from_meta:
                dt = datetime.fromtimestamp(int(ts_from_meta), tz=timezone.utc)
                fname_base = f"{dt.strftime('%Y%m%d_%H%M%S')}_{station_id}"
            else:
                fname_base = f"latest_{station_id}"
        else:
            ts = int(timestamp)
            dt = datetime.fromtimestamp(ts, tz=timezone.utc)
            fname_base = f"{dt.strftime('%Y%m%d_%H%M%S')}_{station_id}"

        img_path  = img_folder  / f"{fname_base}.jpg"
        json_path = json_folder / f"{fname_base}.json"

        # Saltar si ya existe (útil al relanzar --all)
        if img_path.exists():
            print(f"  [=] Ya existe {station_name}/images/{fname_base}.jpg — omitiendo")
            return img_path

        r = self._get({"station": station_id, "image": timestamp}, stream=True)
        if r.status_code != 200:
            print(f"  [!] Error {r.status_code} imagen {timestamp}")
            return None
        ct = r.headers.get("Content-Type", "")
        if "image" not in ct:
            print(f"  [!] No es imagen: {ct} — {r.text[:100]}")
            return None

        img_path.write_bytes(r.content)
        json_path.write_text(json.dumps(metadata or {}, indent=2, ensure_ascii=False))

        print(f"  [+] {station_name}/images/{fname_base}.jpg  ({len(r.content)//1024} KB)")
        return img_path

    def download_range(
        self,
        station_id: str,
        station_name: str,
        from_dt: str,
        to_dt: str,
        base_out_dir: Path,
        hour_filter: int | None = 12,
    ) -> list[Path]:
        """
        Descarga imágenes + JSON en un rango de fechas.
        hour_filter=None descarga todas las horas; por defecto solo 12:00h.
        """
        data = self.get_station_data(station_id, from_dt=from_dt, to_dt=to_dt, tz="local")
        points = data.get("data", [])
        params_info = data.get("parameters", [])
        print(f"  {len(points)} puntos disponibles entre {from_dt} y {to_dt}")

        saved = []
        for pt in points:
            ts = int(pt["time"]) if isinstance(pt, dict) else int(pt[0])
            if hour_filter is not None:
                dt = datetime.fromtimestamp(ts, tz=timezone.utc)
                if dt.hour != hour_filter:
                    continue
            meta = pt if isinstance(pt, dict) else dict(zip([p["name"] for p in params_info], pt))
            path = self.download_image(station_id, station_name, ts, base_out_dir, metadata=meta)
            if path:
                saved.append(path)
        return saved


# ── CLI ────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Cliente API Obscape")
    parser.add_argument("--station",   default=None,
                        help="ID de estación (ej: 8213 para CAM 1)")
    parser.add_argument("--from",      dest="from_dt", default=None,
                        help="Fecha inicio yyyy-mm-dd o yyyy-mm-ddThh:mm:ss")
    parser.add_argument("--to",        dest="to_dt", default=None,
                        help="Fecha fin yyyy-mm-dd o yyyy-mm-ddThh:mm:ss")
    parser.add_argument("--latest",    type=int, default=None,
                        help="Últimas N horas (solo visualización)")
    parser.add_argument("--download",  action="store_true",
                        help="Descargar imágenes")
    parser.add_argument("--all",       dest="all_data", action="store_true",
                        help="Descargar TODO el historial (todas las cámaras, todas las horas)")
    parser.add_argument("--all-hours", action="store_true",
                        help="En un rango --from/--to, descargar todas las horas (no solo 12:00h)")
    parser.add_argument("--out",       default=str(OUT_DIR),
                        help="Directorio de salida")
    args = parser.parse_args()

    client  = ObscapeClient()
    out_dir = Path(args.out)

    def norm_date(s):
        if s and "T" not in s:
            return s + "T00:00:00"
        return s

    args.from_dt = norm_date(args.from_dt)
    args.to_dt   = norm_date(args.to_dt)

    # Listar cámaras
    print("=== Cámaras disponibles ===")
    stations = client.list_stations(cameras_only=True)
    for s in stations:
        print(f"  {s['id']:>6}  {s['name']}  ({s['latitude']}, {s['longitude']})")

    if not stations:
        print("  [!] Sin cámaras. Verificar credenciales.")
        sys.exit(1)

    # Seleccionar estaciones objetivo
    if args.station:
        target_stations = [s for s in stations if s["id"] == args.station]
        if not target_stations:
            print(f"  [!] Estación {args.station} no encontrada.")
            sys.exit(1)
    else:
        target_stations = stations

    # ── Descarga ──────────────────────────────────────────────────────────────

    if args.all_data:
        # Descargar TODO el historial: desde PROJECT_START hasta hoy, todas las horas
        to_dt = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        total = 0
        print(f"\n=== Descarga completa ({PROJECT_START} → {to_dt}) ===")
        for s in target_stations:
            print(f"\n--- {s['name']} (id={s['id']}) ---")
            saved = client.download_range(
                s["id"], s["name"], PROJECT_START, to_dt, out_dir, hour_filter=None
            )
            total += len(saved)
            print(f"  {len(saved)} imágenes → {out_dir}/{s['name'].replace(' ', '_')}/")
        print(f"\nTotal: {total} imágenes descargadas.")

    elif args.download:
        if args.from_dt and args.to_dt:
            hour = None if args.all_hours else 12
            total = 0
            for s in target_stations:
                print(f"\n=== Descargando {s['name']} (id={s['id']}) ===")
                saved = client.download_range(
                    s["id"], s["name"], args.from_dt, args.to_dt, out_dir, hour_filter=hour
                )
                total += len(saved)
                print(f"  {len(saved)} imágenes → {out_dir}/{s['name'].replace(' ', '_')}/")
            print(f"\nTotal: {total} imágenes descargadas.")
        else:
            print("\nDescargando última imagen de cada cámara...")
            for s in target_stations:
                print(f"\n=== {s['name']} (id={s['id']}) ===")
                latest_data = client.get_station_data(s["id"], latest_hours=1, tz="local")
                points = latest_data.get("data", [])
                meta = points[-1] if points else {}
                client.download_image(s["id"], s["name"], "latest", out_dir, metadata=meta)

    else:
        # Solo mostrar metadatos
        latest = args.latest or 24
        for s in target_stations:
            print(f"\n=== Datos de {s['name']} (id={s['id']}) ===")
            data = client.get_station_data(s["id"], latest_hours=latest, tz="local")
            params_info = data.get("parameters", [])
            points = data.get("data", [])
            print(f"Parámetros: {[p['name'] for p in params_info]}")
            print(f"Puntos en las últimas {latest}h: {len(points)}")
            if points:
                print("Últimos 3 puntos:")
                for pt in points[-3:]:
                    print(f"  {pt}")


if __name__ == "__main__":
    main()
