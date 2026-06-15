#!/bin/bash

# setup_weights.sh - Descarga los pesos de SAM (Segment Anything Model)
# Modelo: ViT-H (El mas grande y preciso)

WEIGHTS_FILE="sam_vit_h_4b8939.pth"
URL="https://dl.fbaipublicfiles.com/segment_anything/sam_vit_h_4b8939.pth"

echo "=== CV-LIT: Configuración de Pesos de IA ==="

if [ -f "$WEIGHTS_FILE" ]; then
    echo "[OK] El archivo $WEIGHTS_FILE ya existe."
    exit 0
fi

echo "[.] Descargando pesos de SAM (2.4 GB)..."
echo "[!] Esto puede tardar varios minutos dependiendo de tu conexión."

if command -v wget &> /dev/null; then
    wget -O "$WEIGHTS_FILE" "$URL"
elif command -v curl &> /dev/null; then
    curl -L -o "$WEIGHTS_FILE" "$URL"
else
    echo "[FAILED] No se encontró wget ni curl. Por favor instala uno de ellos o descarga el archivo manualmente desde:"
    echo "$URL"
    exit 1
fi

if [ $? -eq 0 ]; then
    echo "[OK] Pesos descargados correctamente."
else
    echo "[FAILED] Error en la descarga."
    exit 1
fi
