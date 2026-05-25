#!/usr/bin/env python3
"""
pipeline_schema.py — Diagrama visual del pipeline cv-lit

Genera un PNG con el flujo completo:
  Obscape API → Preprocesado → SAM → Extracción → Homografía → GeoJSON
  más el módulo offline de Calibración que alimenta la Homografía.

Uso:
  python pipeline_schema.py              # muestra en pantalla
  python pipeline_schema.py --save       # guarda en output/pipeline.png
"""
import os
import argparse
import matplotlib
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")

# ── Paleta ────────────────────────────────────────────────────────────────────
C = {
    "bg":       "#0d1117",
    "main":     "#1e2d3d",
    "calib":    "#1a2e1a",
    "border_m": "#3a7bd5",
    "border_c": "#3a9e3a",
    "text":     "#e6edf3",
    "text_sub": "#8b949e",
    "arrow":    "#58a6ff",
    "arrow_c":  "#56d364",
    "accent":   "#f0883e",
    "title":    "#79c0ff",
}

# ── Definición de nodos ───────────────────────────────────────────────────────
NODES = [
    # (id, x, y, w, h, título, subtítulo, tipo)
    ("entrada",  0.50, 0.90, 0.30, 0.07,
     "Imágenes Obscape API",
     "6 cámaras · 12:00h · CAM 1–6",
     "main"),

    ("preproc",  0.50, 0.76, 0.34, 0.09,
     "3.1  Preprocesado",
     "Normalización radiométrica\nBalance de blancos · Recorte ROI",
     "main"),

    ("sam",      0.50, 0.60, 0.38, 0.10,
     "3.2  Segmentación semántica  (SAM)",
     "Mapa probabilístico: arena seca / húmeda / agua\n"
     "Umbral adaptativo + filtrado morfológico → máscara binaria",
     "main"),

    ("linea",    0.50, 0.445, 0.36, 0.09,
     "3.3  Extracción de línea de costa",
     "cv2.findContours · borde húmedo–seco\n"
     "Polilínea en coordenadas de píxel  (u, v)",
     "main"),

    ("homo",     0.50, 0.295, 0.34, 0.09,
     "3.4  Proyección homografía",
     "(u, v)  →  (X, Y)  EPSG:25830\n"
     "Matriz H por cámara  (3×3)",
     "main"),

    ("export",   0.50, 0.135, 0.40, 0.10,
     "3.5  Postprocesado + Exportación",
     "Suavizado Douglas-Peucker · Filtros temporales\n"
     "Área seca (m²) · GeoJSON: ID_Camara, Timestamp,\n"
     "Confianza_IA, Area_Seca_m2  [EPSG:25830]",
     "main"),

    # Módulo offline calibración (columna izquierda)
    ("gcps",     0.13, 0.76, 0.18, 0.07,
     "GCPs GNSS  (IEL)",
     "EPSG:25830 · ≥8 puntos\n(bloqueado — pendiente IEL)",
     "calib"),

    ("calib",    0.13, 0.60, 0.20, 0.10,
     "3.0  Calibración  (offline)",
     "Correspondencias píxel ↔ UTM\ncv2.findHomography + RANSAC\n"
     "Perfil: H · K · dist · RMSE",
     "calib"),
]

# ── Flechas ───────────────────────────────────────────────────────────────────
ARROWS_MAIN = [
    ("entrada", "preproc"),
    ("preproc", "sam"),
    ("sam",     "linea"),
    ("linea",   "homo"),
    ("homo",    "export"),
]

# GCPs → Calib → H (flecha que entra en homo)
ARROWS_CALIB = [
    ("gcps",  "calib"),
    ("calib", "homo"),
]


def _node_center(nd):
    return nd[1], nd[2]


def _node_rect(nd):
    x, y, w, h = nd[1], nd[2], nd[3], nd[4]
    return x - w / 2, y - h / 2, w, h


def draw(save: bool = False):
    fig, ax = plt.subplots(figsize=(14, 18))
    fig.patch.set_facecolor(C["bg"])
    ax.set_facecolor(C["bg"])
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")

    # Título
    ax.text(0.50, 0.97, "cv-lit — Pipeline de detección de línea de costa",
            ha="center", va="top", fontsize=15, fontweight="bold",
            color=C["title"], fontfamily="monospace")
    ax.text(0.50, 0.945, "Guardamar del Segura · 6 cámaras · SAM + Homografía → GeoJSON EPSG:25830",
            ha="center", va="top", fontsize=9, color=C["text_sub"])

    node_map = {nd[0]: nd for nd in NODES}

    # ── Dibujar nodos ──────────────────────────────────────────────────────
    for nd in NODES:
        nid, x, y, w, h, title, sub, typ = nd
        bx, by, bw, bh = _node_rect(nd)
        bc  = C["border_m"] if typ == "main" else C["border_c"]
        bgc = C["main"]     if typ == "main" else C["calib"]

        box = FancyBboxPatch((bx, by), bw, bh,
                             boxstyle="round,pad=0.005",
                             linewidth=1.6,
                             edgecolor=bc, facecolor=bgc,
                             transform=ax.transAxes, zorder=3)
        ax.add_patch(box)

        # Título del nodo
        ax.text(x, y + bh * 0.18, title,
                ha="center", va="center", fontsize=9.5, fontweight="bold",
                color=C["text"], transform=ax.transAxes, zorder=4)

        # Subtítulo
        ax.text(x, y - bh * 0.16, sub,
                ha="center", va="center", fontsize=7.5,
                color=C["text_sub"], transform=ax.transAxes, zorder=4,
                linespacing=1.45)

    # ── Flechas principales (canal central) ───────────────────────────────
    for src_id, dst_id in ARROWS_MAIN:
        src = node_map[src_id]
        dst = node_map[dst_id]
        sx, sy = src[1], src[2] - src[4] / 2          # fondo del src
        dx, dy = dst[1], dst[2] + dst[4] / 2 + 0.004  # techo del dst

        ax.annotate("", xy=(dx, dy), xytext=(sx, sy),
                    xycoords="axes fraction", textcoords="axes fraction",
                    arrowprops=dict(
                        arrowstyle="->,head_width=0.012,head_length=0.012",
                        color=C["arrow"], lw=1.8,
                        connectionstyle="arc3,rad=0.0"),
                    zorder=2)

    # ── Flechas calibración ───────────────────────────────────────────────
    # GCPs → Calib (vertical)
    src = node_map["gcps"]
    dst = node_map["calib"]
    ax.annotate("", xy=(dst[1], dst[2] + dst[4] / 2 + 0.004),
                xytext=(src[1], src[2] - src[4] / 2),
                xycoords="axes fraction", textcoords="axes fraction",
                arrowprops=dict(
                    arrowstyle="->,head_width=0.010,head_length=0.010",
                    color=C["arrow_c"], lw=1.6),
                zorder=2)

    # Calib → homo (diagonal izquierda → centro)
    src = node_map["calib"]
    dst = node_map["homo"]
    sx  = src[1] + src[3] / 2       # lado derecho del bloque calib
    sy  = src[2]
    dx  = dst[1] - dst[3] / 2       # lado izquierdo del bloque homo
    dy  = dst[2]
    ax.annotate("", xy=(dx, dy), xytext=(sx, sy),
                xycoords="axes fraction", textcoords="axes fraction",
                arrowprops=dict(
                    arrowstyle="->,head_width=0.010,head_length=0.010",
                    color=C["arrow_c"], lw=1.6,
                    connectionstyle="arc3,rad=-0.15"),
                zorder=2)

    # ── Leyenda ───────────────────────────────────────────────────────────
    legend_items = [
        mpatches.Patch(facecolor=C["main"],  edgecolor=C["border_m"], label="Pipeline principal"),
        mpatches.Patch(facecolor=C["calib"], edgecolor=C["border_c"], label="Módulo offline — Calibración"),
    ]
    ax.legend(handles=legend_items, loc="lower right",
              facecolor=C["bg"], edgecolor=C["border_m"],
              labelcolor=C["text"], fontsize=8.5, framealpha=0.9)

    # ── Etiqueta módulo offline ───────────────────────────────────────────
    ax.text(0.13, 0.83, "OFFLINE\n(una vez por cámara)",
            ha="center", va="bottom", fontsize=7.5,
            color=C["border_c"], style="italic",
            transform=ax.transAxes)

    plt.tight_layout(pad=0)

    if save:
        os.makedirs(OUT_DIR, exist_ok=True)
        out = os.path.join(OUT_DIR, "pipeline.png")
        fig.savefig(out, dpi=160, bbox_inches="tight", facecolor=C["bg"])
        print(f"Diagrama guardado: {out}")

    plt.show()


def main():
    ap = argparse.ArgumentParser(description="Diagrama del pipeline cv-lit")
    ap.add_argument("--save", action="store_true", help="Guardar PNG en output/")
    args = ap.parse_args()
    draw(save=args.save)


if __name__ == "__main__":
    main()
