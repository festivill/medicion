"""Dibujos Tk del preview: tanques, esferas, camiones, buques, ductos, eléctrico.

Extraído de app.py sin modificaciones (refactor modular v1.5).
"""
import hashlib

try:
    _real_md5 = hashlib.md5
    def patched_md5(data=b'', **kwargs):
        # Eliminamos el argumento 'usedforsecurity' si existe, porque Python 3.8 no lo entiende
        if 'usedforsecurity' in kwargs:
            del kwargs['usedforsecurity']
        return _real_md5(data, **kwargs)
    hashlib.md5 = patched_md5
except:
    pass


import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib import colors
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
import json
import os
from datetime import datetime
import math
import base64
from io import BytesIO
import ctypes
import re
import platform
import subprocess
import traceback
import sqlite3, pathlib

from db import (
    _get_db_path, _init_db,
    db_buscar_funcionarios, db_guardar_funcionario,
    db_todos_funcionarios, db_eliminar_funcionario,
    _get_aduana_db_path, _init_aduana_db,
    db_get_aduanas, db_guardar_aduana, db_eliminar_aduana,
    db_get_lugares_operativos, db_guardar_lugar_operativo,
    db_eliminar_lugar_operativo,
    _init_funciones_db,
    db_get_funciones, db_guardar_funcion, db_eliminar_funcion,
)
from assets.icons import ICON_WINDOW_B64, ICON_REPORT_B64
from applog import app_dir as _app_dir, instalar_hooks as _instalar_hooks


class DibujoTkMixin:
    def construir_preview_tab(self):
        """Construye la solapa de Vista Previa con dibujo del buque y botones de reportes."""
        main_f = ttk.Frame(self.tab_preview)
        main_f.pack(fill="both", expand=True)

        # --- BARRA SUPERIOR ---
        top_bar = tk.Frame(main_f, bg="#1B3A5C", height=50)
        top_bar.pack(fill="x")
        top_bar.pack_propagate(False)
        tk.Label(top_bar, text="VISTA PREVIA DEL BUQUE Y REPORTES", font=("Arial", 8, "bold"), fg="white", bg="#1B3A5C").pack(side="left", padx=15)
        tk.Button(top_bar, text="  Actualizar Vista  ", bg="#2980B9", fg="white", font=("Arial", 8, "bold"),
                  command=lambda: self.refresh_preview_canvas(canvas_prev)).pack(side="left", padx=10, pady=8)
        tk.Button(top_bar, text="  GENERAR REPORTES PDF...  ", bg="#27AE60", fg="white", font=("Arial", 8, "bold"),
                  command=self.generar_con_seleccion, cursor="hand2").pack(side="right", padx=15, pady=8, ipadx=8)
        tk.Button(top_bar, text="  Vista Previa PDF  ", bg="#8E44AD", fg="white", font=("Arial", 8, "bold"),
                  command=self.preview_pdf_temp, cursor="hand2").pack(side="right", padx=5, pady=8)

        # --- CANVAS PRINCIPAL ---
        canvas_prev = tk.Canvas(main_f, bg="#E8F0FE")
        canvas_prev.pack(fill="both", expand=True)
        canvas_prev.bind("<Configure>", lambda e: self.refresh_preview_canvas(canvas_prev))

    def refresh_preview_canvas(self, cv):
        """Dibuja la vista del buque/unidad en el canvas de preview."""
        cv.delete("all")
        w = cv.winfo_width()
        h = cv.winfo_height()
        if w < 200 or h < 200: return

        buque_name = self.get_var("car_buque").get() or "Sin Nombre"
        tipo_nave = self.get_var("car_tipo_nave").get() or "BUQUE"
        cv.create_text(w/2, 18, text=f"{tipo_nave}: {buque_name}", font=("Arial", 8), fill="#1B3A5C")

        ship_w = w - 20
        if self.es_maritimo():
            # Buques: 2 vistas (babor arriba, estribor abajo)
            half_h = (h - 40) / 2
            self.dibujar_unidad_tk(cv, 10, 35, ship_w, half_h - 10, "BABOR", "inicial")
            self.dibujar_unidad_tk(cv, 10, 35 + half_h, ship_w, half_h - 10, "ESTRIBOR", "inicial")
        else:
            # Tierra/esfera/camion/ducto/electrico: canvas completo
            self.dibujar_unidad_tk(cv, 10, 35, ship_w, h - 50, "AMBOS", "inicial")

    def dibujar_unidad_tk(self, cv, x, y, width, height, side_label, etapa_key, tank_names=None, carb_names=None):
        """Dispatcher principal — redirige al dibujo correcto."""
        tm = self.get_tipo_medio()
        if "TANQUE FIJO" in tm:
            self._draw_vertical_tank(cv, x, y, width, height, etapa_key, tank_names, flotante=False)
        elif "TANQUE FLOTANTE" in tm:
            self._draw_vertical_tank(cv, x, y, width, height, etapa_key, tank_names, flotante=True)
        elif tm == "ESFERA DE GAS":
            self._draw_spheres(cv, x, y, width, height, etapa_key, tank_names)
        elif "CAMION GAS" in tm:
            self._draw_pressure_truck(cv, x, y, width, height, etapa_key, tank_names)
        elif "CAMION" in tm:
            self._draw_liquid_truck(cv, x, y, width, height, etapa_key, tank_names)
        elif tm in ("OLEODUCTO","POLIDUCTO","GASODUCTO"):
            self._draw_pipeline(cv, x, y, width, height, etapa_key, tm, tank_names)
        elif tm == "MEDICION ELECTRICA":
            self._draw_electric(cv, x, y, width, height, etapa_key, tank_names)
        elif "GASERO" in tm or ("GLP" in tm and "CAMION" not in tm):
            self._draw_moss_vessel(cv, x, y, width, height, side_label, etapa_key, tank_names, carb_names)
        elif "METANERO" in tm or "GNL" in tm:
            self._draw_membrane_vessel(cv, x, y, width, height, side_label, etapa_key, tank_names, carb_names)
        else:
            self.dibujar_buque_tk(cv, x, y, width, height, side_label, etapa_key, tank_names, carb_names)

    def _sz(self, H, base=0.032, cap=8, floor=5):
        return ("Arial", min(cap, max(floor, int(H*base))))

    def _draw_bg(self, cv, x, y, W, H, color="#F4F6F7", border="#BDC3C7"):
        cv.create_rectangle(x, y, x+W, y+H, fill=color, outline=border, width=2)

    def _draw_fill_bar(self, cv, x, y_top, y_bot, x_left, x_right, pct, prod_fill, water_pct=0.0):
        """Draw product (bottom) and water layer (very bottom) with no blue for product."""
        if pct <= 0: return
        bar_h = y_bot - y_top
        # Water layer (blue)
        if water_pct > 0:
            wy = y_bot - int(bar_h * water_pct)
            cv.create_rectangle(x_left, wy, x_right, y_bot, fill="#3498DB", outline="")
        # Product layer above water
        prod_h = int(bar_h * max(0, pct - water_pct))
        if prod_h > 0:
            py = y_bot - int(bar_h*pct)
            # Gradient simulation: 3 shades
            shade1, shade2 = prod_fill
            cv.create_rectangle(x_left, py, x_right, y_bot - int(bar_h*water_pct), fill=shade1, outline="")
            # Highlight top 20% — sin stipple, dos capas de color
            hlt_h = max(2, prod_h//5)
            cv.create_rectangle(x_left, py, x_right, py+hlt_h, fill=shade2, outline="")

    def _draw_level_text(self, cv, cx, cy, pct, font, color="#1B3A5C"):
        if pct > 0.02:
            cv.create_text(cx, cy, text=f"{pct*100:.1f}%", font=font, fill=color)

    def _get_fill_pct(self, tk_name, etapa_key, alt_var="alt_ref", sond_var="s_corr"):
        """Return (vol_pct, water_pct) safely.
        vol_pct = fracción del tanque con producto total (incluye agua abajo).
        water_pct = fracción del tanque con agua (desde el fondo).
        Para dibujos: el producto ocupa [water_pct .. vol_pct], agua [0 .. water_pct].
        """
        try:
            if not etapa_key or not tk_name: return 0.0, 0.0
            ref = self.parse_float(self.get_var(f"{etapa_key}_{tk_name}_{alt_var}").get() or "0")
            if ref <= 0: return 0.0, 0.0
            s   = self.parse_float(self.get_var(f"{etapa_key}_{tk_name}_{sond_var}").get() or "0")
            # Intentar agua_s_real primero (marítimo), luego agua_mm (tierra), luego vol_nat_agua como fallback
            aw_str = (self.get_var(f"{etapa_key}_{tk_name}_agua_s_real").get()
                      or self.get_var(f"{etapa_key}_{tk_name}_agua_mm").get()
                      or "0")
            aw = self.parse_float(aw_str)
            vol_pct = min(max(s/ref, 0.0), 1.0)
            # agua como fracción de la altura total — limitada a 40% del volumen
            wat_pct = min(max(aw/ref, 0.0), vol_pct * 0.4)
            return vol_pct, wat_pct
        except: return 0.0, 0.0

    def _draw_vertical_tank(self, cv, x, y, W, H, etapa_key, tank_names, flotante=False):
        """Tanque vertical API 650 -- techo fijo conico 1:16 o techo flotante con ponton."""
        import math
        if tank_names is None: tank_names = self.lista_tanques
        if H < 40 or W < 60: return
        n = max(len(tank_names), 1)

        def bez(p0, p1, p2, p3, n_pts=16):
            pts = []
            for i in range(n_pts + 1):
                t = i / n_pts; u = 1 - t
                pts += [u**3*p0[0]+3*u**2*t*p1[0]+3*u*t**2*p2[0]+t**3*p3[0],
                        u**3*p0[1]+3*u**2*t*p1[1]+3*u*t**2*p2[1]+t**3*p3[1]]
            return pts

        fs  = min(10, max(5, int(H * 0.036))); fss = min(9, max(4, int(H * 0.029)))
        FT  = ("Arial", fs);  FTS = ("Arial", fss)

        TITLE_H  = max(16, int(H * 0.075))
        GROUND_Y = y + H - max(24, int(H * 0.12))
        BUND_H   = max(14, int(H * 0.09))

        # Vista lateral de tanque cilíndrico vertical: rectángulo más alto que ancho o cuadrado
        avail_h  = GROUND_Y - BUND_H - y - TITLE_H - 10
        pad      = max(10, int(W * 0.05))
        total_w  = W - 2 * pad
        raw_tw   = max(32, total_w // n)
        TK_W     = min(raw_tw, int(total_w * 0.90 / n))
        TK_H     = min(int(avail_h * 0.85), int(TK_W * 1.2))  # más alto que ancho o cuadrado
        TK_H     = max(40, TK_H)
        TK_BOT   = GROUND_Y - BUND_H - max(4, int(H * 0.02))
        TK_TOP   = TK_BOT - TK_H
        ELIPSE_RY = 0  # sin elipses, vista lateral pura

        gap = max(4, int(TK_W * 0.06))
        total_tanks_w = n * TK_W
        x_offset_cv = (W - total_tanks_w) // 2

        # ── Sky gradient background ───────────────────────────────────────
        sky_colors = ["#D6EAF8", "#DCE9F5", "#E2E9F1", "#E8EAEE", "#EFF0F2", "#F5F6F8", "#F7F9FC"]
        sky_zone_h = GROUND_Y - y
        for si, sc in enumerate(sky_colors):
            sy1 = y + int(sky_zone_h * si / len(sky_colors))
            sy2 = y + int(sky_zone_h * (si + 1) / len(sky_colors))
            cv.create_rectangle(x, sy1, x + W, sy2, fill=sc, outline="")
        cv.create_rectangle(x, y, x + W, y + H, fill="", outline="#85929E", width=1)

        tipo_lbl = "TANQUE TECHO FLOTANTE" if flotante else "TANQUE TECHO FIJO"
        instalacion = self.get_var("car_buque").get() or ""
        title_txt = f"{tipo_lbl}  --  {instalacion}" if instalacion else tipo_lbl
        cv.create_text(x + W // 2 + 1, y + TITLE_H // 2 + 1, text=title_txt, font=FT, fill="#B0B8C0")
        cv.create_text(x + W // 2, y + TITLE_H // 2, text=title_txt, font=FT, fill="#1B3A5C")

        # ── Ground (asphalt gradient) ─────────────────────────────────────
        ground_h = y + H - GROUND_Y
        gnd_cols = ["#6B7380", "#5F6672", "#545B66", "#4A5059", "#41474F"]
        for gi, gc in enumerate(gnd_cols):
            gy1 = GROUND_Y + int(ground_h * gi / len(gnd_cols))
            gy2 = GROUND_Y + int(ground_h * (gi + 1) / len(gnd_cols))
            cv.create_rectangle(x, gy1, x + W, gy2, fill=gc, outline="")
        cv.create_line(x, GROUND_Y, x + W, GROUND_Y, fill="#8A929C", width=1)

        # ── Bund (containment dike) ───────────────────────────────────────
        bund_x = x + pad // 2;  bund_w = W - pad
        bund_top = GROUND_Y - BUND_H
        cv.create_rectangle(bund_x + 3, bund_top + 3, bund_x + bund_w + 3, GROUND_Y + 6,
                            fill="#3A3F47", outline="")
        bund_grads = ["#D5D8DB", "#CDD0D3", "#C5C8CB", "#BDC0C3", "#B5B8BB", "#ADB0B3"]
        for bi, bc in enumerate(bund_grads):
            by1 = bund_top + int(BUND_H * bi / len(bund_grads))
            by2 = bund_top + int(BUND_H * (bi + 1) / len(bund_grads))
            cv.create_rectangle(bund_x, by1, bund_x + bund_w, by2, fill=bc, outline="")
        for li in range(0, bund_w, max(8, bund_w // 14)):
            cv.create_line(bund_x + li, bund_top + 4, bund_x + li + 5, GROUND_Y,
                           fill="#B0B5B8", width=1)
        for px2 in [bund_x, bund_x + bund_w]:
            cv.create_rectangle(px2 - 4, bund_top - 8, px2 + 4, GROUND_Y + 4,
                                fill="#909AA3", outline="#6D7880", width=1)
            cv.create_line(px2 - 4, bund_top - 8, px2 - 4, GROUND_Y + 4, fill="#C0C8CC", width=1)
            cv.create_line(px2 + 4, bund_top - 8, px2 + 4, GROUND_Y + 4, fill="#6D7880", width=1)
        cv.create_rectangle(bund_x, bund_top, bund_x + bund_w, GROUND_Y, fill="", outline="#7F8C8D", width=2)
        for ej in range(1, 4):
            ej_x = bund_x + int(bund_w * ej / 4)
            cv.create_line(ej_x, bund_top, ej_x, GROUND_Y, fill="#A0A5A8", width=1, dash=(6, 4))

        PROD_COL = [
            ("#C0392B", "#7B241C", "#F1948A"), ("#E67E22", "#A04000", "#FAD7A0"),
            ("#27AE60", "#1E8449", "#A9DFBF"), ("#D4AC0D", "#9A7D0A", "#F9E79F"),
            ("#784212", "#6E2C00", "#C39BD3"), ("#2C3E50", "#17202A", "#85929E"),
            ("#7D3C98", "#6C3483", "#D2B4DE"), ("#C2185B", "#AD1457", "#F48FB1"),
        ]

        for i, tn in enumerate(tank_names[:n]):
            tx = x + x_offset_cv + i * TK_W + gap // 2
            tw = TK_W - gap
            cx_t = tx + tw // 2
            inner_h = TK_BOT - TK_TOP
            sh_w = max(3, tw // 9)

            # ── Drop shadow ───────────────────────────────────────────────
            sh_off = max(3, int(tw * 0.04))
            cv.create_rectangle(tx + sh_off, TK_TOP + ELIPSE_RY + sh_off,
                                tx + tw + sh_off, TK_BOT + sh_off,
                                fill="#404850", outline="")
            cv.create_oval(tx + sh_off, TK_BOT - ELIPSE_RY + sh_off,
                           tx + tw + sh_off, TK_BOT + ELIPSE_RY + sh_off,
                           fill="#404850", outline="")

            # ── Concrete ringwall foundation ──────────────────────────────
            base_h = max(8, int(TK_H * 0.07))
            base_x = tx - max(6, tw // 8)
            base_w = tw + max(12, tw // 4)
            cv.create_rectangle(base_x + 2, TK_BOT + 2, base_x + base_w + 2, TK_BOT + base_h + 2,
                                fill="#6D7880", outline="")
            fnd_grads = ["#C8CDD1", "#BCC1C5", "#B0B5B9", "#A4A9AD", "#989DA1"]
            for fi, fc in enumerate(fnd_grads):
                fy1 = TK_BOT + int(base_h * fi / len(fnd_grads))
                fy2 = TK_BOT + int(base_h * (fi + 1) / len(fnd_grads))
                cv.create_rectangle(base_x, fy1, base_x + base_w, fy2, fill=fc, outline="")
            cv.create_rectangle(base_x, TK_BOT, base_x + base_w, TK_BOT + base_h,
                                fill="", outline="#8D9498", width=1)
            n_bolts = max(3, tw // 16)
            for bi in range(n_bolts):
                bx = base_x + int(base_w * (bi + 0.5) / n_bolts)
                cv.create_oval(bx - 2, TK_BOT + 1, bx + 2, TK_BOT + 5, fill="#6D7880", outline="#5D6D7E")

            # ── Fill percentages ──────────────────────────────────────────
            vp, wp = self._get_fill_pct(tn, etapa_key)
            pnm  = self.get_var(f"{etapa_key}_{tn}_prod_name").get() if etapa_key else ""
            vlit = self.get_var(f"{etapa_key}_{tn}_vol_nat_prod").get() if etapa_key else ""
            ci = abs(hash(pnm)) % len(PROD_COL) if pnm else i % len(PROD_COL)
            prod_c, prod_dk, prod_lt = PROD_COL[ci]

            # ── Cylinder body: 12-strip metallic gradient ─────────────────
            stripe_defs = [
                (0.00, 0.05, "#707D87"), (0.05, 0.10, "#808D97"),
                (0.10, 0.18, "#95A2AC"), (0.18, 0.28, "#A8B5BF"),
                (0.28, 0.40, "#BCC9D3"), (0.40, 0.52, "#D0DCE5"),
                (0.52, 0.60, "#E0E9EF"), (0.60, 0.68, "#E8F0F5"),
                (0.68, 0.76, "#DFE7EC"), (0.76, 0.84, "#CCD6DD"),
                (0.84, 0.92, "#B0BAC2"), (0.92, 1.00, "#8A9398"),
            ]
            for s_from, s_to, sc in stripe_defs:
                sx1 = int(tx + tw * s_from)
                sx2 = int(tx + tw * s_to)
                cv.create_rectangle(sx1, TK_TOP + ELIPSE_RY, sx2, TK_BOT, fill=sc, outline="")

            # ── Shell courses (5-7 horizontal weld seams) ─────────────────
            n_courses = min(7, max(5, TK_H // 25))
            for ci2 in range(1, n_courses):
                wy = TK_TOP + ELIPSE_RY + int((inner_h - ELIPSE_RY) * ci2 / n_courses)
                # Double weld line (realistic butt-weld seam)
                cv.create_line(tx + 2, wy, tx + tw - 2, wy, fill="#98A0A8", width=1)
                cv.create_line(tx + 2, wy + 1, tx + tw - 2, wy + 1, fill="#B8C0C8", width=1)

            # Vertical weld seam (staggered between courses)
            for ci2 in range(n_courses):
                wy1 = TK_TOP + ELIPSE_RY + int((inner_h - ELIPSE_RY) * ci2 / n_courses)
                wy2 = TK_TOP + ELIPSE_RY + int((inner_h - ELIPSE_RY) * (ci2 + 1) / n_courses)
                vwx = tx + int(tw * (0.45 + 0.10 * (ci2 % 2)))
                cv.create_line(vwx, wy1 + 2, vwx, wy2 - 2, fill="#B0B8C0", width=1, dash=(8, 12))

            # ── Water layer (blue, from bottom) ───────────────────────────
            if wp > 0:
                wy = int(TK_BOT - inner_h * wp)
                cv.create_rectangle(tx + sh_w, wy, tx + tw - sh_w, TK_BOT - ELIPSE_RY,
                                    fill="#5DADE2", outline="")
                cv.create_oval(tx + sh_w, wy - ELIPSE_RY // 2, tx + tw - sh_w, wy + ELIPSE_RY // 2,
                               fill="#2E86C1", outline="#2E86C1", width=1)
                for sw in range(3):
                    sw_y = wy + int((TK_BOT - ELIPSE_RY - wy) * (sw + 1) / 4)
                    cv.create_line(tx + sh_w + int(tw * 0.15), sw_y,
                                   tx + tw - sh_w - int(tw * 0.15), sw_y,
                                   fill="#85C1E9", width=1, dash=(4, 6))

            # ── Product fill above water ──────────────────────────────────
            if vp > wp + 0.01:
                py_top = int(TK_BOT - inner_h * vp)
                py_bot = int(TK_BOT - inner_h * wp) if wp > 0 else TK_BOT - ELIPSE_RY
                cv.create_rectangle(tx + sh_w, py_top, tx + tw - sh_w, py_bot, fill=prod_c, outline="")
                prod_zone_h = py_bot - py_top
                if prod_zone_h > 10:
                    refl_h = max(3, int(prod_zone_h * 0.12))
                    cv.create_rectangle(tx + sh_w, py_top, tx + tw - sh_w, py_top + refl_h,
                                        fill=prod_lt, outline="")
                    cv.create_rectangle(tx + sh_w, py_bot - max(2, refl_h // 2), tx + tw - sh_w, py_bot,
                                        fill=prod_dk, outline="")
                cv.create_oval(tx + sh_w, py_top - ELIPSE_RY // 2, tx + tw - sh_w, py_top + ELIPSE_RY // 2,
                               fill=prod_lt, outline=prod_dk, width=1)

            # ── Bottom ellipse ────────────────────────────────────────────
            cv.create_oval(tx, TK_BOT - ELIPSE_RY, tx + tw, TK_BOT + ELIPSE_RY,
                           fill="#8A9398", outline="#6D7880", width=1)
            if vp > 0.01:
                fill_col_bot = prod_c if vp > wp else "#5DADE2"
                cv.create_rectangle(tx + sh_w, TK_BOT - ELIPSE_RY, tx + tw - sh_w, TK_BOT,
                                    fill=fill_col_bot, outline="")
            else:
                cv.create_rectangle(tx, TK_BOT - ELIPSE_RY, tx + tw, TK_BOT, fill="#9BA7B2", outline="")

            # ── ROOF ──────────────────────────────────────────────────────
            if flotante:
                # ── Floating roof: pontón plano sobre el líquido ──────────
                PATAS_FRAC = 0.15
                ponton_h = max(6, int(TK_H * 0.04))
                liq_y   = int(TK_BOT - inner_h * vp)
                patas_y = int(TK_BOT - inner_h * PATAS_FRAC)
                fy = patas_y if vp <= PATAS_FRAC else liq_y

                # Support legs (patas de apoyo debajo del pontón)
                pata_base = fy + ponton_h
                for pi_frac in [0.20, 0.45, 0.70]:
                    px = int(tx + tw * pi_frac)
                    cv.create_line(px, pata_base, px, TK_BOT,
                                   fill="#7F8C8D", width=2)
                    cv.create_rectangle(px - 4, TK_BOT - 2, px + 4, TK_BOT + 1,
                                        fill="#808B96", outline="")

                # Pontón (rectángulo plano sobre el líquido)
                pont_margin = max(2, int(tw * 0.03))
                # Sombra del pontón
                cv.create_rectangle(tx + pont_margin + 2, fy + 2,
                                    tx + tw - pont_margin + 2, fy + ponton_h + 2,
                                    fill="#3A4550", outline="")
                # Cuerpo del pontón (gradiente)
                pont_grads = ["#6D8898", "#7A9CAC", "#88AAB8", "#7A9CAC", "#6D8898"]
                for pg_i, pg_c in enumerate(pont_grads):
                    pg_y1 = fy + int(ponton_h * pg_i / len(pont_grads))
                    pg_y2 = fy + int(ponton_h * (pg_i + 1) / len(pont_grads))
                    cv.create_rectangle(tx + pont_margin, pg_y1,
                                        tx + tw - pont_margin, pg_y2,
                                        fill=pg_c, outline="")
                cv.create_rectangle(tx + pont_margin, fy,
                                    tx + tw - pont_margin, fy + ponton_h,
                                    fill="", outline="#4A6878", width=2)

                # Rim seal (sello entre pontón y pared del tanque)
                seal_h = max(3, ponton_h // 2)
                # Sello izquierdo
                cv.create_rectangle(tx + 1, fy - seal_h, tx + pont_margin + 2, fy + ponton_h + seal_h,
                                    fill="#3D3D3D", outline="#2A2A2A", width=1)
                # Sello derecho
                cv.create_rectangle(tx + tw - pont_margin - 2, fy - seal_h,
                                    tx + tw - 1, fy + ponton_h + seal_h,
                                    fill="#3D3D3D", outline="#2A2A2A", width=1)

                # Drain pipe (articulado, del pontón al fondo)
                drain_x = tx + int(tw * 0.35)
                cv.create_line(drain_x, fy + ponton_h, drain_x - 4, TK_BOT - 6,
                               fill="#5D6D7E", width=2)
                cv.create_oval(drain_x - 6, fy + ponton_h - 3,
                               drain_x + 2, fy + ponton_h + 3,
                               fill="#4A5568", outline="")

                # Rolling ladder (escalera pivotante DENTRO del tanque, del borde superior al pontón)
                lad_x  = tx + int(tw * 0.82)
                lad_top_y = TK_TOP + 2
                lad_bot_y = fy
                lad_off = max(4, int(tw * 0.05))
                cv.create_line(lad_x, lad_top_y, lad_x, lad_bot_y, fill="#808B96", width=1)
                cv.create_line(lad_x + lad_off, lad_top_y, lad_x + lad_off, lad_bot_y, fill="#95A5A6", width=1)
                n_rungs = max(3, int((lad_bot_y - lad_top_y) / max(8, int(TK_H * 0.08))))
                for ri in range(n_rungs):
                    ry = int(lad_top_y + (lad_bot_y - lad_top_y) * (ri + 0.5) / n_rungs)
                    cv.create_line(lad_x, ry, lad_x + lad_off, ry, fill="#7F8C8D", width=1)

                # Guide poles (guías verticales)
                for cg_frac in [0.15, 0.85]:
                    cgx = int(tx + tw * cg_frac)
                    cv.create_line(cgx, fy, cgx, TK_TOP,
                                   fill="#95A5A6", width=1, dash=(4, 5))

                # Sounding reference (línea de medición)
                datum_x = tx + int(tw * 0.12)
                _sond_y_top = fy + 2
                _sond_y_bot = TK_BOT - 2
                if _sond_y_bot > _sond_y_top + 10:
                    cv.create_line(datum_x, _sond_y_top, datum_x, _sond_y_bot,
                                   fill="#F4D03F", width=1, dash=(3, 3))
                    cv.create_polygon(datum_x - 4, _sond_y_top + 6, datum_x, _sond_y_top,
                                      datum_x + 4, _sond_y_top + 6, fill="#F4D03F", outline="")
                    cv.create_polygon(datum_x - 4, _sond_y_bot - 6, datum_x, _sond_y_bot,
                                      datum_x + 4, _sond_y_bot - 6, fill="#F4D03F", outline="")
                    if fss >= 5:
                        cv.create_text(datum_x - 3, (_sond_y_top + _sond_y_bot) // 2,
                                       text="S", font=("Arial", max(4, fss - 2), "bold"),
                                       fill="#F4D03F", anchor="e")

                if vp > PATAS_FRAC and fss >= 5:
                    cv.create_text(cx_t, fy,
                                   text=f"Ponton {vp*100:.0f}%",
                                   font=("Arial", max(4, fss - 2)), fill="#D5D8DC")

            else:
                # ── Fixed cone roof (slope 1:16, almost flat) ─────────────
                # 1:16 slope = rise/run -> rise = tw / (2*16) -> very shallow
                roof_rise = max(4, int(tw / 32))  # 1:16 slope from edge to center
                apex_y = TK_TOP - roof_rise
                # Slight overhang beyond shell
                overhang = max(3, int(tw * 0.03))

                # Shadow behind roof
                cv.create_polygon(tx - overhang + 2, TK_TOP + ELIPSE_RY + 2,
                                  cx_t + 2, apex_y + 2,
                                  tx + tw + overhang + 2, TK_TOP + ELIPSE_RY + 2,
                                  fill="#707880", outline="")
                # Multi-face shading for very shallow cone
                faces = [
                    (0.00, 0.30, "#D8E0E5"), (0.30, 0.55, "#C8D2D8"),
                    (0.55, 0.75, "#B0BCC4"), (0.75, 1.00, "#96A8B0"),
                ]
                for f_from, f_to, f_col in faces:
                    fx1 = int(tx - overhang + (tw + 2 * overhang) * f_from)
                    fx2 = int(tx - overhang + (tw + 2 * overhang) * f_to)
                    cv.create_polygon(fx1, TK_TOP + ELIPSE_RY, cx_t, apex_y, fx2, TK_TOP + ELIPSE_RY,
                                      fill=f_col, outline="")
                # Specular band
                cv.create_polygon(tx + int(tw * 0.25), TK_TOP + ELIPSE_RY,
                                  cx_t, apex_y,
                                  tx + int(tw * 0.42), TK_TOP + ELIPSE_RY,
                                  fill="#E8EFF3", outline="")
                cv.create_polygon(tx - overhang, TK_TOP + ELIPSE_RY, cx_t, apex_y,
                                  tx + tw + overhang, TK_TOP + ELIPSE_RY,
                                  fill="", outline="#6D7D84", width=2)
                # Rafters
                for ri_a in [0.15, 0.30, 0.50, 0.70, 0.85]:
                    rib_x = int(tx + tw * ri_a)
                    cv.create_line(rib_x + 1, TK_TOP + ELIPSE_RY + 1, cx_t + 1, apex_y + 1,
                                   fill="#7A868F", width=1)
                    cv.create_line(rib_x, TK_TOP + ELIPSE_RY, cx_t, apex_y, fill="#9DABB5", width=1)
                # Center hub plate
                hub_r = max(3, tw // 16)
                cv.create_oval(cx_t - hub_r, apex_y - hub_r // 2, cx_t + hub_r, apex_y + hub_r // 2,
                               fill="#A0ABB4", outline="#7F8C8D")

                # PVRV (pressure-vacuum relief valve) - mushroom shape
                pvrv_h = max(8, int(TK_H * 0.08))
                pvrv_x = cx_t + int(tw * 0.15)
                # Nozzle stub
                cv.create_rectangle(pvrv_x - 3, apex_y - pvrv_h, pvrv_x + 3, apex_y - 2,
                                    fill="#808B96", outline="#5D6D7E", width=1)
                # Mushroom cap (wider disc on top)
                cap_w = max(8, tw // 8)
                cap_h = max(4, int(TK_H * 0.03))
                cv.create_oval(pvrv_x - cap_w // 2, apex_y - pvrv_h - cap_h,
                               pvrv_x + cap_w // 2, apex_y - pvrv_h + cap_h // 2,
                               fill="#95A5A6", outline="#636E72", width=1)
                cv.create_oval(pvrv_x - cap_w // 3, apex_y - pvrv_h - cap_h + 1,
                               pvrv_x + cap_w // 4, apex_y - pvrv_h,
                               fill="#B0BCC4", outline="")

                # Gauge hatch / thief hatch on roof
                gh_x = tx + int(tw * 0.30)
                gh_base = TK_TOP + ELIPSE_RY - 2
                # Interpolate roof height at gh_x
                ghf = abs(gh_x - cx_t) / max(1, tw // 2)
                gh_roof_y = int(apex_y + (TK_TOP + ELIPSE_RY - apex_y) * ghf)
                cv.create_rectangle(gh_x - 3, gh_roof_y - 8, gh_x + 3, gh_roof_y,
                                    fill="#5D6D7E", outline="#4A5568")
                cv.create_oval(gh_x - 5, gh_roof_y - 12, gh_x + 5, gh_roof_y - 7,
                               fill="#808B96", outline="#5D6D7E", width=1)

            # ── Top ellipse (cylinder cap) ────────────────────────────────
            if not flotante:
                cv.create_arc(tx, TK_TOP - ELIPSE_RY, tx + tw, TK_TOP + ELIPSE_RY,
                              start=180, extent=180,
                              fill="#CAD2D7", outline="#808B96", width=2, style="chord")
                cv.create_arc(tx + tw // 5, TK_TOP - ELIPSE_RY // 2,
                              tx + tw * 3 // 4, TK_TOP + ELIPSE_RY // 2,
                              start=195, extent=150,
                              fill="#E2E8EC", outline="", style="chord")

            # ── Wind girders (1-2 stiffening rings on shell) ──────────────
            wg_positions = [0.33, 0.66] if TK_H > 60 else [0.50]
            for ri_frac in wg_positions:
                ry = TK_TOP + ELIPSE_RY + int((TK_BOT - TK_TOP - ELIPSE_RY) * ri_frac)
                cv.create_oval(tx + 1, ry - 2, tx + tw + 1, ry + 4, fill="#808890", outline="")
                cv.create_oval(tx, ry - 3, tx + tw, ry + 3, fill="#A0ABB4", outline="#7F8C8D", width=1)
                cv.create_oval(tx + 2, ry - 2, tx + tw - 2, ry, fill="#C0CAD0", outline="")
                for lug_x in [tx - 5, tx + tw]:
                    cv.create_rectangle(lug_x, ry - 4, lug_x + 5, ry + 4, fill="#95A5A6", outline="#7F8C8D")

            # ── Nozzle stubs on shell ─────────────────────────────────────
            noz_fracs = [0.20, 0.50, 0.80]
            for nfrac in noz_fracs:
                noz_y = TK_TOP + ELIPSE_RY + int((inner_h - ELIPSE_RY) * nfrac)
                noz_len = max(4, int(tw * 0.06))
                # Nozzle pipe stub on right side of tank
                cv.create_rectangle(tx + tw, noz_y - 2, tx + tw + noz_len, noz_y + 2,
                                    fill="#6D7880", outline="#4A5568", width=1)
                # Blind flange cap
                cv.create_rectangle(tx + tw + noz_len, noz_y - 4, tx + tw + noz_len + 3, noz_y + 4,
                                    fill="#5D6D7E", outline="#4A5568", width=1)

            # ── Spiral staircase (diagonal line with landings) ────────────
            esc_x = tx + tw + max(6, int(tw * 0.08))
            esc_w = max(10, int(tw * 0.15))
            if esc_x + esc_w < x + W - 4:
                # Diagonal run (wrap simulation)
                n_landings = max(2, TK_H // 50)
                for li2 in range(n_landings):
                    lf1 = li2 / n_landings
                    lf2 = (li2 + 1) / n_landings
                    sy1 = int(TK_BOT - (inner_h - ELIPSE_RY) * lf1)
                    sy2 = int(TK_BOT - (inner_h - ELIPSE_RY) * lf2)
                    # Diagonal stair run
                    if li2 % 2 == 0:
                        cv.create_line(esc_x, sy1, esc_x + esc_w, sy2, fill="#808B96", width=2)
                        cv.create_line(esc_x + esc_w, sy1, esc_x + esc_w + max(4, esc_w // 3), sy2,
                                       fill="#95A5A6", width=1)
                    else:
                        cv.create_line(esc_x + esc_w, sy1, esc_x, sy2, fill="#808B96", width=2)
                    # Landing platform
                    cv.create_rectangle(esc_x - 2, sy2 - 2, esc_x + esc_w + 2, sy2 + 2,
                                        fill="#A0A8B0", outline="#808B96", width=1)
                # Handrail (continuous)
                cv.create_line(esc_x + esc_w + 3, TK_TOP + ELIPSE_RY, esc_x + esc_w + 3, TK_BOT,
                               fill="#BDC3C7", width=1)
                # Top platform
                plt_w = esc_w + 6
                cv.create_rectangle(esc_x - 3, TK_TOP - ELIPSE_RY - 6,
                                    esc_x + plt_w, TK_TOP - ELIPSE_RY,
                                    fill="#808B96", outline="#5D6D7E", width=1)
                rail_h = max(4, int(TK_H * 0.03))
                cv.create_line(esc_x - 3, TK_TOP - ELIPSE_RY - 6,
                               esc_x - 3, TK_TOP - ELIPSE_RY - 6 - rail_h, fill="#95A5A6", width=1)
                cv.create_line(esc_x + plt_w, TK_TOP - ELIPSE_RY - 6,
                               esc_x + plt_w, TK_TOP - ELIPSE_RY - 6 - rail_h, fill="#95A5A6", width=1)
                cv.create_line(esc_x - 3, TK_TOP - ELIPSE_RY - 6 - rail_h,
                               esc_x + plt_w, TK_TOP - ELIPSE_RY - 6 - rail_h, fill="#95A5A6", width=1)

            # ── Base piping and valves ────────────────────────────────────
            pipe_y_base = TK_BOT + base_h - 2
            asp_x = tx + tw // 4
            cv.create_rectangle(asp_x - 3, TK_BOT, asp_x + 3, pipe_y_base + 6, fill="#6D7880", outline="")
            cv.create_rectangle(asp_x - 2, TK_BOT, asp_x + 2, pipe_y_base + 6, fill="#808B96", outline="")
            cv.create_line(asp_x - 1, TK_BOT, asp_x - 1, pipe_y_base + 6, fill="#95A5A6", width=1)
            cv.create_rectangle(asp_x, pipe_y_base + 3, tx - 12, pipe_y_base + 7, fill="#6D7880", outline="")
            cv.create_rectangle(asp_x - 6, TK_BOT - 2, asp_x + 6, TK_BOT + 4,
                                fill="#4A5568", outline="#2C3E50", width=1)
            for fb in [asp_x - 5, asp_x + 4]:
                cv.create_oval(fb, TK_BOT - 1, fb + 2, TK_BOT + 1, fill="#808B96", outline="")
            vv_y = pipe_y_base + 5
            cv.create_polygon(asp_x - 7, vv_y - 6, asp_x + 7, vv_y + 6,
                              asp_x + 7, vv_y - 6, asp_x - 7, vv_y + 6,
                              fill="#2C3E50", outline="#1B2631", width=1)
            cv.create_line(asp_x, vv_y - 6, asp_x, vv_y - 14, fill="#5D6D7E", width=2)
            cv.create_oval(asp_x - 6, vv_y - 18, asp_x + 6, vv_y - 12, fill="", outline="#5D6D7E", width=2)

            # ── External level indicator (sight glass) ────────────────────
            lvl_x = tx - max(8, int(tw * 0.10))
            if lvl_x > x + 4:
                cv.create_rectangle(lvl_x - 3, TK_TOP + ELIPSE_RY, lvl_x + 3, TK_BOT - ELIPSE_RY,
                                    fill="#CDD4D8", outline="#95A5A6", width=1)
                cv.create_rectangle(lvl_x - 1, TK_TOP + ELIPSE_RY + 2, lvl_x + 1, TK_BOT - ELIPSE_RY - 2,
                                    fill="#E8F0F5", outline="")
                for mk_pct in [0.2, 0.4, 0.6, 0.8]:
                    mk_y = int(TK_BOT - inner_h * mk_pct)
                    cv.create_line(lvl_x - 7, mk_y, lvl_x + 7, mk_y, fill="#5D6D7E", width=1)
                    if fss >= 5:
                        cv.create_text(lvl_x - 9, mk_y, text=f"{int(mk_pct*100)}%",
                                       font=("Arial", max(4, fss - 2)), fill="#5D6D7E", anchor="e")
                if vp > 0:
                    lvl_y = int(TK_BOT - inner_h * vp)
                    cv.create_rectangle(lvl_x - 1, lvl_y, lvl_x + 1, TK_BOT - ELIPSE_RY - 2,
                                        fill=prod_c, outline="")
                    cv.create_rectangle(lvl_x - 7, lvl_y - 4, lvl_x + 7, lvl_y + 4,
                                        fill="#E74C3C", outline="#C0392B", width=2)

            # ── Final cylinder outline ────────────────────────────────────
            cv.create_rectangle(tx, TK_TOP + ELIPSE_RY, tx + tw, TK_BOT - ELIPSE_RY,
                                fill="", outline="#4A5568", width=2)
            cv.create_line(tx, TK_TOP + ELIPSE_RY, tx, TK_BOT - ELIPSE_RY, fill="#3D4B56", width=2)
            cv.create_line(tx + tw, TK_TOP + ELIPSE_RY, tx + tw, TK_BOT - ELIPSE_RY, fill="#3D4B56", width=2)

            # ── Bund drain ────────────────────────────────────────────────
            sump_x = bund_x + max(4, int(bund_w * 0.08))
            cv.create_rectangle(sump_x, bund_top + 1, sump_x + 10, bund_top + 5,
                                fill="#A9B2BC", outline="#7F8C8D")

            # ── Labels ────────────────────────────────────────────────────
            short = tn.replace("TANQUE ", "T.").replace("COMPARTIMENTO ", "C.").strip()[:8]
            plate_w = max(16, int(tw * 0.35))
            plate_h = max(10, int(inner_h * 0.06))
            plate_x_loc = cx_t - plate_w // 2
            plate_y_loc = TK_TOP + ELIPSE_RY + int(inner_h * 0.06)
            cv.create_rectangle(plate_x_loc, plate_y_loc, plate_x_loc + plate_w, plate_y_loc + plate_h,
                                fill="#F0F2F4", outline="#5D6D7E", width=1)
            txt_fill = self.contrast_text(prod_c) if vp > 0.2 else "#1B3A5C"
            cv.create_text(cx_t, plate_y_loc + plate_h // 2, text=short, font=FT, fill="#1B3A5C")
            cv.create_text(cx_t, plate_y_loc + plate_h + fs + 3, text=f"{vp*100:.0f}%", font=FTS,
                           fill=txt_fill if vp > 0.35 else "#1B3A5C")
            if pnm:
                cv.create_text(cx_t, TK_BOT - int(inner_h * 0.28), text=pnm[:12], font=FTS,
                               fill=txt_fill if vp > 0.4 else "#2C3E50")
            if vlit:
                cv.create_text(cx_t, TK_BOT - 12, text=f"{vlit} L", font=FTS,
                               fill=txt_fill if vp > 0.15 else "#1B3A5C")

    def _draw_spheres(self, cv, x, y, W, H, etapa_key, tank_names):
        """Horton spheres -- columns at EQUATOR splaying outward, beach-ball weld pattern, white/silver."""
        import math
        if tank_names is None: tank_names = self.lista_tanques
        if H < 60 or W < 80: return
        n = max(len(tank_names), 1)

        def bez(p0, p1, p2, p3, n_pts=16):
            pts = []
            for i in range(n_pts + 1):
                t = i / n_pts; u = 1 - t
                pts += [u**3*p0[0]+3*u**2*t*p1[0]+3*u*t**2*p2[0]+t**3*p3[0],
                        u**3*p0[1]+3*u**2*t*p1[1]+3*u*t**2*p2[1]+t**3*p3[1]]
            return pts

        fs  = min(10, max(5, int(H * 0.036)));  fss = min(9, max(4, int(H * 0.028)))
        FT  = ("Arial", fs);  FTS = ("Arial", fss)

        TITLE_H  = max(16, int(H * 0.075))
        GROUND_Y = y + H - max(18, int(H * 0.09))

        # ── Sky gradient background ───────────────────────────────────────
        sky_cols = ["#D6EAF8", "#DCEAF4", "#E2EBF0", "#E8ECEE", "#F0F2F4", "#F5F7FA"]
        sky_h = GROUND_Y - y
        for si, sc in enumerate(sky_cols):
            sy1 = y + int(sky_h * si / len(sky_cols))
            sy2 = y + int(sky_h * (si + 1) / len(sky_cols))
            cv.create_rectangle(x, sy1, x + W, sy2, fill=sc, outline="")
        cv.create_rectangle(x, y, x + W, y + H, fill="", outline="#5D6D7E", width=2)

        instalacion = self.get_var("car_buque").get() or "PLANTA"
        cv.create_text(x + W // 2 + 1, y + TITLE_H // 2 + 1,
                       text=f"ESFERAS DE GAS  --  {instalacion}", font=FT, fill="#B0B8C0")
        cv.create_text(x + W // 2, y + TITLE_H // 2,
                       text=f"ESFERAS DE GAS  --  {instalacion}", font=FT, fill="#1B3A5C")

        # ── Ground (concrete/gravel) ──────────────────────────────────────
        gnd_h = y + H - GROUND_Y
        gnd_cols = ["#8A929C", "#7D858F", "#707882", "#636B75", "#565E68"]
        for gi, gc in enumerate(gnd_cols):
            gy1 = GROUND_Y + int(gnd_h * gi / len(gnd_cols))
            gy2 = GROUND_Y + int(gnd_h * (gi + 1) / len(gnd_cols))
            cv.create_rectangle(x, gy1, x + W, gy2, fill=gc, outline="")
        cv.create_line(x + 1, GROUND_Y, x + W - 1, GROUND_Y, fill="#A0A8B0", width=1)

        zone_w = W - 30
        each_w = zone_w // n
        SPH_R  = min(int(H * 0.33), each_w // 2 - 14, int((GROUND_Y - y - TITLE_H - 22) * 0.46))
        SPH_R  = max(22, SPH_R)

        for i, tn in enumerate(tank_names[:n]):
            cx_s = x + 15 + i * each_w + each_w // 2
            # Columns attach at EQUATOR, splay outward to foundations
            LEG_H   = int(SPH_R * 0.85)
            EQ_Y    = GROUND_Y - LEG_H   # equator sits here
            cy_s    = EQ_Y                # sphere center = equator

            # ── Ground shadow ─────────────────────────────────────────────
            sh_r = int(SPH_R * 0.85)
            cv.create_oval(cx_s - sh_r, GROUND_Y - 3, cx_s + sh_r, GROUND_Y + 5,
                           fill="#404850", outline="")

            # ── 6-8 support columns from EQUATOR splaying outward ─────────
            n_cols = 8 if SPH_R > 40 else 6
            leg_w = max(3, SPH_R // 8)
            for ci2 in range(n_cols):
                ang_deg = ci2 * 360 / n_cols
                # Only draw columns visible in side view (front half roughly)
                ang_rad = math.radians(ang_deg)
                # Column attachment at equator (appears as ellipse projection)
                eq_x_off = int(SPH_R * 0.92 * math.cos(ang_rad))
                depth = math.sin(ang_rad)  # front/back (-1 to 1)
                # Skip columns on far side that are mostly hidden
                if abs(depth) > 0.85:
                    continue
                col_top_x = cx_s + eq_x_off
                col_top_y = cy_s
                # Splay outward: bottom is further from center than top
                splay = int(SPH_R * 0.35)
                col_bot_x = col_top_x + int(splay * math.cos(ang_rad) * 0.5)
                col_bot_y = GROUND_Y
                # Column shade based on depth
                col_fill = "#5D6D7E" if depth < 0 else "#808B96"
                # Tapered column
                tw_top = leg_w - 1
                tw_bot = leg_w + 2
                cv.create_polygon(col_top_x - tw_top, col_top_y,
                                  col_top_x + tw_top, col_top_y,
                                  col_bot_x + tw_bot, col_bot_y,
                                  col_bot_x - tw_bot, col_bot_y,
                                  fill=col_fill, outline="#4A5568", width=1)
                # Column highlight
                cv.create_line(col_top_x - tw_top + 1, col_top_y,
                               col_bot_x - tw_bot + 1, col_bot_y,
                               fill="#95A5A6", width=1)
                # Foundation pad
                bp_w = max(6, leg_w + 4)
                cv.create_rectangle(col_bot_x - bp_w, GROUND_Y - 3,
                                    col_bot_x + bp_w, GROUND_Y + 4,
                                    fill="#4A5568", outline="#2C3E50", width=1)
                for blt in [-bp_w + 2, bp_w - 2]:
                    cv.create_oval(col_bot_x + blt - 1, GROUND_Y - 1,
                                   col_bot_x + blt + 1, GROUND_Y + 1,
                                   fill="#3D4B56", outline="")

            # ── Diagonal cross-bracing between columns ────────────────────
            leg_spread = int(SPH_R * 0.92)
            mid_brace_y = cy_s + int(LEG_H * 0.50)
            cv.create_line(cx_s - leg_spread, cy_s, cx_s + leg_spread, GROUND_Y - 3,
                           fill="#7F8C8D", width=2, dash=(5, 4))
            cv.create_line(cx_s + leg_spread, cy_s, cx_s - leg_spread, GROUND_Y - 3,
                           fill="#7F8C8D", width=2, dash=(5, 4))
            # Horizontal bracing ring at mid-height
            cv.create_rectangle(cx_s - leg_spread, mid_brace_y - 2,
                                cx_s + leg_spread, mid_brace_y + 2,
                                fill="#6D7880", outline="#5D6D7E")

            # ── Equatorial walkway/platform with handrails ────────────────
            plt_w = int(SPH_R * 1.85)
            plt_h = max(5, int(SPH_R * 0.10))
            plt_y = cy_s
            # Platform shadow
            cv.create_rectangle(cx_s - plt_w // 2 + 2, plt_y + 2,
                                cx_s + plt_w // 2 + 2, plt_y + plt_h + 2,
                                fill="#4A5058", outline="")
            # Platform body with grating
            cv.create_rectangle(cx_s - plt_w // 2, plt_y, cx_s + plt_w // 2, plt_y + plt_h,
                                fill="#6D7880", outline="#5D6D7E", width=1)
            for gx in range(cx_s - plt_w // 2 + 4, cx_s + plt_w // 2 - 4, max(4, plt_w // 12)):
                cv.create_line(gx, plt_y + 1, gx, plt_y + plt_h - 1, fill="#5D6D7E", width=1)
            # Handrail posts and rails
            rail_h = max(8, int(SPH_R * 0.18))
            for rx in [-plt_w // 2 + 2, -plt_w // 4, 0, plt_w // 4, plt_w // 2 - 2]:
                bx2 = cx_s + rx
                cv.create_line(bx2, plt_y, bx2, plt_y - rail_h, fill="#808B96", width=1)
            cv.create_line(cx_s - plt_w // 2 + 2, plt_y - rail_h,
                           cx_s + plt_w // 2 - 2, plt_y - rail_h,
                           fill="#95A5A6", width=2)
            cv.create_line(cx_s - plt_w // 2 + 2, plt_y - rail_h // 2,
                           cx_s + plt_w // 2 - 2, plt_y - rail_h // 2,
                           fill="#808B96", width=1)

            # ── Access ladder from ground to equatorial platform ──────────
            lad_x = cx_s + int(SPH_R * 0.95)
            lad_w = max(6, int(SPH_R * 0.12))
            if lad_x + lad_w < x + W - 5:
                cv.create_line(lad_x, plt_y + plt_h, lad_x, GROUND_Y, fill="#808B96", width=2)
                cv.create_line(lad_x + lad_w, plt_y + plt_h, lad_x + lad_w, GROUND_Y, fill="#808B96", width=2)
                lad_h = GROUND_Y - plt_y - plt_h
                n_rungs = max(4, lad_h // max(6, int(SPH_R * 0.1)))
                for ri in range(n_rungs):
                    ry = plt_y + plt_h + int(lad_h * (ri + 0.5) / n_rungs)
                    cv.create_line(lad_x, ry, lad_x + lad_w, ry, fill="#7F8C8D", width=1)
                # Safety cage hoops
                for ci2 in range(0, n_rungs, max(1, n_rungs // 3)):
                    ry = plt_y + plt_h + int(lad_h * (ci2 + 0.5) / n_rungs)
                    cage_r = lad_w + 3
                    cv.create_arc(lad_x - 2, ry - cage_r, lad_x + lad_w + 2, ry + cage_r,
                                  start=0, extent=180, style="arc", outline="#95A5A6", width=1)

            # ── Sphere: white/silver 3D gradient (LPG reflective) ─────────
            # White/silver gradient for mandatory LPG reflective coating
            sphere_gradient = [
                "#A8B0B8", "#B0B8C0", "#B8C0C8", "#C0C8D0", "#C8D0D8",
                "#D0D8E0", "#D8E0E5", "#E0E5EA", "#E5EAEF", "#EAF0F4",
                "#EFF4F8", "#F2F6FA", "#F5F9FC", "#F8FBFD", "#FAFCFE",
                "#FCFDFE", "#FDFEFE", "#FEFEFE", "#FEFFFE", "#FFFFFF",
            ]
            n_layers = len(sphere_gradient)
            # Drop shadow
            cv.create_oval(cx_s - SPH_R + 4, cy_s - SPH_R + 4,
                           cx_s + SPH_R + 4, cy_s + SPH_R + 4,
                           fill="#2A3540", outline="")
            for k in range(n_layers - 1, -1, -1):
                frac  = k / (n_layers - 1)
                r_k   = int(SPH_R * (0.08 + frac * 0.92))
                if r_k < 1: continue
                max_off = int(SPH_R * 0.35)
                off_x   = int(max_off * (1 - frac) * 0.60)
                off_y   = int(max_off * (1 - frac) * 0.85)
                sc3 = sphere_gradient[k]
                cv.create_oval(cx_s - r_k - off_x // 2, cy_s - r_k - off_y // 2,
                               cx_s + r_k - off_x // 2, cy_s + r_k - off_y // 2,
                               fill=sc3, outline="")

            # ── Weld seams: beach-ball pattern (meridional + equatorial) ──
            # Equatorial weld
            cv.create_oval(cx_s - SPH_R + 2, cy_s - 1, cx_s + SPH_R - 2, cy_s + 1,
                           fill="", outline="#A0A8B0", width=1)
            # 4 meridional welds (vertical great circles seen as ellipses)
            for m_frac in [-0.55, -0.20, 0.20, 0.55]:
                m_off = int(SPH_R * m_frac)
                m_w = max(2, int(SPH_R * abs(1 - abs(m_frac)) * 0.30))
                cv.create_oval(cx_s + m_off - m_w, cy_s - SPH_R + 2,
                               cx_s + m_off + m_w, cy_s + SPH_R - 2,
                               fill="", outline="#A0A8B0", width=1)

            # Sphere outline
            cv.create_oval(cx_s - SPH_R, cy_s - SPH_R, cx_s + SPH_R, cy_s + SPH_R,
                           fill="", outline="#6D7880", width=3)

            # ── Gas fill level ────────────────────────────────────────────
            try:
                vol = self.parse_float(self.get_var(f"{etapa_key}_{tn}_vol_nat_prod").get() or "0") if etapa_key and tn else 0
                cap = self.parse_float(self.get_var(f"{etapa_key}_{tn}_alt_ref").get() or "1")
                vp  = min(max(vol / (cap if cap > 0 else 1), 0.0), 1.0)
            except: vp = 0.0

            pnm  = self.get_var(f"{etapa_key}_{tn}_prod_name").get() if etapa_key else ""
            pres = self.get_var(f"{etapa_key}_{tn}_temp").get() if etapa_key else ""

            if vp > 0.02:
                fill_h  = int(SPH_R * (2 * vp - 1))
                fill_top = cy_s - fill_h
                clip_top = max(cy_s - SPH_R + 3, fill_top)
                fill_c = self.get_prod_color(tn, etapa_key)[0] if etapa_key else "#F39C12"
                if fill_c in ("#3498DB", "#5DADE2", "#2E86C1", "#85C1E9", "#B8E0F7"):
                    fill_c = "#FF6B35"
                cv.create_rectangle(cx_s - SPH_R + 3, clip_top,
                                    cx_s + SPH_R - 3, cy_s + SPH_R - 3,
                                    fill=fill_c, outline="")
                # Re-draw sphere outline over fill
                cv.create_oval(cx_s - SPH_R, cy_s - SPH_R, cx_s + SPH_R, cy_s + SPH_R,
                               fill="", outline="#6D7880", width=3)
                # Level chord line
                lv_y = clip_top
                try:
                    half_chord = int((SPH_R**2 - (cy_s - lv_y)**2)**0.5)
                except: half_chord = 0
                if half_chord > 0:
                    cv.create_line(cx_s - half_chord, lv_y, cx_s + half_chord, lv_y,
                                   fill="#4A4A4A", width=2, dash=(6, 3))
                    cv.create_line(cx_s - half_chord + 3, lv_y + 2,
                                   cx_s + half_chord - 3, lv_y + 2,
                                   fill="#FFFFFF", width=1, dash=(3, 5))
                cv.create_text(cx_s, cy_s + int(SPH_R * 0.25), text=f"{vp*100:.0f}%",
                               font=FTS, fill=self.contrast_text(fill_c))

            # ── Small top platform for relief valve ───────────────────────
            top_plt_w = max(12, int(SPH_R * 0.40))
            top_plt_y = cy_s - SPH_R - 2
            cv.create_rectangle(cx_s - top_plt_w // 2, top_plt_y - 3,
                                cx_s + top_plt_w // 2, top_plt_y,
                                fill="#6D7880", outline="#5D6D7E", width=1)
            # Mini handrail on top platform
            cv.create_line(cx_s - top_plt_w // 2, top_plt_y - 3,
                           cx_s - top_plt_w // 2, top_plt_y - 3 - max(4, int(SPH_R * 0.08)),
                           fill="#808B96", width=1)
            cv.create_line(cx_s + top_plt_w // 2, top_plt_y - 3,
                           cx_s + top_plt_w // 2, top_plt_y - 3 - max(4, int(SPH_R * 0.08)),
                           fill="#808B96", width=1)
            cv.create_line(cx_s - top_plt_w // 2, top_plt_y - 3 - max(4, int(SPH_R * 0.08)),
                           cx_s + top_plt_w // 2, top_plt_y - 3 - max(4, int(SPH_R * 0.08)),
                           fill="#95A5A6", width=1)

            # PSV (pressure safety valve) on top platform
            psv_x = cx_s + int(SPH_R * 0.10)
            psv_top = top_plt_y - max(14, int(SPH_R * 0.25))
            cv.create_rectangle(psv_x - 4, psv_top, psv_x + 4, top_plt_y - 3,
                                fill="#E74C3C", outline="#922B21", width=1)
            cv.create_polygon(psv_x - 7, psv_top - 2, psv_x + 7, psv_top - 2,
                              psv_x + 4, psv_top + 5, psv_x - 4, psv_top + 5,
                              fill="#C0392B", outline="#7B241C")
            cv.create_rectangle(psv_x - 2, psv_top - 10, psv_x + 2, psv_top - 1,
                                fill="#5D6D7E", outline="")
            cv.create_text(psv_x, psv_top - 12, text="PSV", font=("Arial", max(3, fss - 2)), fill="#E74C3C")

            # ── Fire deluge piping ring near top ──────────────────────────
            ring_r = int(SPH_R * 1.05)
            ring_h = max(3, int(SPH_R * 0.06))
            # Upper deluge ring
            cv.create_oval(cx_s - int(ring_r * 0.85), cy_s - int(SPH_R * 0.55) - ring_h,
                           cx_s + int(ring_r * 0.85), cy_s - int(SPH_R * 0.55) + ring_h,
                           fill="", outline="#2E86C1", width=2, dash=(3, 4))
            # Spray nozzles on ring
            for dang in [30, 150, 210, 330]:
                dr_x = cx_s + int(ring_r * 0.85 * math.cos(math.radians(dang)))
                dr_y = cy_s - int(SPH_R * 0.55) + int(ring_h * math.sin(math.radians(dang)))
                cv.create_oval(dr_x - 2, dr_y - 2, dr_x + 2, dr_y + 2,
                               fill="#7F8C8D", outline="#5D6D7E", width=1)
                cv.create_line(dr_x, dr_y, dr_x, dr_y + max(4, int(SPH_R * 0.10)),
                               fill="#AAB2B9", width=1, dash=(2, 3))

            # ── Pressure gauge ────────────────────────────────────────────
            gx = cx_s + int(SPH_R * 0.58); gy = cy_s - int(SPH_R * 0.38)
            gauge_r = max(8, int(SPH_R * 0.15))
            cv.create_line(gx, gy + gauge_r, gx + int(SPH_R * 0.15), gy + gauge_r + 8,
                           fill="#808B96", width=2)
            cv.create_oval(gx - gauge_r - 2, gy - gauge_r - 2, gx + gauge_r + 2, gy + gauge_r + 2,
                           fill="#4A5568", outline="#2C3E50", width=1)
            cv.create_oval(gx - gauge_r, gy - gauge_r, gx + gauge_r, gy + gauge_r,
                           fill="#FDFEFE", outline="#E74C3C", width=2)
            cv.create_arc(gx - gauge_r + 3, gy - gauge_r + 3, gx + gauge_r - 3, gy + gauge_r - 3,
                          start=30, extent=240, style="arc", outline="#E8E8E8", width=1)
            ang_v = pres[:3] if pres else "???"
            try:
                p_frac = min(float(pres.replace(",", ".")) / 1000, 1.0) if pres else 0.3
            except: p_frac = 0.3
            ang = math.radians(-30 + 240 * p_frac)
            nx = gx + int(gauge_r * 0.7 * math.cos(ang))
            ny = gy - int(gauge_r * 0.7 * math.sin(ang))
            cv.create_line(gx, gy, nx, ny, fill="#C0392B", width=2)
            cv.create_oval(gx - 2, gy - 2, gx + 2, gy + 2, fill="#C0392B", outline="")
            cv.create_text(gx, gy + gauge_r // 2, text=ang_v[:3],
                           font=("Arial", max(4, fss - 1)), fill="#C0392B")

            # ── Nameplate ─────────────────────────────────────────────────
            lbl = tn[:12]
            plate_w = max(30, int(each_w * 0.5))
            cv.create_rectangle(cx_s - plate_w // 2, GROUND_Y + 3,
                                cx_s + plate_w // 2, GROUND_Y + 3 + fss + 6,
                                fill="#F0F2F4", outline="#5D6D7E", width=1)
            cv.create_text(cx_s, GROUND_Y + 6 + fss // 2, text=lbl, font=FTS, fill="#1B3A5C")
            if pnm:
                cv.create_text(cx_s, GROUND_Y + 8 + fss + fss // 2,
                               text=pnm[:12], font=FTS, fill="#5D6D7E")

        # ── Interconnecting piping manifold ───────────────────────────────
        if n > 1:
            manif_y = GROUND_Y - 10
            first_cx = x + 15 + each_w // 2
            last_cx  = x + 15 + (n - 1) * each_w + each_w // 2
            cv.create_rectangle(first_cx, manif_y - 5, last_cx, manif_y + 1, fill="#4A5568", outline="")
            cv.create_rectangle(first_cx, manif_y - 4, last_cx, manif_y, fill="#6D7880", outline="")
            cv.create_line(first_cx, manif_y - 3, last_cx, manif_y - 3, fill="#808B96", width=1)
            cv.create_rectangle(first_cx, manif_y - 5, last_cx, manif_y + 1, fill="", outline="#4A5568", width=1)
            for i2 in range(n):
                cx_m = x + 15 + i2 * each_w + each_w // 2
                cv.create_rectangle(cx_m - 2, manif_y - 16, cx_m + 2, manif_y - 4, fill="#5D6D7E", outline="")
                cv.create_polygon(cx_m - 4, manif_y - 16, cx_m + 4, manif_y - 10,
                                  cx_m + 4, manif_y - 16, cx_m - 4, manif_y - 10,
                                  fill="#E74C3C", outline="#922B21", width=1)
            for fx in [first_cx, last_cx]:
                cv.create_rectangle(fx - 2, manif_y - 7, fx + 2, manif_y + 3,
                                    fill="#4A5568", outline="#2C3E50")

    def _draw_liquid_truck(self, cv, x, y, W, H, etapa_key, tank_names):
        """DOT 406 fuel tanker -- elliptical barrel, multi-compartment, polished aluminum."""
        if tank_names is None: tank_names = self.lista_tanques
        if H < 80 or W < 180: return
        import math

        n   = max(len(tank_names), 1)
        fs  = min(9, max(5, int(H * 0.032))); fss = min(7, max(4, int(H * 0.026)))
        FT  = ("Arial", fs); FTS = ("Arial", fss)
        patente = self.get_var("car_patente").get() or "CISTERNA"

        # ── Proportions ───────────────────────────────────────────────────
        GROUND_Y    = y + H - max(14, int(H * 0.08))
        AXLE_R      = max(10, int(H * 0.12))
        CISTERN_BOT = GROUND_Y - AXLE_R * 2 - 4
        CISTERN_H   = max(30, int(H * 0.38))
        CISTERN_TOP = CISTERN_BOT - CISTERN_H
        CISTERN_MID = (CISTERN_TOP + CISTERN_BOT) // 2
        ELLIP_FLAT  = max(3, int(CISTERN_H * 0.08))  # elliptical top flatness

        PAD_L  = max(8, int(W * 0.03))
        CAB_W  = max(55, int(W * 0.17))
        CAB_X  = x + PAD_L
        CIS_X  = CAB_X + CAB_W + max(6, int(W * 0.01))
        CIS_W  = W - PAD_L - CAB_W - max(6, int(W * 0.01)) - max(8, int(W * 0.03))
        DOME_R = int(CISTERN_H * 0.50)  # end-cap dome radius

        PROD_COL = [
            ("#C0392B", "#922B21", "#F1948A"), ("#E67E22", "#A04000", "#FAD7A0"),
            ("#27AE60", "#1E8449", "#A9DFBF"), ("#D4AC0D", "#9A7D0A", "#F9E79F"),
            ("#784212", "#6E2C00", "#C39BD3"), ("#2C3E50", "#17202A", "#85929E"),
            ("#8E44AD", "#6C3483", "#D2B4DE"), ("#E74C3C", "#C0392B", "#F5B7B1"),
        ]

        # ── Background ────────────────────────────────────────────────────
        cv.create_rectangle(x, y, x + W, y + H, fill="#F5F7FA", outline="#5D6D7E", width=2)
        cv.create_rectangle(x, GROUND_Y, x + W, y + H, fill="#5A6370", outline="")
        cv.create_text(x + W // 2, y + max(10, int(H * 0.06)),
                       text=f"CAMION CISTERNA  --  {patente}", font=FT, fill="#1B3A5C")

        # ── Chassis frame rails ───────────────────────────────────────────
        ch_h = max(5, int(H * 0.04))
        ch_y = CISTERN_BOT
        cv.create_rectangle(CAB_X + int(CAB_W * 0.3), ch_y, CIS_X + CIS_W, ch_y + ch_h,
                            fill="#4A5568", outline="#2C3E50", width=1)
        cv.create_line(CAB_X + int(CAB_W * 0.3), ch_y + ch_h // 2,
                       CIS_X + CIS_W, ch_y + ch_h // 2, fill="#5D6D7E", width=1)
        for ci in range(5):
            cx_tr = CIS_X + int(CIS_W * ci / 4)
            cv.create_rectangle(cx_tr - 3, ch_y - max(4, int(H * 0.03)), cx_tr + 3, ch_y + ch_h,
                                fill="#3D4B56", outline="")

        # ── ELLIPTICAL BARREL with compartments ───────────────────────────
        COMP_W = CIS_W // n
        # Draw the overall barrel shape (elliptical top curve)
        # Top arc: slightly flatter than bottom = elliptical cross-section look
        cv.create_arc(CIS_X, CISTERN_TOP - ELLIP_FLAT, CIS_X + CIS_W, CISTERN_TOP + ELLIP_FLAT * 3,
                      start=0, extent=180, style="arc", outline="#B0B8C0", width=1)

        for i, tn in enumerate(tank_names[:n]):
            cx2 = CIS_X + i * COMP_W
            cw2 = COMP_W
            is_first = (i == 0)
            is_last  = (i == n - 1)

            body_x1 = cx2 + (DOME_R if is_first else 0)
            body_x2 = cx2 + cw2 - (DOME_R if is_last else 0)

            # Polished aluminum barrel gradient (8 strips, silver)
            barrel_cols = ["#B8C0C8", "#C4CCD4", "#D0D8E0", "#DCE4EC",
                           "#E4ECF0", "#DCE4EC", "#CCD4DC", "#BCC4CC"]
            for si, sc in enumerate(barrel_cols):
                sy = CISTERN_TOP + int(CISTERN_H * si / len(barrel_cols))
                sh = CISTERN_H // len(barrel_cols) + 1
                cv.create_rectangle(body_x1, sy, body_x2, sy + sh, fill=sc, outline="")
            # Specular highlight band near top
            cv.create_rectangle(body_x1 + 2, CISTERN_TOP + max(2, CISTERN_H // 8),
                                body_x2 - 2, CISTERN_TOP + max(4, CISTERN_H // 5),
                                fill="#F0F4F8", outline="")

            # Elliptical end caps (left=first, right=last)
            if is_first:
                for ki, kc in enumerate(["#A0A8B0", "#B0B8C0", "#C0C8D0", "#D0D8E0", "#E0E8F0"]):
                    kr = DOME_R - ki * 3
                    if kr > 0:
                        cv.create_oval(cx2, CISTERN_TOP + ki * 2, cx2 + 2 * DOME_R, CISTERN_BOT - ki * 2,
                                       fill=kc, outline="")
            if is_last:
                for ki, kc in enumerate(["#E0E8F0", "#D0D8E0", "#C0C8D0", "#B0B8C0", "#A0A8B0"]):
                    kr = DOME_R - ki * 3
                    if kr > 0:
                        cv.create_oval(cx2 + cw2 - 2 * DOME_R + ki * 2, CISTERN_TOP + ki * 2,
                                       cx2 + cw2, CISTERN_BOT - ki * 2, fill=kc, outline="")

            # ── Compartment rings (vertical baffle bands) ─────────────────
            if not is_last:
                sep_x = cx2 + cw2
                cv.create_rectangle(sep_x - 3, CISTERN_TOP - 1, sep_x + 3, CISTERN_BOT + 1,
                                    fill="#8A929C", outline="#5D6D7E", width=1)
                cv.create_line(sep_x, CISTERN_TOP, sep_x, CISTERN_BOT, fill="#A0A8B0", width=1)

            # ── Fill level ────────────────────────────────────────────────
            vp, wp = self._get_fill_pct(tn, etapa_key)
            pnm  = self.get_var(f"{etapa_key}_{tn}_prod_name").get() if etapa_key else ""
            vlit = self.get_var(f"{etapa_key}_{tn}_vol_nat_prod").get() if etapa_key else ""
            ci_c = abs(hash(pnm)) % len(PROD_COL) if pnm else i % len(PROD_COL)
            prod_c, prod_dk, prod_lt = PROD_COL[ci_c]

            fill_top = int(CISTERN_BOT - CISTERN_H * vp)
            _fx1 = (cx2 + 2) if is_first else (body_x1 + 2)
            _fx2 = (cx2 + cw2 - 2) if is_last else (body_x2 - 2)
            if vp > 0.02:
                if wp > 0:
                    wat_top = int(CISTERN_BOT - CISTERN_H * wp)
                    cv.create_rectangle(_fx1, wat_top, _fx2, CISTERN_BOT - 2,
                                        fill="#5DADE2", outline="")
                cv.create_rectangle(_fx1, fill_top, _fx2,
                                    int(CISTERN_BOT - CISTERN_H * wp) if wp > 0 else CISTERN_BOT - 2,
                                    fill=prod_c, outline="")
                cv.create_rectangle(_fx1, fill_top, _fx2,
                                    fill_top + max(2, int(CISTERN_H * 0.06)),
                                    fill=prod_lt, outline="")
                cv.create_line(body_x1, fill_top, body_x2, fill_top, fill=prod_dk, width=2)

            # Barrel outline
            cv.create_rectangle(body_x1, CISTERN_TOP, body_x2, CISTERN_BOT,
                                fill="", outline="#8A929C", width=2)

            # ── Manhole cover on top (one per compartment) ────────────────
            top_cx = cx2 + cw2 // 2
            mh_r = max(4, int(min(cw2, CISTERN_H) * 0.10))
            cv.create_oval(top_cx - mh_r, CISTERN_TOP - mh_r - 2,
                           top_cx + mh_r, CISTERN_TOP + mh_r - 2,
                           fill="#B8C0C8", outline="#636E72", width=2)
            # Hinge on manhole
            cv.create_rectangle(top_cx - mh_r - 3, CISTERN_TOP - 3,
                                top_cx - mh_r, CISTERN_TOP + 2,
                                fill="#808B96", outline="#5D6D7E")
            # Handle on manhole
            cv.create_line(top_cx - 2, CISTERN_TOP - mh_r - 2,
                           top_cx + 2, CISTERN_TOP - mh_r - 2, fill="#4A5568", width=2)

            # ── Bottom loading valve under each compartment ───────────────
            bv_x = top_cx
            bv_y = CISTERN_BOT + ch_h + 2
            cv.create_rectangle(bv_x - 3, CISTERN_BOT, bv_x + 3, bv_y + 4,
                                fill="#5D6D7E", outline="#4A5568", width=1)
            cv.create_polygon(bv_x - 5, bv_y, bv_x + 5, bv_y + 6,
                              bv_x + 5, bv_y, bv_x - 5, bv_y + 6,
                              fill="#E74C3C", outline="#922B21", width=1)

            # ── Labels ────────────────────────────────────────────────────
            short = tn.replace("COMPARTIMENTO ", "C.").replace("TK ", "").strip()[:6]
            txt_fill = "white" if vp > 0.35 else "#1B3A5C"
            cv.create_text(body_x1 + (body_x2 - body_x1) // 2,
                           CISTERN_TOP + max(10, int(CISTERN_H * 0.15)),
                           text=short, font=FT, fill=txt_fill)
            if vp > 0:
                cv.create_text(body_x1 + (body_x2 - body_x1) // 2,
                               CISTERN_TOP + max(22, int(CISTERN_H * 0.35)),
                               text=f"{vp*100:.0f}%", font=FTS, fill=txt_fill)
            if pnm:
                cv.create_text(body_x1 + (body_x2 - body_x1) // 2,
                               CISTERN_BOT - max(18, int(CISTERN_H * 0.25)),
                               text=pnm[:10], font=FTS, fill=txt_fill)
            if vlit:
                cv.create_text(body_x1 + (body_x2 - body_x1) // 2,
                               CISTERN_BOT - max(6, int(CISTERN_H * 0.10)),
                               text=f"{vlit}L", font=FTS, fill=txt_fill)

        # ── Hazmat diamond placard ────────────────────────────────────────
        plac_x = CIS_X + CIS_W - max(20, int(CIS_W * 0.08))
        plac_y = CISTERN_MID
        plac_s = max(8, int(CISTERN_H * 0.14))
        cv.create_polygon(plac_x, plac_y - plac_s, plac_x + plac_s, plac_y,
                          plac_x, plac_y + plac_s, plac_x - plac_s, plac_y,
                          fill="#E74C3C", outline="#922B21", width=1)
        cv.create_text(plac_x, plac_y, text="3", font=("Arial", max(3, fss - 1), "bold"), fill="white")

        # ── SEMI-TRUCK CAB ────────────────────────────────────────────────
        CAB_BOT = CISTERN_BOT
        CAB_TOP = CAB_BOT - CISTERN_H - max(8, int(CISTERN_H * 0.22))
        CAB_H   = CAB_BOT - CAB_TOP
        cv.create_rectangle(CAB_X + int(CAB_W * 0.1), CAB_BOT, CAB_X + CAB_W, CAB_BOT + ch_h,
                            fill="#4A5568", outline="#2C3E50", width=1)
        cab_slope = max(4, int(CAB_W * 0.12))
        cab_pts = [CAB_X, CAB_BOT, CAB_X + CAB_W, CAB_BOT,
                   CAB_X + CAB_W, CAB_TOP + int(CAB_H * 0.18),
                   CAB_X + CAB_W - cab_slope, CAB_TOP,
                   CAB_X + cab_slope, CAB_TOP,
                   CAB_X, CAB_TOP + int(CAB_H * 0.18)]
        cv.create_polygon(cab_pts, fill="#2E4053", outline="#1B2631", width=2)

        # Stripe and chrome
        stripe_y1 = CAB_TOP + int(CAB_H * 0.35)
        stripe_y2 = CAB_TOP + int(CAB_H * 0.52)
        cv.create_rectangle(CAB_X, stripe_y1, CAB_X + CAB_W, stripe_y2, fill="#C0392B", outline="")
        cv.create_rectangle(CAB_X, stripe_y2, CAB_X + CAB_W, stripe_y2 + max(2, int(CAB_H * 0.03)),
                            fill="#95A5A6", outline="")

        # Roof and spoiler
        cv.create_rectangle(CAB_X, CAB_TOP + 1, CAB_X + CAB_W, CAB_TOP + max(5, int(CAB_H * 0.09)),
                            fill="#3D5166", outline="")
        sp_h = max(6, int(CAB_H * 0.16)); sp_w = int(CAB_W * 0.75)
        cv.create_polygon(CAB_X + int(CAB_W * 0.12), CAB_TOP,
                          CAB_X + int(CAB_W * 0.12) + sp_w, CAB_TOP,
                          CAB_X + int(CAB_W * 0.12) + sp_w, CAB_TOP - sp_h + max(2, sp_h // 4),
                          CAB_X + int(CAB_W * 0.12) + int(sp_w * 0.8), CAB_TOP - sp_h,
                          CAB_X + int(CAB_W * 0.12), CAB_TOP - sp_h,
                          fill="#3D5166", outline="#2C3E50", width=1)

        # Window
        front_w = max(4, int(CAB_W * 0.12))
        cv.create_rectangle(CAB_X + CAB_W - front_w, CAB_TOP + int(CAB_H * 0.18),
                            CAB_X + CAB_W, CAB_TOP + int(CAB_H * 0.72),
                            fill="#1A5276", outline="#0E3850", width=1)
        cv.create_polygon(CAB_X + CAB_W - front_w, CAB_TOP + int(CAB_H * 0.18),
                          CAB_X + CAB_W, CAB_TOP + int(CAB_H * 0.18),
                          CAB_X + CAB_W, CAB_TOP + int(CAB_H * 0.35),
                          fill="#2E86C1", outline="")

        # Door
        d_ml = max(4, int(CAB_W * 0.08)); d_mr = front_w + max(4, int(CAB_W * 0.06))
        door_top = CAB_TOP + int(CAB_H * 0.18); door_bot = CAB_BOT - max(4, int(CAB_H * 0.05))
        dx1 = CAB_X + d_ml; dx2 = CAB_X + CAB_W - d_mr
        cv.create_rectangle(dx1, door_top, dx2, door_bot, fill="", outline="#1B2631", width=2)
        panel_div_y = door_top + int((door_bot - door_top) * 0.52)
        cv.create_line(dx1, panel_div_y, dx2, panel_div_y, fill="#1B2631", width=1)
        hx = dx1 + int((dx2 - dx1) * 0.72); hh = max(4, int(CAB_H * 0.07)); hw = max(6, int(CAB_W * 0.10))
        cv.create_rectangle(hx, panel_div_y - hh, hx + hw, panel_div_y, fill="#7F8C8D", outline="#5D6D7E")

        # Side window
        wm_l = d_ml + max(4, int(CAB_W * 0.05)); wm_r = d_mr + max(4, int(CAB_W * 0.05))
        wy = CAB_TOP + int(CAB_H * 0.08); wb = panel_div_y - max(3, int(CAB_H * 0.04))
        wx1 = CAB_X + wm_l; wx2 = CAB_X + CAB_W - wm_r
        cv.create_rectangle(wx1 - 2, wy - 2, wx2 + 2, wb + 2, fill="#1B2631", outline="")
        cv.create_rectangle(wx1, wy, wx2, wb, fill="#1A5276", outline="#0E3850", width=1)
        cv.create_polygon(wx1 + 2, wy + 2, wx1 + max(4, int((wx2 - wx1) * 0.45)), wy + 2,
                          wx1 + 2, wy + max(4, int((wb - wy) * 0.55)), fill="#2E86C1", outline="")
        if wx2 - wx1 > 20:
            cv.create_line(wx1 + int((wx2 - wx1) * 0.28), wy,
                           wx1 + int((wx2 - wx1) * 0.28), wb, fill="#0E3850", width=2)

        # Mirror
        mirror_x = CAB_X + CAB_W + max(3, int(CAB_W * 0.06))
        mirror_y = wy + max(2, int((wb - wy) * 0.15))
        mirror_w = max(6, int(CAB_W * 0.12)); mirror_h = max(4, int((wb - wy) * 0.3))
        cv.create_rectangle(mirror_x - 1, mirror_y - 1, mirror_x + mirror_w + 1, mirror_y + mirror_h + 1,
                            fill="#2C3E50", outline="")
        cv.create_rectangle(mirror_x, mirror_y, mirror_x + mirror_w, mirror_y + mirror_h,
                            fill="#7F8C8D", outline="")

        # Exhaust stack
        exh_x = CAB_X + CAB_W - max(6, int(CAB_W * 0.08))
        exh_h = max(16, int(CAB_H * 0.55))
        cv.create_rectangle(exh_x - 3, CAB_TOP - exh_h, exh_x + 3, CAB_TOP + 5,
                            fill="#4A5568", outline="#2C3E50", width=1)
        cv.create_oval(exh_x - 5, CAB_TOP - exh_h - 5, exh_x + 5, CAB_TOP - exh_h + 3,
                       fill="#3D4B56", outline="#2C3E50")
        for sm_j in range(3):
            sm_r2 = max(3, 4 * (sm_j + 1))
            sm_x2 = exh_x + sm_j * 2
            sm_y2 = CAB_TOP - exh_h - 6 - sm_j * max(4, exh_h // 7)
            cv.create_oval(sm_x2 - sm_r2, sm_y2 - sm_r2, sm_x2 + sm_r2, sm_y2 + sm_r2,
                           fill=["#808B96", "#AAB7B8", "#BDC3C7"][sm_j], outline="")

        # Grille and headlight
        grill_y = CAB_BOT - max(16, int(CAB_H * 0.26))
        grill_h = max(10, int(CAB_H * 0.24)); grill_w = max(8, int(CAB_W * 0.28))
        grill_x = CAB_X - grill_w
        cv.create_rectangle(grill_x, grill_y, CAB_X, grill_y + grill_h,
                            fill="#BDC3C7", outline="#7F8C8D", width=1)
        for gi in range(max(3, grill_h // 5)):
            gy2 = grill_y + 2 + gi * grill_h // max(3, grill_h // 5)
            cv.create_rectangle(grill_x + 2, gy2, CAB_X - 2, gy2 + max(1, grill_h // max(3, grill_h // 5) - 2),
                                fill="#2C3E50", outline="")
        hl_r = max(5, int(grill_h * 0.38))
        hl_cx = grill_x + grill_w // 2; hl_cy = grill_y + grill_h - hl_r - 3
        cv.create_oval(hl_cx - hl_r, hl_cy - hl_r, hl_cx + hl_r, hl_cy + hl_r,
                       fill="#F9E79F", outline="#BDC3C7")
        cv.create_oval(hl_cx - hl_r // 2, hl_cy - hl_r // 2, hl_cx + hl_r // 2, hl_cy + hl_r // 2,
                       fill="#FEFEFE", outline="")

        # ── Landing gear (near front of trailer) ─────────────────────────
        lg_x = CIS_X + max(8, int(CIS_W * 0.05))
        lg_h = GROUND_Y - CISTERN_BOT - ch_h
        cv.create_line(lg_x, CISTERN_BOT + ch_h, lg_x, GROUND_Y, fill="#4A5568", width=2)
        cv.create_line(lg_x + 6, CISTERN_BOT + ch_h, lg_x + 6, GROUND_Y, fill="#4A5568", width=2)
        cv.create_rectangle(lg_x - 2, GROUND_Y - 4, lg_x + 8, GROUND_Y, fill="#5D6D7E", outline="#4A5568")

        # ── ICC rear bumper bar ───────────────────────────────────────────
        rear_x = CIS_X + CIS_W + max(2, int(W * 0.005))
        cv.create_rectangle(rear_x, CISTERN_BOT + ch_h - 2, rear_x + max(4, int(W * 0.01)),
                            GROUND_Y - 2, fill="#4A5568", outline="#2C3E50")
        # Reflective tape
        cv.create_rectangle(rear_x, GROUND_Y - max(6, int(H * 0.04)),
                            rear_x + max(4, int(W * 0.01)), GROUND_Y - 2,
                            fill="#E74C3C", outline="")

        # ── WHEELS with hub detail ────────────────────────────────────────
        AXLE_Y = GROUND_Y - AXLE_R
        wheel_positions = [CAB_X + int(CAB_W * 0.62)]
        # Tandem rear axles
        rear_center = CIS_X + int(CIS_W * 0.70)
        wheel_positions.append(rear_center - max(5, AXLE_R // 4))
        wheel_positions.append(rear_center + max(5, AXLE_R // 4))
        if CIS_W > 120:
            wheel_positions.insert(1, CIS_X + int(CIS_W * 0.45))

        for wx in wheel_positions:
            cv.create_oval(wx - AXLE_R, AXLE_Y - AXLE_R, wx + AXLE_R, AXLE_Y + AXLE_R,
                           fill="#1B2631", outline="#0E1A27", width=2)
            rim_r = max(4, int(AXLE_R * 0.55))
            cv.create_oval(wx - rim_r, AXLE_Y - rim_r, wx + rim_r, AXLE_Y + rim_r,
                           fill="#7F8C8D", outline="#5D6D7E", width=1)
            for angle_r in [0, 60, 120, 180, 240, 300]:
                ar = math.radians(angle_r)
                cv.create_line(wx + int(rim_r * 0.25 * math.cos(ar)),
                               AXLE_Y + int(rim_r * 0.25 * math.sin(ar)),
                               wx + int(rim_r * 0.85 * math.cos(ar)),
                               AXLE_Y + int(rim_r * 0.85 * math.sin(ar)),
                               fill="#5D6D7E", width=1)
            cv.create_oval(wx - 3, AXLE_Y - 3, wx + 3, AXLE_Y + 3, fill="#4A5568", outline="")

        for wx in wheel_positions:
            cv.create_arc(wx - AXLE_R - 2, AXLE_Y - AXLE_R - 2, wx + AXLE_R + 2, AXLE_Y + AXLE_R + 2,
                          start=30, extent=120, style="arc", outline="#5D6D7E", width=3)

    def _draw_pressure_truck(self, cv, x, y, W, H, etapa_key, tank_names):
        """MC-331 LPG pressure truck -- circular cross-section, hemispherical heads, WHITE, single vessel."""
        import math
        if tank_names is None: tank_names = self.lista_tanques
        if H < 80 or W < 180: return

        n   = max(len(tank_names), 1)
        fs  = min(9, max(5, int(H * 0.032))); fss = min(7, max(4, int(H * 0.026)))
        FT  = ("Arial", fs); FTS = ("Arial", fss)
        patente = self.get_var("car_patente").get() or "GAS/GLP"

        GROUND_Y    = y + H - max(14, int(H * 0.08))
        AXLE_R      = max(10, int(H * 0.11))
        CISTERN_BOT = GROUND_Y - AXLE_R * 2 - 4
        # Circular cross-section: height = diameter -> perfectly round barrel in side view
        CISTERN_H   = max(30, int(H * 0.40))
        CISTERN_TOP = CISTERN_BOT - CISTERN_H
        DOME_R      = int(CISTERN_H * 0.52)  # hemispherical dished end caps
        PAD_L       = max(8, int(W * 0.03))
        CAB_W       = max(50, int(W * 0.16))
        CAB_X       = x + PAD_L
        CIS_X       = CAB_X + CAB_W + max(4, int(W * 0.01))
        CIS_W       = W - PAD_L - CAB_W - max(4, int(W * 0.01)) - max(8, int(W * 0.03))
        COMP_W      = CIS_W // n

        # ── Background ─────────────────────────────────────────────────────
        sky_cols = ["#D6EAF8", "#E0EDF6", "#EAF0F4", "#F5F7FA"]
        sky_h = GROUND_Y - y
        for si, sc in enumerate(sky_cols):
            sy1 = y + int(sky_h * si / len(sky_cols))
            sy2 = y + int(sky_h * (si + 1) / len(sky_cols))
            cv.create_rectangle(x, sy1, x + W, sy2, fill=sc, outline="")
        cv.create_rectangle(x, y, x + W, y + H, fill="", outline="#D4AC0D", width=2)
        gnd_cols = ["#808B96", "#747D88", "#686F7A", "#5C636C"]
        gnd_h = y + H - GROUND_Y
        for gi, gc in enumerate(gnd_cols):
            gy1 = GROUND_Y + int(gnd_h * gi / len(gnd_cols))
            gy2 = GROUND_Y + int(gnd_h * (gi + 1) / len(gnd_cols))
            cv.create_rectangle(x, gy1, x + W, gy2, fill=gc, outline="")
        cv.create_line(x, GROUND_Y, x + W, GROUND_Y, fill="#A0A8B0", width=1)

        cv.create_text(x + W // 2 + 1, y + max(10, int(H * 0.06)) + 1,
                       text=f"CAMION GAS/GLP (MC-331)  --  {patente}", font=FT, fill="#C0A050")
        cv.create_text(x + W // 2, y + max(10, int(H * 0.06)),
                       text=f"CAMION GAS/GLP (MC-331)  --  {patente}", font=FT, fill="#784212")

        cv.create_oval(CAB_X, GROUND_Y - 3, CIS_X + CIS_W, GROUND_Y + 5, fill="#404850", outline="")

        # ── Chassis frame ─────────────────────────────────────────────────
        ch_h = max(5, int(H * 0.04))
        cv.create_rectangle(CAB_X + int(CAB_W * 0.3), CISTERN_BOT, CIS_X + CIS_W, CISTERN_BOT + ch_h,
                            fill="#2C3E50", outline="#1B2631", width=1)
        for ci in range(6):
            cx_tr = CIS_X + int(CIS_W * ci / 5)
            cv.create_rectangle(cx_tr - 2, CISTERN_BOT - max(3, int(H * 0.02)), cx_tr + 2, CISTERN_BOT + ch_h,
                                fill="#1B2631", outline="")

        # ── SINGLE PRESSURE VESSEL (circular, WHITE, no compartment rings) ─
        # The entire barrel is one single vessel - iterate tanks for data only
        body_x1 = CIS_X + DOME_R
        body_x2 = CIS_X + CIS_W - DOME_R

        # WHITE vessel body (mandatory for LPG) with cylindrical gradient
        WHITE_GRAD = ["#E8E8E8", "#ECECEC", "#F0F0F0", "#F4F4F4", "#F8F8F8",
                      "#FCFCFC", "#FEFEFE", "#FCFCFC", "#F4F4F4", "#ECECEC"]
        for ki, kc in enumerate(WHITE_GRAD):
            ky = CISTERN_TOP + int(ki * CISTERN_H / len(WHITE_GRAD))
            kh = CISTERN_H // len(WHITE_GRAD) + 1
            cv.create_rectangle(body_x1, ky, body_x2, ky + kh, fill=kc, outline="")
        # Specular highlight
        cv.create_rectangle(body_x1 + 4, CISTERN_TOP + max(3, CISTERN_H // 5),
                            body_x2 - 4, CISTERN_TOP + max(5, CISTERN_H // 4),
                            fill="#FFFFFF", outline="")
        cv.create_rectangle(body_x1, CISTERN_TOP, body_x2, CISTERN_BOT,
                            fill="", outline="#C0C0C0", width=2)

        # Hemispherical dished end caps (clearly curved, NOT flat)
        for target, is_left in [(CIS_X, True), (CIS_X + CIS_W - 2 * DOME_R, False)]:
            hemi_colors = ["#D0D0D0", "#D8D8D8", "#E0E0E0", "#E8E8E8", "#F0F0F0",
                           "#F4F4F4", "#F8F8F8", "#FCFCFC", "#FEFEFE", "#FFFFFF"]
            if not is_left:
                hemi_colors = list(reversed(hemi_colors))
            for ki, kc in enumerate(hemi_colors):
                margin = ki * max(1, DOME_R // 12)
                r = DOME_R - margin
                if r > 2:
                    cv.create_oval(target + margin, CISTERN_TOP + margin,
                                   target + 2 * DOME_R - margin, CISTERN_BOT - margin,
                                   fill=kc, outline="")
            cv.create_oval(target, CISTERN_TOP, target + 2 * DOME_R, CISTERN_BOT,
                           fill="", outline="#C0C0C0", width=2)

        # ── Sunshield (half-cylinder shade over top half) ─────────────────
        ss_h = max(4, int(CISTERN_H * 0.08))
        ss_overhang = max(4, int(CIS_W * 0.02))
        cv.create_rectangle(CIS_X + DOME_R - ss_overhang, CISTERN_TOP - ss_h,
                            CIS_X + CIS_W - DOME_R + ss_overhang, CISTERN_TOP,
                            fill="#E0E0E0", outline="#B0B0B0", width=1)
        # Sunshield supports
        for si in range(3):
            sx2 = body_x1 + int((body_x2 - body_x1) * (si + 1) / 4)
            cv.create_line(sx2, CISTERN_TOP - ss_h, sx2, CISTERN_TOP - ss_h - 2,
                           fill="#B0B0B0", width=1)
            cv.create_line(sx2, CISTERN_TOP - ss_h - 2, sx2 + 4, CISTERN_TOP + 2,
                           fill="#B0B0B0", width=1)

        # ── Fill + labels per tank ────────────────────────────────────────
        for i, tn in enumerate(tank_names[:n]):
            # Compute fill zone within the single vessel
            seg_x1 = body_x1 + int((body_x2 - body_x1) * i / n) + 2
            seg_x2 = body_x1 + int((body_x2 - body_x1) * (i + 1) / n) - 2
            try:
                vol = self.parse_float(self.get_var(f"{etapa_key}_{tn}_vol_nat_prod").get() or "0")
                cap = self.parse_float(self.get_var(f"{etapa_key}_{tn}_alt_ref").get() or "1")
                vp  = min(max(vol / (cap if cap > 0 else 1), 0), 1)
            except: vp = 0.0
            pnm  = self.get_var(f"{etapa_key}_{tn}_prod_name").get() if etapa_key else ""
            pres = self.get_var(f"{etapa_key}_{tn}_esf_pres").get() if etapa_key else ""

            if vp > 0.02:
                fill_top = int(CISTERN_BOT - CISTERN_H * vp)
                cv.create_rectangle(seg_x1, fill_top, seg_x2, CISTERN_BOT - 2,
                                    fill="#FF6B35", outline="")
                cv.create_rectangle(seg_x1, fill_top, seg_x2,
                                    fill_top + max(3, int(CISTERN_H * 0.06)),
                                    fill="#FFB088", outline="")
                cv.create_line(seg_x1, fill_top, seg_x2, fill_top, fill="#CC4A1A", width=2)

            mid_y = (CISTERN_TOP + CISTERN_BOT) // 2
            seg_cx = (seg_x1 + seg_x2) // 2
            short = tn.replace("COMPARTIMENTO ", "C.").strip()[:6]
            txt_c = "#1B2631" if vp < 0.4 else "white"
            cv.create_text(seg_cx, CISTERN_TOP + max(10, int(CISTERN_H * 0.18)),
                           text=short, font=FT, fill="#4A5568")
            if vp > 0:
                cv.create_text(seg_cx, mid_y, text=f"{vp*100:.0f}%", font=FTS, fill=txt_c)
            if pnm:
                cv.create_text(seg_cx, CISTERN_BOT - max(8, int(CISTERN_H * 0.15)),
                               text=pnm[:10], font=FTS, fill=txt_c)

        # Redraw vessel outline over fill
        cv.create_rectangle(body_x1, CISTERN_TOP, body_x2, CISTERN_BOT,
                            fill="", outline="#C0C0C0", width=2)

        # ── Safety relief valves on top ───────────────────────────────────
        for vvi in range(2):
            vvx = body_x1 + int((body_x2 - body_x1) * (vvi + 1) / 3)
            cv.create_rectangle(vvx - 4, CISTERN_TOP - ss_h - 10, vvx + 4, CISTERN_TOP - ss_h,
                                fill="#E74C3C", outline="#C0392B", width=1)
            cv.create_rectangle(vvx - 6, CISTERN_TOP - ss_h - 14, vvx + 6, CISTERN_TOP - ss_h - 10,
                                fill="#C0392B", outline="")
            cv.create_rectangle(vvx - 1, CISTERN_TOP - ss_h - 20, vvx + 1, CISTERN_TOP - ss_h - 14,
                                fill="#5D6D7E", outline="")

        # ── Hazmat diamond: RED (flammable gas, Class 2.1) ────────────────
        plac_x = body_x2 - max(15, int(CIS_W * 0.06))
        plac_y = (CISTERN_TOP + CISTERN_BOT) // 2
        plac_s = max(8, int(CISTERN_H * 0.14))
        cv.create_polygon(plac_x, plac_y - plac_s, plac_x + plac_s, plac_y,
                          plac_x, plac_y + plac_s, plac_x - plac_s, plac_y,
                          fill="#E74C3C", outline="#922B21", width=1)
        cv.create_text(plac_x, plac_y - 2, text="2", font=("Arial", max(3, fss - 1), "bold"), fill="white")
        cv.create_text(plac_x, plac_y + plac_s - 4, text="GLP",
                       font=("Arial", max(2, fss - 2)), fill="white")

        # ── Heavy rear protective frame ───────────────────────────────────
        rear_x = CIS_X + CIS_W + max(2, int(W * 0.005))
        frame_w = max(6, int(W * 0.015))
        cv.create_rectangle(rear_x, CISTERN_TOP + int(CISTERN_H * 0.2),
                            rear_x + frame_w, CISTERN_BOT + ch_h,
                            fill="#2C3E50", outline="#1B2631", width=1)
        # Horizontal bars
        for bfi in range(3):
            bfy = CISTERN_TOP + int(CISTERN_H * (0.25 + 0.25 * bfi))
            cv.create_rectangle(rear_x, bfy - 2, rear_x + frame_w, bfy + 2,
                                fill="#4A5568", outline="")
        cv.create_rectangle(rear_x, CISTERN_BOT + ch_h - 2, rear_x + frame_w, GROUND_Y - 2,
                            fill="#4A5568", outline="#2C3E50")
        cv.create_rectangle(rear_x, CISTERN_BOT + ch_h, rear_x + 3, CISTERN_BOT + ch_h + 6,
                            fill="#E74C3C", outline="")

        # ── Cab (same chassis/cab as liquid truck with different color) ───
        CAB_BOT = CISTERN_BOT; CAB_H = CISTERN_H + max(8, int(CISTERN_H * 0.22))
        CAB_TOP = CAB_BOT - CAB_H
        cab_slope = max(4, int(CAB_W * 0.12))
        cab_pts = [CAB_X, CAB_BOT, CAB_X + CAB_W, CAB_BOT,
                   CAB_X + CAB_W, CAB_TOP + int(CAB_H * 0.18),
                   CAB_X + CAB_W - cab_slope, CAB_TOP,
                   CAB_X + cab_slope, CAB_TOP,
                   CAB_X, CAB_TOP + int(CAB_H * 0.18)]
        cv.create_polygon([p + 3 for p in cab_pts], fill="#404850", outline="")
        cv.create_polygon(cab_pts, fill="#2E4053", outline="#1B2631", width=2)
        cv.create_rectangle(CAB_X, CAB_TOP + 1, CAB_X + CAB_W, CAB_TOP + max(4, int(CAB_H * 0.08)),
                            fill="#3D5166", outline="")
        sp_h = max(6, int(CAB_H * 0.14))
        cv.create_polygon(CAB_X + int(CAB_W * 0.1), CAB_TOP,
                          CAB_X + int(CAB_W * 0.9), CAB_TOP,
                          CAB_X + int(CAB_W * 0.9), CAB_TOP - sp_h + 3,
                          CAB_X + int(CAB_W * 0.1), CAB_TOP - sp_h,
                          fill="#3D5166", outline="#2C3E50")
        # Window
        front_w = max(4, int(CAB_W * 0.12))
        cv.create_rectangle(CAB_X + CAB_W - front_w, CAB_TOP + int(CAB_H * 0.18),
                            CAB_X + CAB_W, CAB_TOP + int(CAB_H * 0.72),
                            fill="#AED6F1", outline="#2C3E50", width=1)
        d_ml = max(4, int(CAB_W * 0.08)); d_mr = front_w + max(4, int(CAB_W * 0.06))
        door_top = CAB_TOP + int(CAB_H * 0.18); door_bot = CAB_BOT - max(4, int(CAB_H * 0.05))
        dx1 = CAB_X + d_ml; dx2 = CAB_X + CAB_W - d_mr
        cv.create_rectangle(dx1, door_top, dx2, door_bot, fill="", outline="#1B2631", width=2)
        panel_y = door_top + int((door_bot - door_top) * 0.52)
        cv.create_line(dx1, panel_y, dx2, panel_y, fill="#1B2631", width=1)
        wm_l = d_ml + max(4, int(CAB_W * 0.05)); wm_r = d_mr + max(4, int(CAB_W * 0.05))
        wy = CAB_TOP + int(CAB_H * 0.08); wb = panel_y - max(3, int(CAB_H * 0.04))
        wx1 = CAB_X + wm_l; wx2 = CAB_X + CAB_W - wm_r
        cv.create_rectangle(wx1 - 2, wy - 2, wx2 + 2, wb + 2, fill="#1B2631", outline="")
        cv.create_rectangle(wx1, wy, wx2, wb, fill="#AED6F1", outline="#2C3E50", width=1)

        # Grille and headlight
        grill_h = max(10, int(CAB_H * 0.22)); grill_w = max(6, int(CAB_W * 0.25))
        grill_y = CAB_BOT - max(16, int(CAB_H * 0.24))
        cv.create_rectangle(CAB_X - grill_w, grill_y, CAB_X, grill_y + grill_h,
                            fill="#BDC3C7", outline="#7F8C8D", width=1)
        hl_r = max(4, int(grill_h * 0.35))
        hl_cx = CAB_X - grill_w // 2; hl_cy = grill_y + grill_h - hl_r - 3
        cv.create_oval(hl_cx - hl_r, hl_cy - hl_r, hl_cx + hl_r, hl_cy + hl_r,
                       fill="#F9E79F", outline="#D4AC0D")

        # Exhaust
        exh_x = CAB_X + CAB_W - max(6, int(CAB_W * 0.08))
        cv.create_rectangle(exh_x - 2, CAB_TOP - max(14, int(CAB_H * 0.45)), exh_x + 2, CAB_TOP + 3,
                            fill="#4A5568", outline="#2C3E50")

        # ── Wheels ────────────────────────────────────────────────────────
        AXLE_Y = GROUND_Y - AXLE_R
        wps = [CAB_X + int(CAB_W * 0.62)]
        rc = CIS_X + int(CIS_W * 0.72)
        wps += [rc - max(4, AXLE_R // 4), rc + max(4, AXLE_R // 4)]

        for wx in wps:
            cv.create_oval(wx - AXLE_R + 2, AXLE_Y - AXLE_R + 2,
                           wx + AXLE_R + 2, AXLE_Y + AXLE_R + 2,
                           fill="#0A0E12", outline="")
            cv.create_oval(wx - AXLE_R, AXLE_Y - AXLE_R, wx + AXLE_R, AXLE_Y + AXLE_R,
                           fill="#1B2631", outline="#0E1A27", width=2)
            rim_r = max(4, int(AXLE_R * 0.55))
            cv.create_oval(wx - rim_r, AXLE_Y - rim_r, wx + rim_r, AXLE_Y + rim_r,
                           fill="#808B96", outline="#5D6D7E", width=1)
            for angle_r in [0, 60, 120, 180, 240, 300]:
                ar = math.radians(angle_r)
                cv.create_line(wx + int(rim_r * 0.25 * math.cos(ar)),
                               AXLE_Y + int(rim_r * 0.25 * math.sin(ar)),
                               wx + int(rim_r * 0.85 * math.cos(ar)),
                               AXLE_Y + int(rim_r * 0.85 * math.sin(ar)),
                               fill="#5D6D7E", width=1)
            cv.create_oval(wx - 3, AXLE_Y - 3, wx + 3, AXLE_Y + 3, fill="#4A5568", outline="")

    def _draw_moss_vessel(self, cv, x, y, W, H, side_label, etapa_key, tank_names, carb_names):
        """MOSS type LNG carrier -- 4 large spheres DOMINATING profile above deck, stern superstructure."""
        import math
        if tank_names is None: tank_names = self.lista_tanques
        if H < 60 or W < 120: return

        def bez(p0, p1, p2, p3, n_pts=20):
            pts = []
            for i in range(n_pts + 1):
                t = i / n_pts; u = 1 - t
                pts += [u**3*p0[0]+3*u**2*t*p1[0]+3*u*t**2*p2[0]+t**3*p3[0],
                        u**3*p0[1]+3*u**2*t*p1[1]+3*u*t**2*p2[1]+t**3*p3[1]]
            return pts

        fs  = min(9, max(5, int(H*0.034)));  fss = min(7, max(4, int(H*0.026)))
        FT  = ("Arial", fs);  FTS = ("Arial", fss)

        TITLE_H = max(14, int(H*0.07))
        SPHERE_ZONE = int(H*0.55)   # Spheres DOMINATE the profile
        HULL_ZONE   = H - SPHERE_ZONE - TITLE_H - 4

        buque = self.get_var("car_buque").get() or "BUQUE GASERO"

        # ── Ocean/sky background ──────────────────────────────────────────
        # Sky gradient
        sky_cols = ["#87CEEB","#9DD5EE","#B3DCF1","#C9E4F4","#DFF0FA"]
        sky_h = int(H * 0.55)
        for si, sc in enumerate(sky_cols):
            sy1 = y + int(sky_h * si / len(sky_cols))
            sy2 = y + int(sky_h * (si + 1) / len(sky_cols))
            cv.create_rectangle(x, sy1, x + W, sy2, fill=sc, outline="")
        # Ocean water
        ocean_cols = ["#1A5276","#1F618D","#2471A3","#2980B9","#2E86C1","#3498DB"]
        ocean_top = y + sky_h
        ocean_h = y + H - ocean_top
        for oi, oc in enumerate(ocean_cols):
            oy1 = ocean_top + int(ocean_h * oi / len(ocean_cols))
            oy2 = ocean_top + int(ocean_h * (oi + 1) / len(ocean_cols))
            cv.create_rectangle(x, oy1, x + W, oy2, fill=oc, outline="")
        # Wave pattern on water surface
        for wi in range(0, W, max(20, W // 15)):
            wx = x + wi
            wave_pts = bez((wx, ocean_top), (wx + 5, ocean_top - 2), (wx + 10, ocean_top + 2), (wx + 15, ocean_top), 8)
            for wj in range(0, len(wave_pts) - 2, 2):
                cv.create_line(int(wave_pts[wj]), int(wave_pts[wj+1]),
                               int(wave_pts[wj+2]), int(wave_pts[wj+3]),
                               fill="#5DADE2", width=1)
        cv.create_rectangle(x, y, x + W, y + H, fill="", outline="#1B3A5C", width=2)

        # Title with shadow
        cv.create_text(x+W//2+1, y+TITLE_H//2+1, text=f"BUQUE GASERO/GLP  --  {buque}", font=FT, fill="#A0B0C0")
        cv.create_text(x+W//2, y+TITLE_H//2, text=f"BUQUE GASERO/GLP  --  {buque}", font=FT, fill="#1B3A5C")

        # ── Hull ──────────────────────────────────────────────────────────
        DECK_Y  = y + TITLE_H + SPHERE_ZONE + 4
        KEEL_Y  = y + H - 4
        HULL_H  = KEEL_Y - DECK_Y
        WL_Y    = DECK_Y + int(HULL_H * 0.55)
        BOW_X   = x + W - max(14, int(W * 0.03))
        STERN_X = x + max(14, int(W * 0.03))
        proa    = int(W * 0.045)
        CX      = x + W // 2

        # Freeboard (dark hull above waterline)
        bow_top = bez((BOW_X, DECK_Y), (BOW_X + proa, DECK_Y),
                      (BOW_X + proa, WL_Y - int(HULL_H * 0.1)), (BOW_X + proa // 2, WL_Y))
        top_poly = [STERN_X - 4, DECK_Y, BOW_X, DECK_Y] + bow_top + [STERN_X - 4, WL_Y]
        # Hull gradient (dark to slightly lighter)
        cv.create_polygon(top_poly, fill="#2C3E50", outline="")
        # Lighter band near deck
        for hi in range(3):
            hf = hi / 3
            hy = DECK_Y + int((WL_Y - DECK_Y) * hf * 0.3)
            hh = max(2, int(HULL_H * 0.04))
            hull_band_col = ["#34495E","#3D5166","#2C3E50"][hi]
            cv.create_rectangle(STERN_X, hy, BOW_X, hy + hh, fill=hull_band_col, outline="")
        cv.create_polygon(top_poly, fill="", outline="#1B2631", width=1)

        # Underwater hull (anti-fouling red)
        bow_bot = bez((BOW_X + proa // 2, WL_Y),
                      (BOW_X + proa // 2, KEEL_Y - int(HULL_H * 0.05)),
                      (BOW_X - int(W * 0.03), KEEL_Y), (CX, KEEL_Y + int(HULL_H * 0.03)))
        stern_bot = bez((CX, KEEL_Y + int(HULL_H * 0.03)),
                        (STERN_X + int(W * 0.04), KEEL_Y),
                        (STERN_X, KEEL_Y - int(HULL_H * 0.02)), (STERN_X - 4, WL_Y))
        bot_poly = [STERN_X - 4, WL_Y] + bow_bot + stern_bot
        cv.create_polygon(bot_poly, fill="#7B241C", outline="#5B1A14", width=1)
        # Boot-topping stripe
        cv.create_line(STERN_X - 10, WL_Y, BOW_X + proa // 2, WL_Y, fill="#1A1A1A", width=2)
        cv.create_line(STERN_X - 10, WL_Y + 2, BOW_X + proa // 2, WL_Y + 2, fill="#2E86C1", width=1, dash=(5, 3))
        cv.create_text(x + W - 25, WL_Y - 7, text="WL", font=FTS, fill="#2E86C1")

        # Deck with plating detail
        deck_x1 = STERN_X + int(W * 0.02)
        deck_x2 = BOW_X - int(W * 0.02)
        cv.create_rectangle(deck_x1, DECK_Y - 5, deck_x2, DECK_Y, fill="#3D4B56", outline="")
        cv.create_line(deck_x1, DECK_Y - 5, deck_x2, DECK_Y - 5, fill="#4A5568", width=1)
        # Deck plating lines
        for di in range(deck_x1, deck_x2, max(12, (deck_x2 - deck_x1) // 20)):
            cv.create_line(di, DECK_Y - 4, di, DECK_Y - 1, fill="#4A5568", width=1)

        # Bulwark (raised edge of deck)
        cv.create_rectangle(deck_x1, DECK_Y - 7, deck_x2, DECK_Y - 5, fill="#4A5568", outline="#3D4B56")

        # ── Superstructure (aft) ──────────────────────────────────────────
        SUP_W = max(50, int(W * 0.12))
        SUP_H = max(30, int(SPHERE_ZONE * 0.60))
        SUP_X = STERN_X + int(W * 0.02)

        # Multiple deck levels
        n_levels = 4
        for li in range(n_levels):
            lw = SUP_W - li * max(3, int(SUP_W * 0.05))
            lh = SUP_H // n_levels
            ly = DECK_Y - (li + 1) * lh
            lx = SUP_X + li * max(1, int(SUP_W * 0.025))
            col = ["#D5D8DC","#E0E3E7","#E5E8EC","#EBEDF0"][li]
            cv.create_rectangle(lx, ly, lx + lw, ly + lh, fill=col, outline="#ABB2B9", width=1)
            # Windows
            win_y = ly + max(2, lh // 4)
            win_h = max(3, lh // 3)
            for wi in range(max(2, lw // 10)):
                win_x = lx + 4 + wi * max(6, lw // max(2, lw // 10))
                if win_x + 4 < lx + lw - 4:
                    cv.create_rectangle(win_x, win_y, win_x + max(3, lw // 12), win_y + win_h,
                                        fill="#2E86C1", outline="#1A5276")
        # Bridge wing
        bridge_y = DECK_Y - SUP_H
        cv.create_rectangle(SUP_X - max(4, int(SUP_W * 0.08)), bridge_y,
                            SUP_X + SUP_W + max(4, int(SUP_W * 0.08)), bridge_y + max(4, SUP_H // n_levels),
                            fill="#E5E7E9", outline="#ABB2B9")

        # Funnel/chimney
        chim_w = max(8, int(SUP_W * 0.25))
        chim_h = max(14, int(SUP_H * 0.45))
        chim_x = SUP_X + SUP_W // 2 - chim_w // 2
        # Funnel body gradient
        chim_grads = ["#C0392B","#CD4535","#DA5040","#C0392B","#A82E22"]
        for ci2, cc in enumerate(chim_grads):
            cw1 = chim_x + int(chim_w * ci2 / len(chim_grads))
            cw2 = chim_x + int(chim_w * (ci2 + 1) / len(chim_grads))
            cv.create_rectangle(cw1, bridge_y - chim_h, cw2, bridge_y,
                                fill=cc, outline="")
        cv.create_rectangle(chim_x, bridge_y - chim_h, chim_x + chim_w, bridge_y,
                            fill="", outline="#922B21", width=1)
        # Funnel top (dark opening)
        cv.create_oval(chim_x, bridge_y - chim_h - 3, chim_x + chim_w, bridge_y - chim_h + 3,
                       fill="#4A1A14", outline="#922B21")
        # Company mark on funnel
        cv.create_rectangle(chim_x + 2, bridge_y - int(chim_h * 0.5),
                            chim_x + chim_w - 2, bridge_y - int(chim_h * 0.3),
                            fill="#F4D03F", outline="")

        # ── Spheres on deck ───────────────────────────────────────────────
        n = max(len(tank_names), 1)
        sph_start = SUP_X + SUP_W + max(8, int(W * 0.02))
        sph_end   = BOW_X - max(20, int(W * 0.05))
        sph_total = sph_end - sph_start
        sph_each  = sph_total // n
        SPH_R     = min(int(SPHERE_ZONE * 0.42), sph_each // 2 - 6)
        SPH_R     = max(18, SPH_R)
        SPH_BASE  = int(SPH_R * 0.22)

        for i, tn in enumerate(tank_names[:n]):
            cx_s = sph_start + i * sph_each + sph_each // 2
            cy_s = DECK_Y - SPH_BASE - SPH_R

            # Sphere shadow on deck
            sh_w = int(SPH_R * 0.7)
            cv.create_oval(cx_s - sh_w, DECK_Y - 5, cx_s + sh_w, DECK_Y + 1,
                           fill="#2A3540", outline="")

            # Skirt (cylindrical support)
            skirt_w = int(SPH_R * 0.5)
            skirt_top = DECK_Y - SPH_BASE - max(6, int(SPH_R * 0.25))
            # Skirt gradient
            cv.create_rectangle(cx_s - skirt_w, skirt_top, cx_s + skirt_w, DECK_Y,
                                fill="#4A5568", outline="")
            cv.create_line(cx_s - skirt_w + 2, skirt_top, cx_s - skirt_w + 2, DECK_Y,
                           fill="#5D6D7E", width=1)
            cv.create_rectangle(cx_s - skirt_w, skirt_top, cx_s + skirt_w, DECK_Y,
                                fill="", outline="#3D4456", width=1)
            # Skirt ventilation openings
            for vi in range(3):
                vx = cx_s - skirt_w + int(skirt_w * 2 * (vi + 1) / 4)
                cv.create_rectangle(vx - 2, DECK_Y - max(4, int(SPH_R * 0.06)),
                                    vx + 2, DECK_Y - 2, fill="#2C3E50", outline="")

            # Containment cover (dome housing visible above sphere equator)
            cover_r = int(SPH_R * 1.08)
            cover_h = int(SPH_R * 0.25)
            cv.create_arc(cx_s - cover_r, cy_s - cover_h, cx_s + cover_r, cy_s + cover_h,
                          start=0, extent=180, style="chord", fill="#D5D8DC", outline="#ABB2B9")

            # Sphere with 16-layer radial gradient
            sphere_gradient = [
                "#2D3E4C","#354A5A","#3D5668","#456276","#506E84","#5C7A92",
                "#6B88A0","#7E98AE","#94ABBC","#AAC0CC","#BFD4DC","#D4E4EC",
                "#E4EFF4","#EFF6F9","#F6FBFC","#FAFEFE",
            ]
            n_layers = len(sphere_gradient)
            for k in range(n_layers - 1, -1, -1):
                frac = k / (n_layers - 1)
                r_k = int(SPH_R * (0.10 + frac * 0.90))
                if r_k < 1: continue
                max_off = int(SPH_R * 0.30)
                off_x = int(max_off * (1 - frac) * 0.55)
                off_y = int(max_off * (1 - frac) * 0.80)
                sc3 = sphere_gradient[k]
                cv.create_oval(cx_s - r_k - off_x // 2, cy_s - r_k - off_y // 2,
                               cx_s + r_k - off_x // 2, cy_s + r_k - off_y // 2,
                               fill=sc3, outline="")

            # Weld seams on sphere
            cv.create_oval(cx_s - SPH_R + 2, cy_s - 1, cx_s + SPH_R - 2, cy_s + 1,
                           fill="", outline="#4A6070", width=1)
            for m_off in [-int(SPH_R * 0.40), int(SPH_R * 0.40)]:
                m_w = max(2, int(SPH_R * 0.12))
                cv.create_oval(cx_s + m_off - m_w, cy_s - SPH_R + 2,
                               cx_s + m_off + m_w, cy_s + SPH_R - 2,
                               fill="", outline="#4A6070", width=1)

            cv.create_oval(cx_s - SPH_R, cy_s - SPH_R, cx_s + SPH_R, cy_s + SPH_R,
                           fill="", outline="#2C3E50", width=3)

            # Nozzles at top
            for nxi in [-int(SPH_R * 0.3), 0, int(SPH_R * 0.3)]:
                nx2 = cx_s + nxi
                cv.create_rectangle(nx2 - 3, cy_s - SPH_R - 12, nx2 + 3, cy_s - SPH_R,
                                    fill="#4A5568", outline="#2C3E50", width=1)
                cv.create_rectangle(nx2 - 5, cy_s - SPH_R - 15, nx2 + 5, cy_s - SPH_R - 12,
                                    fill="#5D6D7E", outline="#2C3E50")

            # Fill level
            try:
                vol = self.parse_float(self.get_var(f"{etapa_key}_{tn}_vol_nat_prod").get() or "0") if etapa_key and tn else 0
                ref = self.parse_float(self.get_var(f"{etapa_key}_{tn}_alt_ref").get() or "1")
                vp  = min(max(vol / ref, 0), 1) if ref > 0 else 0
            except: vp = 0.0
            prod_fill = self.get_prod_color(tn, etapa_key)[0]

            if vp > 0.02:
                fh2 = int(SPH_R * (2 * vp - 1))
                ftop = cy_s - fh2
                clip_top = max(cy_s - SPH_R + 3, ftop)
                liq_fill = prod_fill if prod_fill not in ("#3498DB","#5DADE2","#2E86C1","#2471A3","#AED6F1","#85C1E9") else "#FF6B35"
                cv.create_rectangle(cx_s - SPH_R + 3, clip_top, cx_s + SPH_R - 3, cy_s + SPH_R - 3,
                                    fill=liq_fill, outline="")
                cv.create_oval(cx_s - SPH_R, cy_s - SPH_R, cx_s + SPH_R, cy_s + SPH_R,
                               fill="", outline="#2C3E50", width=3)
                lv_y2 = clip_top
                hc2 = int((SPH_R**2 - (cy_s - lv_y2)**2)**0.5) if abs(cy_s - lv_y2) < SPH_R else 0
                if hc2 > 0:
                    cv.create_line(cx_s - hc2, lv_y2, cx_s + hc2, lv_y2, fill="#4A4A4A", width=2, dash=(4, 3))
                txt_col_s = self.contrast_text(liq_fill) if vp > 0.5 else "white"
                cv.create_text(cx_s, cy_s, text=f"{vp*100:.0f}%", font=FTS, fill=txt_col_s)

            # Dome/trunk fitting above sphere
            cv.create_rectangle(cx_s - 7, cy_s - SPH_R - 12, cx_s + 7, cy_s - SPH_R,
                                fill="#5D6D7E", outline="#2C3E50")
            cv.create_oval(cx_s - 8, cy_s - SPH_R - 15, cx_s + 8, cy_s - SPH_R - 11,
                           fill="#808B96", outline="#5D6D7E")

            # Label
            tn_s = tn[:6]
            cv.create_text(cx_s, cy_s + SPH_R + SPH_BASE + 6, text=tn_s, font=FTS, fill="#1B3A5C")

        # ── Deck piping (manifold between spheres) ────────────────────────
        if n > 1:
            pipe_y = DECK_Y - 3
            first_cx = sph_start + sph_each // 2
            last_cx  = sph_start + (n - 1) * sph_each + sph_each // 2
            cv.create_rectangle(first_cx, pipe_y - 2, last_cx, pipe_y + 2, fill="#5D6D7E", outline="#4A5568")
            cv.create_line(first_cx, pipe_y - 1, last_cx, pipe_y - 1, fill="#808B96", width=1)

        # Bow mast
        mast_x = BOW_X - max(16, int(W * 0.04))
        mast_top = DECK_Y - max(25, int(SPHERE_ZONE * 0.60))
        cv.create_line(mast_x, DECK_Y - 5, mast_x, mast_top, fill="#626567", width=2)
        # Stays
        cv.create_line(mast_x, mast_top, BOW_X, DECK_Y - 5, fill="#95A5A6", width=1, dash=(3, 4))
        cv.create_line(mast_x, mast_top, mast_x - max(20, int(W * 0.05)), DECK_Y - 5,
                       fill="#95A5A6", width=1, dash=(3, 4))

        # Draft marks at bow
        for di in range(3):
            dm_y = WL_Y + int(di * HULL_H * 0.08)
            cv.create_text(BOW_X + proa // 2 - 4, dm_y, text=str(8 - di),
                           font=("Arial", max(3, fss - 2)), fill="#FDFEFE")

        # Side label
        cv.create_text(x + 12, y + TITLE_H + SPHERE_ZONE // 2, text=side_label,
                       font=FTS, fill="#1B3A5C", angle=90)

    def _draw_membrane_vessel(self, cv, x, y, W, H, side_label, etapa_key, tank_names, carb_names):
        """Membrane/GTT LNG carrier -- FLAT deck, NO spheres, low trunk coamings, clean sleek profile."""
        import math
        if tank_names is None: tank_names = self.lista_tanques
        if H < 60 or W < 120: return

        def bez(p0, p1, p2, p3, n_pts=20):
            pts = []
            for i in range(n_pts + 1):
                t = i / n_pts; u = 1 - t
                pts += [u**3*p0[0]+3*u**2*t*p1[0]+3*u*t**2*p2[0]+t**3*p3[0],
                        u**3*p0[1]+3*u**2*t*p1[1]+3*u*t**2*p2[1]+t**3*p3[1]]
            return pts

        fs  = min(9, max(5, int(H*0.034)));  fss = min(7, max(4, int(H*0.026)))
        FT  = ("Arial", fs);  FTS = ("Arial", fss)

        TITLE_H       = max(14, int(H*0.07))
        SUP_CLEARANCE = max(40, int(H*0.22))

        buque = self.get_var("car_buque").get() or "BUQUE METANERO"

        # ── Ocean/sky background ──────────────────────────────────────────
        sky_cols = ["#87CEEB","#9DD5EE","#B3DCF1","#C9E4F4","#E0F0FA"]
        sky_h = int(H * 0.45)
        for si, sc in enumerate(sky_cols):
            sy1 = y + int(sky_h * si / len(sky_cols))
            sy2 = y + int(sky_h * (si + 1) / len(sky_cols))
            cv.create_rectangle(x, sy1, x + W, sy2, fill=sc, outline="")
        ocean_cols = ["#154360","#1A5276","#1F618D","#2471A3","#2980B9","#3498DB"]
        ocean_top = y + sky_h
        ocean_h = y + H - ocean_top
        for oi, oc in enumerate(ocean_cols):
            oy1 = ocean_top + int(ocean_h * oi / len(ocean_cols))
            oy2 = ocean_top + int(ocean_h * (oi + 1) / len(ocean_cols))
            cv.create_rectangle(x, oy1, x + W, oy2, fill=oc, outline="")
        # Wave highlights
        for wi in range(0, W, max(18, W // 15)):
            wx = x + wi
            wave_pts = bez((wx, ocean_top), (wx + 5, ocean_top - 2), (wx + 10, ocean_top + 1), (wx + 14, ocean_top), 6)
            for wj in range(0, len(wave_pts) - 2, 2):
                cv.create_line(int(wave_pts[wj]), int(wave_pts[wj+1]),
                               int(wave_pts[wj+2]), int(wave_pts[wj+3]), fill="#5DADE2", width=1)
        cv.create_rectangle(x, y, x + W, y + H, fill="", outline="#1A5276", width=2)

        # Title
        cv.create_text(x+W//2+1, y+TITLE_H//2+1, text=f"BUQUE METANERO / GNL  --  {buque}", font=FT, fill="#A0B0C0")
        cv.create_text(x+W//2, y+TITLE_H//2, text=f"BUQUE METANERO / GNL  --  {buque}", font=FT, fill="#1A5276")

        # ── Hull ──────────────────────────────────────────────────────────
        DECK_Y  = y + TITLE_H + SUP_CLEARANCE
        KEEL_Y  = y + H - 4
        HULL_H  = KEEL_Y - DECK_Y
        WL_Y    = DECK_Y + int(HULL_H * 0.55)
        BOW_X   = x + W - max(14, int(W * 0.03))
        STERN_X = x + max(14, int(W * 0.03))
        proa    = int(W * 0.045)
        CX      = x + W // 2

        # Freeboard (solo contorno, interior se ve como cross-section con tanques)
        bow_top = bez((BOW_X, DECK_Y), (BOW_X + proa, DECK_Y),
                      (BOW_X + proa, WL_Y - int(HULL_H * 0.1)), (BOW_X + proa // 2, WL_Y))
        top_poly = [STERN_X - 4, DECK_Y, BOW_X, DECK_Y] + bow_top + [STERN_X - 4, WL_Y]
        # Fondo claro para cross-section del casco (los tanques se dibujan encima)
        cv.create_polygon(top_poly, fill="#2C3E50", outline="")
        cv.create_polygon(top_poly, fill="", outline="#0E1A27", width=1)

        # Underwater hull
        bow_bot = bez((BOW_X + proa // 2, WL_Y),
                      (BOW_X + proa // 2, KEEL_Y - int(HULL_H * 0.05)),
                      (BOW_X - int(W * 0.03), KEEL_Y), (CX, KEEL_Y + int(HULL_H * 0.03)))
        stern_bot = bez((CX, KEEL_Y + int(HULL_H * 0.03)),
                        (STERN_X + int(W * 0.04), KEEL_Y),
                        (STERN_X, KEEL_Y - int(HULL_H * 0.02)), (STERN_X - 4, WL_Y))
        bot_poly = [STERN_X - 4, WL_Y] + bow_bot + stern_bot
        cv.create_polygon(bot_poly, fill="#7B241C", outline="#5B1A14", width=1)
        # Boot-topping
        cv.create_line(STERN_X - 10, WL_Y, BOW_X + proa // 2, WL_Y, fill="#1A1A1A", width=2)
        cv.create_line(STERN_X - 10, WL_Y + 2, BOW_X + proa // 2, WL_Y + 2, fill="#2E86C1", width=1, dash=(5, 3))
        cv.create_text(x + W - 25, WL_Y - 7, text="WL", font=FTS, fill="#2E86C1")

        # Deck with plating detail
        deck_x1 = STERN_X + int(W * 0.02)
        deck_x2 = BOW_X - int(W * 0.02)
        cv.create_rectangle(deck_x1, DECK_Y - 5, deck_x2, DECK_Y, fill="#2C3E50", outline="")
        cv.create_line(deck_x1, DECK_Y - 5, deck_x2, DECK_Y - 5, fill="#3D4B56", width=1)
        # Bulwark
        cv.create_rectangle(deck_x1, DECK_Y - 7, deck_x2, DECK_Y - 5, fill="#3D4B56", outline="#2C3E50")

        # ── Superstructure ────────────────────────────────────────────────
        SUP_W = max(40, int(W * 0.08));  SUP_H = max(30, int(SUP_CLEARANCE * 0.85))
        SUP_X = STERN_X + int(W * 0.02)

        # Multi-level superstructure
        n_levels = 4
        for li in range(n_levels):
            lw = SUP_W - li * max(3, int(SUP_W * 0.05))
            lh = SUP_H // n_levels
            ly = DECK_Y - (li + 1) * lh
            lx = SUP_X + li * max(1, int(SUP_W * 0.02))
            col = ["#D5D8DC","#DFE2E6","#E5E8EC","#EBEDF0"][li]
            cv.create_rectangle(lx, ly, lx + lw, ly + lh, fill=col, outline="#ABB2B9", width=1)
            # Windows
            win_y = ly + max(2, lh // 4)
            win_h = max(3, lh // 3)
            for wi in range(max(2, lw // 10)):
                win_x = lx + 4 + wi * max(6, lw // max(2, lw // 10))
                if win_x + 4 < lx + lw - 4:
                    cv.create_rectangle(win_x, win_y, win_x + max(3, lw // 12), win_y + win_h,
                                        fill="#2E86C1", outline="#1A5276")
        # Bridge wing
        bridge_y = DECK_Y - SUP_H
        cv.create_rectangle(SUP_X - max(4, int(SUP_W * 0.08)), bridge_y,
                            SUP_X + SUP_W + max(4, int(SUP_W * 0.08)), bridge_y + max(4, SUP_H // n_levels),
                            fill="#E5E7E9", outline="#ABB2B9")

        # Chimney
        chim_w = max(8, int(SUP_W * 0.25))
        chim_h = max(12, int(SUP_H * 0.40))
        chim_x = SUP_X + SUP_W // 2 - chim_w // 2
        chim_grads = ["#C0392B","#CD4535","#DA5040","#C0392B","#A82E22"]
        for ci2, cc in enumerate(chim_grads):
            cw1 = chim_x + int(chim_w * ci2 / len(chim_grads))
            cw2 = chim_x + int(chim_w * (ci2 + 1) / len(chim_grads))
            cv.create_rectangle(cw1, bridge_y - chim_h, cw2, bridge_y, fill=cc, outline="")
        cv.create_rectangle(chim_x, bridge_y - chim_h, chim_x + chim_w, bridge_y,
                            fill="", outline="#922B21", width=1)
        cv.create_oval(chim_x, bridge_y - chim_h - 3, chim_x + chim_w, bridge_y - chim_h + 3,
                       fill="#4A1A14", outline="#922B21")

        # ── Membrane tanks (inside hull, visible through cross-section) ───
        # Un metanero real tiene mínimo 4 tanques
        n = max(len(tank_names), 4)
        # Tanques ocupan máximo espacio del casco
        tk_start = SUP_X + SUP_W + max(3, int(W * 0.005))
        tk_end   = BOW_X - max(8, int(W * 0.03))
        tk_total = max(40, tk_end - tk_start)
        cofferdam = max(2, int(tk_total * 0.008))
        tk_each  = max(10, (tk_total - cofferdam * (n - 1)) // n)
        TK_TOP   = DECK_Y + max(4, int(HULL_H * 0.04))
        TK_BOT   = KEEL_Y - max(6, int(HULL_H * 0.07))
        TK_H     = TK_BOT - TK_TOP
        CH       = max(5, int(min(tk_each * 0.9, TK_H) * 0.07))

        # Extender lista de tanques para que siempre haya n tanques visibles
        _display_tanks = list(tank_names[:n])
        while len(_display_tanks) < n:
            _display_tanks.append(f"TK {len(_display_tanks)+1}")


        for i, tn in enumerate(_display_tanks):
            tx = tk_start + i * (tk_each + cofferdam)
            tw = tk_each


            # Outer insulation layer
            insul_margin = max(2, int(tw * 0.03))
            cv.create_polygon(
                tx - insul_margin, TK_TOP + CH - insul_margin,
                tx + tw + insul_margin, TK_TOP + CH - insul_margin,
                tx + tw + insul_margin, TK_BOT + insul_margin,
                tx - insul_margin, TK_BOT + insul_margin,
                fill="#9EAAB2", outline="#7F8C8D", width=1
            )
            # Perlite/foam insulation pattern
            for pi in range(0, tw + 2 * insul_margin, max(6, tw // 8)):
                px = tx - insul_margin + pi
                cv.create_line(px, TK_TOP + CH - insul_margin, px, TK_BOT + insul_margin,
                               fill="#8A969E", width=1, dash=(1, 8))

            # Prismatic body with chamfers
            body = [
                tx + CH, TK_TOP,
                tx + tw - CH, TK_TOP,
                tx + tw, TK_TOP + CH,
                tx + tw, TK_BOT,
                tx, TK_BOT,
                tx, TK_TOP + CH,
            ]
            cv.create_polygon(body, fill="#2E4057", outline="", width=0)

            # Cryogenic stainless steel gradient (silver tones)
            cryo_colors = ["#F0F3F4","#E8ECF0","#E0E5EA","#D5DCE1","#CCD4DA","#C0CAD2",
                           "#B8C2CC","#B0BAC4","#A8B2BC","#A0AAB4"]
            for ki, cc in enumerate(cryo_colors):
                strip_y = TK_TOP + CH + int((TK_H - CH) * ki / len(cryo_colors))
                strip_h = int((TK_H - CH) / len(cryo_colors)) + 1
                clip_top2 = max(TK_TOP + CH, strip_y)
                clip_bot2 = min(TK_BOT, strip_y + strip_h)
                if clip_bot2 > clip_top2:
                    cv.create_polygon(
                        tx + CH, clip_top2, tx + tw - CH, clip_top2,
                        tx + tw, min(clip_top2 + CH, clip_bot2), tx + tw, clip_bot2,
                        tx, clip_bot2, tx, min(clip_top2 + CH, clip_bot2),
                        fill=cc, outline=""
                    )

            # Membrane corrugation pattern (GTT NO96 or Mark III style)
            corr_spacing = max(6, TK_H // 12)
            for ci2 in range(int(TK_TOP + CH + corr_spacing), int(TK_BOT), int(corr_spacing)):
                cv.create_line(tx + 3, ci2, tx + tw - 3, ci2, fill="#8A96A0", width=1, dash=(6, 4))
            # Vertical corrugations
            v_spacing = max(8, tw // 8)
            for vi in range(tx + v_spacing, tx + tw, v_spacing):
                cv.create_line(vi, TK_TOP + CH + 3, vi, TK_BOT - 3, fill="#8A96A0", width=1, dash=(6, 4))

            # Tank outline
            cv.create_polygon(body, fill="", outline="#1A4F6E", width=2)

            # Top chamfer highlight (metallic reflection)
            cv.create_polygon(tx + CH, TK_TOP, tx + tw - CH, TK_TOP, tx + tw, TK_TOP + CH,
                              tx + CH + 3, TK_TOP + 3, fill="#E8F0F5", outline="")
            # Left edge highlight
            cv.create_line(tx, TK_TOP + CH, tx, TK_BOT, fill="#D0D8E0", width=1)

            # Fill level
            try:
                s   = self.parse_float(self.get_var(f"{etapa_key}_{tn}_s_corr").get() or "0") if etapa_key and tn else 0
                ref = self.parse_float(self.get_var(f"{etapa_key}_{tn}_alt_ref").get() or "1")
                vp  = min(max(s / ref, 0), 1) if ref > 0 else 0
            except: vp = 0.0
            pnm = self.get_var(f"{etapa_key}_{tn}_prod_name").get() if etapa_key else ""

            if vp > 0.01:
                fill_h2 = int(TK_H * vp)
                fy = TK_BOT - fill_h2
                gnl_fill = self.get_prod_color(tn, etapa_key)[0] if etapa_key else "#E8E8F0"
                # LNG fill with gradient
                cv.create_rectangle(tx + 2, fy, tx + tw - 2, TK_BOT - 2, fill=gnl_fill, outline="")
                # Lighter band at top of liquid
                cv.create_rectangle(tx + 2, fy, tx + tw - 2, fy + max(2, fill_h2 // 8),
                                    fill="#F0F0F8", outline="")
                # Level line
                cv.create_line(tx + 2, fy, tx + tw - 2, fy, fill="#5D6D7E", width=2)
                # Boil-off gas bubbles
                for si in range(1, 5):
                    sx2 = tx + int(tw * si / 5)
                    bub_r = max(1, int(tw * 0.015))
                    cv.create_oval(sx2 - bub_r, fy - max(6, int(TK_H * 0.03)) - bub_r,
                                   sx2 + bub_r, fy - max(6, int(TK_H * 0.03)) + bub_r,
                                   fill="white", outline="#D0D8E0")
                    cv.create_line(sx2, fy, sx2, fy - max(6, int(TK_H * 0.03)),
                                   fill="#D0D8E0", width=1, dash=(2, 3))
                txt_gnl = self.contrast_text(gnl_fill)
                cv.create_text(tx + tw // 2, fy + fill_h2 // 2, text=f"{vp*100:.0f}%",
                               font=FTS, fill=txt_gnl)

            # Cryogenic dome (top of tank, above deck line)
            dm_cx = tx + tw // 2
            # Dome base
            cv.create_rectangle(dm_cx - max(12, int(tw * 0.12)), TK_TOP - max(12, int(TK_H * 0.04)),
                                dm_cx + max(12, int(tw * 0.12)), TK_TOP,
                                fill="#CCD1D9", outline="#7F8C8D", width=2)
            # Dome trunk
            cv.create_rectangle(dm_cx - max(6, int(tw * 0.06)), TK_TOP - max(18, int(TK_H * 0.06)),
                                dm_cx + max(6, int(tw * 0.06)), TK_TOP - max(12, int(TK_H * 0.04)),
                                fill="#5D6D7E", outline="#4A5568")
            # Dome cap
            dome_r = max(4, int(tw * 0.05))
            cv.create_oval(dm_cx - dome_r, TK_TOP - max(22, int(TK_H * 0.08)),
                           dm_cx + dome_r, TK_TOP - max(16, int(TK_H * 0.05)),
                           fill="#808B96", outline="#5D6D7E")
            # Cryo indicator
            cv.create_text(tx + 6, TK_TOP + 8, text="[C]", font=("Arial", max(4, fss - 1)), fill="#1ABC9C")

            # Tank number and labels
            tn_s = tn[:6]
            cv.create_text(tx + tw // 2, TK_BOT + max(8, int(HULL_H * 0.04)),
                           text=tn_s, font=FTS, fill="#2C3E50")
            if pnm:
                cv.create_text(tx + tw // 2, TK_TOP + TK_H // 2, text=pnm[:8], font=FTS, fill="#2C3E50")

        # Deck piping between tanks
        if n > 1:
            pipe_y = DECK_Y - 3
            cv.create_rectangle(tk_start, pipe_y - 1, tk_end, pipe_y + 1, fill="#5D6D7E", outline="#4A5568")

        # Bow mast with stays
        mast_x = BOW_X - max(16, int(W * 0.04))
        mast_top = DECK_Y - max(25, int(SUP_CLEARANCE * 0.60))
        cv.create_line(mast_x, DECK_Y - 5, mast_x, mast_top, fill="#626567", width=2)
        cv.create_line(mast_x, mast_top, BOW_X, DECK_Y - 5, fill="#95A5A6", width=1, dash=(3, 4))
        cv.create_line(mast_x, mast_top, mast_x - max(20, int(W * 0.05)), DECK_Y - 5,
                       fill="#95A5A6", width=1, dash=(3, 4))

        # Draft marks
        for di in range(3):
            dm_y = WL_Y + int(di * HULL_H * 0.08)
            cv.create_text(BOW_X + proa // 2 - 4, dm_y, text=str(10 - di),
                           font=("Arial", max(3, fss - 2)), fill="#FDFEFE")

        # Side label
        cv.create_text(x + 12, y + TITLE_H + HULL_H // 2, text=side_label,
                       font=FTS, fill="#1A5276", angle=90)

    def _draw_pipeline(self, cv, x, y, W, H, etapa_key, tipo, tank_names):
        """Underground pipeline cross-section -- earth layers, trench, FBE coating, warning tape, CP anode."""
        import math
        if H < 60 or W < 120: return
        if tank_names is None: tank_names = self.lista_tanques

        def bez(p0, p1, p2, p3, n_pts=16):
            pts = []
            for i in range(n_pts + 1):
                t = i / n_pts; u = 1 - t
                pts += [u**3*p0[0]+3*u**2*t*p1[0]+3*u*t**2*p2[0]+t**3*p3[0],
                        u**3*p0[1]+3*u**2*t*p1[1]+3*u*t**2*p2[1]+t**3*p3[1]]
            return pts

        fs  = min(10, max(5, int(H*0.036)));  fss = min(9, max(4, int(H*0.028)))
        FT  = ("Arial", fs);  FTS = ("Arial", fss)

        TITLE_H = max(16, int(H*0.08))
        instalacion = self.get_var("car_buque").get() or "DUCTO"
        tipo_color  = {"OLEODUCTO": "#C0392B", "POLIDUCTO": "#1A5276",
                       "GASODUCTO": "#1D6A39"}.get(tipo, "#5D4037")

        GROUND_Y = y + int(H * 0.42)

        # ── Sky background gradient ───────────────────────────────────────
        sky_cols = ["#87CEEB","#9DD5EE","#B3DCF1","#C9E4F4","#DFF0FA","#F0F7FC"]
        sky_h = GROUND_Y - y
        for si, sc in enumerate(sky_cols):
            sy1 = y + int(sky_h * si / len(sky_cols))
            sy2 = y + int(sky_h * (si + 1) / len(sky_cols))
            cv.create_rectangle(x, sy1, x + W, sy2, fill=sc, outline="")
        cv.create_rectangle(x, y, x + W, y + H, fill="", outline="#808B96", width=2)

        # Title with type color bar
        cv.create_rectangle(x + 1, y + 1, x + W - 1, y + TITLE_H + 2, fill="#F0F2F4", outline="")
        cv.create_rectangle(x + 1, y + TITLE_H, x + W - 1, y + TITLE_H + 4, fill=tipo_color, outline="")
        ttl = f"{tipo}  --  {instalacion}"
        cv.create_text(x + W // 2 + 1, y + TITLE_H // 2 + 1, text=ttl, font=FT, fill="#B0B8C0")
        cv.create_text(x + W // 2, y + TITLE_H // 2, text=ttl, font=FT, fill="#1B3A5C")

        # ── Ground surface with grass/vegetation ──────────────────────────
        # Grass line (irregular with Bezier)
        grass_pts = [x, GROUND_Y]
        seg_w = max(20, W // 12)
        for gi in range(0, W, seg_w):
            gx1 = x + gi
            gx2 = min(x + gi + seg_w, x + W)
            gh = max(2, int(H * 0.01)) * (1 + (gi % (seg_w * 2) == 0))
            grass_pts += bez((gx1, GROUND_Y), (gx1 + seg_w // 3, GROUND_Y - gh),
                             (gx2 - seg_w // 3, GROUND_Y - gh // 2), (gx2, GROUND_Y), 6)
        grass_pts += [x + W, GROUND_Y + 4, x, GROUND_Y + 4]
        cv.create_polygon(grass_pts, fill="#4A7C3F", outline="")
        # Grass tufts
        for gt in range(0, W, max(8, W // 30)):
            gx = x + gt + (hash(gt) % 5)
            gh = max(3, int(H * 0.015)) + (hash(gt * 7) % 3)
            cv.create_line(gx, GROUND_Y, gx - 2, GROUND_Y - gh, fill="#5D9B48", width=1)
            cv.create_line(gx, GROUND_Y, gx + 2, GROUND_Y - gh + 1, fill="#3E7A30", width=1)

        # ── Earth layers (cross section) ──────────────────────────────────
        UG_H = y + H - GROUND_Y
        earth_layers = [
            (0.00, 0.12, "#6B4F36", "#7D5E42"),  # topsoil (dark brown)
            (0.12, 0.30, "#8B6F47", "#9C7E55"),  # subsoil (lighter brown)
            (0.30, 0.55, "#C4A86C", "#D4B87C"),  # clay/sand
            (0.55, 0.75, "#A09080", "#B0A090"),  # gravel
            (0.75, 1.00, "#808080", "#909090"),  # bedrock
        ]
        for ef1, ef2, ec1, ec2 in earth_layers:
            ey1 = GROUND_Y + int(UG_H * ef1)
            ey2 = GROUND_Y + int(UG_H * ef2)
            # Two-tone gradient per layer
            mid = (ey1 + ey2) // 2
            cv.create_rectangle(x + 1, ey1, x + W - 1, mid, fill=ec1, outline="")
            cv.create_rectangle(x + 1, mid, x + W - 1, ey2, fill=ec2, outline="")
        # Layer boundary lines
        for ef1, ef2, ec1, ec2 in earth_layers[1:]:
            ey = GROUND_Y + int(UG_H * ef1)
            cv.create_line(x + 2, ey, x + W - 2, ey, fill="#5D5040", width=1, dash=(8, 4))
        # Rocks in gravel layer
        gravel_y1 = GROUND_Y + int(UG_H * 0.55)
        gravel_y2 = GROUND_Y + int(UG_H * 0.75)
        for ri in range(0, W, max(15, W // 20)):
            rx = x + ri + (hash(ri * 13) % 8)
            ry = gravel_y1 + (hash(ri * 7) % max(1, gravel_y2 - gravel_y1 - 6))
            rr = max(2, int(H * 0.008)) + hash(ri * 3) % 3
            cv.create_oval(rx, ry, rx + rr * 2, ry + rr, fill="#989088", outline="#807870")
        # Root-like lines in topsoil
        for ri in range(0, W, max(25, W // 10)):
            rx = x + ri + (hash(ri * 17) % 12)
            ry = GROUND_Y + int(UG_H * 0.02)
            cv.create_line(rx, ry, rx + max(6, W // 20), ry + int(UG_H * 0.08),
                           fill="#5A4030", width=1, dash=(3, 5))

        # ── Pipe parameters ───────────────────────────────────────────────
        PIPE_Y   = GROUND_Y + int(UG_H * 0.38)
        PIPE_R   = max(10, int(UG_H * 0.14))
        PAD_L    = max(40, int(W * 0.1))
        PAD_R    = PAD_L
        P_LEFT   = x + PAD_L
        P_RIGHT  = x + W - PAD_R
        PIPE_W   = P_RIGHT - P_LEFT

        # ── Yellow warning tape (300-500mm below surface, ABOVE pipe) ─────
        tape_y = GROUND_Y + int(UG_H * 0.15)  # about 300-500mm below surface
        tape_h = max(3, int(UG_H * 0.025))
        cv.create_rectangle(P_LEFT, tape_y, P_RIGHT, tape_y + tape_h,
                            fill="#F4D03F", outline="#D4AC0D", width=1)
        # "CAUTION BURIED PIPELINE" text on tape
        cv.create_text((P_LEFT + P_RIGHT) // 2, tape_y + tape_h // 2,
                       text="PELIGRO - DUCTO ENTERRADO", font=("Arial", max(3, fss - 2)), fill="#922B21")
        # Dashed edges for visibility
        cv.create_line(P_LEFT, tape_y, P_RIGHT, tape_y, fill="#D4AC0D", width=1, dash=(4, 4))
        cv.create_line(P_LEFT, tape_y + tape_h, P_RIGHT, tape_y + tape_h, fill="#D4AC0D", width=1, dash=(4, 4))

        # ── Trapezoidal trench with sloped walls ─────────────────────────
        trench_top_w = PIPE_R * 4
        trench_bot_w = PIPE_R * 3
        trench_top_y = PIPE_Y - PIPE_R - max(8, int(PIPE_R * 0.6))
        trench_bot_y = PIPE_Y + PIPE_R + max(8, int(PIPE_R * 0.6))
        trench_cx = (P_LEFT + P_RIGHT) // 2
        # Only draw trench cross-section at left end
        if True:
            tcx = P_LEFT
            cv.create_polygon(tcx - trench_top_w // 2, trench_top_y,
                              tcx + trench_top_w // 2, trench_top_y,
                              tcx + trench_bot_w // 2, trench_bot_y,
                              tcx - trench_bot_w // 2, trench_bot_y,
                              fill="", outline="#8B6F47", width=1, dash=(4, 3))

        # ── Cathodic protection anode ─────────────────────────────────────
        cp_x = P_LEFT + int(PIPE_W * 0.18)
        cp_y = PIPE_Y + PIPE_R + max(8, int(UG_H * 0.06))
        cp_h = max(12, int(UG_H * 0.12))
        # Anode body
        cv.create_rectangle(cp_x - 3, cp_y, cp_x + 3, cp_y + cp_h,
                            fill="#808080", outline="#606060")
        # Wire from anode to pipe
        cv.create_line(cp_x, cp_y, cp_x, PIPE_Y + PIPE_R + 2, fill="#F4D03F", width=1, dash=(2, 2))
        cv.create_text(cp_x, cp_y + cp_h + max(4, fss), text="CP", font=("Arial", max(3, fss - 2)), fill="#D4AC0D")

        # ── Buried pipe with coatings ─────────────────────────────────────
        n_pipes = 2 if tipo in ("POLIDUCTO",) else 1
        pipe_offsets = [0] if n_pipes == 1 else [-PIPE_R - 4, PIPE_R + 4]

        for pi, p_off in enumerate(pipe_offsets):
            py = PIPE_Y + p_off
            pc = tipo_color if pi == 0 else "#7D3C98"

            # Sand padding/bedding around pipe (light tan)
            cv.create_rectangle(P_LEFT - PIPE_R, py - PIPE_R - max(6, int(PIPE_R * 0.5)),
                                P_RIGHT + PIPE_R, py + PIPE_R + max(6, int(PIPE_R * 0.5)),
                                fill="#E8D8B0", outline="")

            # FBE coating (dark green layer around pipe - Fusion Bonded Epoxy)
            coat_t = max(2, int(PIPE_R * 0.15))
            cv.create_rectangle(P_LEFT, py - PIPE_R - coat_t, P_RIGHT, py + PIPE_R + coat_t,
                                fill="#1A3D1A", outline="")
            # FBE inner layer (dark green)
            cv.create_rectangle(P_LEFT, py - PIPE_R - coat_t + 1, P_RIGHT, py + PIPE_R + coat_t - 1,
                                fill="#2D5A2D" if pi == 0 else "#6A329F", outline="")

            # Steel pipe with cylindrical gradient
            cv.create_rectangle(P_LEFT, py - PIPE_R, P_RIGHT, py + PIPE_R, fill=pc, outline="")
            try:
                _r0 = int(pc[1:3], 16); _g0 = int(pc[3:5], 16); _b0 = int(pc[5:7], 16)
            except: _r0, _g0, _b0 = 100, 100, 100
            pipe_strips_grad = [
                (0.00, 0.08, 0.50), (0.08, 0.18, 0.68), (0.18, 0.32, 0.88),
                (0.32, 0.45, 1.15), (0.45, 0.55, 1.35), (0.55, 0.68, 1.15),
                (0.68, 0.82, 0.82), (0.82, 0.92, 0.62), (0.92, 1.00, 0.45),
            ]
            for pf1, pf2, bright in pipe_strips_grad:
                _rr = min(255, int(_r0 * bright)); _gg = min(255, int(_g0 * bright)); _bb = min(255, int(_b0 * bright))
                sc2 = f"#{_rr:02x}{_gg:02x}{_bb:02x}"
                sy1 = py - PIPE_R + int(pf1 * 2 * PIPE_R)
                sy2 = py - PIPE_R + int(pf2 * 2 * PIPE_R)
                cv.create_rectangle(P_LEFT + 2, sy1, P_RIGHT - 2, sy2 + 1, fill=sc2, outline="")
            # Specular highlight
            hl_y = py - PIPE_R + max(3, PIPE_R // 4)
            cv.create_rectangle(P_LEFT + PIPE_W // 8, hl_y, P_RIGHT - PIPE_W // 8,
                                hl_y + max(2, PIPE_R // 6), fill="#FFFFFF", outline="")
            # Pipe outline
            cv.create_rectangle(P_LEFT, py - PIPE_R, P_RIGHT, py + PIPE_R,
                                fill="", outline="#2C3E50", width=2)

            # End caps (cross-section view ellipses)
            # Left end - full cross section
            cap_r = PIPE_R + coat_t + 2
            cv.create_oval(P_LEFT - cap_r, py - cap_r, P_LEFT + cap_r, py + cap_r,
                           fill="#1A1A1A", outline="#0A0A0A", width=1)
            cv.create_oval(P_LEFT - PIPE_R, py - PIPE_R, P_LEFT + PIPE_R, py + PIPE_R,
                           fill=pc, outline="#2C3E50", width=2)
            # Inner bore
            inner_r = max(3, int(PIPE_R * 0.7))
            cv.create_oval(P_LEFT - inner_r, py - inner_r, P_LEFT + inner_r, py + inner_r,
                           fill="#2C2C2C", outline="#1A1A1A", width=1)
            # Product in bore
            if tipo == "OLEODUCTO":
                cv.create_oval(P_LEFT - inner_r + 1, py - inner_r + 1, P_LEFT + inner_r - 1, py + inner_r - 1,
                               fill="#7B241C", outline="")
            elif tipo == "GASODUCTO":
                cv.create_oval(P_LEFT - inner_r + 1, py - inner_r + 1, P_LEFT + inner_r - 1, py + inner_r - 1,
                               fill="#3D6B3D", outline="")

            # Right end
            cv.create_oval(P_RIGHT - cap_r, py - cap_r, P_RIGHT + cap_r, py + cap_r,
                           fill="#1A1A1A", outline="#0A0A0A", width=1)
            cv.create_oval(P_RIGHT - PIPE_R, py - PIPE_R, P_RIGHT + PIPE_R, py + PIPE_R,
                           fill="#4A5568", outline="#2C3E50", width=2)

            # Flanges (welded joints)
            n_flanges = max(3, min(7, PIPE_W // 60))
            flange_step = PIPE_W // (n_flanges + 1)
            for fi in range(n_flanges):
                fx = P_LEFT + (fi + 1) * flange_step
                # Flange ring
                cv.create_rectangle(fx - 2, py - PIPE_R - 4, fx + 2, py + PIPE_R + 4,
                                    fill="#5D6D7E", outline="#4A5568", width=1)
                # Bolts
                for by_off in [-PIPE_R - 3, PIPE_R + 2]:
                    cv.create_oval(fx - 1, py + by_off - 1, fx + 1, py + by_off + 1,
                                   fill="#3D4B56", outline="")

            # Weld seam indicators (circumferential)
            for wi in range(1, n_flanges + 2):
                wx = P_LEFT + int(PIPE_W * wi / (n_flanges + 2))
                cv.create_line(wx, py - PIPE_R + 2, wx, py + PIPE_R - 2,
                               fill="#808890", width=1, dash=(2, 6))

        # ── Flow direction arrows ─────────────────────────────────────────
        flow_val = self.get_var(f"{etapa_key}_{tank_names[0]}_vol_nat_prod").get() if etapa_key and tank_names else ""
        arrow_color = "#F4D03F" if flow_val else "#95A5A6"
        n_arrows = max(3, min(6, PIPE_W // 80))
        for ai in range(n_arrows):
            ax = P_LEFT + (ai + 1) * PIPE_W // (n_arrows + 1)
            aw = max(8, int(PIPE_R * 0.6))
            # Arrow with shadow
            cv.create_polygon(ax - aw // 2 + 1, PIPE_Y - aw // 3 + 1,
                              ax + aw // 2 + 1, PIPE_Y + 1,
                              ax - aw // 2 + 1, PIPE_Y + aw // 3 + 1,
                              fill="#80800A", outline="")
            cv.create_polygon(ax - aw // 2, PIPE_Y - aw // 3,
                              ax + aw // 2, PIPE_Y,
                              ax - aw // 2, PIPE_Y + aw // 3,
                              fill=arrow_color, outline=arrow_color)

        # ── Aboveground section: valve station ────────────────────────────
        # Riser pipe (pipe coming out of ground)
        riser_x = P_LEFT + int(PIPE_W * 0.15)
        riser_top = GROUND_Y - max(20, int(sky_h * 0.25))
        cv.create_rectangle(riser_x - 3, riser_top, riser_x + 3, GROUND_Y + 2,
                            fill=tipo_color, outline="#2C3E50", width=1)
        # Riser elbow
        cv.create_arc(riser_x - 8, riser_top - 4, riser_x + 8, riser_top + 12,
                       start=0, extent=180, style="arc", outline=tipo_color, width=4)
        # Block valve on riser
        vv_y = riser_top + max(6, int(sky_h * 0.06))
        vv_r = max(4, PIPE_R // 3)
        cv.create_polygon(riser_x - vv_r, vv_y - vv_r, riser_x + vv_r, vv_y + vv_r,
                          riser_x + vv_r, vv_y - vv_r, riser_x - vv_r, vv_y + vv_r,
                          fill="#E74C3C", outline="#C0392B", width=2)
        cv.create_line(riser_x, vv_y - vv_r, riser_x, vv_y - vv_r * 2, fill="#C0392B", width=2)
        cv.create_oval(riser_x - vv_r, vv_y - vv_r * 2 - 3, riser_x + vv_r, vv_y - vv_r * 2,
                       fill="", outline="#C0392B", width=1)

        # ── Pig launcher/receiver station ─────────────────────────────────
        pig_x = P_RIGHT - int(PIPE_W * 0.12)
        pig_top = GROUND_Y - max(18, int(sky_h * 0.22))
        pig_w = max(30, int(W * 0.08))
        pig_h = max(8, int(PIPE_R * 0.8))
        # Barrel (horizontal cylinder)
        cv.create_rectangle(pig_x, pig_top, pig_x + pig_w, pig_top + pig_h * 2,
                            fill=tipo_color, outline="#2C3E50", width=1)
        # Barrel gradient
        try:
            _r0 = int(tipo_color[1:3], 16); _g0 = int(tipo_color[3:5], 16); _b0 = int(tipo_color[5:7], 16)
        except: _r0, _g0, _b0 = 100, 100, 100
        for pgi in range(5):
            frac = pgi / 4
            bright = 0.6 + 0.8 * (1 - abs(frac - 0.35) * 2)
            _rr = min(255, int(_r0 * bright)); _gg = min(255, int(_g0 * bright)); _bb = min(255, int(_b0 * bright))
            pgc = f"#{_rr:02x}{_gg:02x}{_bb:02x}"
            pgy = pig_top + int(pig_h * 2 * pgi / 5)
            cv.create_rectangle(pig_x + 2, pgy, pig_x + pig_w - 2, pgy + pig_h * 2 // 5 + 1,
                                fill=pgc, outline="")
        cv.create_rectangle(pig_x, pig_top, pig_x + pig_w, pig_top + pig_h * 2,
                            fill="", outline="#2C3E50", width=1)
        # Closure door (end cap)
        cv.create_oval(pig_x + pig_w - 3, pig_top - 2, pig_x + pig_w + 5, pig_top + pig_h * 2 + 2,
                       fill="#4A5568", outline="#2C3E50", width=2)
        # Kicker line
        cv.create_rectangle(pig_x - 2, pig_top + pig_h, pig_x, pig_top + pig_h + 3,
                            fill="#5D6D7E", outline="")
        cv.create_line(pig_x, pig_top + pig_h + 1, pig_x - max(8, int(W * 0.02)), pig_top + pig_h + 1,
                       fill="#5D6D7E", width=2)
        # Label
        cv.create_text(pig_x + pig_w // 2, pig_top - max(4, fss),
                       text="PIG L/R", font=("Arial", max(3, fss - 2)), fill="#5D6D7E")
        # Support legs
        for sl in [pig_x + 4, pig_x + pig_w - 4]:
            cv.create_line(sl, pig_top + pig_h * 2, sl, GROUND_Y, fill="#5D6D7E", width=2)

        # ── Meter station (above ground) ──────────────────────────────────
        mtr_x = x + W // 2
        mtr_top = GROUND_Y - max(30, int(sky_h * 0.40))
        mtr_w = max(45, int(W * 0.13)); mtr_h = max(30, int(sky_h * 0.35))
        # Cabinet shadow
        cv.create_rectangle(mtr_x - mtr_w // 2 + 3, mtr_top + 3,
                            mtr_x + mtr_w // 2 + 3, mtr_top + mtr_h + 3,
                            fill="#404850", outline="")
        # Cabinet body with metallic gradient
        cab_grads = ["#D0D4D8","#C8CCD0","#C0C4C8","#B8BCC0","#B0B4B8","#A8ACB0"]
        for ci2, cc in enumerate(cab_grads):
            cy1 = mtr_top + int(mtr_h * ci2 / len(cab_grads))
            cy2 = mtr_top + int(mtr_h * (ci2 + 1) / len(cab_grads))
            cv.create_rectangle(mtr_x - mtr_w // 2, cy1, mtr_x + mtr_w // 2, cy2, fill=cc, outline="")
        cv.create_rectangle(mtr_x - mtr_w // 2, mtr_top, mtr_x + mtr_w // 2, mtr_top + mtr_h,
                            fill="", outline="#2C3E50", width=2)
        # Header bar
        cv.create_rectangle(mtr_x - mtr_w // 2, mtr_top, mtr_x + mtr_w // 2, mtr_top + max(5, mtr_h // 5),
                            fill="#2C3E50", outline="")
        cv.create_text(mtr_x, mtr_top + max(3, mtr_h // 10),
                       text="MEDIDOR", font=("Arial", max(4, fss - 1)), fill="white")
        # Digital display
        disp_bg = "#1A5276" if flow_val else "#4A5568"
        disp_y = mtr_top + mtr_h // 5 + 4
        disp_h = max(16, int(mtr_h * 0.35))
        cv.create_rectangle(mtr_x - mtr_w // 2 + 5, disp_y,
                            mtr_x + mtr_w // 2 - 5, disp_y + disp_h,
                            fill=disp_bg, outline="#1ABC9C", width=2)
        disp_val = flow_val[:8] if flow_val else "---"
        cv.create_text(mtr_x, disp_y + disp_h // 2,
                       text=disp_val, font=("Arial", max(5, fss)), fill="#1ABC9C")
        # Unit label
        unit_txt = {"OLEODUCTO": "m3", "GASODUCTO": "m3/h", "POLIDUCTO": "m3"}.get(tipo, "m3")
        cv.create_text(mtr_x, disp_y + disp_h + max(3, fss // 2),
                       text=unit_txt, font=("Arial", max(3, fss - 2)), fill="#85929E")
        # LED status lights
        for li, lc in enumerate(["#27AE60", "#F4D03F"]):
            cv.create_oval(mtr_x - mtr_w // 2 + 8 + li * 10, mtr_top + mtr_h - 10,
                           mtr_x - mtr_w // 2 + 14 + li * 10, mtr_top + mtr_h - 4,
                           fill=lc, outline="#2C3E50")
        # Connection pipe to underground
        cv.create_line(mtr_x, mtr_top + mtr_h, mtr_x, GROUND_Y + 2, fill="#5D6D7E", width=3)
        cv.create_line(mtr_x, GROUND_Y + 2, mtr_x, PIPE_Y - PIPE_R, fill="#5D6D7E", width=3)
        # Legs
        for sl in [mtr_x - mtr_w // 2 + 4, mtr_x + mtr_w // 2 - 4]:
            cv.create_line(sl, mtr_top + mtr_h, sl, GROUND_Y, fill="#4A5568", width=2)

        # ── Pressure gauges above ground ──────────────────────────────────
        for gpos in [P_LEFT + int(PIPE_W * 0.35), P_LEFT + int(PIPE_W * 0.70)]:
            # Gauge post
            g_top = GROUND_Y - max(12, int(sky_h * 0.15))
            cv.create_line(gpos, GROUND_Y, gpos, g_top, fill="#5D6D7E", width=2)
            g_r = max(6, int(sky_h * 0.06))
            cv.create_oval(gpos - g_r - 1, g_top - g_r - 1, gpos + g_r + 1, g_top + g_r + 1,
                           fill="#4A5568", outline="")
            cv.create_oval(gpos - g_r, g_top - g_r, gpos + g_r, g_top + g_r,
                           fill="white", outline="#E74C3C", width=2)
            # Scale
            cv.create_arc(gpos - g_r + 2, g_top - g_r + 2, gpos + g_r - 2, g_top + g_r - 2,
                          start=30, extent=240, style="arc", outline="#E0E0E0", width=1)
            # Needle
            cv.create_line(gpos, g_top, gpos + int(g_r * 0.6), g_top - int(g_r * 0.4),
                           fill="#C0392B", width=1)
            cv.create_oval(gpos - 1, g_top - 1, gpos + 1, g_top + 1, fill="#C0392B", outline="")

        # ── Warning marker posts ──────────────────────────────────────────
        for mp in [P_LEFT + int(PIPE_W * 0.05), P_LEFT + int(PIPE_W * 0.95)]:
            post_top = GROUND_Y - max(15, int(sky_h * 0.20))
            cv.create_rectangle(mp - 2, post_top, mp + 2, GROUND_Y, fill="#F4D03F", outline="#D4AC0D")
            cv.create_rectangle(mp - 5, post_top - 8, mp + 5, post_top,
                                fill="#F4D03F", outline="#D4AC0D", width=1)
            # Diamond hazmat sign
            cv.create_polygon(mp, post_top - 8, mp + 4, post_top - 4,
                              mp, post_top, mp - 4, post_top - 4,
                              fill=tipo_color, outline="#2C3E50")

        # ── Depth dimension annotations ────────────────────────────────────
        dim_x = x + max(10, int(W * 0.03))
        # Ground to pipe center
        cv.create_line(dim_x, GROUND_Y, dim_x, PIPE_Y, fill="#F4D03F", width=1)
        cv.create_line(dim_x - 3, GROUND_Y, dim_x + 3, GROUND_Y, fill="#F4D03F", width=1)
        cv.create_line(dim_x - 3, PIPE_Y, dim_x + 3, PIPE_Y, fill="#F4D03F", width=1)
        cv.create_text(dim_x + 6, (GROUND_Y + PIPE_Y) // 2,
                       text="Prof.", font=("Arial", max(3, fss - 2)), fill="#F4D03F", anchor="w")

        # ── Layer labels on right side ────────────────────────────────────
        lbl_x = x + W - max(30, int(W * 0.08))
        layer_lbls = [("Suelo", 0.06), ("Subsuelo", 0.21), ("Arcilla", 0.42), ("Grava", 0.65), ("Roca", 0.88)]
        for lt, lf in layer_lbls:
            ly = GROUND_Y + int(UG_H * lf)
            if ly < y + H - 4:
                cv.create_text(lbl_x, ly, text=lt, font=("Arial", max(3, fss - 2)), fill="#D5D0C8", anchor="e")

        # ── Flow direction label ──────────────────────────────────────────
        flow_dir = "-->  FLUJO"
        cv.create_text(x + W // 2, y + H - max(4, int(H * 0.02)),
                       text=flow_dir, font=FTS, fill="#5D6D7E")

    def _draw_electric(self, cv, x, y, W, H, etapa_key, tank_names):
        """Electrical metering room -- RAL 7035 grey cabinet, HV warning, CT symbol, anti-static floor."""
        import math
        if H < 60 or W < 100: return
        if tank_names is None: tank_names = self.lista_tanques

        fs  = min(10, max(5, int(H*0.036)));  fss = min(9, max(4, int(H*0.028)))
        FT  = ("Arial", fs);  FTS = ("Arial", fss)

        TITLE_H  = max(18, int(H*0.09))
        instalacion = self.get_var("car_buque").get() or "INSTALACION"

        # ── Room background (concrete wall) ───────────────────────────────
        wall_grads = ["#2D3436","#2C3335","#2A3133","#282F31","#262D2F","#242B2D"]
        for wi, wc in enumerate(wall_grads):
            wy1 = y + int(H * wi / len(wall_grads))
            wy2 = y + int(H * (wi + 1) / len(wall_grads))
            cv.create_rectangle(x, wy1, x + W, wy2, fill=wc, outline="")
        cv.create_rectangle(x, y, x + W, y + H, fill="", outline="#4A5568", width=3)

        # ── Conduit/cable tray at top ─────────────────────────────────────
        tray_h = max(6, int(H * 0.03))
        cv.create_rectangle(x + 4, y + 4, x + W - 4, y + 4 + tray_h, fill="#3D4B56", outline="#2C3E50")
        # Cables in tray
        cable_cols = ["#E74C3C","#3498DB","#2ECC71","#F4D03F","#95A5A6"]
        for ci in range(min(5, W // 20)):
            cx2 = x + 8 + ci * max(5, W // 20)
            cv.create_line(cx2, y + 5, cx2, y + 4 + tray_h - 1, fill=cable_cols[ci % 5], width=2)

        # ── Title bar with high voltage warning ───────────────────────────
        cv.create_rectangle(x + 1, y + 4 + tray_h + 2, x + W - 1, y + TITLE_H + tray_h + 2,
                            fill="#6A1B9A", outline="")
        # Lightning bolt symbols
        bolt_y = y + (TITLE_H + tray_h) // 2 + 3
        for bx in [x + max(12, int(W * 0.04)), x + W - max(12, int(W * 0.04))]:
            cv.create_polygon(bx - 3, bolt_y - 5, bx + 1, bolt_y - 1, bx - 1, bolt_y,
                              bx + 3, bolt_y + 5, bx - 1, bolt_y + 1, bx + 1, bolt_y,
                              fill="#F4D03F", outline="")
        cv.create_text(x + W // 2, bolt_y,
                       text=f"MEDICION ELECTRICA  --  {instalacion}",
                       font=FT, fill="white")

        # ── Main panel cabinet body ───────────────────────────────────────
        panel_x = x + int(W * 0.04); panel_y = y + TITLE_H + tray_h + max(8, int(H * 0.04))
        panel_w = W - int(W * 0.08); panel_h = H - TITLE_H - tray_h - max(28, int(H * 0.16))
        # Panel shadow
        cv.create_rectangle(panel_x + 3, panel_y + 3, panel_x + panel_w + 3, panel_y + panel_h + 3,
                            fill="#0A0E12", outline="")
        # Panel body: RAL 7035 light grey metallic gradient
        pan_grads = ["#C8CDD2","#C4C9CE","#C0C5CA","#BCC1C6","#B8BDC2","#B4B9BE"]
        for pi2, pc2 in enumerate(pan_grads):
            py1 = panel_y + int(panel_h * pi2 / len(pan_grads))
            py2 = panel_y + int(panel_h * (pi2 + 1) / len(pan_grads))
            cv.create_rectangle(panel_x, py1, panel_x + panel_w, py2, fill=pc2, outline="")
        cv.create_rectangle(panel_x, panel_y, panel_x + panel_w, panel_y + panel_h,
                            fill="", outline="#95A5A6", width=2)
        # Panel bevel highlight (RAL 7035 light grey)
        cv.create_line(panel_x, panel_y, panel_x + panel_w, panel_y, fill="#D0D5DA", width=1)
        cv.create_line(panel_x, panel_y, panel_x, panel_y + panel_h, fill="#A8ADB2", width=1)

        # ── Hinges on panel door ──────────────────────────────────────────
        for hy in [panel_y + int(panel_h * 0.2), panel_y + int(panel_h * 0.8)]:
            cv.create_rectangle(panel_x - 3, hy - 4, panel_x + 2, hy + 4,
                                fill="#5D6D7E", outline="#4A5568")
            cv.create_oval(panel_x - 2, hy - 1, panel_x + 1, hy + 1, fill="#808B96", outline="")

        # ── Door handle/lock ──────────────────────────────────────────────
        lock_x = panel_x + panel_w - max(8, int(panel_w * 0.03))
        lock_y = panel_y + panel_h // 2
        cv.create_rectangle(lock_x - 4, lock_y - 8, lock_x + 4, lock_y + 8,
                            fill="#7F8C8D", outline="#5D6D7E", width=1)
        cv.create_oval(lock_x - 2, lock_y - 2, lock_x + 2, lock_y + 2,
                       fill="#4A5568", outline="")

        # ── Status LEDs row ───────────────────────────────────────────────
        leds = [("#27AE60","ON"), ("#F4D03F","WARN"), ("#C0392B","ALM"), ("#3498DB","COM")]
        led_y = panel_y + max(6, int(panel_h * 0.03))
        for li, (lc, lt) in enumerate(leds):
            lx = panel_x + max(10, int(panel_w * 0.03)) + li * max(22, int(panel_w * 0.06))
            # LED housing
            cv.create_oval(lx - 1, led_y - 1, lx + max(10, int(panel_w * 0.025)) + 1,
                           led_y + max(10, int(panel_w * 0.025)) + 1,
                           fill="#1A252F", outline="#4A5568")
            led_r = max(4, int(panel_w * 0.01))
            cv.create_oval(lx + led_r // 2, led_y + led_r // 2,
                           lx + led_r * 3, led_y + led_r * 3,
                           fill=lc, outline="white", width=1)
            # LED glow effect
            cv.create_oval(lx + led_r, led_y + led_r, lx + led_r * 2, led_y + led_r * 2,
                           fill="white", outline="")
            cv.create_text(lx + led_r * 2, led_y + led_r * 3 + max(3, fss),
                           text=lt, font=("Arial", max(3, fss - 2)), fill="#BDC3C7")

        # ── High voltage warning sign ─────────────────────────────────────
        warn_x = panel_x + panel_w - max(30, int(panel_w * 0.10))
        warn_y = led_y
        warn_s = max(10, int(panel_h * 0.08))
        # Yellow triangle
        cv.create_polygon(warn_x + warn_s // 2, warn_y, warn_x, warn_y + warn_s,
                          warn_x + warn_s, warn_y + warn_s,
                          fill="#F4D03F", outline="#2C3E50", width=1)
        # Lightning bolt inside
        cv.create_polygon(warn_x + warn_s // 2 - 1, warn_y + 3,
                          warn_x + warn_s // 2 + 2, warn_y + warn_s // 2,
                          warn_x + warn_s // 2 - 1, warn_y + warn_s // 2,
                          warn_x + warn_s // 2 + 1, warn_y + warn_s - 3,
                          fill="#2C3E50", outline="")

        # ── Circuit breaker row ───────────────────────────────────────────
        cb_y = led_y + max(20, int(panel_h * 0.10))
        cb_h = max(12, int(panel_h * 0.08))
        cb_w_each = max(8, int(panel_w * 0.04))
        n_breakers = min(8, panel_w // (cb_w_each + 4))
        cb_start_x = panel_x + (panel_w - n_breakers * (cb_w_each + 3)) // 2
        for bi in range(n_breakers):
            bx = cb_start_x + bi * (cb_w_each + 3)
            # Breaker body
            cv.create_rectangle(bx, cb_y, bx + cb_w_each, cb_y + cb_h,
                                fill="#1A252F", outline="#4A5568", width=1)
            # Toggle switch (up = ON)
            toggle_h = max(4, cb_h // 3)
            cv.create_rectangle(bx + 2, cb_y + 2, bx + cb_w_each - 2, cb_y + 2 + toggle_h,
                                fill="#27AE60" if bi < n_breakers - 1 else "#E74C3C",
                                outline="#1A252F")
            # Label
            cv.create_text(bx + cb_w_each // 2, cb_y + cb_h + max(3, fss // 2),
                           text=f"{bi+1}", font=("Arial", max(3, fss - 2)), fill="#808B96")

        # ── Meters per measurement point ──────────────────────────────────
        n = max(len(tank_names), 1)
        mt_w = (panel_w - 20) // n
        mt_pad = 5
        meters_top = cb_y + cb_h + max(14, int(panel_h * 0.08))

        for i, tn in enumerate(tank_names[:n]):
            mx = panel_x + 10 + i * mt_w
            my = meters_top
            mw = mt_w - mt_pad * 2
            mh = panel_y + panel_h - meters_top - max(10, int(panel_h * 0.06))

            # Meter sub-panel with beveled edge
            cv.create_rectangle(mx + 1, my + 1, mx + mw + 1, my + mh + 1,
                                fill="#0A0E12", outline="")
            cv.create_rectangle(mx, my, mx + mw, my + mh, fill="#1A252F", outline="#5D6D7E", width=2)
            # Header with gradient
            hdr_h = max(12, int(mh * 0.12))
            cv.create_rectangle(mx, my, mx + mw, my + hdr_h, fill="#4A235A", outline="")
            cv.create_rectangle(mx, my + hdr_h - 2, mx + mw, my + hdr_h, fill="#6A1B9A", outline="")
            cv.create_text(mx + mw // 2, my + hdr_h // 2,
                           text=tn[:10], font=FTS, fill="white")

            # kWh readings
            kwh_val   = self.get_var(f"{etapa_key}_{tn}_el_ini_act").get() if etapa_key else ""
            kwh_final = self.get_var(f"{etapa_key}_{tn}_el_fin_act").get() if etapa_key else ""

            # ── Initial kWh display (LCD style) ───────────────────────────
            lcd_y = my + hdr_h + max(4, int(mh * 0.03))
            lcd_h = max(22, int(mh * 0.22))
            cv.create_text(mx + mw // 2, lcd_y - max(2, int(mh * 0.02)),
                           text="kWh INICIAL", font=("Arial", max(4, fss - 2)), fill="#85929E")
            # LCD bezel
            cv.create_rectangle(mx + 3, lcd_y - 1, mx + mw - 3, lcd_y + lcd_h + 1,
                                fill="#0A1520", outline="#1A252F")
            cv.create_rectangle(mx + 4, lcd_y, mx + mw - 4, lcd_y + lcd_h,
                                fill="#0D1B2A", outline="#1ABC9C", width=2)
            # LCD scanline effect
            for sl in range(lcd_y + 3, lcd_y + lcd_h - 2, 3):
                cv.create_line(mx + 6, sl, mx + mw - 6, sl, fill="#0A1822", width=1)
            kwh_disp = kwh_val[:10] if kwh_val else "---"
            cv.create_text(mx + mw // 2, lcd_y + lcd_h // 2, text=kwh_disp,
                           font=("Arial", max(6, min(10, mw // 8))), fill="#1ABC9C")

            # ── Final kWh display ─────────────────────────────────────────
            lcd2_y = lcd_y + lcd_h + max(6, int(mh * 0.04))
            lcd2_h = max(20, int(mh * 0.20))
            cv.create_text(mx + mw // 2, lcd2_y - max(2, int(mh * 0.02)),
                           text="kWh FINAL", font=("Arial", max(4, fss - 2)), fill="#85929E")
            cv.create_rectangle(mx + 3, lcd2_y - 1, mx + mw - 3, lcd2_y + lcd2_h + 1,
                                fill="#0A1520", outline="#1A252F")
            cv.create_rectangle(mx + 4, lcd2_y, mx + mw - 4, lcd2_y + lcd2_h,
                                fill="#0D1B2A", outline="#E74C3C", width=2)
            for sl in range(lcd2_y + 3, lcd2_y + lcd2_h - 2, 3):
                cv.create_line(mx + 6, sl, mx + mw - 6, sl, fill="#0A1218", width=1)
            kwh2_disp = kwh_final[:10] if kwh_final else "---"
            cv.create_text(mx + mw // 2, lcd2_y + lcd2_h // 2, text=kwh2_disp,
                           font=("Arial", max(6, min(10, mw // 8))), fill="#E74C3C")

            # ── Consumption bar with gradient ─────────────────────────────
            dif_y = lcd2_y + lcd2_h + max(6, int(mh * 0.04))
            dif_h = max(12, int(mh * 0.10))
            bar_w = mw - 12
            # Bar background with notches
            cv.create_rectangle(mx + 6, dif_y, mx + 6 + bar_w, dif_y + dif_h,
                                fill="#17202A", outline="#5D6D7E", width=1)
            # Notches on bar
            for ni in range(1, 5):
                nx = mx + 6 + int(bar_w * ni / 5)
                cv.create_line(nx, dif_y, nx, dif_y + dif_h, fill="#2C3E50", width=1)
            try:
                ini_f = float(kwh_val.replace(",", ".") if kwh_val else "0")
                fin_f = float(kwh_final.replace(",", ".") if kwh_final else "0")
                if fin_f > ini_f and ini_f >= 0:
                    pct = min((fin_f - ini_f) / max(ini_f, fin_f, 1), 1.0)
                    bar_filled = int(bar_w * pct)
                    bar_color = "#27AE60" if pct < 0.7 else ("#F39C12" if pct < 0.9 else "#E74C3C")
                    # Gradient fill on bar
                    cv.create_rectangle(mx + 6, dif_y, mx + 6 + bar_filled, dif_y + dif_h,
                                        fill=bar_color, outline="")
                    # Bar highlight
                    cv.create_rectangle(mx + 6, dif_y, mx + 6 + bar_filled, dif_y + max(2, dif_h // 4),
                                        fill="#FFFFFF", outline="", stipple="gray25")
                    cv.create_text(mx + mw // 2, dif_y + dif_h // 2,
                                   text=f"DkWh: {fin_f-ini_f:.0f}", font=FTS, fill="white")
            except: pass

            # ── Analog gauges (Voltmeter and Ammeter) ─────────────────────
            gauge_y = dif_y + dif_h + max(6, int(mh * 0.04))
            remaining_h = my + mh - gauge_y - 4
            for gi, (gl, gc, gv_key, gmax) in enumerate([
                ("V", "#F4D03F", "el_V", 500),
                ("A", "#E74C3C", "el_A", 500)
            ]):
                gx2 = mx + 4 + gi * (mw // 2)
                gy2 = gauge_y
                gr  = max(8, min(mw // 4 - 6, remaining_h // 2 - 4))
                gcx = gx2 + gr + 2
                gcy = gy2 + gr + 2

                # Gauge housing (dark bezel)
                cv.create_oval(gcx - gr - 3, gcy - gr - 3, gcx + gr + 3, gcy + gr + 3,
                               fill="#0A0E12", outline="#4A5568", width=1)
                # Gauge face
                cv.create_oval(gcx - gr, gcy - gr, gcx + gr, gcy + gr,
                               fill="#1A252F", outline="#5D6D7E", width=1)
                # Glass highlight
                cv.create_arc(gcx - gr + 2, gcy - gr + 2, gcx + gr - 2, gcy + gr - 2,
                              start=45, extent=90, style="chord", fill="#2A3540", outline="")
                # Scale arc
                cv.create_arc(gcx - gr + 4, gcy - gr + 4, gcx + gr - 4, gcy + gr - 4,
                              start=30, extent=240, style="arc", outline=gc, width=1)
                # Scale ticks
                for ti in range(11):
                    tick_ang = math.radians(210 - ti * 24)
                    tx1 = gcx + int((gr - 3) * math.cos(tick_ang))
                    ty1 = gcy - int((gr - 3) * math.sin(tick_ang))
                    tx2 = gcx + int((gr - max(4, gr // 4)) * math.cos(tick_ang))
                    ty2 = gcy - int((gr - max(4, gr // 4)) * math.sin(tick_ang))
                    tw = 2 if ti % 5 == 0 else 1
                    cv.create_line(tx1, ty1, tx2, ty2, fill=gc, width=tw)
                # Needle
                gval = self.get_var(f"{etapa_key}_{tn}_{gv_key}").get() if etapa_key else ""
                try:
                    gfrac = min(float(gval.replace(",", ".")) / gmax, 1.0) if gval else 0.0
                    ang = math.radians(210 - 240 * gfrac)
                    gnx = gcx + int(gr * 0.75 * math.cos(ang))
                    gny = gcy - int(gr * 0.75 * math.sin(ang))
                    cv.create_line(gcx, gcy, gnx, gny, fill=gc, width=2)
                except: pass
                # Center pivot
                cv.create_oval(gcx - 2, gcy - 2, gcx + 2, gcy + 2, fill=gc, outline="")
                # Label
                cv.create_text(gcx, gcy + gr + max(3, fss),
                               text=gl, font=FTS, fill=gc)

            # ── Conduit drops from cable tray to each meter ───────────────
            conduit_x = mx + mw // 2
            cv.create_line(conduit_x, y + 4 + tray_h, conduit_x, my, fill="#4A5568", width=2)
            # Conduit entry fitting
            cv.create_rectangle(conduit_x - 3, my - 2, conduit_x + 3, my + 2,
                                fill="#5D6D7E", outline="#4A5568")

        # ── Grounding bus bar (green-yellow stripe per IEC 60446) ─────────
        gnd_y = panel_y + panel_h + max(4, int(H * 0.02))
        gnd_h = max(8, int(H * 0.04))
        # Green-yellow alternating stripe pattern
        stripe_w = max(4, gnd_h)
        for gi in range(0, panel_w, stripe_w * 2):
            gx1 = panel_x + gi
            gx2 = min(panel_x + gi + stripe_w, panel_x + panel_w)
            cv.create_rectangle(gx1, gnd_y, gx2, gnd_y + gnd_h, fill="#2ECC71", outline="")
            gx3 = min(gx2 + stripe_w, panel_x + panel_w)
            if gx3 > gx2:
                cv.create_rectangle(gx2, gnd_y, gx3, gnd_y + gnd_h, fill="#F4D03F", outline="")
        cv.create_rectangle(panel_x, gnd_y, panel_x + panel_w, gnd_y + gnd_h,
                            fill="", outline="#27AE60", width=1)
        # Grounding connections
        for gi in range(0, panel_w, max(15, panel_w // 8)):
            gx = panel_x + gi + 6
            cv.create_oval(gx - 2, gnd_y + 1, gx + 2, gnd_y + gnd_h - 1,
                           fill="#1E8449", outline="")
        # Ground symbol
        gs_x = panel_x + panel_w // 2
        gs_y = gnd_y + gnd_h + 2
        cv.create_line(gs_x, gs_y, gs_x, gs_y + 6, fill="#2ECC71", width=2)
        for gsi, gsw in enumerate([8, 5, 2]):
            cv.create_line(gs_x - gsw, gs_y + 6 + gsi * 3, gs_x + gsw, gs_y + 6 + gsi * 3,
                           fill="#2ECC71", width=1)

        # ── Floor / cable channel ─────────────────────────────────────────
        floor_y = y + H - max(10, int(H * 0.05))
        cv.create_rectangle(x + 1, floor_y, x + W - 1, y + H - 1, fill="#1A1A1A", outline="")
        # Anti-static floor tiles pattern
        tile_w = max(12, W // 15)
        for ti in range(0, W, tile_w):
            cv.create_rectangle(x + ti + 1, floor_y + 1, x + ti + tile_w - 1, y + H - 2,
                                fill="#1E1E1E" if (ti // tile_w) % 2 == 0 else "#222222",
                                outline="#2A2A2A")

    def dibujar_tanque_tierra_tk(self, cv, x, y, W, H, flotante, etapa_key, tank_names=None):
        self._draw_vertical_tank(cv, x, y, W, H, etapa_key, tank_names, flotante=flotante)

    def dibujar_camion_tk(self, cv, x, y, W, H, etapa_key, tank_names=None):
        self._draw_liquid_truck(cv, x, y, W, H, etapa_key, tank_names)

    def dibujar_gasero_tk(self, cv, x, y, W, H, side_label, etapa_key, tank_names=None, carb_names=None):
        self._draw_moss_vessel(cv, x, y, W, H, side_label, etapa_key, tank_names, carb_names)

    def dibujar_metanero_tk(self, cv, x, y, W, H, side_label, etapa_key, tank_names=None, carb_names=None):
        self._draw_membrane_vessel(cv, x, y, W, H, side_label, etapa_key, tank_names, carb_names)

    def dibujar_camion_gas_tk(self, cv, x, y, W, H, etapa_key, tank_names=None):
        self._draw_pressure_truck(cv, x, y, W, H, etapa_key, tank_names)

    def dibujar_ducto_tk(self, cv, x, y, W, H, etapa_key, tipo="GASODUCTO", tank_names=None):
        self._draw_pipeline(cv, x, y, W, H, etapa_key, tipo, tank_names)

    def dibujar_electrico_tk(self, cv, x, y, W, H, etapa_key, tank_names=None):
        self._draw_electric(cv, x, y, W, H, etapa_key, tank_names)

    def dibujar_buque_tk(self, cv, x, y, width, height, side_label, etapa_key, tank_names=None, carb_names=None):
        """Dibujo proporcional al canvas. Sin valores absolutos: todo se escala con width/height."""
        tipo_nave = self.get_var("car_tipo_nave").get() or "BUQUE"
        if tank_names is None: tank_names = self.lista_tanques
        if carb_names is None: carb_names = self.lista_carbonera

        # Forzar aspect ratio apaisado mínimo 3:1 (buque es horizontal)
        min_ratio = 3.0
        if width / max(height, 1) < min_ratio:
            new_height = int(width / min_ratio)
            y = y + (height - new_height) // 2
            height = new_height

        # ── Bézier auxiliar ────────────────────────────────────────────────────
        def bez(p0, p1, p2, p3, n=20):
            pts = []
            for i in range(n + 1):
                t = i / n; u = 1 - t
                pts += [u**3*p0[0]+3*u**2*t*p1[0]+3*u*t**2*p2[0]+t**3*p3[0],
                        u**3*p0[1]+3*u**2*t*p1[1]+3*u*t**2*p2[1]+t**3*p3[1]]
            return pts

        # ── PROPORCIONES (todas relativas a width/height) ──────────────────────
        W = width;  H = height
        # zona de dibujo del casco dentro del rectángulo [x,y,x+W,y+H]
        # reservamos espacio arriba para título y superestructura
        TITLE_H  = max(14, int(H * 0.08))     # altura del título
        SUP_H    = max(40, int(H * 0.28))      # espacio sobre cubierta (superestructura+chimenea+mástil)
        DECK_Y   = y + TITLE_H + SUP_H         # línea de cubierta (Tk: menor Y = arriba)
        KEEL_Y   = y + H - max(6, int(H*0.04)) # quilla (Tk: mayor Y = abajo)
        HULL_H   = KEEL_Y - DECK_Y             # altura total del casco

        # ── Trim visual: leer calado popa/proa para inclinar la línea de flotación ──
        try:
            _trim_popa = self.parse_float(self.get_var(f"{etapa_key}_Calados Popa").get() or "0")
            _trim_proa = self.parse_float(self.get_var(f"{etapa_key}_Calados Proa").get() or "0")
            _trim_val  = _trim_popa - _trim_proa   # positivo = popa hundida
            _list_val  = self.parse_float(self.get_var(f"{etapa_key}_Lista").get() or "0")
        except:
            _trim_val = 0.0; _list_val = 0.0

        # Línea de flotación base: la obra viva ocupa ~35% del casco
        WL_Y_CENTER = DECK_Y + int(HULL_H * 0.65)  # waterline central
        # Ajuste de trim: max ±8% del casco en popa/proa visualmente
        _trim_px = max(-int(HULL_H*0.10), min(int(HULL_H*0.10), int(_trim_val * 0.5)))
        WL_Y_STERN = WL_Y_CENTER + _trim_px    # popa (izquierda): más baja si trim positivo
        WL_Y_BOW   = WL_Y_CENTER - _trim_px    # proa (derecha): más alta si trim positivo
        WL_Y       = WL_Y_CENTER               # waterline central para refs de tanques

        BOW_X    = x + W - max(14, int(W * 0.03))   # proa (derecha)
        STERN_X  = x + max(14, int(W * 0.03))        # popa (izquierda)
        CX       = x + W // 2

        # superestructura (escala proporcional)
        CAS_W    = max(60, int(W * 0.12))
        CAS_X    = STERN_X + max(8, int(W * 0.02))
        F1_H     = max(14, int(SUP_H * 0.30))    # nivel 1 (acomodaciones)
        F2_H     = max(11, int(SUP_H * 0.24))    # nivel 2 (puente)
        F3_H     = max(8,  int(SUP_H * 0.18))    # nivel 3 (ala)
        CHIM_H   = max(14, int(SUP_H * 0.28))    # chimenea
        CHIM_W   = max(10, int(CAS_W * 0.25))
        MAST_H   = max(20, int(SUP_H * 0.70))    # mástil de proa

        # fuentes proporcionales
        # Fuente fija (bitmap) — evita X11 RenderAddGlyphs | +25% sobre versión anterior
        _sz_tk   = min(10, max(6, int(H * 0.038)))   # tanque +25%
        _sz_pct  = min(10, max(6, int(H * 0.033)))   # porcentaje +25%
        _sz_prod = min(9,  max(5, int(H * 0.028)))   # producto +25%
        _sz_ttl  = min(9,  max(5, int(H * 0.035)))   # título +25%
        FONT_TITLE = ("Arial", _sz_ttl)
        FONT_TK    = ("Arial", _sz_tk)
        FONT_PCT   = ("Arial", _sz_pct)
        FONT_PROD  = ("Arial", _sz_prod)

        # ── Fondo neutro ──────────────────────────────────────────────────────────
        cv.create_rectangle(x, y, x+W, y+H, fill="#E8F0FE", outline="#5D6D7E", width=2)
        # ── TÍTULO ────────────────────────────────────────────────────────────
        cv.create_text(x + W//2, y + TITLE_H//2,
                       text=f"VISTA {side_label.upper()}  [{etapa_key.upper() if etapa_key else '-'}]",
                       font=FONT_TITLE, fill="#1B3A5C")

        if tipo_nave == "BARCAZA":
            cv.create_rectangle(STERN_X, DECK_Y, BOW_X, KEEL_Y,
                                fill="#2C3E50", outline="#1B2631", width=2)
            cv.create_rectangle(STERN_X, DECK_Y, BOW_X, DECK_Y + max(5, int(HULL_H*0.05)),
                                fill="#5D6D7E", outline="")
            cv.create_rectangle(STERN_X+1, WL_Y, BOW_X-1, KEEL_Y-1,
                                fill="#922B21", outline="")
            cv.create_line(STERN_X-8, WL_Y, BOW_X+8, WL_Y, fill="#2E86C1", width=2, dash=(5,3))

        else:
            # proa_offset = cómo se extiende la proa más allá de BOW_X
            proa = int(W * 0.045)

            # — Obra muerta con degradado vertical (más oscuro arriba, borda abajo) —
            cp_off = int(HULL_H * 0.12)
            bow_top = bez(
                (BOW_X,        DECK_Y),
                (BOW_X+proa,   DECK_Y),
                (BOW_X+proa,   WL_Y_BOW - cp_off),
                (BOW_X+proa//2, WL_Y_BOW)
            )
            top_poly = [STERN_X-4, DECK_Y, BOW_X, DECK_Y] + bow_top + [STERN_X-4, WL_Y_STERN]
            cv.create_polygon(top_poly, fill="#17202A", outline="")
            # Franja intermedia de la obra muerta (degradado manual)
            mid_wl = DECK_Y + int((WL_Y-DECK_Y)*0.5)
            cv.create_polygon([STERN_X-4, mid_wl, BOW_X, mid_wl] + bow_top + [STERN_X-4, WL_Y],
                              fill="#1B2631", outline="")
            # Borda (franja clara en el borde superior)
            borda_h = max(3, int(HULL_H*0.04))
            cv.create_polygon([STERN_X-4, DECK_Y, BOW_X, DECK_Y] + bez(
                (BOW_X, DECK_Y), (BOW_X+proa//2, DECK_Y), (BOW_X+proa//2, DECK_Y+borda_h), (BOW_X+proa//4, DECK_Y+borda_h)
            ) + [STERN_X-4, DECK_Y+borda_h], fill="#F0F3F4", outline="")
            # Riel de cubierta (línea de guarda)
            cv.create_line(STERN_X-4, DECK_Y+borda_h, BOW_X, DECK_Y+borda_h, fill="#808B96", width=2)
            # Línea de flotación activa (inclinada con trim)
            cv.create_line(STERN_X-4, WL_Y_STERN+1, BOW_X+proa//2, WL_Y_BOW+1,
                           fill="#F0F0F0", width=2)

            # Indicator de Trim visible si hay trim significativo
            if abs(_trim_val) > 0.1:
                trim_lbl = f"TRIM: {_trim_val:+.2f}m"
                trim_color = "#F4D03F" if abs(_trim_val) < 1.0 else "#E74C3C"
                cv.create_text(CX, WL_Y - max(5, int(HULL_H*0.08)),
                               text=trim_lbl, font=("Arial", max(5, int(H*0.028))),
                               fill=trim_color)

            # — Obra viva con degradado rojo-bordo —
            bow_bot = bez(
                (BOW_X+proa//2, WL_Y_BOW),
                (BOW_X+proa//2, KEEL_Y - int(HULL_H*0.05)),
                (BOW_X - int(W*0.04), KEEL_Y),
                (CX,             KEEL_Y + int(HULL_H*0.03))
            )
            stern_bot = bez(
                (CX,            KEEL_Y + int(HULL_H*0.03)),
                (STERN_X + int(W*0.05), KEEL_Y),
                (STERN_X,       KEEL_Y - int(HULL_H*0.02)),
                (STERN_X-4,     WL_Y_STERN)
            )
            bot_poly = [STERN_X-4, WL_Y_STERN] + bow_bot + stern_bot
            cv.create_polygon(bot_poly, fill="#922B21", outline="")
            # Franja más oscura en la quilla
            quilla_h = max(3, int(HULL_H*0.10))
            keel_poly = [STERN_X-4, WL_Y+int((KEEL_Y-WL_Y)*0.78)] + stern_bot[-4:] + bow_bot[-4:] + [BOW_X+proa//2, WL_Y+int((KEEL_Y-WL_Y)*0.78)]
            try: cv.create_polygon(keel_poly, fill="#641E16", outline="")
            except: pass
            # Línea de quilla
            cv.create_line(STERN_X+4, KEEL_Y, CX, KEEL_Y+int(HULL_H*0.035), fill="#1B2631", width=2)
            # Línea de flotación activa con olas (trim-aware)
            cv.create_line(STERN_X-10, WL_Y_STERN, BOW_X+proa//2, WL_Y_BOW,
                           fill="#5DADE2", width=2, dash=(5,3))

            # — Marca de Plimsoll (línea de carga) —
            plim_x = int(CX)
            plim_y = WL_Y_CENTER
            plim_r = max(6, int(HULL_H*0.09))
            # Círculo Plimsoll
            cv.create_oval(plim_x-plim_r, plim_y-plim_r, plim_x+plim_r, plim_y+plim_r,
                           fill="", outline="#F0F0F0", width=2)
            # Línea horizontal a través del círculo
            cv.create_line(plim_x-plim_r-8, plim_y, plim_x+plim_r+8, plim_y,
                           fill="#F0F0F0", width=2)
            # Letras de carga con líneas de nivel (TF, T, S, W, WNA)
            if plim_r > 7:
                fplim = max(4, plim_r//3)
                load_lines = [("S", -plim_r*1.8), ("T", -plim_r*3.2), ("F", -plim_r*4.6)]
                for label_pl, offset_pl in load_lines:
                    lx = plim_x - plim_r - 4
                    ly = WL_Y + int(offset_pl)
                    cv.create_line(lx-8, ly, lx+4, ly, fill="#F0F0F0", width=1)
                    if fplim >= 4:
                        cv.create_text(lx-10, ly, text=label_pl, font=("Arial", fplim),
                                       fill="#F0F0F0", anchor="e")
            # LR / Bureau Veritas letters inside Plimsoll circle
            if plim_r > 8:
                cv.create_text(plim_x, plim_y-plim_r//3, text="LR",
                               font=("Arial", max(4, plim_r//3), "bold"), fill="#F0F0F0")

            # ── MARCAS DE CALADO PROA/POPA (Draft Marks) ─────────────────
            # Estas marcas son características distintivas de los buques:
            # números pintados en el casco indicando el calado en esa sección
            _fdrft = ("Arial", max(4, int(HULL_H*0.065)), "bold")
            _fdsmall = ("Arial", max(3, int(HULL_H*0.050)))

            # Calados medidos: leer de las variables o estimar del trim
            try:
                _c_proa_val = self.parse_float(self.get_var(f"{etapa_key}_Calados Proa").get() or "0")
                _c_popa_val = self.parse_float(self.get_var(f"{etapa_key}_Calados Popa").get() or "0")
            except:
                _c_proa_val = 0.0; _c_popa_val = 0.0

            def _draw_draft_scale(cv2, dx, dy_wl, dy_keel, calado_val, anchor_side="w"):
                """Dibuja escala de calado en dx, desde keel hasta sobre WL."""
                _scale_h = dy_keel - dy_wl
                if _scale_h < 10: return
                # Rango de calado: asumir 0 en quilla → calado máximo en WL
                # Mostramos marcas cada 0.5m (aprox HULL_H/escala)
                _pix_per_m = _scale_h / max(calado_val, 4.0) if calado_val > 0 else _scale_h / 6.0
                # Línea vertical de escala
                _sx1 = dx - 3 if anchor_side == "e" else dx + 3
                cv2.create_line(dx, dy_wl - 6, dx, dy_keel + 2, fill="#D0D0D0", width=1)
                # Marcas numéricas (cada 1m)
                _num_marks = int(calado_val) + 1 if calado_val > 0 else 5
                for _mi in range(0, min(_num_marks + 2, 12)):
                    _my = int(dy_keel - _mi * _pix_per_m)
                    if _my < dy_wl - 8: break
                    if _my > dy_keel + 2: continue
                    _is_integer = True
                    # Marca corta para enteros
                    _llen = 6 if _is_integer else 3
                    _lx1 = dx - _llen if anchor_side == "e" else dx
                    _lx2 = dx if anchor_side == "e" else dx + _llen
                    cv2.create_line(_lx1, _my, _lx2, _my, fill="#D0D0D0", width=1)
                    if _mi > 0 and _fdsmall[1] >= 3:
                        _tx = dx - _llen - 2 if anchor_side == "e" else dx + _llen + 2
                        cv2.create_text(_tx, _my, text=str(_mi), font=_fdsmall,
                                        fill="#CCCCCC", anchor=anchor_side)
                # Línea de flotación actual (destacada con valor medido)
                if calado_val > 0:
                    _wl_mark_y = int(dy_keel - calado_val * _pix_per_m)
                    if dy_wl - 10 < _wl_mark_y < dy_keel:
                        # Flecha/indicador del calado medido
                        _arr_len = 10
                        _ax = dx + _arr_len if anchor_side == "e" else dx - _arr_len
                        cv2.create_line(dx - 3 if anchor_side=="e" else dx + 3,
                                        _wl_mark_y, _ax, _wl_mark_y,
                                        fill="#F4D03F", width=2)
                        cv2.create_text(_ax + (3 if anchor_side=="w" else -3),
                                        _wl_mark_y,
                                        text=f"{calado_val:.2f}m",
                                        font=("Arial", max(4, int(HULL_H*0.055)), "bold"),
                                        fill="#F4D03F",
                                        anchor="w" if anchor_side=="w" else "e")

            # Escala en PROA (derecha del dibujo)
            _bow_draft_x = BOW_X - max(6, int(W*0.015))
            _draw_draft_scale(cv, _bow_draft_x, WL_Y_BOW, KEEL_Y,
                              _c_proa_val if _c_proa_val > 0 else abs(_trim_val)+3.5, "w")

            # Escala en POPA (izquierda del dibujo)
            _stern_draft_x = STERN_X + max(6, int(W*0.015))
            _draw_draft_scale(cv, _stern_draft_x, WL_Y_STERN, KEEL_Y,
                              _c_popa_val if _c_popa_val > 0 else abs(_trim_val)+3.5, "e")

            # Label "PROA" y "POPA" sobre las escalas
            if _fdrft[1] >= 4:
                cv.create_text(_bow_draft_x, DECK_Y + int(HULL_H*0.04),
                               text="PROA", font=_fdsmall, fill="#A0A0A0", anchor="w")
                cv.create_text(_stern_draft_x, DECK_Y + int(HULL_H*0.04),
                               text="POPA", font=_fdsmall, fill="#A0A0A0", anchor="e")

            # — Hawse pipe / escobén (proa) —
            haw_x = int(BOW_X - max(8, int(W*0.025)))
            haw_y = int(DECK_Y + HULL_H*0.15)
            haw_r = max(4, int(HULL_H*0.05))
            cv.create_oval(haw_x-haw_r, haw_y-haw_r, haw_x+haw_r, haw_y+haw_r,
                           fill="#1B2631", outline="#808B96", width=2)
            # Cadena del ancla saliendo del escobén
            chain_y = haw_y + haw_r
            chain_pts = []
            import math as _math
            for ci_ch in range(10):
                cx_ch = haw_x + ci_ch*max(3, int(HULL_H*0.02))
                cy_ch = chain_y + int(_math.sin(ci_ch*0.8) * max(2, int(HULL_H*0.03))) + ci_ch*max(1, int(HULL_H*0.01))
                chain_pts.extend([cx_ch, cy_ch])
            if len(chain_pts) >= 4:
                try: cv.create_line(chain_pts, fill="#7F8C8D", width=2, smooth=True)
                except: pass
            # Ancla en el costado
            anc_x = int(BOW_X - max(6, int(W*0.03)))
            anc_y = int(DECK_Y - max(5, int(HULL_H*0.05)))
            anc_r = max(3, int(H*0.018))
            cv.create_oval(anc_x-anc_r, anc_y-anc_r, anc_x+anc_r, anc_y+anc_r,
                           fill="#7F8C8D", outline="#5D6D7E", width=1)
            cv.create_line(anc_x, anc_y, anc_x, anc_y+anc_r*2, fill="#7F8C8D", width=max(2,anc_r//2))
            cv.create_line(anc_x-anc_r, anc_y+anc_r, anc_x+anc_r, anc_y+anc_r,
                           fill="#7F8C8D", width=max(1,anc_r//3))


            # Se ubica ENCIMA de la cubierta (menor Y que DECK_Y)
            # Superestructura con pisos
            F0_H  = max(10, int(SUP_H * 0.22))
            f1_bot = DECK_Y;             f1_top = f1_bot - F1_H
            f2_bot = f1_top;             f2_top = f2_bot - F2_H
            f3_bot = f2_top;             f3_top = f3_bot - F3_H
            chim_bot = f3_top;           chim_top = chim_bot - CHIM_H
            chim_x = CAS_X + max(3, CHIM_W//3)

            # Nivel 0 — plataforma base (más ancha)
            cas_w0 = int(CAS_W * 1.10)
            cas_x0 = CAS_X - (cas_w0 - CAS_W)//2
            cv.create_rectangle(cas_x0+2, f1_bot-F0_H+2, cas_x0+cas_w0+2, f1_bot+2, fill="#8D99A4", outline="")
            cv.create_rectangle(cas_x0, f1_bot-F0_H, cas_x0+cas_w0, f1_bot, fill="#D0D3D4", outline="#ABB2B9", width=1)

            # Nivel 1 — acomodaciones
            cv.create_rectangle(CAS_X+2, f1_top+2, CAS_X+CAS_W+2, f1_bot+2, fill="#7D8C93", outline="")
            cv.create_rectangle(CAS_X, f1_top, CAS_X+CAS_W, f1_bot, fill="#E8EAEB", outline="#ABB2B9", width=1)
            # (ventanas acomodaciones removidas)

            # Nivel 2 — puente de mando (más estrecho)
            br_indent = max(2, CAS_W//10)
            cv.create_rectangle(CAS_X+br_indent+2, f2_top+2, CAS_X+CAS_W-br_indent+2, f2_bot+2, fill="#7D8C93", outline="")
            cv.create_rectangle(CAS_X+br_indent, f2_top, CAS_X+CAS_W-br_indent, f2_bot, fill="#E0E3E5", outline="#ABB2B9", width=1)
            # (ventana panorámica del puente removida)
            # Aletas del puente
            wing_ext = max(8, int(CAS_W*0.25))
            cv.create_rectangle(cas_x0, f2_top, CAS_X+br_indent, f2_bot, fill="#D0D3D4", outline="#95A5A6", width=1)
            cv.create_rectangle(CAS_X+CAS_W-br_indent, f2_top, CAS_X+CAS_W+wing_ext//2, f2_bot, fill="#D0D3D4", outline="#95A5A6", width=1)

            # Nivel 3 — techo con pasamanos
            cv.create_rectangle(CAS_X+br_indent//2, f3_top, CAS_X+CAS_W-br_indent//2, f3_bot, fill="#BDC3C7", outline="#95A5A6", width=1)
            rng_step = max(4, CAS_W//10)
            for pr_x in range(CAS_X+2, CAS_X+CAS_W-2, rng_step):
                cv.create_line(pr_x, f3_top-4, pr_x, f3_top, fill="#7F8C8D", width=1)
            cv.create_line(CAS_X+2, f3_top-4, CAS_X+CAS_W-2, f3_top-4, fill="#7F8C8D", width=1)

            # Radar/antena
            rad_cx = CAS_X + CAS_W//2
            rad_cy = f3_top - max(5, int(SUP_H*0.12))
            rad_r  = max(4, int(CAS_W*0.08))
            cv.create_line(rad_cx, f3_top, rad_cx, rad_cy, fill="#95A5A6", width=2)
            cv.create_arc(rad_cx-rad_r, rad_cy-rad_r, rad_cx+rad_r, rad_cy+rad_r,
                          start=0, extent=180, style="arc", outline="#7F8C8D", width=2)
            cv.create_line(rad_cx-rad_r, rad_cy, rad_cx+rad_r, rad_cy, fill="#95A5A6", width=1)

            # Chimenea
            cv.create_rectangle(chim_x+3, chim_top+4, chim_x+CHIM_W+3, chim_bot+3, fill="#641E16", outline="")
            cv.create_rectangle(chim_x, chim_top, chim_x+CHIM_W, chim_bot, fill="#B03A2E", outline="#7B241C", width=2)
            cv.create_rectangle(chim_x-2, chim_top, chim_x+CHIM_W+2, chim_top+max(3,CHIM_H//8),
                                fill="#808B96", outline="#5D6D7E", width=1)
            stripe_h = max(2, CHIM_H//5)
            cv.create_rectangle(chim_x+1, chim_top+stripe_h, chim_x+CHIM_W-1, chim_top+stripe_h*2,
                                fill="#212F3D", outline="")
            cv.create_rectangle(chim_x+1, chim_top+stripe_h*2+1, chim_x+CHIM_W-1, chim_top+stripe_h*3+1,
                                fill="#F4D03F", outline="")
            for sm_i in range(4):
                sm_r  = max(3, int(CHIM_H * (0.18 + sm_i*0.10)))
                sm_ox = int(sm_i * max(1, CHIM_W*0.10))
                sm_y  = chim_top - sm_i * max(3, CHIM_H//6) - sm_r
                smoke_shades = ["#95A5A6","#AAB7B8","#BDC3C7","#D5D8DC"]
                cv.create_oval(chim_x+CHIM_W//2-sm_r+sm_ox, sm_y,
                               chim_x+CHIM_W//2+sm_r+sm_ox, sm_y+sm_r*2,
                               fill=smoke_shades[sm_i], outline="")

                        # Mástil de proa con obenques (stays)
            mast_x = BOW_X - max(16, int(W*0.04))
            cv.create_line(mast_x, DECK_Y, mast_x, DECK_Y - MAST_H, fill="#626567", width=3)
            # Obenques
            stay_bot_1 = int(mast_x - MAST_H*0.35)
            stay_bot_2 = int(mast_x + MAST_H*0.25)
            cv.create_line(stay_bot_1, DECK_Y, mast_x, DECK_Y-int(MAST_H*0.8), fill="#7F8C8D", width=1, dash=(3,3))
            cv.create_line(stay_bot_2, DECK_Y, mast_x, DECK_Y-int(MAST_H*0.8), fill="#7F8C8D", width=1, dash=(3,3))
            # Verga horizontal
            cv.create_line(mast_x - max(7,MAST_H//4), DECK_Y-int(MAST_H*0.72),
                          mast_x + max(7,MAST_H//4), DECK_Y-int(MAST_H*0.72), fill="#626567", width=2)
            # Luces de navegación (tricolor: verde, rojo)
            cv.create_oval(mast_x-3, DECK_Y-int(MAST_H*0.72)-5, mast_x+3, DECK_Y-int(MAST_H*0.72)+5,
                          fill="#2ECC71", outline="")  # verde estribor
            cv.create_oval(mast_x-max(7,MAST_H//4)-5, DECK_Y-int(MAST_H*0.72)-3,
                           mast_x-max(7,MAST_H//4)+5, DECK_Y-int(MAST_H*0.72)+3,
                           fill="#E74C3C", outline="")  # rojo babor
            # Luz blanca en tope
            r_luz = max(3, MAST_H//8)
            cv.create_oval(mast_x-r_luz, DECK_Y-MAST_H-r_luz, mast_x+r_luz, DECK_Y-MAST_H+r_luz,
                          fill="#F8F9FA", outline="#BDC3C7")
            # Bandera en la cima (argentina)
            flag_w = max(10, MAST_H//3); flag_h = max(7, MAST_H//5)
            cv.create_rectangle(mast_x, DECK_Y-MAST_H,
                                mast_x+flag_w, DECK_Y-MAST_H+flag_h,
                                fill="#74B9FF", outline="#2980B9", width=1)
            cv.create_rectangle(mast_x, DECK_Y-MAST_H+flag_h//3,
                                mast_x+flag_w, DECK_Y-MAST_H+flag_h*2//3,
                                fill="#FFEAA7", outline="")
            cv.create_rectangle(mast_x, DECK_Y-MAST_H+flag_h*2//3,
                                mast_x+flag_w, DECK_Y-MAST_H+flag_h,
                                fill="#74B9FF", outline="")


            # ── Ojos de buey (portholes) ──────────────────────────────────
            n_ph = max(3, min(8, int((BOW_X - CAS_X - CAS_W - 30) // max(14, int(W*0.025)))))
            ph_y = WL_Y - int(HULL_H*0.28)
            ph_r = max(3, int(HULL_H*0.055))
            ph_step = (BOW_X - CAS_X - CAS_W - 20) // max(n_ph, 1)
            for phi in range(n_ph):
                ph_x = CAS_X + CAS_W + 10 + phi*ph_step
                cv.create_oval(ph_x-ph_r, ph_y-ph_r, ph_x+ph_r, ph_y+ph_r,
                               fill="#AED6F1", outline="#1B2631", width=2)
                cv.create_oval(ph_x-ph_r+2, ph_y-ph_r+2, ph_x, ph_y,
                               fill="white", outline="")  # reflejo

            # ── Nombre del buque en el casco ───────────────────────────────
            buq_txt = self.get_var("car_buque").get()[:18] if self.get_var("car_buque").get() else ""
            if buq_txt and tipo_nave != "BARCAZA":
                mid_hull_x = (CAS_X + CAS_W + BOW_X) // 2
                cv.create_text(mid_hull_x, ph_y + int(HULL_H*0.22),
                               text=buq_txt, font=("Arial", max(4, int(HULL_H*0.09))),
                               fill="#F0F0F0")

            # ── Grúa de cubierta (solo si el buque no es metanero/gasero) ──
            if tipo_nave in ("BUQUE",) and int(W*0.08) > 20:
                gc_x = int(CAS_X + CAS_W + (BOW_X - CAS_X - CAS_W)*0.55)
                gc_base_y = DECK_Y
                gc_h = int(SUP_H * 0.55)
                cv.create_rectangle(gc_x-4, gc_base_y-gc_h//3, gc_x+4, gc_base_y,
                                    fill="#5D6D7E", outline="#4A5568", width=1)
                # Pluma de la grúa
                cv.create_line(gc_x, gc_base_y-gc_h//3, gc_x+int(W*0.06), gc_base_y-gc_h,
                               fill="#4A5568", width=3)
                # Cable con gancho
                cable_x = gc_x+int(W*0.04); cable_top = gc_base_y-int(gc_h*0.75)
                cv.create_line(cable_x, cable_top, cable_x, cable_top+int(gc_h*0.35),
                               fill="#7F8C8D", width=1)
                cv.create_oval(cable_x-3, cable_top+int(gc_h*0.35)-3,
                               cable_x+3, cable_top+int(gc_h*0.35)+3,
                               fill="#E74C3C", outline="#C0392B")

            # ── Escotillas de carga (cargo hatches) en cubierta ──────────
            hatch_zone_start = CAS_X + CAS_W + max(8, int(W*0.015))
            hatch_zone_end   = BOW_X - max(20, int(W*0.04))
            hatch_zone_w     = hatch_zone_end - hatch_zone_start
            n_hatches = max(2, min(6, hatch_zone_w // max(20, int(W*0.07))))
            hatch_w   = hatch_zone_w // n_hatches
            hatch_h   = max(4, int(HULL_H*0.10))
            hatch_top = DECK_Y - hatch_h
            for hi in range(n_hatches):
                hx  = hatch_zone_start + hi*hatch_w + max(2, hatch_w//8)
                hw2 = hatch_w - max(4, hatch_w//4)
                # Tapa de la escotilla
                cv.create_rectangle(hx, hatch_top, hx+hw2, DECK_Y,
                                    fill="#2E4053", outline="#1A252F", width=1)
                # Panel central de la escotilla
                cv.create_rectangle(hx+2, hatch_top+2, hx+hw2-2, DECK_Y-1,
                                    fill="#2C3E50", outline="")
                # Resaltado superior (brillo metálico)
                cv.create_rectangle(hx+1, hatch_top, hx+hw2-1, hatch_top+2,
                                    fill="#5D6D7E", outline="")
                # Pestillo central
                pst_x = hx + hw2//2
                cv.create_rectangle(pst_x-2, hatch_top+hatch_h//3, pst_x+2, hatch_top+2*hatch_h//3,
                                    fill="#E74C3C", outline="")

            # ── Bollards (bitas de amarre) en cubierta ────────────────────
            bollard_positions = [int(STERN_X + (BOW_X-STERN_X)*f) for f in [0.08, 0.18, 0.85, 0.94]]
            boll_h = max(3, int(HULL_H*0.06))
            for bpx in bollard_positions:
                cv.create_rectangle(bpx-3, DECK_Y-boll_h, bpx+3, DECK_Y,
                                    fill="#808B96", outline="#5D6D7E", width=1)
                # Cabeza de la bita (más ancha)
                cv.create_rectangle(bpx-5, DECK_Y-boll_h, bpx+5, DECK_Y-boll_h+3,
                                    fill="#7F8C8D", outline="")

            # ── Timón y hélice en la popa ─────────────────────────────────
            rud_x = STERN_X - max(4, int(W*0.008))
            # Hélice (círculo con aspas)
            prop_cx = rud_x - max(5, int(W*0.012))
            prop_cy = WL_Y + int(HULL_H*0.55)
            prop_r  = max(5, int(HULL_H*0.14))
            # Aspas de la hélice
            for ang in [0, 120, 240]:
                pa_x = prop_cx + int(prop_r * math.cos(math.radians(ang)))
                pa_y = prop_cy + int(prop_r * math.sin(math.radians(ang)))
                cv.create_oval(pa_x-max(3,prop_r//4), pa_y-max(3,prop_r//4),
                               pa_x+max(3,prop_r//4), pa_y+max(3,prop_r//4),
                               fill="#5D6D7E", outline="")
            cv.create_oval(prop_cx-2, prop_cy-2, prop_cx+2, prop_cy+2,
                           fill="#95A5A6", outline="")
            # Bocina / eje de la hélice
            cv.create_line(prop_cx, prop_cy, rud_x+3, prop_cy, fill="#4A5568", width=3)
            # Timón
            rud_top = WL_Y + int(HULL_H*0.20)
            rud_bot = WL_Y + int(HULL_H*0.75)
            rud_w   = max(3, int(W*0.008))
            rud_h   = rud_bot - rud_top
            cv.create_polygon(rud_x, rud_top, rud_x+rud_w, rud_top+max(2,rud_h)//5,
                              rud_x+rud_w, rud_top+rud_h*4//5, rud_x, rud_bot,
                              fill="#4A5568", outline="#2C3E50", width=1)

        # ══════════ TANQUES ══════════════════════════════════════════════════
        target_side = side_label.upper()
        tanks_to_draw = [t for t in tank_names if target_side in t.upper()]
        if tanks_to_draw:
            # Zona: entre cubierta y línea de flotación
            t_top = DECK_Y + 2
            t_bot = WL_Y - 2
            t_h   = t_bot - t_top
            if t_h < 5: t_h = 5

            # Zona horizontal: entre superestructura y mástil
            sup_end = CAS_X + CAS_W + max(4, int(W*0.01))
            mast_x2 = BOW_X - max(16, int(W*0.04))
            t_start = sup_end
            t_end   = mast_x2 - max(4, int(W*0.01))
            total_tw = t_end - t_start
            if total_tw < 20: t_start = STERN_X + 4; total_tw = BOW_X - STERN_X - 8

            n_t = len(tanks_to_draw)
            t_w = total_tw / n_t
            gap = max(1.5, t_w * 0.04)

            PRODUCT_COLORS = ["#C0392B","#E67E22","#27AE60","#D4AC0D","#784212","#2C3E50","#7D3C98","#C2185B"]
            cur_tx = t_start
            for t_nm in tanks_to_draw:
                vliq = self.parse_float(self.get_var(f"{etapa_key}_{t_nm}_s_corr").get()) if etapa_key else 0
                vref = self.parse_float(self.get_var(f"{etapa_key}_{t_nm}_alt_ref").get()) if etapa_key else 0
                vwat = self.parse_float(self.get_var(f"{etapa_key}_{t_nm}_agua_s_real").get()) if etapa_key else 0
                vlit = self.get_var(f"{etapa_key}_{t_nm}_vol_nat_prod").get() if etapa_key else ""
                pnm  = self.get_var(f"{etapa_key}_{t_nm}_prod_name").get() if etapa_key else ""
                ref_h = vref if vref > 0 else 10000.0
                alt   = max(0.0, vref - vliq)
                pct_l = min(alt / ref_h, 1.0)
                pct_w = min(vwat / ref_h, 1.0) if vwat > 0 else 0.0
                px_f  = t_h * pct_l
                px_w  = t_h * pct_w

                tx = cur_tx + gap/2;  tw = t_w - gap
                # Fondo acero (con gradiente lateral)
                cv.create_rectangle(tx, t_top, tx+tw, t_bot, fill="#3D4B56", outline="")
                # Franjas de sombreado lateral (efecto 3D)
                sh_tk = max(2, tw//8)
                cv.create_rectangle(tx, t_top, tx+sh_tk, t_bot, fill="#2C3E50", outline="")
                cv.create_rectangle(tx+tw-sh_tk, t_top, tx+tw, t_bot, fill="#2A3742", outline="")
                cv.create_rectangle(tx, t_top, tx+tw, t_bot, fill="", outline="#2C3E50", width=1)
                # Agua (desde el fondo)
                if px_w > 0:
                    cv.create_rectangle(tx+1, t_bot-px_w, tx+tw-1, t_bot, fill="#5DADE2", outline="")
                # Producto — SIN stipple
                px_p = px_f - px_w
                ci_col = 0
                if px_p > 0:
                    dv = self.parse_float(self.get_var(f"{etapa_key}_{t_nm}_dens_lab").get()) if etapa_key else 0
                    ci_col = abs(int(round(dv,3)*1000)) % len(PRODUCT_COLORS) if dv else 0
                    cv.create_rectangle(tx+1, t_bot-px_f, tx+tw-1, t_bot-px_w,
                                        fill=PRODUCT_COLORS[ci_col], outline="")
                # Tapa
                cv.create_rectangle(tx, t_top, tx+tw, t_top+3, fill="#7F8C8D", outline="")
                # Textos — color legible según fondo del producto
                short = t_nm.replace("BABOR","B").replace("ESTRIBOR","E").strip()
                cyt_t = (t_top + t_bot) / 2
                # Calcular luminancia del color de producto para elegir letra legible
                _pc = PRODUCT_COLORS[ci_col] if px_p > 0 else "#3D4B56"
                try:
                    _r,_g,_b = int(_pc[1:3],16),int(_pc[3:5],16),int(_pc[5:7],16)
                    _lum = 0.299*_r + 0.587*_g + 0.114*_b
                    _txt_col = "#000000" if _lum > 140 else "white"
                    _pnm_col = "#000000" if _lum > 140 else "#E8F8F5"
                except: _txt_col = "white"; _pnm_col = "#E8F8F5"
                # Distribuir textos centrados evitando el borde inferior del tanque
                # 4 líneas: nombre, %, producto, litros — espaciado uniforme en zona segura
                _lines = [short[:14]]         # siempre
                _lines.append(f"{pct_l*100:.0f}%")
                if pnm:  _lines.append(pnm[:14])
                if vlit: _lines.append(f"{vlit} L")
                _n = len(_lines)
                # zona de texto: desde 15% desde arriba hasta 85% (evita tapa y línea de agua)
                _y_top  = t_top + t_h * 0.15
                _y_bot  = t_top + t_h * 0.82
                _step   = (_y_bot - _y_top) / max(_n - 1, 1) if _n > 1 else 0
                _fonts  = [FONT_TK, FONT_PCT] + [FONT_PROD] * max(0, _n - 2)
                _colors = [_txt_col, _txt_col] + [_pnm_col] * max(0, _n - 2)
                for _li, (_lt, _lf, _lc) in enumerate(zip(_lines, _fonts, _colors)):
                    _ly = _y_top + _li * _step if _n > 1 else (t_top + t_bot) / 2
                    cv.create_text(tx+tw/2, _ly, text=_lt, font=_lf, fill=_lc)
                cur_tx += t_w

        # ══════════ CARBONERAS ════════════════════════════════════════════════
        carbs = [c for c in carb_names
                 if target_side in c.upper() or ("BABOR" not in c.upper() and "ESTRIBOR" not in c.upper())]
        if carbs:
            czx = CAS_X + 2;  czw = CAS_W - 4
            cih = max(14, int((WL_Y - DECK_Y - 6) / max(len(carbs), 1)))
            for ci2, c_nm in enumerate(carbs):
                cyb = WL_Y - 2 - ci2*(cih+2)
                cyt2 = cyb - cih
                pc2 = 0.0; vc = ""
                if etapa_key:
                    sc = self.parse_float(self.get_var(f"{etapa_key}_{c_nm}_s_corr").get())
                    rc = self.parse_float(self.get_var(f"{etapa_key}_{c_nm}_alt_ref").get())
                    vc = self.get_var(f"{etapa_key}_{c_nm}_vol_nat_prod").get()
                    rh2 = rc if rc > 0 else 10000.0
                    pc2 = min(max(0.0, rh2-sc)/rh2, 1.0)
                px_cc = cih * pc2
                cv.create_rectangle(czx, cyt2, czx+czw, cyb, fill="#FEF9E7", outline="#D4AC0D", width=2)
                if px_cc > 0:
                    cv.create_rectangle(czx+1, cyb-px_cc, czx+czw-1, cyb-1, fill="#F0B429", outline="")
                ccy = (cyt2+cyb)/2
                sc2 = c_nm.replace("BABOR","B").replace("ESTRIBOR","E").strip()
                cv.create_text(czx+czw/2, ccy-3, text=sc2[:12], font=FONT_PROD, fill="#6E4B00")
                parts = ([vc] if vc else [])+[f"{pc2*100:.0f}%"]
                cv.create_text(czx+czw/2, ccy+5, text=" | ".join(parts), font=("Arial", max(4, FONT_PROD[1]-1)), fill="#6E4B00")

