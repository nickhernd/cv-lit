"""
Cliente para la API de Obscape.
Descarga imágenes y metadatos de estaciones de cámaras fijas.

Uso:
    python obscape_api.py                      # listar proyectos y estaciones
    python obscape_api.py --download           # descargar últimas imágenes
    python obscape_api.py --from 2026-04-30 --to 2026-05-01  # rango de fechas
    python obscape_api.py --station PTM61474 --latest 24      # últimas 24h

# Última imagen de CAM 1
  python obscape_api.py --station 8213 --download

  # Todas las imágenes de CAM 2 entre fechas (solo 12:00h)
  python obscape_api.py --station 8214 --from 2026-05-01 --to 2026-05-20 --download

  # Todas las horas
  python obscape_api.py --station 8214 --from 2026-05-01 --to 2026-05-20 --download --all-hours

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

    def list_stations(self, cameras_only: bool = True) -> list[dict]:
        """
        Devuelve la lista de estaciones de la cuenta.
        Si cameras_only=True filtra BOYAs y devuelve solo cámaras (CAM*).
        """
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
        Estructura: base_out_dir/CAM_X/{YYYYMMDD}_{HHMMSS}_{station_id}.jpg/.json
        """
        folder = base_out_dir / station_name.replace(" ", "_")
        folder.mkdir(parents=True, exist_ok=True)

        if timestamp == "latest":
            fname_base = f"latest_{station_id}"
        else:
            ts = int(timestamp)
            dt = datetime.fromtimestamp(ts, tz=timezone.utc)
            fname_base = f"{dt.strftime('%Y%m%d_%H%M%S')}_{station_id}"

        r = self._get({"station": station_id, "image": timestamp}, stream=True)
        if r.status_code != 200:
            print(f"  [!] Error {r.status_code} imagen {timestamp}")
            return None
        ct = r.headers.get("Content-Type", "")
        if "image" not in ct:
            print(f"  [!] No es imagen: {ct} — {r.text[:100]}")
            return None

        img_path = folder / f"{fname_base}.jpg"
        img_path.write_bytes(r.content)

        json_path = folder / f"{fname_base}.json"
        json_path.write_text(json.dumps(metadata or {}, indent=2, ensure_ascii=False))

        print(f"  [+] {station_name}/{fname_base}.jpg  ({len(r.content)//1024} KB)")
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
        Descarga imágenes + JSON de metadatos en un rango de fechas.
        Si hour_filter != None, descarga solo las imágenes de esa hora (prioridad 12:00h).
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
    parser.add_argument("--station",  default=None, help="ID de estación (ej: 8213 para CAM 1)")
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

    # Listar cámaras (excluye BOYAs)
    print("=== Cámaras disponibles ===")
    stations = client.list_stations(cameras_only=True)
    for s in stations:
        print(f"  {s['id']:>6}  {s['name']}  ({s['latitude']}, {s['longitude']})")

    if not stations:
        print("  [!] Sin cámaras. Verificar credenciales.")
        sys.exit(1)

    station_id = args.station or stations[0]["id"]
    station_name = next((s["name"] for s in stations if s["id"] == station_id), station_id)
    print(f"\n=== Datos de {station_name} (id={station_id}) ===")

    if args.download:
        if args.from_dt and args.to_dt:
            hour = None if args.all_hours else 12
            saved = client.download_range(
                station_id, station_name, args.from_dt, args.to_dt, out_dir, hour_filter=hour
            )
            print(f"\n{len(saved)} imágenes descargadas en {out_dir}/{station_name.replace(' ', '_')}/")
        else:
            print("Descargando última imagen...")
            latest_data = client.get_station_data(station_id, latest_hours=1, tz="local")
            points = latest_data.get("data", [])
            meta = points[-1] if points else {}
            client.download_image(station_id, station_name, "latest", out_dir, metadata=meta)
    else:
        # Mostrar metadatos / últimas observaciones
        latest = args.latest or 24
        data = client.get_station_data(station_id, latest_hours=latest, tz="local")
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
