# routers/alignment.py
from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import StreamingResponse
import cv2
import numpy as np
import io

# Importa la función align() de tu script existente
from align_images import align, SIFT_FEATURES

# DEBUG (INIT): router NO está montado en backend/main.py (solo se incluye
# batch_router). Este archivo parece código muerto/legado — align_preview() de
# main.py y batch_alignment.py cubren la misma función. Verificar si sigue en uso
# antes de tocarlo.
router = APIRouter(prefix="/api", tags=["alignment"])


# DEBUG: decodifica un UploadFile subido por HTTP a un array de imagen BGR de OpenCV.
def _decode_upload(upload: UploadFile) -> np.ndarray:
    """Lee un UploadFile y lo decodifica como imagen BGR."""
    data = upload.file.read()
    arr  = np.frombuffer(data, np.uint8)
    img  = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        raise HTTPException(400, f"No se pudo leer la imagen: {upload.filename}")
    return img


# DEBUG: alinea 'target' contra 'reference' usando la función align() de
# homography/align_images.py y devuelve un blend 50/50 en PNG.
@router.post("/align-preview")
async def align_preview(
    reference: UploadFile = File(...),
    target:    UploadFile = File(...),
):
    """
    Recibe dos imágenes (reference, target), alinea target respecto a reference
    y devuelve un PNG con el blend 50/50 para diagnóstico visual.
    """
    ref_img = _decode_upload(reference)
    tgt_img = _decode_upload(target)

    ref_gray = cv2.cvtColor(ref_img, cv2.COLOR_BGR2GRAY)

    sift = cv2.SIFT_create(nfeatures=SIFT_FEATURES)
    ref_kp, ref_des = sift.detectAndCompute(ref_gray, None)

    aligned, info = align(tgt_img, ref_gray, ref_kp, ref_des, ref_img=ref_img)

    if info["status"] not in ("ok", "reference"):
        raise HTTPException(422, f"Alineación fallida: {info['status']} ({info['inliers']} inliers)")

    # ── Blend 50/50 en escala de grises ──────────────────────────────────────
    # Convertir ambas a gris para el efecto B&W clásico de "superposición"
    ref_bw     = cv2.cvtColor(ref_img, cv2.COLOR_BGR2GRAY)
    aligned_bw = cv2.cvtColor(aligned,  cv2.COLOR_BGR2GRAY)

    # Igualar tamaños por si acaso
    h, w = ref_bw.shape
    aligned_bw = cv2.resize(aligned_bw, (w, h))

    blend_bw = cv2.addWeighted(ref_bw, 0.5, aligned_bw, 0.5, 0)

    # Codificar como PNG y devolver
    _, buf = cv2.imencode(".png", blend_bw)
    return StreamingResponse(io.BytesIO(buf.tobytes()), media_type="image/png")