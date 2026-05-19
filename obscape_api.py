"""
Cliente para la API de Obscape.
Descarga imágenes y metadatos de estaciones de cámaras fijas.

Uso:
    python obscape_api.py                      # listar proyectos y estaciones
    python obscape_api.py --download           # descargar últimas imágenes
    python obscape_api.py --from 2026-04-30 --to 2026-05-01  # rango de fechas
    python obscape_api.py --station PTM61474 --latest 24      # últimas 24h
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
API_KEY  = "gtbOeudRqK6NIdanljoULOhyT1rsyKpFZgrbxMBfbA6REh9gjG"

# Directorio de salida por defecto
OUT_DIR = Path(__file__).parent / "proces_images" / "images"

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

    def list_projects(self) -> list[dict]:
        r = self._get({})
        r.raise_for_status()
        data = r.json()
        if isinstance(data, list) and data and "name" in data[0]:
            return data
        return []

    def list_stations(self, project: str) -> list[dict]:
        r = self._get({"project": project})
        r.raise_for_status()
        data = r.json()
        if isinstance(data, list):
            return data
        return []

    def get_station_data(
        self,
        project: str,
        station: str,
        from_dt: str | None = None,
        to_dt: str | None = None,
        latest_hours: int | None = None,
        latest_minutes: int | None = None,
        parameters: list[str] | None = None,
        tz: str = "local",
    ) -> dict:
        params: dict = {"project": project, "station": station, "tz": tz}
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
        project: str,
        station: str,
        timestamp: int | str,
        out_dir: Path,
    ) -> Path | None:
        """
        Descarga una imagen por timestamp unix o 'latest'.
        Devuelve la ruta del fichero guardado o None si falla.
        """
        params = {"project": project, "station": station, "image": timestamp}
        r = self._get(params, stream=True)
        if r.status_code != 200:
            print(f"  [!] Error {r.status_code} descargando imagen {timestamp}")
            return None
        ct = r.headers.get("Content-Type", "")
        if "image" not in ct:
            print(f"  [!] Respuesta no es imagen: {ct} — {r.text[:100]}")
            return None

        out_dir.mkdir(parents=True, exist_ok=True)
        if timestamp == "latest":
            fname = f"latest_{station}.jpg"
        else:
            ts = int(timestamp)
            dt = datetime.fromtimestamp(ts, tz=timezone.utc)
            fname = f"{ts}_{dt.strftime('%Y%m%d_%H%M%S')}_{station}.jpg"

        out_path = out_dir / fname
        out_path.write_bytes(r.content)
        print(f"  [+] {fname}  ({len(r.content)//1024} KB)")
        return out_path

    def download_range(
        self,
        project: str,
        station: str,
        from_dt: str,
        to_dt: str,
        out_dir: Path,
        hour_filter: int | None = 12,
    ) -> list[Path]:
        """
        Descarga todas las imágenes en un rango de fechas.
        Si hour_filter != None, descarga sólo las imágenes de esa hora (prioridad 12:00h).
        """
        data = self.get_station_data(project, station, from_dt=from_dt, to_dt=to_dt, tz="local")
        points = data.get("data", [])
        print(f"  {len(points)} puntos disponibles entre {from_dt} y {to_dt}")

        saved = []
        for pt in points:
            ts  = pt[0]   # unix timestamp
            tstr = pt[1]  # human readable
            if hour_filter is not None:
                dt = datetime.fromtimestamp(ts, tz=timezone.utc)
                if dt.hour != hour_filter:
                    continue
            path = self.download_image(project, station, ts, out_dir)
            if path:
                saved.append(path)
        return saved


# ── CLI ────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Cliente API Obscape")
    parser.add_argument("--project",  default=None, help="Nombre del proyecto")
    parser.add_argument("--station",  default=None, help="ID de estación")
    parser.add_argument("--from",     dest="from_dt", default=None,
                        help="Fecha inicio yyyy-mm-dd o yyyy-mm-ddThh:mm:ss")
    parser.add_argument("--to",       dest="to_dt", default=None,
                        help="Fecha fin yyyy-mm-dd o yyyy-mm-ddThh:mm:ss")
    parser.add_argument("--latest",   type=int, default=None,
                        help="Últimas N horas")
    parser.add_argument("--download", action="store_true",
                        help="Descargar imágenes")
    parser.add_argument("--all-hours", action="store_true",
                        help="Descargar todas las horas (no solo 12:00h)")
    parser.add_argument("--out",      default=str(OUT_DIR),
                        help="Directorio de salida")
    args = parser.parse_args()

    client  = ObscapeClient()
    out_dir = Path(args.out)

    # Normalizar fechas
    def norm_date(s):
        if s and "T" not in s:
            return s + "T00:00:00"
        return s

    args.from_dt = norm_date(args.from_dt)
    args.to_dt   = norm_date(args.to_dt)

    # Listar proyectos
    print("=== Proyectos disponibles ===")
    projects = client.list_projects()
    for p in projects:
        print(f"  {p['id']:>6}  {p['name']}  ({p['latitude']}, {p['longitude']})")

    if not projects:
        print("  [!] Sin proyectos. Verificar credenciales.")
        sys.exit(1)

    project = args.project or projects[0]["name"]
    print(f"\n=== Estaciones del proyecto '{project}' ===")
    stations = client.list_stations(project)
    for s in stations:
        print(f"  {s}")

    if not stations:
        print("  [!] Sin estaciones en este proyecto.")
        sys.exit(1)

    station = args.station or stations[0].get("id") or stations[0].get("station")
    if not station:
        print("  [!] No se pudo determinar el ID de estación.")
        sys.exit(1)

    print(f"\n=== Datos de estación '{station}' ===")

    if args.download:
        if args.from_dt and args.to_dt:
            hour = None if args.all_hours else 12
            saved = client.download_range(
                project, station, args.from_dt, args.to_dt, out_dir, hour_filter=hour
            )
            print(f"\n{len(saved)} imágenes descargadas en {out_dir}")
        else:
            print("Descargando última imagen...")
            client.download_image(project, station, "latest", out_dir)
    else:
        # Mostrar metadatos / últimas observaciones
        latest = args.latest or 24
        data = client.get_station_data(
            project, station, latest_hours=latest, tz="local"
        )
        params = data.get("parameters", [])
        points = data.get("data", [])
        print(f"Parámetros: {[p['name'] for p in params]}")
        print(f"Puntos en las últimas {latest}h: {len(points)}")
        if points:
            print("Últimos 3 puntos:")
            for pt in points[-3:]:
                print(f"  {pt}")


if __name__ == "__main__":
    main()
