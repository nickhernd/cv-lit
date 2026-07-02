#!/usr/bin/env python3
"""
auto_process_noon.py — Procesamiento automático de imágenes de las 12:00h (#91).

Para cada cámara (1-6) busca la imagen más cercana a mediodía de hoy,
llama a la API de análisis y guarda el resultado GeoJSON.

Uso manual:
    python scripts/auto_process_noon.py
    python scripts/auto_process_noon.py --date 2026-06-01
    python scripts/auto_process_noon.py --api http://localhost:8000

Configurar en crontab:
    crontab: 0 12 * * * cd /home/nickhernd/Desktop/cv-lit && python scripts/auto_process_noon.py >> /tmp/cv_lit_noon.log 2>&1
"""

import argparse
import datetime
import json
import logging
import os
import re
import sys
from pathlib import Path

import requests

ROOT     = Path(__file__).parent.parent
DATA_DIR = ROOT / "proces_images" / "data"
LOG_FILE = Path("/tmp/cv_lit_noon.log")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
    ],
)
log = logging.getLogger(__name__)

CAM_FOLDERS = {
    1: "camera1",
    2: "camera2",
    3: "camera3",
    4: "camera4",
    5: "camera5",
    6: "camera6",
}

# También buscar en proces_images/CAM_X/images/ (imágenes de demo)
CAM_DEMO_FOLDERS = {i: ROOT / "proces_images" / f"CAM_{i}" / "images" for i in range(1, 7)}


def _parse_timestamp(filename: str) -> datetime.datetime | None:
    """Extrae timestamp del nombre de fichero. Soporta formato YYYYMMDD_HHMMSS_* y unix-ts."""
    # Formato 20260303_130000_8213.jpg
    m = re.search(r"(\d{8})_(\d{6})", filename)
    if m:
        try:
            return datetime.datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M%S")
        except ValueError:
            pass
    # Formato unix timestamp al inicio: 1779788400_...
    m2 = re.match(r"^(\d{10})_", filename)
    if m2:
        try:
            return datetime.datetime.fromtimestamp(int(m2.group(1)))
        except (ValueError, OSError):
            pass
    return None


def find_noon_image(cam_id: int, target_date: datetime.date) -> Path | None:
    """
    Busca la imagen más cercana a las 12:00h del día dado para la cámara.
    Busca primero en datos reales, luego en imágenes de demo.
    """
    noon = datetime.datetime.combine(target_date, datetime.time(12, 0, 0))
    candidates: list[tuple[float, Path]] = []

    for search_dir in [
        DATA_DIR / CAM_FOLDERS.get(cam_id, f"camera{cam_id}"),
        CAM_DEMO_FOLDERS[cam_id],
    ]:
        if not search_dir.exists():
            continue
        for p in search_dir.iterdir():
            if not p.suffix.lower() in (".jpg", ".jpeg", ".png"):
                continue
            ts = _parse_timestamp(p.name)
            if ts is None:
                continue
            if ts.date() != target_date:
                continue
            diff = abs((ts - noon).total_seconds())
            candidates.append((diff, p))

    if not candidates:
        return None
    candidates.sort(key=lambda x: x[0])
    return candidates[0][1]


def process_camera(cam_id: int, image_path: Path, api: str) -> dict:
    """Llama a POST /api/cameras/{cam_id}/analyze-roi y devuelve el resultado."""
    url = f"{api}/api/cameras/{cam_id}/analyze-roi"
    try:
        resp = requests.post(url, params={"filename": image_path.name}, timeout=120)
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as e:
        return {"error": str(e)}


def main():
    ap = argparse.ArgumentParser(description="Procesamiento automático mediodía CV-LIT")
    ap.add_argument("--date", default=None,
                    help="Fecha a procesar YYYY-MM-DD (por defecto: hoy)")
    ap.add_argument("--api", default="http://localhost:8000",
                    help="URL base de la API (default: http://localhost:8000)")
    ap.add_argument("--cams", nargs="+", type=int, default=list(range(1, 7)),
                    help="Cámaras a procesar (default: 1-6)")
    args = ap.parse_args()

    target_date = (datetime.date.fromisoformat(args.date)
                   if args.date else datetime.date.today())

    log.info("═" * 60)
    log.info(f"CV-LIT procesamiento automático mediodía — {target_date}")
    log.info(f"API: {args.api}  |  Cámaras: {args.cams}")
    log.info("═" * 60)

    summary = {}

    for cam_id in args.cams:
        img_path = find_noon_image(cam_id, target_date)
        if img_path is None:
            log.warning(f"CAM_{cam_id}: no se encontró imagen para {target_date}")
            summary[f"CAM_{cam_id}"] = {"status": "no_image"}
            continue

        log.info(f"CAM_{cam_id}: procesando {img_path.name}")
        result = process_camera(cam_id, img_path, args.api)

        if "error" in result:
            log.error(f"CAM_{cam_id}: error de API — {result['error']}")
            summary[f"CAM_{cam_id}"] = {"status": "api_error", "error": result["error"]}
        elif result.get("rejected"):
            log.warning(f"CAM_{cam_id}: rechazada — {result.get('reject_reason')}")
            summary[f"CAM_{cam_id}"] = {"status": "rejected", **result}
        else:
            log.info(f"CAM_{cam_id}: OK — área={result.get('dry_area_m2')} m²  "
                     f"confianza={result.get('confidence')}  puntos={result.get('points_utm')}")
            summary[f"CAM_{cam_id}"] = {"status": "ok", **result}

    # Guardar resumen del día
    summary_path = ROOT / "proces_images" / "data" / f"noon_summary_{target_date}.json"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    with open(summary_path, "w") as f:
        json.dump({"date": str(target_date), "cameras": summary}, f, indent=2)
    log.info(f"Resumen guardado en {summary_path}")

    ok  = sum(1 for v in summary.values() if v["status"] == "ok")
    err = len(summary) - ok
    log.info(f"Finalizado: {ok} cámaras procesadas, {err} errores/rechazos")


if __name__ == "__main__":
    main()
