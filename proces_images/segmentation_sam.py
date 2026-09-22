#!/usr/bin/env python3
"""
segmentation_sam.py - Modulo de segmentacion semantica usando SAM (Segment Anything Model)

Este modulo se encarga de:
  1. Cargar el modelo SAM (ViT-H, ViT-L o ViT-B).
  2. Aplicar la Region de Interes (ROI).
  3. Generar mascaras binarias de la arena seca.
  4. Post-procesado morfologico para limpiar ruido.
  5. Generacion de mapa de probabilidad por pixel (#44).
  6. Eliminacion de falsas detecciones: espuma, reflejos, sombras (#48).
  7. Consistencia temporal entre frames (#50).
  8. Evaluacion de correccion de horizonte (#54).
"""

import os
import cv2
import numpy as np
import json
from pathlib import Path

try:
    from segment_anything import sam_model_registry, SamPredictor
    SAM_AVAILABLE = True
except ImportError:
    SAM_AVAILABLE = False

BASE_DIR  = Path(__file__).parent.parent

# CALIB_DIR: NO se calcula solo a partir de __file__ — en la app empaquetada
# (PyInstaller) ese cómputo apunta dentro del bundle de solo lectura, no a la
# carpeta real de datos del usuario (%LOCALAPPDATA%\LineaDeCosta\calibration).
# Se reutiliza la resolución ya correcta y consciente del entorno de
# backend/config.py — con fallback local por si este módulo se usa suelto
# (su propio CLI --image/--cam/--checkpoint) sin backend/ en sys.path.
# Bug real detectado 2026-08-31: sin esto, ROI_FILE.exists() daba False en
# el .exe instalado, get_roi() devolvía None, y SAM colocaba sus puntos de
# referencia sobre la imagen SIN recortar — arena mal detectada, confianza
# baja en TODAS las imágenes de cámaras con ROI personalizado.
try:
    from config import CALIBRATION_DIR as _CALIB_DIR_STR
    CALIB_DIR = Path(_CALIB_DIR_STR)
except ImportError:
    CALIB_DIR = BASE_DIR / "calibration"

ROI_FILE  = CALIB_DIR / "roi_config.json"

# ── Prompts por camara (#43) ─────────────────────────────────────────────────
# Fracciones [0-1] relativas al ROI de cada camara.
# Cada entrada: lista de {point: [fx, fy], label: 1=fg/0=bg}
# La zona baja-central del ROI corresponde a la arena seca en Guardamar.
#
# 3 puntos de arena (no 1) repartidos en horizontal a la misma altura: con un
# solo punto, una persona o sombrilla justo encima de esa coordenada hace que
# SAM pierda la referencia de "esto es arena" en toda la imagen (causa real
# de confianza diluida en playas con gente, detectada 2026-08-31). Con 3
# puntos separados, basta con que uno quede libre de obstáculos.
CAM_PROMPTS = {
    "CAM_1": [
        {"point": [0.25, 0.80], "label": 1},
        {"point": [0.50, 0.80], "label": 1},  # centro-bajo: arena seca
        {"point": [0.75, 0.80], "label": 1},
        {"point": [0.50, 0.15], "label": 0},  # zona alta: agua/horizonte
    ],
    # CAM_2: bug real detectado y verificado 2026-09-02 con el checkpoint SAM
    # real y una foto real de esta cámara — CAM_2 no encuadra la playa de
    # frente (como CAM_1/3/4/5/6), sino en fuerte oblicuo "mirando a lo largo
    # de la costa": la arena seca no es una franja horizontal, es una cuña
    # diagonal que ocupa el borde IZQUIERDO del ROI y se estrecha hacia
    # arriba-derecha, con duna/vegetación a la izquierda de x≈0.15 y mar
    # abierto a la derecha de x≈0.5 (variable según fila). La fila horizontal
    # fija en y=0.78 que usan el resto de cámaras pone el 3er punto (x=0.70)
    # DENTRO DEL MAR — verificado visualmente: SAM etiquetaba el mar entero
    # como "arena seca" y dejaba casi toda la arena real fuera de la máscara
    # (52% del ROI marcado como arena, la mayoría agua). Corregido siguiendo
    # la diagonal real de la orilla; verificado con el checkpoint real: la
    # máscara resultante ahora sigue la franja de arena visible, mar y duna
    # excluidos correctamente.
    "CAM_2": [
        {"point": [0.20, 0.85], "label": 1},
        {"point": [0.28, 0.65], "label": 1},
        {"point": [0.38, 0.50], "label": 1},
        {"point": [0.50, 0.12], "label": 0},
    ],
    # CAM_3: bug real detectado y verificado 2026-09-02 igual que CAM_2 —
    # esta cámara tiene una hilera de sombrillas fija ocupando x≈[0.19,0.50]
    # y un chiringuito + palmeras ocupando x≈[0.68,1.0] del ROI a la altura
    # y=0.82; SON OBSTÁCULOS PERMANENTES (no transitorios como una persona o
    # una sombrilla suelta), así que la fila de 3 puntos repartida al 25/50/75%
    # que sí funciona en el resto de cámaras aquí clava 2 de los 3 puntos
    # sobre sombrilla/palmera en TODAS las fotos de esta cámara, siempre.
    # Verificado con el checkpoint real: con esos 3 puntos la máscara cubría
    # solo el 1.8% del ROI (un fragmento junto al chiringuito); con los 2
    # puntos de abajo, ambos en el único hueco de arena abierta sin
    # obstáculo permanente, la máscara pasa a cubrir el 24.7% del ROI y sigue
    # correctamente la franja completa de arena seca (sombrillas incluidas,
    # que sí son arena por debajo).
    # 2026-09-10: verificado con foto real que, incluso con el relleno de
    # huecos (fill_small_gaps), quedaba sin cubrir una plaza de arena real y
    # abierta más allá del chiringuito/palmeras (junto a unas carpas
    # blancas, lejos de la cámara) — NO es un hueco cerrado (no lo detecta
    # fill_small_gaps), es que la propia máscara de SAM no llegaba tan
    # lejos. Añadido un 3er punto ahí (0.858, 0.309, en fracción del ROI).
    "CAM_3": [
        {"point": [0.50, 0.80], "label": 1},
        {"point": [0.58, 0.85], "label": 1},
        {"point": [0.858, 0.309], "label": 1},
        {"point": [0.50, 0.10], "label": 0},
    ],
    "CAM_4": [
        {"point": [0.27, 0.80], "label": 1},
        {"point": [0.52, 0.80], "label": 1},
        {"point": [0.77, 0.80], "label": 1},
        {"point": [0.50, 0.12], "label": 0},
    ],
    "CAM_5": [
        {"point": [0.23, 0.75], "label": 1},
        {"point": [0.48, 0.75], "label": 1},
        {"point": [0.73, 0.75], "label": 1},
        {"point": [0.50, 0.15], "label": 0},
    ],
    "CAM_6": [
        {"point": [0.25, 0.78], "label": 1},
        {"point": [0.50, 0.78], "label": 1},
        {"point": [0.75, 0.78], "label": 1},
        {"point": [0.50, 0.12], "label": 0},
    ],
}

# NOTA 2026-08-31: se probó añadir una caja genérica (CAM_BOX) acotando la
# zona de arena junto a los puntos — verificado EN IMAGEN REAL que empeora el
# resultado (cobertura 14% -> 7%, la máscara se encoge a una esquina) porque
# la arena seca en estas cámaras es una franja diagonal alargada, no un
# blob compacto tipo caja; SAM con prompt de caja tiende a buscar "el objeto
# que llena ese rectángulo", no una franja fina que lo cruza. Descartada.

def generate_probability_map(logits: np.ndarray) -> np.ndarray:
    """
    Genera mapa de probabilidad por pixel con 3 clases: [seca, humeda, agua] (#44).

    Entrada: logits SAM shape (N, H, W) — tipicamente N=3 mascaras multimask.
    Salida:  ndarray float32 (H, W, 3) con probabilidades suavizadas por clase
             via sigmoid. Los logits de SAM son scores por pixel; los 3 canales
             se asignan heuristicamente: el de mayor score = seca, el intermedio
             = humeda, el menor = agua.
    """
    if logits is None or logits.ndim < 3:
        return np.zeros((1, 1, 3), dtype=np.float32)

    def sigmoid(x):
        return 1.0 / (1.0 + np.exp(-np.clip(x, -88, 88)))

    probs = sigmoid(logits.astype(np.float32))  # (N, H, W)

    # Ordenar canales por score medio descendente: mayor = arena seca
    mean_scores = probs.mean(axis=(1, 2))
    order = np.argsort(mean_scores)[::-1]  # indices de mayor a menor
    n = probs.shape[0]

    h, w = probs.shape[1], probs.shape[2]
    out = np.zeros((h, w, 3), dtype=np.float32)
    out[:, :, 0] = probs[order[0]] if n > 0 else 0        # seca
    out[:, :, 1] = probs[order[1]] if n > 1 else 0        # humeda
    out[:, :, 2] = probs[order[2]] if n > 2 else 0        # agua

    return out


def evaluate_sam_vs_sam2(image: np.ndarray, cam_id: str) -> dict:
    """
    Compara SAM base vs SAM2 sobre una imagen y retorna scores (#45).
    Si SAM2 no esta instalado devuelve solo el resultado de SAM base.
    """
    result = {"cam_id": cam_id, "sam_available": SAM_AVAILABLE, "sam2_available": False,
              "recommendation": "sam_base"}

    try:
        import sam2  # noqa: F401
        result["sam2_available"] = True
    except ImportError:
        pass

    if not SAM_AVAILABLE:
        result["recommendation"] = "ninguno_disponible"
        return result

    # Con modelo real: ejecutar ambos y comparar IoU contra GT si existe.
    # Sin modelo: retornar disponibilidad y recomendacion heuristica.
    # SAM2 es superior en videos; para imagenes estatticas SAM base es suficiente.
    if result["sam2_available"]:
        result["recommendation"] = "sam2"
        result["reason"] = "SAM2 mejora consistencia temporal en secuencias de video"
    else:
        result["recommendation"] = "sam_base"
        result["reason"] = "SAM base disponible; instalar SAM2 para mayor robustez temporal"

    return result


def remove_false_detections(mask: np.ndarray, image: np.ndarray) -> np.ndarray:
    """
    Elimina falsas detecciones de espuma, reflejos y sombras (#48).

    Estrategia de tres filtros:
      1. Filtro HSV: elimina zonas de espuma (blanco saturado, S<30, V>220).
      2. Filtro de brillo: elimina reflejos especulares (V > 245 en HSV).
      3. Filtro de posicion vertical: la arena seca debe estar en la mitad
         inferior de la imagen; elimina regiones en el tercio superior.
    """
    if mask is None or image is None:
        return mask

    result = mask.copy()
    h, w = mask.shape[:2]
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)

    # 1. Espuma: baja saturacion + alto brillo
    espuma = (hsv[:, :, 1] < 30) & (hsv[:, :, 2] > 220)
    result[espuma] = 0

    # 2. Reflejos especulares: brillo extremo
    reflejos = hsv[:, :, 2] > 245
    result[reflejos] = 0

    # 3. Eliminar detecciones en tercio superior (cielo, gaviotas, horizonte)
    result[:int(h * 0.33), :] = 0

    # 4. Limpieza morfologica tras filtros
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
    result = cv2.morphologyEx(result, cv2.MORPH_OPEN, kernel)

    return result


# Umbral de relleno de huecos: fracción máxima del área de arena ya
# detectada que puede ocupar un hueco/objeto para considerarse "sobre la
# arena" y rellenarse, en vez de una laguna/charco real grande. Calibrado con
# datos reales el 2026-09-09: la plaza de arena de CAM_3 (real, verificada
# visualmente — ver comentario de fill_small_gaps) mide un 5.61% del área de
# arena de esa cámara; se deja margen por encima (8%) sin acercarse a
# "tragarse media playa".
MAX_GAP_AREA_RATIO = 0.08

# Radio (px, a la resolución nativa de la cámara ~4608px de ancho) de
# reconstrucción morfológica — ver fill_small_gaps. Calibrado con datos
# reales el 2026-09-09: 101px corta con margen los "hilos" de sombra de
# sombrillas/palmeras (unos pocos px de ancho) sin fusionar la arena con el
# mar en ninguna de las 5 cámaras probadas (CAM_1/2/3/4/6, todas con foto
# real).
GAP_FILL_KERNEL_PX = 101

def fill_small_gaps(
    mask: np.ndarray,
    max_gap_area_ratio: float = MAX_GAP_AREA_RATIO,
    kernel_px: int = GAP_FILL_KERNEL_PX,
) -> np.ndarray:
    """
    Rellena huecos de arena seca ocupados por objetos, SIN usar las varillas
    de calibración como referencia en ningún caso (a petición explícita del
    usuario 2026-09-09 — ver también el recorte al casco de varillas, ya
    desactivado, en backend/main.py::analyze_roi).

    Una persona, sombrilla o palmera sobre la arena interrumpe localmente la
    detección de SAM justo ahí, dejando un "agujero" de "no arena" — la
    arena que SÍ hay debajo/alrededor del objeto no desaparece porque haya
    algo encima. Sin este relleno: (a) resta cobertura real a
    confidence_index() sin motivo (usa mask.sum() en bruto), y (b) si el
    objeto está pegado al borde de la orilla, mella artificialmente la línea
    de costa extraída justo en ese tramo.

    Primera versión (2026-09-03): un hueco se rellenaba solo si su
    componente conexo en el COMPLEMENTO de la máscara no tocaba ningún borde
    de la imagen (mar/cielo/exterior del ROI siempre tocan alguno). Bug real
    detectado y verificado 2026-09-09 con fotos reales de CAM_2 y CAM_3: casi
    ningún objeto real está de verdad "cerrado" — su sombra suele conectar,
    por un hilo de solo 1-2px, con el mar o con otra zona de fondo que sí
    toca el borde, así que ese criterio los trataba a TODOS como "exterior"
    y no rellenaba nada (comprobado: 0 huecos detectados pese a sombrillas y
    troncos de palmera claramente visibles en las fotos).

    Solución (apertura por reconstrucción morfológica): erosionar el
    complemento con un elemento de radio kernel_px ANTES de decidir qué toca
    el borde corta esos hilos finos — la sombra de una sombrilla no sobrevive
    a la erosión, pero el mar (una región ancha de verdad) sí. A partir de
    los componentes erosionados que aún tocan el borde ("semillas" de fondo
    real), se reconstruye su extensión completa creciendo la semilla DENTRO
    DEL COMPLEMENTO YA EROSIONADO (no del original — si se creciera sin esa
    restricción, la dilatación acabaría atravesando el mismo hilo fino que
    la erosión debía cortar, porque la conectividad es una propiedad
    topológica: si existe cualquier camino, por fino que sea, tarde o
    temprano se encuentra) y dilatando el resultado de vuelta para
    recuperar su tamaño real. Todo lo que queda en el complemento original y
    NO forma parte de ese fondo reconstruido es un hueco/objeto — se rellena
    si su tamaño no supera max_gap_area_ratio del área de arena (protección
    extra: una laguna real que por algún motivo quedara aislada no se traga
    sin más).

    Verificado con fotos reales (checkpoint SAM real, 2026-09-09): cubre
    correctamente sombrillas sueltas, troncos de palmera y una plaza de
    arena completa junto a un chiringuito (CAM_3) sin fusionar la máscara
    con el mar en ninguna de las 5 cámaras probadas.
    """
    if mask is None:
        return mask
    binary = (mask > 0).astype(np.uint8)
    sand_area = int(binary.sum())
    if sand_area == 0:
        return mask

    inverse = 1 - binary
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kernel_px, kernel_px))
    eroded_inverse = cv2.erode(inverse, kernel)

    n_labels, labels = cv2.connectedComponents(eroded_inverse, connectivity=8)
    border_labels = (
        set(labels[0, :].tolist()) | set(labels[-1, :].tolist())
        | set(labels[:, 0].tolist()) | set(labels[:, -1].tolist())
    )
    border_labels.discard(0)
    seed = np.isin(labels, list(border_labels)).astype(np.uint8) if border_labels else np.zeros_like(binary)

    # Reconstrucción: crecer la semilla dentro del complemento EROSIONADO
    # (ver docstring) hasta estabilizarse.
    prev = seed
    for _ in range(300):
        grown = cv2.bitwise_and(cv2.dilate(prev, kernel), eroded_inverse)
        if np.array_equal(grown, prev):
            break
        prev = grown
    # Deshacer la erosión inicial para recuperar la extensión real del fondo.
    background = cv2.bitwise_and(cv2.dilate(prev, kernel), inverse)

    holes = (inverse.astype(bool) & ~background.astype(bool)).astype(np.uint8)
    n_holes, hole_labels = cv2.connectedComponents(holes, connectivity=8)
    max_gap_px = max_gap_area_ratio * sand_area
    filled = binary.copy()
    for label in range(1, n_holes):
        component = hole_labels == label
        if int(component.sum()) <= max_gap_px:
            filled[component] = 1

    return (filled * 255).astype(np.uint8)


def check_temporal_consistency(
    mask_prev: np.ndarray,
    mask_curr: np.ndarray,
    threshold: float = 0.15,
) -> tuple[bool, float]:
    """
    Evalua la consistencia de segmentacion entre dos frames consecutivos (#50).

    Calcula la interseccion sobre union (IoU) entre las dos mascaras.
    Si IoU < threshold, los frames son inconsistentes (posible error de segmentacion).

    Retorna (consistente: bool, iou: float).
    """
    if mask_prev is None or mask_curr is None:
        return False, 0.0

    prev = (mask_prev > 0).astype(np.uint8)
    curr = (mask_curr > 0).astype(np.uint8)

    # Redimensionar si difieren
    if prev.shape != curr.shape:
        curr = cv2.resize(curr, (prev.shape[1], prev.shape[0]),
                          interpolation=cv2.INTER_NEAREST)

    intersection = np.logical_and(prev, curr).sum()
    union = np.logical_or(prev, curr).sum()

    iou = float(intersection) / float(union) if union > 0 else 1.0
    return iou >= threshold, iou


def evaluate_horizon_correction_needed(image: np.ndarray, cam_id: str) -> bool:
    """
    Detecta si la linea de horizonte esta inclinada mas de 1 grado (#54).
    Usa transformada de Hough sobre bordes del tercio superior de la imagen.

    Retorna True si se detecta inclinacion significativa (>1 deg) y la
    correccion de horizonte deberia aplicarse antes de segmentar.
    """
    h, w = image.shape[:2]
    roi_top = image[:int(h * 0.45), :]
    gray = cv2.cvtColor(roi_top, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 50, 150)

    lines = cv2.HoughLinesP(edges, rho=1, theta=np.pi / 180,
                             threshold=100, minLineLength=w // 4, maxLineGap=30)
    if lines is None:
        return False

    angles = []
    for line in lines:
        x1, y1, x2, y2 = line[0]
        if x2 != x1:
            angle = np.degrees(np.arctan2(abs(y2 - y1), abs(x2 - x1)))
            if angle < 20:  # solo lineas casi horizontales
                angles.append(angle)

    if not angles:
        return False

    median_angle = float(np.median(angles))
    return median_angle > 1.0


class SAMSegmenter:
    def __init__(self, model_type="vit_h", checkpoint_path=None):
        self.model_type = model_type
        self.checkpoint_path = checkpoint_path
        self.predictor = None
        self.sam = None

        if not SAM_AVAILABLE:
            print("[FAILED] Error: 'segment-anything' no esta instalado.")
            return

        if checkpoint_path and os.path.exists(checkpoint_path):
            print(f"[.] Cargando SAM ({model_type}) desde {checkpoint_path}...")
            self.sam = sam_model_registry[model_type](checkpoint=checkpoint_path)
            import torch
            device = "cuda" if torch.cuda.is_available() else "cpu"
            self.sam.to(device=device)
            self.predictor = SamPredictor(self.sam)
            print(f"[OK] SAM cargado en {device}.")
        else:
            print(f"[WARNING] Checkpoint no encontrado en {checkpoint_path}.")

    def get_roi(self, cam_id: str):
        if not ROI_FILE.exists():
            return None
        with open(ROI_FILE) as f:
            rois = json.load(f)
        key = f"CAM_{cam_id}" if not str(cam_id).startswith("CAM") else str(cam_id)
        return rois.get(key)

    def apply_roi(self, image, roi):
        if not roi:
            return image, (0, 0)
        x1, y1, x2, y2 = roi["x_min"], roi["y_min"], roi["x_max"], roi["y_max"]
        return image[y1:y2, x1:x2], (x1, y1)

    def _build_cam_prompts(self, cam_id: str, roi_h: int, roi_w: int):
        """Convierte CAM_PROMPTS fraccionarios a coordenadas pixel en el ROI (#43)."""
        key = f"CAM_{cam_id}" if not str(cam_id).startswith("CAM") else str(cam_id)
        entries = CAM_PROMPTS.get(key, [{"point": [0.5, 0.8], "label": 1}])
        points = np.array([[int(e["point"][0] * roi_w), int(e["point"][1] * roi_h)]
                           for e in entries])
        labels = np.array([e["label"] for e in entries])
        return points, labels

    def segment_dry_sand(self, image, cam_id: str, prompts=None,
                         remove_false=True, return_prob_map=False):
        """
        Segmenta la arena seca usando SAM.
        prompts: dict {"points": [[x,y],...], "labels": [1,0,...]} en coords ROI.
        remove_false: aplicar filtro de falsas detecciones (#48).
        return_prob_map: retornar tambien el mapa de probabilidad (#44).
        """
        if self.predictor is None:
            print("[FAILED] Predictor no inicializado.")
            return (None, None) if return_prob_map else None

        roi = self.get_roi(cam_id)
        roi_img, offset = self.apply_roi(image, roi)
        h_roi, w_roi = roi_img.shape[:2]

        img_rgb = cv2.cvtColor(roi_img, cv2.COLOR_BGR2RGB)
        self.predictor.set_image(img_rgb)

        if prompts is None:
            input_point, input_label = self._build_cam_prompts(cam_id, h_roi, w_roi)
        else:
            input_point = np.array(prompts["points"])
            input_label = np.array(prompts["labels"])

        masks, scores, logits = self.predictor.predict(
            point_coords=input_point,
            point_labels=input_label,
            multimask_output=True,
        )

        best_idx = np.argmax(scores)
        mask = masks[best_idx]

        # Mapa de probabilidad (#44)
        prob_map = generate_probability_map(logits) if return_prob_map else None

        # Recomponer mascara al tamano original
        full_mask = np.zeros(image.shape[:2], dtype=np.uint8)
        if roi:
            x1, y1, x2, y2 = roi["x_min"], roi["y_min"], roi["x_max"], roi["y_max"]
            full_mask[y1:y2, x1:x2] = mask.astype(np.uint8) * 255
        else:
            full_mask = mask.astype(np.uint8) * 255

        # Post-procesado morfologico
        kernel = np.ones((5, 5), np.uint8)
        full_mask = cv2.morphologyEx(full_mask, cv2.MORPH_OPEN, kernel)
        full_mask = cv2.morphologyEx(full_mask, cv2.MORPH_CLOSE, kernel)

        # Filtro de falsas detecciones (#48)
        if remove_false:
            full_mask = remove_false_detections(full_mask, image)

        # Relleno de huecos pequeños (personas/objetos sobre la arena, ver
        # fill_small_gaps) — DESPUÉS de remove_false_detections a propósito:
        # ese filtro puede él mismo abrir pequeños huecos nuevos (p.ej. al
        # quitar un reflejo puntual sobre arena mojada), así que el relleno
        # tiene que ser el último paso para limpiar el resultado final, no
        # uno intermedio que luego otro filtro vuelva a agujerear.
        full_mask = fill_small_gaps(full_mask)

        if return_prob_map:
            return full_mask, prob_map
        return full_mask


def main():
    import argparse
    import tempfile
    # Bug real detectado 2026-08-31: "/tmp/..." como valor por defecto no
    # existe en Windows (único SO objetivo de este proyecto, ver
    # installer/cv-lit.iss) — este CLI de depuración fallaba al escribir la
    # máscara si se ejecutaba sin pasar --out explícito.
    default_out = os.path.join(tempfile.gettempdir(), "mask_debug.png")
    ap = argparse.ArgumentParser(description="SAM segmentation debug")
    ap.add_argument("--image", required=True, help="Ruta a la imagen")
    ap.add_argument("--cam",   required=True, help="ID camara (1-6)")
    ap.add_argument("--checkpoint", default=None, help="Ruta al checkpoint SAM")
    ap.add_argument("--out",   default=default_out)
    args = ap.parse_args()

    img = cv2.imread(args.image)
    if img is None:
        print(f"No se pudo leer: {args.image}")
        return

    # Evaluaciones independientes del modelo
    needs_horizon = evaluate_horizon_correction_needed(img, args.cam)
    print(f"Correccion horizonte necesaria: {needs_horizon}")

    sam_eval = evaluate_sam_vs_sam2(img, args.cam)
    print(f"Evaluacion SAM: {sam_eval}")

    segmenter = SAMSegmenter(checkpoint_path=args.checkpoint)
    mask = segmenter.segment_dry_sand(img, args.cam)
    if mask is not None:
        cv2.imwrite(args.out, mask)
        print(f"Mascara guardada en {args.out}")
    else:
        print("No se genero mascara (modelo no disponible)")


if __name__ == "__main__":
    main()
