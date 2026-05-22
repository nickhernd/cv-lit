import cv2
import os
import sys

def procesar_imagen_orb(ruta_archivo):
    if not os.path.exists(ruta_archivo):
        print(f"Error: El archivo no existe en: {ruta_archivo}")
        return False

    img = cv2.imread(ruta_archivo)
    if img is None:
        print(f"Error: No se pudo leer la imagen: {ruta_archivo}")
        return False

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    orb = cv2.ORB_create(nfeatures=500)
    keypoints, descriptors = orb.detectAndCompute(gray, None)

    img_with_keypoints = cv2.drawKeypoints(
        img, 
        keypoints, 
        None, 
        color=(0, 255, 0), 
        flags=cv2.DRAW_MATCHES_FLAGS_DRAW_RICH_KEYPOINTS
    )

    # --- NUEVO: Control de tamaño de ventana ---
    ventana_nombre = 'ORB Features'
    # Creamos la ventana con modo normal para permitir redimensionamiento
    cv2.namedWindow(ventana_nombre, cv2.WINDOW_NORMAL)
    # Definimos un tamaño fijo (ancho, alto)
    cv2.resizeWindow(ventana_nombre, 800, 600)
    # -------------------------------------------

    cv2.imshow(ventana_nombre, img_with_keypoints)
    
    print(f"Puntos clave detectados: {len(keypoints)}")
    print("Presiona cualquier tecla para cerrar la ventana.")
    
    cv2.waitKey(0)
    cv2.destroyWindow(ventana_nombre)
    cv2.waitKey(1)
    return True

if __name__ == "__main__":
    base_dir = "/home/nickhernd/Desktop/cv-lit/proces_images"
    nombre_archivo = "20260303_130000_8213.jpg"
    ruta_completa = os.path.join(base_dir, "CAM_1/images", nombre_archivo)
    
    if procesar_imagen_orb(ruta_completa):
        print("Proceso completado.")
    else:
        sys.exit(1)