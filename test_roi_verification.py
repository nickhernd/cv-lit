import cv2
import numpy as np
import json

# ROI config
roi_config = {
  "CAM_1": {"x_min": 0, "y_min": 400, "x_max": 1920, "y_max": 1080},
  "CAM_2": {"x_min": 0, "y_min": 350, "x_max": 1920, "y_max": 1080},
  "CAM_3": {"x_min": 0, "y_min": 450, "x_max": 1920, "y_max": 1080},
  "CAM_4": {"x_min": 0, "y_min": 400, "x_max": 1920, "y_max": 1080},
  "CAM_5": {"x_min": 0, "y_min": 380, "x_max": 1920, "y_max": 1080},
  "CAM_6": {"x_min": 0, "y_min": 420, "x_max": 1920, "y_max": 1080}
}

# Create dummy image (1920x1080)
img = np.zeros((1080, 1920, 3), dtype=np.uint8)
cv2.putText(img, "Original", (50, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)

# Visualize ROI for CAM_1
roi = roi_config["CAM_1"]
vis = img.copy()
cv2.rectangle(vis, (roi["x_min"], roi["y_min"]), (roi["x_max"], roi["y_max"]), (0, 255, 0), 3)
cv2.putText(vis, "ROI CAM 1", (roi["x_min"] + 10, roi["y_min"] + 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)

cv2.imwrite("test_roi_viz.png", vis)
print("Imagen de prueba guardada: test_roi_viz.png")
