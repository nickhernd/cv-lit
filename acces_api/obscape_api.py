"""
Cliente para la API de Obscape.
Descarga imagenes y metadatos de estaciones de camaras fijas.

Uso:
    python obscape_api.py                                             # listar camaras
    python obscape_api.py --download                                  # ultima imagen de cada camara
    python obscape_api.py --download --all                            # Todo el historial de todas las camaras
    python obscape_api.py --station 8213 --download                   # ultima imagen de CAM 1
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
import csv
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

BASE_DIR = Path(__file__).parent.parent


def _load_dotenv(path: Path) -> None:
    """Carga pares KEY=VALUE de un .env a os.environ (sin pisar variables ya
    definidas en el entorno real). Sin dependencias externas — solo para no
    obligar a exportar OBSCAPE_USERNAME/OBSCAPE_API_KEY a mano cada sesión."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


_load_dotenv(BASE_DIR / ".env")

# ── Configuracion ──────────────────────────────────────────────────────────────
# Credenciales SIEMPRE desde entorno (variable real o .env local, nunca
# hardcodeadas en el código — ver .env.example en la raíz del repo).
API_URL  = "https://obscape.com/portal/api/v3/api"
USERNAME = os.environ.get("OBSCAPE_USERNAME")
API_KEY  = os.environ.get("OBSCAPE_API_KEY")

# Fecha de inicio del proyecto (limite para --all)
PROJECT_START = "2026-01-01T00:00:00"

# Directorios de salida
OUT_DIR  = BASE_DIR / "proces_images" / "data"
LOG_DIR  = BASE_DIR / "data" / "logs"

# ── Cliente API ────────────────────────────────────────────────────────────────

class ObscapeClient:
    def __init__(self, username: str = USERNAME, api_key: str = API_KEY):
        if not username or not api_key:
            raise RuntimeError(
                "Faltan credenciales de Obscape: define OBSCAPE_USERNAME y "
                "OBSCAPE_API_KEY (variables de entorno o en un .env en la raíz "
                "del repo, ver .env.example)."
            )
        self.username = username
        self.api_key  = api_key
        self.session  = requests.Session()
        self.session.headers.update({"User-Agent": "cv-lit/1.0"})
        
        # Configurar reintentos automaticos (Issue 99)
        retry_strategy = Retry(
            total=3,
            backoff_factor=2, # 2s, 4s, 8s
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET"]
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("https://", adapter)
        
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        self.log_file = LOG_DIR / "download_history.csv"
        self._init_log()

    def _init_log(self):
        """Inicializa el CSV de logs si no existe (Issue 100)."""
        if not self.log_file.exists():
            with open(self.log_file, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(["timestamp_proc", "cam_id", "cam_name", "img_timestamp", "status", "detail"])

    def log_event(self, cam_id, cam_name, img_ts, status, detail=""):
        """Registra un evento en el log (Issue 100)."""
        with open(self.log_file, "a", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([datetime.now().isoformat(), cam_id, cam_name, img_ts, status, detail])

    def _get(self, params: dict, stream: bool = False) -> requests.Response:
        params = {"username": self.username, "key": self.api_key, **params}
        r = self.session.get(API_URL, params=params, stream=stream, timeout=30)
        return r

    def list_stations(self, cameras_only: bool = True) -> list[dict]:
        """Devuelve las estaciones. Si cameras_only=True filtra solo CAM*."""
        try:
            r = self._get({})
            r.raise_for_status()
            data = r.json()
            if not isinstance(data, list):
                return []
            if cameras_only:
                data = [s for s in data if s.get("name", "").upper().startswith("CAM")]
            return data
        except Exception as e:
            print(f"  [!] Error listando estaciones: {e}")
            return []

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

    def check_health(self, station_name: str, metadata: dict):
        """Alertas de estado de la camara (Issue 101)."""
        # Metadatos tipicos: battery (V), rssi (dBm), tilt (deg)
        bat = metadata.get("battery")
        rssi = metadata.get("rssi")
        if bat is not None and bat < 11.5:
            print(f"  [WARNING] Bateria BAJA en {station_name}: {bat}V")
        if rssi is not None and rssi < -90:
            print(f"  [WARNING] Senal DEBIL en {station_name}: {rssi}dBm")

    def download_image(
        self,
        station_id: str,
        station_name: str,
        timestamp: int | str,
        base_out_dir: Path,
        metadata: dict | None = None,
    ) -> tuple[Path | None, bool]:
        """
        Descarga una imagen y su JSON de metadatos.
        Retorna (path, is_new)
        """
        cam_folder  = base_out_dir / station_name.replace(" ", "_")
        img_folder  = cam_folder / "images"
        json_folder = cam_folder / "json"
        img_folder.mkdir(parents=True, exist_ok=True)
        json_folder.mkdir(parents=True, exist_ok=True)

        # Determinar nombre de fichero
        ts_val = timestamp
        if timestamp == "latest":
            ts_val = (metadata or {}).get("time") or "latest"
            if ts_val != "latest":
                dt = datetime.fromtimestamp(int(ts_val), tz=timezone.utc)
                fname_base = f"{dt.strftime('%Y%m%d_%H%M%S')}_{station_id}"
            else:
                fname_base = f"latest_{station_id}"
        else:
            ts = int(timestamp)
            dt = datetime.fromtimestamp(ts, tz=timezone.utc)
            fname_base = f"{dt.strftime('%Y%m%d_%H%M%S')}_{station_id}"

        img_path  = img_folder  / f"{fname_base}.jpg"
        json_path = json_folder / f"{fname_base}.json"

        # Control de duplicados (Issue 98)
        if img_path.exists():
            print(f"  [=] Ya existe {station_name}/{fname_base}.jpg")
            return img_path, False

        try:
            # Monitoreo de salud (Issue 101)
            if metadata:
                self.check_health(station_name, metadata)

            r = self._get({"station": station_id, "image": timestamp}, stream=True)
            if r.status_code != 200:
                self.log_event(station_id, station_name, ts_val, "ERROR", f"HTTP {r.status_code}")
                print(f"  [!] Error {r.status_code} imagen {timestamp}")
                return None, False
            
            ct = r.headers.get("Content-Type", "")
            if "image" not in ct:
                self.log_event(station_id, station_name, ts_val, "ERROR", f"Invalid content-type: {ct}")
                print(f"  [!] No es imagen: {ct}")
                return None, False

            img_path.write_bytes(r.content)
            json_path.write_text(json.dumps(metadata or {}, indent=2, ensure_ascii=False))

            self.log_event(station_id, station_name, ts_val, "OK")
            print(f"  [+] {station_name}/images/{fname_base}.jpg")
            return img_path, True
        except Exception as e:
            self.log_event(station_id, station_name, ts_val, "ERROR", str(e))
            print(f"  [!] Excepcion: {e}")
            return None, False

    def download_image_flat(
        self,
        station_id: str,
        serial: str,
        timestamp: int,
        out_dir: Path,
    ) -> tuple[Path | None, bool]:
        """
        Variante de download_image() para consumidores que guardan las imágenes
        planas en una sola carpeta por cámara (sin subcarpetas images/+json/),
        nombradas "<epoch>_<YYYYMMDD>_<HHMMSS>_<serial>.jpg" — el formato que
        reconoce backend/main.py (FILENAME_TS_RE) para leer la fecha de captura
        directamente del nombre de archivo. Usado por backend/auto_mode.py.
        Retorna (path, is_new).
        """
        out_dir.mkdir(parents=True, exist_ok=True)
        ts = int(timestamp)
        dt = datetime.fromtimestamp(ts, tz=timezone.utc)
        img_path = out_dir / f"{ts}_{dt.strftime('%Y%m%d_%H%M%S')}_{serial}.jpg"

        if img_path.exists():
            return img_path, False

        try:
            r = self._get({"station": station_id, "image": ts}, stream=True)
            if r.status_code != 200:
                self.log_event(station_id, serial, ts, "ERROR", f"HTTP {r.status_code}")
                return None, False
            ct = r.headers.get("Content-Type", "")
            if "image" not in ct:
                self.log_event(station_id, serial, ts, "ERROR", f"Invalid content-type: {ct}")
                return None, False
            img_path.write_bytes(r.content)
            self.log_event(station_id, serial, ts, "OK")
            return img_path, True
        except Exception as e:
            self.log_event(station_id, serial, ts, "ERROR", str(e))
            return None, False

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
        Descarga imagenes + JSON en un rango de fechas.
        Retorna lista de nuevos paths descargados.
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
            path, is_new = self.download_image(station_id, station_name, ts, base_out_dir, metadata=meta)
            if is_new and path:
                saved.append(path)
        return saved


# ── CLI ────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Cliente API Obscape")
    parser.add_argument("--station",   default=None,
                        help="ID de estacion (ej: 8213 para CAM 1)")
    parser.add_argument("--from",      dest="from_dt", default=None,
                        help="Fecha inicio yyyy-mm-dd o yyyy-mm-ddThh:mm:ss")
    parser.add_argument("--to",        dest="to_dt", default=None,
                        help="Fecha fin yyyy-mm-dd o yyyy-mm-ddThh:mm:ss")
    parser.add_argument("--latest",    type=int, default=None,
                        help="Ultimas N horas (solo visualizacion)")
    parser.add_argument("--download",  action="store_true",
                        help="Descargar imagenes")
    parser.add_argument("--all",       dest="all_data", action="store_true",
                        help="Descargar TODO el historial (todas las camaras, todas las horas)")
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

    # Listar camaras
    print("=== Camaras disponibles ===")
    stations = client.list_stations(cameras_only=True)
    for s in stations:
        print(f"  {s['id']:>6}  {s['name']}  ({s['latitude']}, {s['longitude']})")

    if not stations:
        print("  [!] Sin camaras. Verificar credenciales.")
        sys.exit(1)

    # Seleccionar estaciones objetivo
    if args.station:
        target_stations = [s for s in stations if s["id"] == args.station]
        if not target_stations:
            print(f"  [!] Estacion {args.station} no encontrada.")
            sys.exit(1)
    else:
        target_stations = stations

    # ── Descarga ──────────────────────────────────────────────────────────────

    if args.all_data:
        # Descargar TODO el historial: desde PROJECT_START hasta hoy, todas las horas
        to_dt = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        total = 0
        print(f"\n=== Descarga completa ({PROJECT_START} -> {to_dt}) ===")
        for s in target_stations:
            print(f"\n--- {s['name']} (id={s['id']}) ---")
            saved = client.download_range(
                s["id"], s["name"], PROJECT_START, to_dt, out_dir, hour_filter=None
            )
            total += len(saved)
            print(f"  {len(saved)} imagenes -> {out_dir}/{s['name'].replace(' ', '_')}/")
        print(f"\nTotal: {total} imagenes descargadas.")

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
                print(f"  {len(saved)} imagenes -> {out_dir}/{s['name'].replace(' ', '_')}/")
            print(f"\nTotal: {total} imagenes descargadas.")
        else:
            print("\nDescargando ultima imagen de cada camara...")
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
            print(f"Parametros: {[p['name'] for p in params_info]}")
            print(f"Puntos en las ultimas {latest}h: {len(points)}")
            if points:
                print("Ultimos 3 puntos:")
                for pt in points[-3:]:
                    print(f"  {pt}")


if __name__ == "__main__":
    main()
