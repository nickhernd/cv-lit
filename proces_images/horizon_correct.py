"""
Corrección de curvatura del horizonte mediante selección interactiva de puntos.

Flujo:
  Fase 1 - REFERENCIA (verde): clic en 4 puntos (2 pares) que forman 2 rectas
           que representan cómo debería verse el horizonte recto.
  Fase 2 - HORIZONTE CURVO (naranja): clic en N puntos (mínimo 3) a lo largo
           del horizonte curvo real.
  Resultado: warp vertical que alinea la curva con la línea de referencia.

Controles:
  Clic izquierdo  → añadir punto
  Clic derecho    → deshacer último punto
  ENTER / espacio → confirmar fase / procesar
  R               → reiniciar puntos de la fase actual
  ESC / Q         → salir sin guardar
"""

import sys
import os
import numpy as np
import matplotlib
matplotlib.use("GTK3Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.lines import Line2D
import cv2
from scipy.interpolate import interp1d


MAX_DISPLAY_W = 1600
MAX_DISPLAY_H = 900


def resize_for_display(img_rgb, max_w=MAX_DISPLAY_W, max_h=MAX_DISPLAY_H):
    h, w = img_rgb.shape[:2]
    scale = min(max_w / w, max_h / h, 1.0)
    if scale < 1.0:
        new_w, new_h = int(w * scale), int(h * scale)
        return cv2.resize(img_rgb, (new_w, new_h)), scale
    return img_rgb.copy(), 1.0


def fit_line(points):
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    coeffs = np.polyfit(xs, ys, 1)
    return np.poly1d(coeffs)


def fit_curve(points, degree=2):
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    degree = min(degree, len(points) - 1)
    coeffs = np.polyfit(xs, ys, degree)
    return np.poly1d(coeffs)


def apply_correction(img_bgr, ref_pts, curve_pts):
    h, w = img_bgr.shape[:2]
    xs = np.arange(w, dtype=np.float32)

    ref_fn   = fit_line(ref_pts)
    y_ref    = ref_fn(xs).astype(np.float32)

    curve_fn = fit_curve(curve_pts, degree=2)
    y_curve  = curve_fn(xs).astype(np.float32)

    delta_y = y_ref - y_curve

    map_x = np.tile(xs, (h, 1))
    ys_dst = np.arange(h, dtype=np.float32)
    map_y  = np.tile(ys_dst[:, None], (1, w)) - delta_y

    corrected = cv2.remap(img_bgr, map_x, map_y.astype(np.float32),
                          interpolation=cv2.INTER_LINEAR,
                          borderMode=cv2.BORDER_REPLICATE)
    return corrected


class HorizonCorrector:
    def __init__(self, img_path):
        self.img_path  = img_path
        img_bgr        = cv2.imread(img_path)
        if img_bgr is None:
            raise FileNotFoundError(f"No se puede leer: {img_path}")
        self.img_bgr   = img_bgr
        img_rgb        = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
        self.disp, self.scale = resize_for_display(img_rgb)
        self.h_d, self.w_d   = self.disp.shape[:2]

        self.phase      = 1   # 1 = referencia, 2 = horizonte curvo
        self.ref_pts    = []  # coordenadas de pantalla
        self.curve_pts  = []
        self.done       = False
        self.cancelled  = False

        self._build_ui()

    # ── UI ────────────────────────────────────────────────────────────────────
    def _build_ui(self):
        self.fig, self.ax = plt.subplots(figsize=(14, 8))
        self.fig.canvas.manager.set_window_title("Corrección de horizonte")
        plt.subplots_adjust(bottom=0.01, top=0.93, left=0.01, right=0.99)

        self.im_handle = self.ax.imshow(self.disp)
        self.ax.set_axis_off()

        self.fig.canvas.mpl_connect("button_press_event",  self._on_click)
        self.fig.canvas.mpl_connect("key_press_event",     self._on_key)

        self._redraw()
        plt.show()

    def _redraw(self):
        self.ax.cla()
        self.ax.imshow(self.disp)
        self.ax.set_axis_off()

        xs_full = np.linspace(0, self.w_d - 1, self.w_d)

        # Líneas entre pares de referencia + scatter
        if self.ref_pts:
            rxs = [p[0] for p in self.ref_pts]
            rys = [p[1] for p in self.ref_pts]
            self.ax.scatter(rxs, rys, c="lime", s=60, zorder=5)
            for i in range(0, len(self.ref_pts) - 1, 2):
                if i + 1 < len(self.ref_pts):
                    p1, p2 = self.ref_pts[i], self.ref_pts[i + 1]
                    self.ax.plot([p1[0], p2[0]], [p1[1], p2[1]], "lime", lw=1.5)

        # Línea de referencia global (cuando hay 4 puntos)
        if len(self.ref_pts) == 4:
            pts_orig = [(int(x / self.scale), int(y / self.scale)) for x, y in self.ref_pts]
            fn = fit_line(pts_orig)
            ys = fn(xs_full / self.scale) * self.scale
            self.ax.plot(xs_full, ys, color="cyan", lw=2, linestyle="--", label="Línea ref.")

        # Puntos del horizonte curvo
        if self.curve_pts:
            cxs = [p[0] for p in self.curve_pts]
            cys = [p[1] for p in self.curve_pts]
            self.ax.scatter(cxs, cys, c="orange", s=60, zorder=5)

        # Curva ajustada al horizonte
        if len(self.curve_pts) >= 3:
            pts_orig = [(int(x / self.scale), int(y / self.scale)) for x, y in self.curve_pts]
            fn = fit_curve(pts_orig, degree=2)
            ys = fn(xs_full / self.scale) * self.scale
            self.ax.plot(xs_full, ys, color="yellow", lw=2, label="Curva horizonte")

        # Título / instrucciones
        if self.phase == 1:
            title = (f"FASE 1 — REFERENCIA (verde): {len(self.ref_pts)}/4 puntos  |  "
                     "ENTER=confirmar   R=reiniciar   Clic derecho=deshacer   ESC=salir")
            col = "lime"
        else:
            title = (f"FASE 2 — HORIZONTE CURVO (naranja): {len(self.curve_pts)} puntos (mín 3)  |  "
                     "ENTER=procesar   R=reiniciar   Clic derecho=deshacer   ESC=salir")
            col = "orange"

        self.fig.suptitle(title, fontsize=10, color=col, backgroundcolor="#111111")
        self.fig.canvas.draw_idle()

    # ── eventos ───────────────────────────────────────────────────────────────
    def _on_click(self, event):
        if event.inaxes != self.ax or event.xdata is None:
            return
        x, y = int(event.xdata), int(event.ydata)

        if event.button == 1:  # izquierdo → añadir
            if self.phase == 1 and len(self.ref_pts) < 4:
                self.ref_pts.append((x, y))
            elif self.phase == 2:
                self.curve_pts.append((x, y))
        elif event.button == 3:  # derecho → deshacer
            if self.phase == 1 and self.ref_pts:
                self.ref_pts.pop()
            elif self.phase == 2 and self.curve_pts:
                self.curve_pts.pop()

        self._redraw()

    def _on_key(self, event):
        key = event.key

        if key in ("escape", "q"):
            self.cancelled = True
            plt.close("all")
            return

        if key in ("r",):
            if self.phase == 1:
                self.ref_pts.clear()
            else:
                self.curve_pts.clear()
            self._redraw()
            return

        if key in ("enter", " "):
            if self.phase == 1:
                if len(self.ref_pts) < 4:
                    print(f"  Necesitas 4 puntos de referencia (tienes {len(self.ref_pts)}).")
                else:
                    self.phase = 2
                    print("  Fase 1 OK. Ahora marca el horizonte curvo (mín 3 puntos) y pulsa ENTER.")
                    self._redraw()
            else:
                if len(self.curve_pts) < 3:
                    print(f"  Necesitas al menos 3 puntos del horizonte (tienes {len(self.curve_pts)}).")
                else:
                    self.done = True
                    plt.close("all")

    # ── resultado ─────────────────────────────────────────────────────────────
    def get_points_original(self):
        """Devuelve los puntos en coordenadas de la imagen original."""
        s = self.scale
        ref   = [(int(x / s), int(y / s)) for x, y in self.ref_pts]
        curve = [(int(x / s), int(y / s)) for x, y in self.curve_pts]
        return ref, curve


def show_comparison(img_orig_bgr, corrected_bgr):
    orig_rgb = cv2.cvtColor(img_orig_bgr, cv2.COLOR_BGR2RGB)
    corr_rgb = cv2.cvtColor(corrected_bgr, cv2.COLOR_BGR2RGB)

    orig_d, _ = resize_for_display(orig_rgb, MAX_DISPLAY_W // 2, MAX_DISPLAY_H)
    corr_d, _ = resize_for_display(corr_rgb, MAX_DISPLAY_W // 2, MAX_DISPLAY_H)

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))
    fig.canvas.manager.set_window_title("Comparación")
    ax1.imshow(orig_d);  ax1.set_title("ORIGINAL",   color="white"); ax1.axis("off")
    ax2.imshow(corr_d);  ax2.set_title("CORREGIDA",  color="white"); ax2.axis("off")
    fig.patch.set_facecolor("#111111")
    fig.suptitle("Cierra esta ventana para terminar", color="gray", fontsize=9)
    plt.tight_layout()
    plt.show()


def process_image(img_path):
    print(f"\nAbriendo: {os.path.basename(img_path)}")
    print("  Fase 1: haz clic en 4 puntos de referencia (2 pares formando 2 rectas).")

    corrector = HorizonCorrector(img_path)

    if corrector.cancelled or not corrector.done:
        print("  Cancelado.")
        return

    ref_orig, curve_orig = corrector.get_points_original()
    print(f"  Puntos referencia: {ref_orig}")
    print(f"  Puntos horizonte:  {curve_orig}")
    print("  Aplicando corrección...")

    img_bgr   = corrector.img_bgr
    corrected = apply_correction(img_bgr, ref_orig, curve_orig)

    base_name = os.path.splitext(img_path)[0]
    out_path  = base_name + "_corrected.jpg"
    cv2.imwrite(out_path, corrected, [cv2.IMWRITE_JPEG_QUALITY, 92])
    print(f"  Guardado: {out_path}")

    show_comparison(img_bgr, corrected)


def main():
    images_dir = os.path.dirname(os.path.abspath(__file__))
    jpgs = sorted([
        f for f in os.listdir(images_dir)
        if f.lower().endswith('.jpg') and '_corrected' not in f
    ])

    if not jpgs:
        print("No se encontraron imágenes JPG.")
        sys.exit(1)

    if len(sys.argv) > 1:
        target = sys.argv[1]
        path   = target if os.path.isfile(target) else None
        if path is None:
            matches = [f for f in jpgs if target in f]
            if not matches:
                print(f"No se encontró ninguna imagen con '{target}'")
                sys.exit(1)
            path = os.path.join(images_dir, matches[0])
        process_image(path)
        return

    print(f"\nImágenes disponibles ({len(jpgs)}):")
    for i, f in enumerate(jpgs):
        print(f"  [{i:3d}] {f}")
    print()
    try:
        idx = int(input("Selecciona el número de imagen: "))
        process_image(os.path.join(images_dir, jpgs[idx]))
    except (ValueError, IndexError):
        print("Índice no válido.")


if __name__ == "__main__":
    main()
