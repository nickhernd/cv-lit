"""
Script para ejecución programada (Cron).
Descarga la imagen de las 12:00h de todas las cámaras disponibles.
"""

from datetime import datetime, timedelta
from pathlib import Path
from obscape_api import ObscapeClient, OUT_DIR

def main():
    client = ObscapeClient()
    stations = client.list_stations(cameras_only=True)
    
    if not stations:
        print("[!] No se encontraron estaciones disponibles.")
        return

    # Usamos el día de ayer para asegurar que la imagen de las 12:00 ya esté procesada/disponible
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    
    print(f"=== Ejecución programada: {datetime.now().isoformat()} ===")
    print(f"Buscando imágenes del día: {yesterday} a las 12:00h")
    
    for s in stations:
        print(f"\n--- Procesando {s['name']} (id={s['id']}) ---")
        # download_range con hour_filter=12 descargará solo la de las 12:00
        client.download_range(
            s["id"], 
            s["name"], 
            from_dt=f"{yesterday}T00:00:00", 
            to_dt=f"{yesterday}T23:59:59", 
            base_out_dir=OUT_DIR,
            hour_filter=12
        )

if __name__ == "__main__":
    main()
