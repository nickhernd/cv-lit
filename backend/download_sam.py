"""Descarga el checkpoint del modelo SAM (segmentación con IA), opcional: la
app funciona sin él (cae a color_fallback/Otsu, ver get_segmenter() en
main.py), así que esto no es un requisito de arranque sino una mejora que el
usuario puede instalar cuando quiera — desde el instalador (tarea opcional,
ver installer/cv-lit.iss) o ejecutando este script/exe a mano más tarde.

Solo usa la librería estándar (urllib) para poder congelarse en un .exe
diminuto aparte del principal, sin arrastrar el resto de dependencias pesadas
del backend.

Uso:
    python download_sam.py [--dest RUTA]

Sin --dest, se guarda junto a este propio script/exe (backend/ en
desarrollo, la carpeta de instalación en la app empaquetada) — el mismo sitio
donde main.py busca sam_vit_h_4b8939.pth (ver BASE_DIR en backend/main.py).
"""
import argparse
import os
import sys
import urllib.request

SAM_URL = "https://dl.fbaipublicfiles.com/segment_anything/sam_vit_h_4b8939.pth"
SAM_FILENAME = "sam_vit_h_4b8939.pth"
# El checkpoint real ronda 2.56 GB — se usa para el aviso de tamaño y como
# referencia aproximada de progreso si el servidor no informa Content-Length.
EXPECTED_SIZE_BYTES = 2_564_550_879


def _default_dest_dir() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def _format_mb(n: int) -> str:
    return f"{n / (1024 * 1024):,.0f} MB"


def download_checkpoint(dest_dir: str | None = None, progress_cb=None) -> str:
    """Descarga el checkpoint a dest_dir (por defecto, junto al ejecutable).
    Escribe primero a un .part y renombra al terminar, para que una descarga
    interrumpida nunca deje un archivo a medias que la app confunda con uno
    válido. progress_cb(downloaded_bytes, total_bytes) se llama en cada chunk,
    si se proporciona. Devuelve la ruta final del checkpoint."""
    dest_dir = dest_dir or _default_dest_dir()
    os.makedirs(dest_dir, exist_ok=True)
    final_path = os.path.join(dest_dir, SAM_FILENAME)
    part_path = final_path + ".part"

    if os.path.exists(final_path):
        return final_path  # ya descargado, nada que hacer

    with urllib.request.urlopen(SAM_URL) as resp, open(part_path, "wb") as out:
        total = int(resp.headers.get("Content-Length") or EXPECTED_SIZE_BYTES)
        downloaded = 0
        chunk_size = 1024 * 1024  # 1 MB
        while True:
            chunk = resp.read(chunk_size)
            if not chunk:
                break
            out.write(chunk)
            downloaded += len(chunk)
            if progress_cb:
                progress_cb(downloaded, total)

    os.replace(part_path, final_path)  # atómico: o queda el archivo completo, o no queda nada
    return final_path


def _cli_progress(downloaded: int, total: int) -> None:
    pct = (downloaded / total * 100) if total else 0
    print(f"\rDescargando SAM: {_format_mb(downloaded)} / {_format_mb(total)} ({pct:.1f}%)", end="", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Descarga el checkpoint SAM (vit_h, ~2.4 GB) para Línea de Costa.")
    parser.add_argument("--dest", default=None, help="Carpeta destino (por defecto, junto al ejecutable)")
    args = parser.parse_args()

    dest_dir = args.dest or _default_dest_dir()
    final_path = os.path.join(dest_dir, SAM_FILENAME)
    if os.path.exists(final_path):
        print(f"Ya existe: {final_path}")
        return

    print(f"Descargando el modelo de segmentación con IA (SAM, ~{_format_mb(EXPECTED_SIZE_BYTES)}) a:\n  {dest_dir}")
    try:
        path = download_checkpoint(dest_dir, progress_cb=_cli_progress)
    except Exception as e:
        print(f"\n[ERROR] No se pudo descargar el modelo: {e}")
        sys.exit(1)
    print(f"\nListo: {path}")


if __name__ == "__main__":
    main()
