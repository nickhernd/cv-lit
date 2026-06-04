import cv2
import numpy as np
import json
from pathlib import Path

def is_too_dark(image, threshold=30):
    """Detecta si la imagen es demasiado oscura (noche/obstrucción)."""
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    v_channel = hsv[:, :, 2]
    avg_brightness = np.mean(v_channel)
    return avg_brightness < threshold, avg_brightness

def is_blurry(image, threshold=100):
    """Detecta si la imagen está borrosa usando la varianza del Laplaciano."""
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    variance = cv2.Laplacian(gray, cv2.CV_64F).var()
    return variance < threshold, variance

def has_artifacts(image, threshold=0.05):
    """Detecta píxeles saturados (quemados) que podrían ser artefactos."""
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    saturated = np.sum(gray > 250) / gray.size
    return saturated > threshold, saturated

def process_image_quality(img_path, json_path):
    """Analiza la calidad y marca el JSON si es inválida."""
    image = cv2.imread(str(img_path))
    if image is None:
        return False, "Error al leer imagen"

    dark, brightness = is_too_dark(image)
    blurry, variance = is_blurry(image)
    artifacts, saturation = has_artifacts(image)

    invalid = dark or blurry or artifacts
    reasons = []
    if dark: reasons.append(f"oscura ({brightness:.1f})")
    if blurry: reasons.append(f"borrosa ({variance:.1f})")
    if artifacts: reasons.append(f"artefactos ({saturation:.2%})")

    # Actualizar JSON
    if json_path.exists():
        with open(json_path, "r") as f:
            data = json.load(f)
        
        data["quality_metrics"] = {
            "brightness": float(brightness),
            "laplacian_variance": float(variance),
            "saturation_ratio": float(saturation)
        }
        data["invalid"] = 1 if invalid else 0
        data["invalid_reason"] = ", ".join(reasons) if invalid else ""

        with open(json_path, "w") as f:
            json.dump(data, f, indent=2)

    return not invalid, ", ".join(reasons)

if __name__ == "__main__":
    # Ejemplo de uso
    import sys
    if len(sys.argv) > 1:
        p = Path(sys.argv[1])
        j = p.with_suffix(".json") # Asume json al lado o en carpeta json
        # Buscar en carpeta json si no existe
        if not j.exists():
            j = p.parent.parent / "json" / (p.stem + ".json")
        
        ok, reason = process_image_quality(p, j)
        print(f"Imagen: {p.name} | Válida: {ok} | Motivo: {reason}")
