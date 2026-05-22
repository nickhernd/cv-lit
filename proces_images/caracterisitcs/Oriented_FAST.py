import cv2
import os
import sys

def procesar_imagen_orb(ruta_archivo):
    if not os.path.exists(ruta_archivo):
        print(f"Error: El archivo no existe en: {ruta_archivo}")
        return False

    img = cv2.imread(ruta_archivo)
    if img is None:
        return False

    alto, ancho = img.shape[:2]
    margen_inferior = 50  # Ajusta este valor según cuántos píxeles quieras quitar
    img_recortada = img[0:alto-margen_inferior, 0:ancho]
    # ---------------------------------

    # Ahora procesamos la imagen recortada
    gray = cv2.cvtColor(img_recortada, cv2.COLOR_BGR2GRAY)
    orb = cv2.ORB_create(nfeatures=500)
    keypoints, descriptors = orb.detectAndCompute(gray, None)

    img_with_keypoints = cv2.drawKeypoints(
        img_recortada, 
        keypoints, 
        None, 
        color=(0, 255, 0), 
        flags=cv2.DRAW_MATCHES_FLAGS_DRAW_RICH_KEYPOINTS
    )

    ventana_nombre = 'ORB Features (Recortado)'
    cv2.namedWindow(ventana_nombre, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(ventana_nombre, 800, 600)
    cv2.imshow(ventana_nombre, img_with_keypoints)
    
    cv2.waitKey(0)
    cv2.destroyWindow(ventana_nombre)
    cv2.waitKey(1)
    return True

if __name__ == "__main__":
    base_dir = "/home/nickhernd/Desktop/cv-lit/proces_images"
    ruta_completa = os.path.join(base_dir, "CAM_1/images", "20260303_130000_8213.jpg")
    procesar_imagen_orb(ruta_completa)