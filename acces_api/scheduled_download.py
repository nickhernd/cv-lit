"""
Script para ejecución programada (Cron).
Descarga la imagen de las 12:00h de todas las cámaras disponibles.
"""

import argparse
from datetime import datetime, timedelta
from pathlib import Path
from obscape_api import ObscapeClient, OUT_DIR

def main():
    parser = argparse.ArgumentParser(description="Descarga programada de imágenes (rolling window)")
    def hour_type(x):
        if x.lower() == 'all':
            return None
        return int(x)

    parser.add_argument("--days", type=int, default=14, help="Número de días hacia atrás a revisar (defecto: 14)")
    parser.add_argument("--hour", type=hour_type, default=12, help="Hora específica (0-23) o 'all' para todas (defecto: 12)")
    args = parser.parse_args()

    client = ObscapeClient()
    stations = client.list_stations(cameras_only=True)
    
    if not stations:
        print("[!] No se encontraron estaciones disponibles.")
        return

    # Calcular rango: desde X días atrás hasta hoy
    to_date = datetime.now()
    from_date = to_date - timedelta(days=args.days)
    
    from_str = from_date.strftime("%Y-%m-%dT00:00:00")
    to_str = to_date.strftime("%Y-%m-%dT23:59:59")
    
    print(f"=== Ejecución programada: {datetime.now().isoformat()} ===")
    print(f"Ventana de revisión: {args.days} días ({from_str} -> {to_str})")
    print(f"Filtro horario: {args.hour if args.hour is not None else 'Todas'}h")
    
    total_new = 0

    for s in stations:
        print(f"\n--- Cámara: {s['name']} (id={s['id']}) ---")
        
        saved_paths = client.download_range(
            s["id"], 
            s["name"], 
            from_dt=from_str, 
            to_dt=to_str, 
            base_out_dir=OUT_DIR,
            hour_filter=args.hour
        )
        
        new_images = len(saved_paths)
        total_new += new_images
        print(f"  > Imágenes nuevas en esta ejecución: {new_images}")

    print("\n" + "="*40)
    print(f"RESUMEN FINAL")
    print(f"Total imágenes nuevas descargadas: {total_new}")
    print(f"Las imágenes que ya existían fueron omitidas automáticamente.")
    print("="*40)

if __name__ == "__main__":
    main()
