#!/usr/bin/env python3
"""
recalibrate.py — Herramienta rápida para actualizar la homografía

Permite cargar un perfil existente y ajustar la posición de los GCPs
en una nueva imagen sin tener que volver a introducir las coordenadas UTM.

Uso:
  python recalibrate.py --cam 1 --image /ruta/nueva_imagen.jpg
"""
import cv2
import numpy as np
import json
import os
import argparse
from calibration_tool import CalibrationTool, CAMERAS, COLORS

class RecalibrateTool(CalibrationTool):
    def __init__(self, cam_idx: int, image_path: str):
        super().__init__(cam_idx, image_path)
        self.load_gcps()
        self.dragging_idx = -1

    def _mouse_callback(self, event, x, y, flags, param):
        # Implementar arrastre de puntos existentes
        if event == cv2.EVENT_LBUTTONDOWN:
            for i, gcp in enumerate(self.gcps):
                u, v = gcp["pixel"]
                if np.sqrt((x-u)**2 + (y-v)**2) < 15:
                    self.dragging_idx = i
                    break
        
        elif event == cv2.EVENT_MOUSEMOVE:
            if self.dragging_idx != -1:
                self.gcps[self.dragging_idx]["pixel"] = [x, y]
                self._render()
                cv2.imshow(self._win_name, self.display)
        
        elif event == cv2.EVENT_LBUTTONUP:
            if self.dragging_idx != -1:
                print(f"  Punto {self.gcps[self.dragging_idx]['label']} movido a ({x}, {y})")
                self.dragging_idx = -1
                self._render()
                cv2.imshow(self._win_name, self.display)

    def _render(self):
        super()._render()
        # Sobrescribir el panel de instrucciones
        panel_w = 360
        cv2.putText(self.display, "MODO RECALIBRACION RAPIDA", (14, 160),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 200, 255), 1, cv2.LINE_AA)
        cv2.putText(self.display, "Arrastra puntos con el raton", (14, 180),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1, cv2.LINE_AA)

def main():
    ap = argparse.ArgumentParser(description="Recalibración rápida de homografía")
    ap.add_argument("--cam", type=int, required=True, choices=range(1, 7))
    ap.add_argument("--image", type=str, required=True)
    args = ap.parse_args()

    tool = RecalibrateTool(args.cam, args.image)
    tool.run()

if __name__ == "__main__":
    main()
