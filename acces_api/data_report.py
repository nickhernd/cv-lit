import json
import pandas as pd
from pathlib import Path
from datetime import datetime

def generate_report(data_dir):
    data_dir = Path(data_dir)
    report_data = []

    for cam_dir in data_dir.glob("CAM_*"):
        json_dir = cam_dir / "json"
        if not json_dir.exists(): continue

        json_files = list(json_dir.glob("*.json"))
        total = len(json_files)
        valid = 0
        batteries = []
        
        for jf in json_files:
            with open(jf, "r") as f:
                data = json.load(f)
                if data.get("invalid") == 0:
                    valid += 1
                bat = data.get("battery")
                if bat is not None:
                    batteries.append(bat)
        
        report_data.append({
            "Cam": cam_dir.name,
            "Total": total,
            "Valid %": (valid / total * 100) if total > 0 else 0,
            "Avg Battery": (sum(batteries) / len(batteries)) if batteries else None
        })

    df = pd.DataFrame(report_data)
    print("=== Informe de Disponibilidad de Datos ===")
    print(df.to_string(index=False))
    
    # Guardar reporte
    out_file = data_dir.parent / "logs" / f"report_{datetime.now().strftime('%Y%m%d')}.csv"
    out_file.parent.mkdir(parents=True, exist_ok=True)  # to_csv no crea el directorio padre
    df.to_csv(out_file, index=False)
    print(f"\nReporte guardado en: {out_file}")

if __name__ == "__main__":
    import sys
    d = sys.argv[1] if len(sys.argv) > 1 else "data/raw"
    generate_report(d)
