import os
import sys
from pathlib import Path
from homography.align_images import run as run_alignment

# Configuración de rutas
DATA_DIR = Path("proces_images/data")
OUTPUT_BASE = Path("proces_images/output")

def get_cameras():
    if not DATA_DIR.exists():
        return []
    return [d.name for d in DATA_DIR.iterdir() if d.is_dir() and d.name.startswith("CAM_")]

def get_images(cam_dir):
    extensions = ["*.jpg", "*.jpeg", "*.JPG", "*.JPEG"]
    paths = []
    for ext in extensions:
        paths.extend(cam_dir.glob(ext))
    return sorted(paths)

def main():
    print("\n--- Herramienta de Alineación por Cámara ---")
    
    # 1. Seleccionar Cámara
    cameras = get_cameras()
    if not cameras:
        print("No se encontraron carpetas de cámaras en:", DATA_DIR)
        return

    print("\nCámaras disponibles:")
    for i, cam in enumerate(cameras):
        print(f"{i+1}. {cam}")
    
    choice = input("\nSelecciona el número de la cámara: ")
    try:
        cam_idx = int(choice) - 1
        selected_cam = cameras[cam_idx]
    except (ValueError, IndexError):
        print("Selección inválida.")
        return

    cam_path = DATA_DIR / selected_cam / "images"
    images = get_images(cam_path)
    
    if not images:
        print(f"No se encontraron imágenes en {cam_path}")
        return

    # 2. Seleccionar Imagen de Referencia
    print(f"\nImágenes encontradas para {selected_cam}: {len(images)}")
    print("0. Usar primera imagen como referencia (default)")
    for i, img in enumerate(images[:10]): # Mostrar primeras 10
        print(f"{i+1}. {img.name}")
    
    ref_choice = input("\nSelecciona el número de la imagen de referencia (o 0): ")
    
    ref_image = None
    try:
        ref_idx = int(ref_choice)
        if ref_idx > 0:
            ref_image = images[ref_idx - 1]
    except ValueError:
        pass
    
    # 3. Ejecutar
    output_dir = OUTPUT_BASE / selected_cam / "aligned_output"
    print(f"\nEjecutando alineación para {selected_cam}...")
    print(f"Referencia: {ref_image.name if ref_image else 'Automática (primera)'}")
    
    run_alignment(cam_path, output_dir, ref_image)
    print(f"\nProceso finalizado. Resultados en: {output_dir}")

if __name__ == "__main__":
    main()
