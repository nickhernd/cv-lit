"""Entrena un modelo YOLO-seg (ultralytics) sobre el dataset de línea húmeda
generado por scripts/export_yolo_dataset.py.

Es un envoltorio fino sobre la API de entrenamiento de ultralytics — no hace
nada que `yolo segment train data=... model=...` no haga ya, solo fija unos
valores por defecto razonables para este caso de uso (dataset pequeño, una
sola clase) y deja el resultado en un sitio predecible.

Modelo base: yolov8n-seg.pt (el más pequeño de la familia-seg) por defecto —
con pocas decenas de imágenes de entrenamiento (el objetivo inicial de la
reunión es ~20 por cámara) un modelo grande sobreajusta enseguida; empezar
por el más pequeño y solo subir de tamaño si hace falta, con más datos.

Uso:
    python scripts/train_yolo_segmentation.py --data training_dataset/linea_humeda/data.yaml
    python scripts/train_yolo_segmentation.py --data ... --epochs 100 --model yolov8s-seg.pt

Salida: pesos entrenados en runs/segment/<name>/weights/best.pt (ruta que
imprime ultralytics al terminar).
"""
import argparse

from ultralytics import YOLO


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", required=True, help="Ruta al data.yaml generado por export_yolo_dataset.py")
    ap.add_argument("--model", default="yolov8n-seg.pt",
                    help="Modelo base de partida (por defecto el más pequeño de la familia -seg)")
    ap.add_argument("--epochs", type=int, default=100)
    ap.add_argument("--imgsz", type=int, default=960,
                    help="Tamaño de imagen de entrenamiento — las fotos reales son ~4600px de ancho, "
                         "se reescalan; 960 es un punto de partida razonable para no agotar memoria")
    ap.add_argument("--batch", type=int, default=4,
                    help="Tamaño de lote — bajo por defecto porque las imágenes de origen son grandes")
    ap.add_argument("--device", default=None,
                    help="'0' para la primera GPU, 'cpu' para forzar CPU — sin especificar, ultralytics "
                         "elige GPU si hay una disponible")
    ap.add_argument("--name", default="linea_humeda",
                    help="Nombre de la carpeta de resultados (runs/segment/<name>)")
    args = ap.parse_args()

    model = YOLO(args.model)
    model.train(
        data=args.data,
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        device=args.device,
        name=args.name,
    )


if __name__ == "__main__":
    main()
