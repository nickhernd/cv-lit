import cv2
import numpy as np

def extract_coastline_from_mask(mask, min_length=500):
    """
    Extrae la línea de costa adaptada a resoluciones 4K.
    """
    h, w = mask.shape
    
    # 1. Ignorar el tercio superior de la imagen (Cielo/Montañas)
    # En 4K (2682px de alto), ignoramos los primeros 1000px
    mask[0:int(h*0.4), :] = 0 
    
    # 2. Ignorar bordes laterales (3% de cada lado)
    margin = int(w * 0.03)
    mask[:, 0:margin] = 0
    mask[:, w-margin:w] = 0
    
    # 3. Encontrar contornos
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    if not contours:
        return None

    # 4. Quedarnos con el contorno más largo (debe ser la orilla)
    # Aumentamos min_length porque en 4K los contornos son mucho más largos
    valid_contours = [c for c in contours if cv2.arcLength(c, False) > min_length]
    if not valid_contours:
        return None
        
    main_contour = max(valid_contours, key=lambda c: cv2.arcLength(c, False))
    
    # Simplificar para suavizar la línea
    epsilon = 0.0015 * cv2.arcLength(main_contour, False)
    approx = cv2.approxPolyDP(main_contour, epsilon, False)
    
    return approx.reshape(-1, 2).tolist()

def draw_coastline(image, points, color=(0, 0, 255), thickness=6):
    """Dibuja la línea en ROJO grueso para 4K."""
    if not points:
        return image
    pts = np.array(points, dtype=np.int32).reshape((-1, 1, 2))
    cv2.polylines(image, [pts], False, color, thickness, cv2.LINE_AA)
    
    # Texto de estado
    cv2.putText(image, "CV-LIT 4K: DETECTADO", (100, 150), 
                cv2.FONT_HERSHEY_SIMPLEX, 3.0, (0, 0, 255), 8)
    return image
