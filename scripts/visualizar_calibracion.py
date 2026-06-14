#!/usr/bin/env python3
import os
import subprocess
import sys

# Configuración
IMG_DIR = "proces_images/CAM_1/images"
TOOL_PATH = "proces_images/calibration_tool.py"

def main():
    if not os.path.exists(IMG_DIR):
        print(f"Error: No se encuentra el directorio de imágenes {IMG_DIR}")
        return

    # Buscar la primera imagen .jpg
    fotos = [f for f in os.listdir(IMG_DIR) if f.lower().endswith(".jpg")]
    if not fotos:
        print(f"No hay imágenes en {IMG_DIR}")
        return

    fotos.sort() # Ordenarlas para consistencia
    img_path = os.path.join(IMG_DIR, fotos[0])

    print(f"--- Lanzador de Calibración Visual ---")
    print(f"Imagen seleccionada: {img_path}")
    print("\nCONTROLES DE LA VENTANA:")
    print("  - Click IZQUIERDO : Añadir punto de CALIBRACIÓN (Verde)")
    print("  - Click DERECHO   : Añadir punto de VALIDACIÓN (Azul)")
    print("  - Tecla 'h'       : Calcular Homografía (verás el error RMSE)")
    print("  - Tecla 's'       : Guardar perfil en 'calibration/'")
    print("  - Tecla 'p'       : Guardar imagen de diagnóstico (vectores de error)")
    print("  - Tecla 'q'       : Salir")
    print("\nAl hacer click, introduce las coordenadas UTM en esta terminal.")
    print("Ejemplo de coordenadas para prueba: 711000 4209000")
    print("-" * 40)

    # Ejecutar la herramienta
    cmd = [sys.executable, TOOL_PATH, "--cam", "1", "--image", img_path]
    try:
        subprocess.run(cmd)
    except KeyboardInterrupt:
        print("\nCerrando...")

if __name__ == "__main__":
    main()
