#!/bin/bash
# Commit de las implementaciones de Mes 5 y Mes 6
# Ejecutar desde la raíz del proyecto: bash scripts/commit_mes56.sh

git add \
  proces_images/cam_thresholds.py \
  backend/main.py \
  frontend/src/components/CoastlineAnalysis.vue \
  frontend/src/App.vue \
  scripts/auto_process_noon.py \
  calibration/cam_1_profile.yaml \
  calibration/cam_2_profile.yaml \
  calibration/cam_3_profile.yaml \
  calibration/cam_4_profile.yaml \
  calibration/cam_5_profile.yaml \
  calibration/cam_6_profile.yaml \
  docs/user_manual.md

git commit -m "feat: implementar issues Mes 5 y Mes 6

- #79: auto-rechazo por confianza baja en analyze-roi
- #80: umbrales SAM por cámara (cam_thresholds.py)
- #81: fallback Otsu cuando SAM y color-fallback fallan
- #82 #84 #85 #86 #87: CoastlineAnalysis.vue con selector
  de imagen, overlay segmentación, métricas y export GeoJSON
- #91: script auto_process_noon.py para cron a las 12:00h
- #93: perfiles YAML de calibración para las 6 cámaras
- #94: manual de usuario en docs/user_manual.md"
