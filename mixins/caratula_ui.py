"""Carátula: datos generales, documentos (DDT), funcionarios y gestores de DB.

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


class CaratulaUIMixin:
    def _init_tanks_for_tipo(self, tipo_medio):
        """Inicializa lista de tanques apropiada según tipo_medio."""
        tm = tipo_medio
        self.lista_tanques = []
        self.lista_carbonera = []
        if tm in ("BUQUE", "BARCAZA"):
            for i in range(1, 9):
                self.lista_tanques.append(f"TK {i} BABOR")
                self.lista_tanques.append(f"TK {i} ESTRIBOR")
            self.lista_tanques += ["SLOP BABOR", "SLOP ESTRIBOR"]
            self.lista_carbonera = ["CARBONERA 1"]
        elif tm in ("BUQUE GASERO/GLP",):
            # Buque gasero tipo MOSS o similar: 4 tanques esféricos/prismáticos
            for i in range(1, 5):
                self.lista_tanques.append(f"TK {i}")
            self.lista_carbonera = ["CARBONERA 1"]
        elif tm in ("BUQUE QUIMIQUERO",):
            for i in range(1, 7):
                self.lista_tanques.append(f"TK {i} BABOR")
                self.lista_tanques.append(f"TK {i} ESTRIBOR")
            self.lista_carbonera = ["CARBONERA 1"]
        elif tm in ("BUQUE METANERO/GNL",):
            for i in range(1, 5):
                self.lista_tanques.append(f"TANQUE {i}")
            self.lista_carbonera = ["CARBONERA 1"]
        elif tm in ("TANQUE FIJO", "TANQUE FLOTANTE"):
            self.lista_tanques.append("TANQUE 1")
        elif tm == "ESFERA DE GAS":
            self.lista_tanques.append("ESFERA 1")
        elif "CAMION" in tm:
            n_comps = 1 if "GAS" in tm else 6
            for i in range(1, n_comps + 1):
                self.lista_tanques.append(f"COMPARTIMENTO {i}")
        elif tm == "DRAFT SURVEY":
            for i in range(1, 9):
                self.lista_tanques.append(f"TK {i} BABOR")
                self.lista_tanques.append(f"TK {i} ESTRIBOR")
            self.lista_tanques += ["SLOP BABOR", "SLOP ESTRIBOR"]
            self.lista_carbonera = ["CARBONERA 1"]
        elif self.es_ducto():
            self.lista_tanques = ["TRAMO 1"]
        elif tm == "MEDICION ELECTRICA":
            self.lista_tanques = ["MEDIDOR 1"]
        else:
            for i in range(1, 5): self.lista_tanques.append(f"TK {i}")

    def wizard_nueva_medicion(self):
        """Diálogo de inicio: pregunta tipo de medio y operación antes de empezar."""
        wizard = tk.Toplevel(self.root)
        wizard.title("Nueva Medición — Configuración Inicial")
        wizard.grab_set()
        wizard.transient(self.root)
        wizard.resizable(True, True)
        wizard.update_idletasks()
        sw, sh = wizard.winfo_screenwidth(), wizard.winfo_screenheight()
        w_dlg = min(720, sw - 40)
        h_dlg = min(640, sh - 80)
        wizard.geometry(f"{w_dlg}x{h_dlg}+{(sw-w_dlg)//2}+{(sh-h_dlg)//2}")
        wizard.minsize(560, 480)

        # ── Header (fijo arriba) ──────────────────────────────────────────────
        fh = tk.Frame(wizard, bg="#1B3A5C")
        fh.pack(fill="x", side="top")
        tk.Label(fh, text="NUEVA MEDICIÓN", bg="#1B3A5C", fg="white",
                 font=("Arial", 13, "bold")).pack(pady=10)
        tk.Label(fh, text="Seleccioná el tipo de medición y la operación",
                 bg="#1B3A5C", fg="#AED6F1", font=("Arial", 9)).pack(pady=(0,8))

        # ── Footer con botones (fijo abajo — DEBE IR ANTES del área scrollable) ──
        fbot = tk.Frame(wizard, bg="#1B3A5C")
        fbot.pack(fill="x", side="bottom")

        resultado = {"ok": False}
        v_tipo = tk.StringVar(value="BUQUE")
        v_op   = tk.StringVar(value="importacion")

        def _confirmar():
            resultado["ok"] = True
            resultado["tipo_medio"] = v_tipo.get()
            resultado["operacion"]  = v_op.get()
            wizard.destroy()

        tk.Button(fbot, text="  COMENZAR MEDICION  >>", bg="#27AE60", fg="white",
                  font=("Arial", 10, "bold"), command=_confirmar,
                  cursor="hand2").pack(side="right", padx=16, pady=10, ipadx=8, ipady=4)
        tk.Button(fbot, text="Cancelar", bg="#5D6D7E", fg="white",
                  font=("Arial", 9), command=wizard.destroy
                  ).pack(side="right", padx=4, pady=10)

        # ── Área scrollable central ───────────────────────────────────────────
        cv_scroll = tk.Canvas(wizard, bg="#F8F9FA", highlightthickness=0)
        vsb = ttk.Scrollbar(wizard, orient="vertical", command=cv_scroll.yview)
        cv_scroll.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        cv_scroll.pack(side="left", fill="both", expand=True)

        fmain = tk.Frame(cv_scroll, bg="#F8F9FA")
        cv_win = cv_scroll.create_window((0, 0), window=fmain, anchor="nw")

        def _on_frame_cfg(e):
            cv_scroll.configure(scrollregion=cv_scroll.bbox("all"))
        def _on_canvas_cfg(e):
            cv_scroll.itemconfig(cv_win, width=e.width)
        fmain.bind("<Configure>", _on_frame_cfg)
        cv_scroll.bind("<Configure>", _on_canvas_cfg)
        # Scroll con rueda del mouse
        def _scroll(e):
            cv_scroll.yview_scroll(int(-1*(e.delta/120)) if e.delta else (1 if e.num==5 else -1), "units")
        cv_scroll.bind("<MouseWheel>", _scroll)
        cv_scroll.bind("<Button-4>", _scroll)
        cv_scroll.bind("<Button-5>", _scroll)

        # ── Contenido: tipos de medio ─────────────────────────────────────────
        tk.Label(fmain, text="QUE VAS A MEDIR?", font=("Arial", 10, "bold"),
                 bg="#F8F9FA", fg="#1B3A5C").pack(anchor="w", padx=20, pady=(14,4))

        CATEGORIAS = [
            ("MARITIMO / FLUVIAL",   "#1B3A5C", ["BUQUE", "BARCAZA", "BUQUE GASERO/GLP", "BUQUE QUIMIQUERO", "BUQUE METANERO/GNL", "DRAFT SURVEY"]),
            ("TIERRA / PLANTA",      "#1D6A39", ["TANQUE FIJO", "TANQUE FLOTANTE", "ESFERA DE GAS"]),
            ("TRANSPORTE TERRESTRE", "#784212", ["CAMION CISTERNA", "CAMION GAS/GLP"]),
            ("DUCTOS / CANERIAS",    "#5D4037", ["OLEODUCTO", "POLIDUCTO", "GASODUCTO"]),
            ("ENERGIA ELECTRICA",    "#6A1B9A", ["MEDICION ELECTRICA"]),
        ]
        ICONS = {
            "BUQUE": "[B]", "BARCAZA": "[Ba]", "BUQUE GASERO/GLP": "[G]",
            "BUQUE QUIMIQUERO": "[Q]", "BUQUE METANERO/GNL": "[M]",
            "TANQUE FIJO": "[TF]", "TANQUE FLOTANTE": "[TFl]", "ESFERA DE GAS": "[E]",
            "CAMION CISTERNA": "[CC]", "CAMION GAS/GLP": "[CG]",
            "OLEODUCTO": "[O]", "POLIDUCTO": "[P]", "GASODUCTO": "[GD]",
            "MEDICION ELECTRICA": "[kWh]", "DRAFT SURVEY": "[DS]",
        }

        # Guardar todos los radiobuttons para poder resaltarlos entre categorías
        all_rbs = []

        def _select(rb_clicked, val, all_rbs_ref):
            v_tipo.set(val)
            for rb_item in all_rbs_ref:
                rb_item.config(relief="flat", bg="#F8F9FA")
            rb_clicked.config(relief="raised", bg="#D6EAF8")

        f_tipos = tk.Frame(fmain, bg="#F8F9FA")
        f_tipos.pack(fill="x", padx=16, pady=2)

        for cat_name, cat_color, cat_tipos in CATEGORIAS:
            fc = tk.LabelFrame(f_tipos, text=f"  {cat_name}  ", bg="#F8F9FA",
                               font=("Arial", 8, "bold"), fg=cat_color, relief="groove", bd=2)
            fc.pack(fill="x", padx=4, pady=3)
            fr = tk.Frame(fc, bg="#F8F9FA")
            fr.pack(fill="x", padx=6, pady=5)
            for t in cat_tipos:
                ico = ICONS.get(t, "[•]")
                rb = tk.Radiobutton(fr, text=f"{ico}  {t}", variable=v_tipo, value=t,
                                    bg="#F8F9FA", font=("Arial", 9),
                                    activebackground="#E8F0FE", selectcolor="#D6EAF8",
                                    indicatoron=0, relief="flat", padx=8, pady=5,
                                    cursor="hand2")
                rb.pack(side="left", padx=3, pady=2)
                all_rbs.append(rb)
                rb.config(command=lambda r=rb, val=t: _select(r, val, all_rbs))

        # Resaltar el default
        if all_rbs:
            all_rbs[0].config(relief="raised", bg="#D6EAF8")

        # ── Tipo de operación ─────────────────────────────────────────────────
        tk.Frame(fmain, bg="#BDC3C7", height=1).pack(fill="x", padx=16, pady=8)
        tk.Label(fmain, text="TIPO DE OPERACION", font=("Arial", 10, "bold"),
                 bg="#F8F9FA", fg="#1B3A5C").pack(anchor="w", padx=20, pady=(4,4))

        f_ops = tk.Frame(fmain, bg="#F8F9FA")
        f_ops.pack(fill="x", padx=20, pady=4)
        ops = [
            ("importacion",     "[+] IMPORTACION  (Art. 954 C.A.)"),
            ("exportacion",     "[-] EXPORTACION  (Art. 959 C.A.)"),
            ("remo_descarga",   "[R] REMO / CABOTAJE - Descarga"),
            ("trafico_interno", "[I] TRAFICO INTERNO / Control Planta"),
        ]
        for val, txt in ops:
            tk.Radiobutton(f_ops, text=txt, variable=v_op, value=val,
                           bg="#F8F9FA", font=("Arial", 9),
                           activebackground="#E8F5E9").pack(anchor="w", padx=10, pady=3)

        tk.Frame(fmain, bg="#F8F9FA", height=12).pack()  # espacio al pie

        wizard.wait_window()
        return resultado

    def nueva_medicion(self):
        if not messagebox.askyesno("Nueva Medición", "¿Está seguro? Se perderán todos los datos no guardados."):
            return
        # Show wizard
        resultado = self.wizard_nueva_medicion()
        if not resultado["ok"]: return

        tipo_medio  = resultado["tipo_medio"]
        operacion   = resultado["operacion"]

        for d in self.ddt_data[:]: d["main_frame"].destroy()
        self.ddt_data = []
        self.ddt_counter = 0
        keys_to_clear = list(self.vars.keys())
        for key in keys_to_clear: self.vars[key].set("")
        self.vars.clear()
        self._archivo_tipo_medio = tipo_medio   # tipo original del wizard
        self._archivo_bloqueado  = True          # bloquear categoría desde el inicio

        # Init tanks based on tipo
        self._init_tanks_for_tipo(tipo_medio)
        self.funcionarios_data = []
        self.func_counter = 0

        for w in self.tab_caratula.winfo_children(): w.destroy()
        self.combos_ddt = []
        self.construir_caratula()

        # Pre-set tipo_medio and operacion
        self.get_var("car_tipo_medio").set(tipo_medio)
        self.get_var("car_tipo_nave").set(tipo_medio)
        if operacion in ("importacion", "exportacion"):
            self.get_var("car_operacion_default").set(operacion)

        self.agregar_ddt_row(def_prod="GASOIL")
        self.rebuild_all_tabs()

    def construir_caratula(self):
        canvas = tk.Canvas(self.tab_caratula)
        sb = ttk.Scrollbar(self.tab_caratula, orient="vertical", command=canvas.yview)
        sf = ttk.Frame(canvas)
        sf.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=sf, anchor="nw")
        
        def on_canvas_configure(event):
             canvas.itemconfig(self.canvas_window_id, width=event.width)
        canvas.bind("<Configure>", on_canvas_configure)
        self.canvas_window_id = canvas.create_window((0, 0), window=sf, anchor="nw")

        canvas.configure(yscrollcommand=sb.set)
        canvas.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        
        def _on_mousewheel(event): canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        def _on_scroll_up(event): canvas.yview_scroll(-3, "units")
        def _on_scroll_down(event): canvas.yview_scroll(3, "units")
        def _bind_mw(e):
            canvas.bind_all("<MouseWheel>", _on_mousewheel)
            canvas.bind_all("<Button-4>", _on_scroll_up)
            canvas.bind_all("<Button-5>", _on_scroll_down)
        def _unbind_mw(e):
            canvas.unbind_all("<MouseWheel>")
            canvas.unbind_all("<Button-4>")
            canvas.unbind_all("<Button-5>")
        canvas.bind("<Enter>", _bind_mw)
        canvas.bind("<Leave>", _unbind_mw)

        f_btns = ttk.Frame(sf)
        f_btns.pack(fill="x", padx=20, pady=10)
        def _lbl_gestor():
            tm = self.get_tipo_medio()
            if "CAMION" in tm: return "GESTIONAR COMPARTIMENTOS"
            if "TANQUE" in tm: return "GESTIONAR TANQUES"
            return "GESTIONAR / EDITAR TANQUES"
        btn_tanks = tk.Button(f_btns, text=_lbl_gestor(), bg="#2196F3", fg="white", font=("Arial", 8, "bold"), command=self.abrir_gestor_tanques)
        btn_tanks.pack(side="left")
        self.get_var("car_tipo_medio").trace_add("write",
            lambda *a: btn_tanks.config(text=_lbl_gestor()))
        MARITIMOS_CON_DRAFT = ("BUQUE","BARCAZA","BUQUE GASERO/GLP","BUQUE QUIMIQUERO","BUQUE METANERO/GNL")
        btn_draft = tk.Button(f_btns, text="DRAFT SURVEY", bg="#5D4037", fg="white",
                              font=("Arial", 8, "bold"), command=self.abrir_draft_survey)
        def _update_draft_btn(*a):
            tm = self.get_tipo_medio()
            if tm in MARITIMOS_CON_DRAFT:
                btn_draft.pack(side="left", padx=6)
            else:
                btn_draft.pack_forget()
        self.get_var("car_tipo_medio").trace_add("write", _update_draft_btn)
        _update_draft_btn()  # aplicar al arranque

        frame_top = ttk.LabelFrame(sf, text="Datos Generales")
        frame_top.pack(padx=20, pady=10, fill="x")
        # Columnas impares (entries) se estiran con la ventana
        for _ci in [1, 3]: frame_top.columnconfigure(_ci, weight=1)

        # --- SELECCION TIPO NAVE ---
        _is_locked = getattr(self, "_archivo_bloqueado", False)
        _lock_icon = "[BLQ] " if _is_locked else ""
        ttk.Label(frame_top, text=f"{_lock_icon}Tipo de Medición:",
                  font=("Arial", min(8, max(7, self.ui_font_size)), "bold"),
                  foreground="#8B0000" if _is_locked else "").grid(row=0, column=0, sticky="e", padx=5, pady=6)
        _tm_var = self.get_var("car_tipo_medio", self.get_var("car_tipo_nave","BUQUE").get() or "BUQUE")
        # Restringir valores del combo a la categoría actual si está bloqueado
        _allowed_tipos = self.CATEGORIA_TIPOS.get(
            getattr(self, "_archivo_tipo_medio", ""),
            self.TIPO_MEDIOS
        ) if _is_locked else self.TIPO_MEDIOS
        cb_tipo = ttk.Combobox(frame_top, textvariable=_tm_var, state="readonly",
                               values=_allowed_tipos, width=27,
                               font=("Arial", max(10, self.ui_font_size+1)))
        cb_tipo.grid(row=0, column=1, sticky="w", padx=5)
        # Indicador visual si está bloqueado
        if _is_locked:
            _locked_cat = getattr(self, "_archivo_tipo_medio", "")
            _cat_label  = {"BUQUE":"MARÍTIMO","BARCAZA":"MARÍTIMO","BUQUE GASERO/GLP":"MARÍTIMO",
                           "BUQUE QUIMIQUERO":"MARÍTIMO","BUQUE METANERO/GNL":"MARÍTIMO",
                           "TANQUE FIJO":"TERRESTRE","TANQUE FLOTANTE":"TERRESTRE","ESFERA DE GAS":"TERRESTRE",
                           "CAMION CISTERNA":"AUTOMOTOR","CAMION GAS/GLP":"AUTOMOTOR",
                           "OLEODUCTO":"DUCTO","POLIDUCTO":"DUCTO","GASODUCTO":"DUCTO",
                           "ELECTRICO":"ELÉCTRICO"}.get(_locked_cat, _locked_cat)
            # Color del banner según categoría
            _lock_colors = {
                "MARÍTIMO":   ("#0A2A4A", "#5DADE2"),
                "TERRESTRE":  ("#0A3A0A", "#58D68D"),
                "AUTOMOTOR":  ("#3A2010", "#E59866"),
                "DUCTO":      ("#1A1A3A", "#85C1E9"),
                "ELÉCTRICO":  ("#2A2A00", "#F9E79F"),
            }
            _lbg, _lfg = _lock_colors.get(_cat_label, ("#8B0000", "#FFFFFF"))
            lbl_lock = tk.Label(frame_top,
                                text=f"  🔒 {_cat_label}  |  {_locked_cat}  —  No se puede cambiar categoría  ",
                                font=("Arial", max(7, self.ui_font_size-1), "bold"),
                                fg=_lfg, bg=_lbg, padx=6, pady=3, relief="flat")
            lbl_lock.grid(row=0, column=2, columnspan=2, sticky="w", padx=8)
        # sync car_tipo_nave for legacy compatibility
        _prev_tipo = [self.get_tipo_medio()]
        def _sync_tipo(*a):
            new_tm = _tm_var.get()
            # Bloqueo de categoría: si está bloqueado, solo se permite cambiar
            # entre tipos de la misma categoría (ej: BUQUE ↔ BARCAZA, no BUQUE → TANQUE)
            if getattr(self, "_archivo_bloqueado", False) and new_tm:
                locked = getattr(self, "_archivo_tipo_medio", "")
                allowed = self.CATEGORIA_TIPOS.get(locked, [locked])
                if new_tm not in allowed:
                    _tm_var.set(_prev_tipo[0])  # revertir
                    import tkinter.messagebox as mb
                    mb.showwarning("Tipo bloqueado",
                        f"Esta medición es de tipo «{locked}».\n"
                        f"No se puede cambiar a «{new_tm}».\n\n"
                        f"Para otro tipo, use: Archivo → Nueva Medición")
                    return
            self.get_var("car_tipo_nave").set(new_tm)
            _toggle_fields()
            if new_tm and new_tm != _prev_tipo[0]:
                _prev_tipo[0] = new_tm
                # Reinicializar tanques y tabs cuando el tipo cambia
                self._init_tanks_for_tipo(new_tm)
                self.rebuild_all_tabs()
        _tm_var.trace_add("write", _sync_tipo)


        _car_fnt = max(10, self.ui_font_size + 1)  # font mínimo 10 en Datos Generales
        _fnt_b = ("Arial", min(8, _car_fnt), "bold")
        _fnt_n = ("Arial", _car_fnt)

        # ── Fila 1: Nombre unidad + IMO/ID ──────────────────────────────────
        lbl_nombre = ttk.Label(frame_top, text="Nombre Buque/Barcaza:", font=_fnt_b)
        lbl_nombre.grid(row=1, column=0, sticky="e", padx=5, pady=6)
        entry_nombre = tk.Entry(frame_top, textvariable=self.get_var("car_buque"), font=_fnt_n)
        entry_nombre.grid(row=1, column=1, sticky="ew", padx=5, ipady=2)
        lbl_imo = ttk.Label(frame_top, text="N° IMO:", font=_fnt_b)
        lbl_imo.grid(row=1, column=2, sticky="e", padx=5, pady=6)
        entry_imo = tk.Entry(frame_top, textvariable=self.get_var("car_imo"), font=_fnt_n)
        entry_imo.grid(row=1, column=3, sticky="ew", padx=5, ipady=2)

        # ── Filas fijas comunes ──────────────────────────────────────────────
        campos_fijos = [
            ("Despachante de Aduana:", "car_despachante", 2, 0), ("CUIT Despachante:", "car_cuit_desp", 2, 2),
            ("Importador / Exportador:", "car_impexp", 3, 0), ("CUIT Imp/Exp:", "car_cuit_impexp", 3, 2),
            ("Agencia Marítima (ATA):", "car_ata", 4, 0), ("CUIT ATA:", "car_cuit_ata", 4, 2),
            ("N° MANI:", "car_mani", 5, 0), ("N° Viaje:", "car_conocimientos", 5, 2),
        ]
        cuit_fields = ["car_cuit_desp", "car_cuit_impexp", "car_cuit_ata"]
        lbl_ata = None; lbl_cuit_ata = None; e_ata = None; e_cuit_ata = None
        lbl_mani = None; e_mani = None
        for item in campos_fijos:
            lbl_txt, key, r, c_col = item
            lbl_w = ttk.Label(frame_top, text=lbl_txt, font=_fnt_b)
            lbl_w.grid(row=r, column=c_col, sticky="e", padx=5, pady=6)
            e_w = tk.Entry(frame_top, textvariable=self.get_var(key), font=_fnt_n)
            e_w.grid(row=r, column=c_col+1, sticky="ew", padx=5, ipady=2)
            if key in cuit_fields:
                var_ref = self.get_var(key)
                e_w.bind("<FocusOut>", lambda ev, wdg=e_w, v=var_ref: self.on_cuit_validate(wdg, v))
            # Save refs for dynamic hiding
            if key == "car_ata": lbl_ata = lbl_w; e_ata = e_w
            if key == "car_cuit_ata": lbl_cuit_ata = lbl_w; e_cuit_ata = e_w
            if key == "car_mani": lbl_mani = lbl_w; e_mani = e_w

        # ── Extra fields: tanques de tierra (techo flotante offset + diámetro) ──
        lbl_radio = ttk.Label(frame_top, text="Radio Interno (m):", font=_fnt_b)
        lbl_radio.grid(row=1, column=2, sticky="e", padx=5, pady=6)
        e_radio = tk.Entry(frame_top, textvariable=self.get_var("car_radio_m",""), font=_fnt_n, width=10)
        e_radio.grid(row=1, column=3, sticky="w", padx=5, ipady=2)

        lbl_tf_off = ttk.Label(frame_top, text="Offset Techo Flotante (mm):", font=_fnt_b)
        lbl_tf_off.grid(row=1, column=2, sticky="e", padx=5, pady=6)  # same pos as radio; toggle later
        e_tf_off = tk.Entry(frame_top, textvariable=self.get_var("car_tf_offset","0"), font=_fnt_n, width=10)
        e_tf_off.grid(row=1, column=3, sticky="w", padx=5, ipady=2)

        # ── Extra fields: camion ─────────────────────────────────────────────
        lbl_patente = ttk.Label(frame_top, text="Dominio / Patente:", font=_fnt_b)
        lbl_patente.grid(row=1, column=0, sticky="e", padx=5, pady=6)
        e_patente = tk.Entry(frame_top, textvariable=self.get_var("car_patente",""), font=_fnt_n)
        e_patente.grid(row=1, column=1, sticky="ew", padx=5, ipady=2)
        lbl_precinto = ttk.Label(frame_top, text="N° Precinto:", font=_fnt_b)
        lbl_precinto.grid(row=1, column=2, sticky="e", padx=5, pady=6)
        e_precinto = tk.Entry(frame_top, textvariable=self.get_var("car_precinto",""), font=_fnt_n, width=10)
        e_precinto.grid(row=1, column=3, sticky="w", padx=5, ipady=2)

        lbl_radio_cam = ttk.Label(frame_top, text="Radio Cisterna (m):", font=_fnt_b)
        lbl_radio_cam.grid(row=4, column=2, sticky="e", padx=5, pady=6)
        e_radio_cam = tk.Entry(frame_top, textvariable=self.get_var("car_radio_camion",""), font=_fnt_n, width=10)
        e_radio_cam.grid(row=4, column=3, sticky="w", padx=5, ipady=2)
        lbl_largo_cam = ttk.Label(frame_top, text="Largo Cisterna (m):", font=_fnt_b)
        lbl_largo_cam.grid(row=4, column=0, sticky="e", padx=5, pady=6)
        e_largo_cam = tk.Entry(frame_top, textvariable=self.get_var("car_largo_camion",""), font=_fnt_n, width=10)
        e_largo_cam.grid(row=4, column=1, sticky="w", padx=5, ipady=2)

        # ── Extra fields: gasero ─────────────────────────────────────────────
        lbl_presion = ttk.Label(frame_top, text="Presión operativa (kPa):", font=_fnt_b)
        lbl_presion.grid(row=4, column=0, sticky="e", padx=5, pady=6)
        e_presion = tk.Entry(frame_top, textvariable=self.get_var("car_presion_op",""), font=_fnt_n, width=10)
        e_presion.grid(row=4, column=1, sticky="w", padx=5, ipady=2)
        lbl_temp_op = ttk.Label(frame_top, text="Temp. operativa (°C):", font=_fnt_b)
        lbl_temp_op.grid(row=4, column=2, sticky="e", padx=5, pady=6)
        e_temp_op = tk.Entry(frame_top, textvariable=self.get_var("car_temp_op",""), font=_fnt_n, width=10)
        e_temp_op.grid(row=4, column=3, sticky="w", padx=5, ipady=2)

        def _toggle_fields():
            tm = self.get_tipo_medio()
            mar = self.es_maritimo()
            gas = self.es_gasero()
            tie = self.es_tierra()
            cam = self.es_camion()
            flot = "FLOTANTE" in tm

            # Fila 1 label switch
            for w in (lbl_nombre, entry_nombre, lbl_imo, entry_imo,
                      lbl_radio, e_radio, lbl_tf_off, e_tf_off,
                      lbl_patente, e_patente, lbl_precinto, e_precinto):
                try: w.grid_remove()
                except: pass

            if mar:
                lbl_nombre.config(text="Nombre Buque/Barcaza:" if "BARCAZA" not in tm else "Nombre Barcaza:")
                lbl_nombre.grid(); entry_nombre.grid()
                lbl_imo.grid(); entry_imo.grid()
            elif tie:
                lbl_nombre.config(text="Nombre del Tanque:")
                lbl_nombre.grid(); entry_nombre.grid()
                lbl_radio.grid(); e_radio.grid()
                if flot: lbl_tf_off.grid(); e_tf_off.grid()
            elif cam:
                lbl_patente.grid(); e_patente.grid()
                lbl_precinto.grid(); e_precinto.grid()

            elif self.es_esfera():
                lbl_nombre.config(text="Nombre Instalacion:")
                lbl_nombre.grid(); entry_nombre.grid()
                lbl_imo.config(text="N Expediente / Contrato:")
                lbl_imo.grid(); entry_imo.grid()

            # ATA: solo marino
            for w in (lbl_ata, e_ata, lbl_cuit_ata, e_cuit_ata):
                if w:
                    try:
                        if mar: w.grid()
                        else: w.grid_remove()
                    except: pass

            # MANI label
            if lbl_mani:
                lbl_mani.config(text="N° MANI:" if mar else "N° Expediente:")

            # Fila 4 extras
            for w in (lbl_radio_cam, e_radio_cam, lbl_largo_cam, e_largo_cam,
                      lbl_presion, e_presion, lbl_temp_op, e_temp_op):
                try: w.grid_remove()
                except: pass
            duc = self.es_ducto()
            cam_gas = self.es_camion_gas()
            elec = self.es_electrico()

            if cam or cam_gas:
                lbl_radio_cam.grid(); e_radio_cam.grid()
                lbl_largo_cam.grid(); e_largo_cam.grid()
            _esf_car = self.es_esfera()
            if gas or cam_gas or _esf_car:
                if _esf_car:
                    lbl_presion.config(text="Presion operativa (kPa):")
                    lbl_temp_op.config(text="Temp. operativa (C):")
                lbl_presion.grid(); e_presion.grid()
                lbl_temp_op.grid(); e_temp_op.grid()
            if duc:
                lbl_presion.config(text="Presion linea (kPa):"); lbl_presion.grid(); e_presion.grid()
                lbl_temp_op.config(text="Temp. linea (C):"); lbl_temp_op.grid(); e_temp_op.grid()
                lbl_nombre.config(text="Nombre del Ducto:"); lbl_nombre.grid(); entry_nombre.grid()
                lbl_imo.config(text="Diametro (pulg):"); lbl_imo.grid(); entry_imo.grid()
            if elec:
                lbl_nombre.config(text="Instalacion / Punto de Medicion:"); lbl_nombre.grid(); entry_nombre.grid()
                lbl_imo.config(text="N Contrato / Suministro:"); lbl_imo.grid(); entry_imo.grid()

        _toggle_fields()

        # --- SELECTOR ADUANA (códigos oficiales ARCA) ---
        ADUANAS_ARG = [
            "001 - BS.AS. (CAPITAL)",       "003 - BAHIA BLANCA",
            "004 - BARILOCHE",              "008 - CAMPANA",
            "010 - BARRANQUERAS",           "012 - CLORINDA",
            "013 - COLON",                  "014 - COMODORO RIVADAVIA",
            "015 - CONCEPCION DEL URUGUAY", "016 - CONCORDIA",
            "017 - CORDOBA",                "018 - CORRIENTES",
            "019 - PUERTO DESEADO",         "020 - DIAMANTE",
            "023 - ESQUEL",                 "024 - FORMOSA",
            "025 - GOYA",                   "026 - GUALEGUAYCHU",
            "029 - IGUAZU",                 "031 - JUJUY",
            "033 - LA PLATA",               "034 - LA QUIACA",
            "037 - MAR DEL PLATA",          "038 - MENDOZA",
            "040 - NECOCHEA",               "041 - PARANA",
            "042 - PASO DE LOS LIBRES",     "045 - POCITOS",
            "046 - POSADAS",                "047 - PUERTO MADRYN",
            "048 - RIO GALLEGOS",           "049 - RIO GRANDE",
            "052 - ROSARIO",                "053 - SALTA",
            "054 - SAN JAVIER",             "055 - SAN JUAN",
            "057 - SAN LORENZO",            "058 - S. MARTIN DE LOS ANDES",
            "059 - SAN NICOLAS",            "060 - SAN PEDRO",
            "061 - SANTA CRUZ",             "062 - SANTA FE",
            "066 - TINOGASTA",              "067 - USHUAIA",
            "069 - VILLA CONSTITUCION",     "073 - EZEIZA",
            "074 - TUCUMAN",                "075 - NEUQUEN",
            "076 - ORAN",                   "078 - SAN RAFAEL",
            "079 - LA RIOJA",               "080 - SAN ANTONIO OESTE",
            "082 - BERNARDO DE YRIGOYEN",   "083 - SAN LUIS",
            "084 - SANTO TOME",             "085 - VILLA REGINA",
            "086 - OBERA",                  "087 - CALETA OLIVIA",
            "088 - GENERAL DEHEZA",         "089 - SANTIAGO DEL ESTERO",
            "090 - GENERAL PICO",           "091 - BS.AS. NORTE",
            "092 - BS.AS. SUR",             "093 - RAFAELA",
            "099 - MULTIADUANA",
            "258 - Z.F GENERAL PICO",       "266 - Z.F CORONEL ROSALES",
            "267 - Z.F CONCEP.DEL.URUG.",   "268 - Z.F. V. CONSTITUCION",
            "269 - Z.F. PUERTO GALVAN",
        ]
        ttk.Label(frame_top, text="Aduana:", font=("Arial", min(8, max(7, self.ui_font_size)), "bold")).grid(row=6, column=0, sticky="e", padx=5, pady=6)
        self.get_var("car_lugar", "067 - USHUAIA")
        cb_aduana = ttk.Combobox(frame_top, textvariable=self.get_var("car_lugar"),
                                 values=ADUANAS_ARG, state="normal", width=28, font=("Arial", max(10, self.ui_font_size+1)))
        cb_aduana.grid(row=6, column=1, sticky="w", padx=5)
        # T/C global del documento (ARS por 1 U$S)
        ttk.Label(frame_top, text="T/C U$S:", font=("Arial", min(8, max(7, self.ui_font_size)), "bold"),
                  foreground="#6A1B9A").grid(row=6, column=2, sticky="e", padx=5, pady=6)
        ttk.Entry(frame_top, textvariable=self.get_var("car_tipo_cambio", ""),
                  width=12, font=("Arial", max(10, self.ui_font_size+1))).grid(row=6, column=3, sticky="w", padx=5)

        # --- LUGAR OPERATIVO: selector desde DB, filtrado por aduana ---
        f_lop = ttk.Frame(frame_top)
        f_lop.grid(row=7, column=0, columnspan=4, sticky="ew", padx=5, pady=3)
        ttk.Label(f_lop, text="Lugar Operativo (LOT):",
                  font=("Arial", min(8, max(7, self.ui_font_size)), "bold")).pack(side="left")
        _lop_display = tk.StringVar()
        _lop_fnt = ("Arial", max(10, self.ui_font_size + 1))
        cb_lop = ttk.Combobox(f_lop, textvariable=_lop_display, width=55,
                               font=_lop_fnt, state="normal")
        cb_lop.pack(side="left", padx=(6, 0))
        tk.Button(f_lop, text="Gestionar LOTs", bg="#1A5276", fg="white",
                  font=("Arial", 8), cursor="hand2",
                  command=self.abrir_gestor_aduanas_lop).pack(side="left", padx=6)
        lbl_lop_hint = tk.Label(f_lop, text="", font=("Arial", 7), fg="gray")
        lbl_lop_hint.pack(side="left", padx=2)

        def _lop_refresh(*_):
            adu_raw = self.get_var("car_lugar").get().strip()
            adu_cod = adu_raw.split(" - ")[0].strip() if " - " in adu_raw else adu_raw[:3]
            lots = db_get_lugares_operativos(adu_cod) if adu_cod else []
            if not lots:
                lots = db_get_lugares_operativos()
            opciones = [f"{r['codigo']} — {r['descripcion']}" for r in lots]
            cb_lop["values"] = opciones
            n = len(opciones)
            lbl_lop_hint.config(text=f"{n} LOT(s)" if n else "(sin LOTs — use Gestionar LOTs)")

        def _lop_sync(*_):
            val = _lop_display.get().strip()
            if " — " in val:
                cod, desc = val.split(" — ", 1)
            else:
                parts = val.split(None, 1)
                cod  = parts[0] if parts else val
                desc = parts[1] if len(parts) > 1 else ""
            self.get_var("car_lop_codigo").set(cod.strip())
            self.get_var("car_lop_desc").set(desc.strip())

        def _lop_preload():
            cod  = self.get_var("car_lop_codigo", "").get().strip()
            desc = self.get_var("car_lop_desc",   "").get().strip()
            if cod or desc:
                sep = " — " if desc else ""
                _lop_display.set(f"{cod}{sep}{desc}")

        cb_lop.bind("<<ComboboxSelected>>", _lop_sync)
        cb_lop.bind("<FocusOut>",           _lop_sync)
        self.get_var("car_lugar").trace_add("write", _lop_refresh)
        _lop_refresh()
        _lop_preload()

        # === SELECTOR NORMA VCF ===
        frame_norma = ttk.LabelFrame(sf, text="Norma de Cálculo VCF (Tablas 54)")
        frame_norma.pack(padx=20, pady=(4, 10), fill="x")
        _fn = ("Arial", max(9, self.ui_font_size), "bold")
        _fn2 = ("Arial", max(8, self.ui_font_size - 1))

        tk.Radiobutton(
            frame_norma, text="ASTM D1250-1980  (tablas impresas — 4 zonas en 54B)",
            variable=self.norma_astm, value="1980",
            font=_fn, fg="#1A5276", activeforeground="#1A5276",
            command=self._on_norma_changed
        ).grid(row=0, column=0, sticky="w", padx=15, pady=(8, 2))
        tk.Label(frame_norma,
                 text="  JP-1 rho=798 t=23°C → 0.99252 | Diesel rho=850 t=25°C → 0.99159  (4 zonas de densidad)",
                 font=_fn2, fg="#555").grid(row=1, column=0, sticky="w", padx=30, pady=(0, 6))

        tk.Radiobutton(
            frame_norma, text="API MPMS 11.1 / ASTM D1250-2004  (norma digital — fórmula única en 54B)",
            variable=self.norma_astm, value="2004",
            font=_fn, fg="#4A235A", activeforeground="#4A235A",
            command=self._on_norma_changed
        ).grid(row=0, column=1, sticky="w", padx=15, pady=(8, 2))
        tk.Label(frame_norma,
                 text="  JP-1 rho=798 t=23°C → 0.99096 | Diesel rho=850 t=25°C → 0.98996  (K0=346.4228 K1=0.4033)",
                 font=_fn2, fg="#555").grid(row=1, column=1, sticky="w", padx=30, pady=(0, 6))

        # === FUNCIONARIOS INTERVINIENTES ===
        self.frame_func_master = ttk.LabelFrame(sf, text="Funcionarios Intervinientes")
        self.frame_func_master.pack(padx=20, pady=10, fill="x")
        _fb = ttk.Frame(self.frame_func_master)
        _fb.pack(fill="x", padx=10, pady=5)
        tk.Button(_fb, text="+ Fila en blanco", bg="#6A1B9A", fg="white",
                  font=("Arial", 8, "bold"), command=self.agregar_funcionario_row).pack(side="left")
        tk.Button(_fb, text="Buscar en DB", bg="#27AE60", fg="white",
                  font=("Arial", 8, "bold"), command=self.buscar_y_agregar_funcionario_db).pack(side="left", padx=6)
        tk.Button(_fb, text="Administrar DB", bg="#37474F", fg="white",
                  font=("Arial", 8, "bold"), command=self.abrir_gestor_funcionarios_db).pack(side="left", padx=4)
        tk.Button(_fb, text="Gestionar Funciones", bg="#0D47A1", fg="white",
                  font=("Arial", 8, "bold"), command=self.abrir_gestor_funciones).pack(side="left", padx=4)
        self.func_stack = ttk.Frame(self.frame_func_master)
        self.func_stack.pack(fill="x", padx=5)
        # Cabecera con grid
        f_func_hdr = ttk.Frame(self.func_stack)
        f_func_hdr.pack(fill="x")
        for ci, (col_txt, col_w) in enumerate([("CUIL", 14), ("Legajo", 10), ("Apellido", 22), ("Nombre", 22), ("Función", 26), ("", 3)]):
            tk.Label(f_func_hdr, text=col_txt, font=("Arial", 8, "bold"), fg="gray", width=col_w, anchor="w").grid(row=0, column=ci, padx=2)

        self.frame_ddt_master = ttk.LabelFrame(sf, text="Documentos y Salidas")
        self.frame_ddt_master.pack(padx=20, pady=10, fill="both", expand=True)
        tk.Button(self.frame_ddt_master, text="+ AGREGAR DOCUMENTO", bg="#2E7D32", fg="white", font=("Arial", 8, "bold"), command=self.popup_tipo_documento).pack(pady=10, anchor="w", padx=10)
        self.ddt_stack = ttk.Frame(self.frame_ddt_master)
        self.ddt_stack.pack(fill="both", expand=True, padx=5)

    def abrir_gestor_tanques(self):
        try:
            toplevel = tk.Toplevel(self.root)
            toplevel.title("Gestión de Tanques y Carbonera")
            # Maximizar ventana
            try:
                toplevel.state("zoomed")       # Windows
            except:
                try:
                    toplevel.attributes("-zoomed", True)  # Linux
                except:
                    sw2, sh2 = toplevel.winfo_screenwidth(), toplevel.winfo_screenheight()
                    toplevel.geometry(f"{sw2}x{sh2}+0+0")
            
            # --- BOTONERA INFERIOR FIJA (fuera del PanedWindow) ---
            f_bot = tk.Frame(toplevel, bg="#2C3E50", bd=0, height=60)
            f_bot.pack(side="bottom", fill="x")
            f_bot.pack_propagate(False)  # Mantener altura fija
            
            # Frame interior centrado
            f_bot_inner = tk.Frame(f_bot, bg="#2C3E50")
            f_bot_inner.pack(expand=True)

            # PanedWindow para dividir lista (izq) y dibujo (der)
            pw = ttk.PanedWindow(toplevel, orient=tk.HORIZONTAL)
            pw.pack(fill="both", expand=True)

            left_frame = ttk.Frame(pw)
            right_frame = ttk.Frame(pw)
            pw.add(left_frame, weight=2)
            pw.add(right_frame, weight=3)

            # --- CANVAS SCROLL ---
            canvas_list = tk.Canvas(left_frame, bg="white")
            sb = ttk.Scrollbar(left_frame, orient="vertical", command=canvas_list.yview)
            scroll_f = ttk.Frame(canvas_list)
            
            scroll_f.bind("<Configure>", lambda e: canvas_list.configure(scrollregion=canvas_list.bbox("all")))
            window_id = canvas_list.create_window((0, 0), window=scroll_f, anchor="nw")

            def on_canvas_configure(event):
                canvas_list.itemconfig(window_id, width=event.width)
            canvas_list.bind("<Configure>", on_canvas_configure)

            canvas_list.configure(yscrollcommand=sb.set)
            sb.pack(side="right", fill="y")
            canvas_list.pack(fill="both", expand=True)
            # Mousewheel scoped to this canvas only
            def _cl_on_mw(event): canvas_list.yview_scroll(int(-1*(event.delta/120)), "units")
            def _cl_up(event): canvas_list.yview_scroll(-3, "units")
            def _cl_down(event): canvas_list.yview_scroll(3, "units")
            def _cl_bind(e):
                canvas_list.bind_all("<MouseWheel>", _cl_on_mw)
                canvas_list.bind_all("<Button-4>", _cl_up)
                canvas_list.bind_all("<Button-5>", _cl_down)
            def _cl_unbind(e):
                canvas_list.unbind_all("<MouseWheel>")
                canvas_list.unbind_all("<Button-4>")
                canvas_list.unbind_all("<Button-5>")
            canvas_list.bind("<Enter>", _cl_bind)
            canvas_list.bind("<Leave>", _cl_unbind)

            def _parse_side(name):
                """Extrae el lado del nombre"""
                if "BABOR" in name.upper(): return "BABOR"
                if "ESTRIBOR" in name.upper(): return "ESTRIBOR"
                return "AMBOS"

            def _strip_side(name):
                """Quita BABOR/ESTRIBOR del nombre"""
                n = name.strip()
                for s in [" BABOR", " ESTRIBOR", " babor", " estribor"]:
                    if n.endswith(s): n = n[:-len(s)].strip()
                return n

            # Datos temporales: (nombre_sin_lado, lado)
            self.temp_tanks = []
            for t in self.lista_tanques:
                self.temp_tanks.append({
                    "name": tk.StringVar(value=_strip_side(t)),
                    "side": tk.StringVar(value=_parse_side(t))
                })

            self.temp_carb = []
            for t in self.lista_carbonera:
                self.temp_carb.append({
                    "name": tk.StringVar(value=_strip_side(t)),
                    "side": tk.StringVar(value=_parse_side(t))
                })

            # Guía Visual (Canvas Derecho)
            gui_canvas = tk.Canvas(right_frame, bg="#f0f0f0")
            gui_canvas.pack(fill="both", expand=True)

            def dibujar_guia():
                gui_canvas.delete("all")
                w_cv = gui_canvas.winfo_width()
                h_cv = gui_canvas.winfo_height()
                if w_cv < 100 or h_cv < 100: return

                # Construir listas temporales con nombres completos
                temp_tank_full = []
                for item in self.temp_tanks:
                    name = item["name"].get().strip()
                    side = item["side"].get()
                    if not name: continue
                    if side == "AMBOS": temp_tank_full.append(name)
                    else: temp_tank_full.append(f"{name} {side}")

                temp_carb_full = []
                for item in self.temp_carb:
                    name = item["name"].get().strip()
                    side = item["side"].get()
                    if not name: continue
                    if side == "AMBOS": temp_carb_full.append(name)
                    else: temp_carb_full.append(f"{name} {side}")

                if self.es_maritimo():
                    half_h = (h_cv - 20) / 2
                    # Buques: 2 vistas
                    self.dibujar_unidad_tk(gui_canvas, 5, 5, w_cv - 10, half_h - 5, "BABOR", None, temp_tank_full, temp_carb_full)
                    self.dibujar_unidad_tk(gui_canvas, 5, 5 + half_h, w_cv - 10, half_h - 5, "ESTRIBOR", None, temp_tank_full, temp_carb_full)
                else:
                    # Tierra/esfera/camion/ducto: canvas completo
                    self.dibujar_unidad_tk(gui_canvas, 5, 5, w_cv - 10, h_cv - 10, "AMBOS", None, temp_tank_full, temp_carb_full)

            _guia_pending = [None]
            def _dibujar_guia_debounced(event=None):
                if _guia_pending[0] is not None:
                    try: toplevel.after_cancel(_guia_pending[0])
                    except: pass
                _guia_pending[0] = toplevel.after(50, dibujar_guia)
            gui_canvas.bind("<Configure>", _dibujar_guia_debounced)

            _render_pending = [None]
            def render_all():
                if _render_pending[0] is not None:
                    try: toplevel.after_cancel(_render_pending[0])
                    except: pass
                _render_pending[0] = toplevel.after(50, _do_render)

            def _do_render():
                for w_child in scroll_f.winfo_children(): w_child.destroy()
                
                # --- TANQUES ---
                _tm_now = self.get_tipo_medio()
                _lbl_tk_sec = "TANQUES DE CARGA"
                if "CAMION" in _tm_now: _lbl_tk_sec = "COMPARTIMENTOS DE CISTERNA"
                elif "TANQUE" in _tm_now: _lbl_tk_sec = "TANQUES DE ALMACENAMIENTO"
                elif "ESFERA" in _tm_now: _lbl_tk_sec = "ESFERAS DE GAS"
                elif "DUCTO" in _tm_now: _lbl_tk_sec = "TRAMOS DE DUCTO"
                elif "ELECTRICA" in _tm_now: _lbl_tk_sec = "MEDIDORES"
                tk.Label(scroll_f, text=_lbl_tk_sec, font=("Arial", 8, "bold"), bg="#D6EAF8").pack(fill="x", pady=5)
                
                for i, item in enumerate(self.temp_tanks):
                    row = ttk.Frame(scroll_f)
                    row.pack(fill="x", pady=1, padx=2)
                    
                    tk.Button(row, text="^", width=2, command=lambda idx=i: move_item(self.temp_tanks, idx, -1)).pack(side="left")
                    tk.Button(row, text="v", width=2, command=lambda idx=i: move_item(self.temp_tanks, idx, 1)).pack(side="left")
                    
                    ttk.Entry(row, textvariable=item["name"], width=20).pack(side="left", padx=3)
                    
                    _is_mar = self.es_maritimo()
                    if _is_mar:
                        cb = ttk.Combobox(row, textvariable=item["side"], values=["BABOR", "ESTRIBOR", "AMBOS"], state="readonly", width=10)
                        cb.pack(side="left", padx=3)
                        cb.bind("<<ComboboxSelected>>", lambda e: dibujar_guia())
                    
                    tk.Button(row, text="X", bg="#E74C3C", fg="white", width=2, command=lambda idx=i: remove_item(self.temp_tanks, idx)).pack(side="right")

                ttk.Separator(scroll_f, orient="horizontal").pack(fill="x", pady=10)
                
                # --- CARBONERAS / CONSUMO (solo buques maritimos clásicos) ---
                _show_carb = self.get_tipo_medio() in ("BUQUE","BARCAZA","BUQUE GASERO/GLP","BUQUE QUIMIQUERO","BUQUE METANERO/GNL")
                if _show_carb:
                    tk.Label(scroll_f, text="CARBONERAS / CONSUMO", font=("Arial", 8, "bold"), bg="#FEF9E7", fg="#6E4B00").pack(fill="x", pady=5)
                    
                    for i, item in enumerate(self.temp_carb):
                        row = ttk.Frame(scroll_f)
                        row.pack(fill="x", pady=1, padx=2)
                        tk.Button(row, text="^", width=2, command=lambda idx=i: move_item(self.temp_carb, idx, -1)).pack(side="left")
                        tk.Button(row, text="v", width=2, command=lambda idx=i: move_item(self.temp_carb, idx, 1)).pack(side="left")
                        ttk.Entry(row, textvariable=item["name"], width=20).pack(side="left", padx=3)
                        cb = ttk.Combobox(row, textvariable=item["side"], values=["BABOR", "ESTRIBOR", "AMBOS"], state="readonly", width=10)
                        cb.pack(side="left", padx=3)
                        cb.bind("<<ComboboxSelected>>", lambda e: dibujar_guia())
                        tk.Button(row, text="X", bg="#E74C3C", fg="white", width=2, command=lambda idx=i: remove_item(self.temp_carb, idx)).pack(side="right")
                
                dibujar_guia()

            def move_item(lista, index, direction):
                new_idx = index + direction
                if 0 <= new_idx < len(lista):
                    lista[index], lista[new_idx] = lista[new_idx], lista[index]
                    render_all()

            def remove_item(lista, index):
                del lista[index]
                render_all()

            def add_t():
                _side_def = "BABOR" if self.es_maritimo() else "AMBOS"
                _name_def = "NUEVO TK" if not self.es_maritimo() else "NUEVO TK"
                self.temp_tanks.append({"name": tk.StringVar(value=_name_def), "side": tk.StringVar(value=_side_def)})
                render_all()
            def add_c():
                self.temp_carb.append({"name": tk.StringVar(value="CARBONERA"), "side": tk.StringVar(value="AMBOS")})
                render_all()

            def save():
                # Construir nombre final: nombre + lado (excepto AMBOS)
                new_tanks = []
                for item in self.temp_tanks:
                    name = item["name"].get().strip()
                    if not name: continue
                    if self.es_maritimo():
                        side = item["side"].get()
                        if side == "AMBOS": new_tanks.append(name)
                        else: new_tanks.append(f"{name} {side}")
                    else:
                        new_tanks.append(name)
                
                new_carb = []
                for item in self.temp_carb:
                    name = item["name"].get().strip()
                    if not name: continue
                    if self.es_maritimo():
                        side = item["side"].get()
                        if side == "AMBOS": new_carb.append(name)
                        else: new_carb.append(f"{name} {side}")
                    else:
                        new_carb.append(name)
                
                self.lista_tanques = new_tanks
                self.lista_carbonera = new_carb
                self.rebuild_all_tabs()
                toplevel.destroy()
                messagebox.showinfo("Listo", "Configuración de tanques guardada.")

            # --- BOTONES EN f_bot ---
            _tm_btn = self.get_tipo_medio()
            _tk_lbl = "+ Compartimento" if ("CAMION" in _tm_btn or "TANQUE" in _tm_btn) else "+ TK Carga"
            tk.Button(f_bot_inner, text=f"  {_tk_lbl}  ", bg="#2980B9", fg="white", font=("Arial", 8, "bold"), command=add_t).pack(side="left", padx=10, pady=12)
            if self.get_tipo_medio() in ("BUQUE","BARCAZA","BUQUE GASERO/GLP","BUQUE QUIMIQUERO","BUQUE METANERO/GNL"):
                tk.Button(f_bot_inner, text="  + Carbonera  ", bg="#D4AC0D", fg="white", font=("Arial", 8, "bold"), command=add_c).pack(side="left", padx=10, pady=12)
            tk.Button(f_bot_inner, text="  GUARDAR CAMBIOS", bg="#27AE60", fg="white", font=("Arial", 8, "bold"), command=save, cursor="hand2").pack(side="right", padx=20, pady=12, ipadx=10, ipady=4)
            
            render_all()

        except Exception as e:
            traceback.print_exc()
            messagebox.showerror("Error", f"Error al abrir el gestor de tanques:\n{e}")

    def popup_tipo_documento(self, edit_obj=None):
        """Popup para seleccionar/editar tipo de documento."""
        dlg = tk.Toplevel(self.root)
        dlg.title("Tipo de Documento" if not edit_obj else "Modificar Documento")
        dlg.transient(self.root)
        dlg.grab_set()
        dlg.update_idletasks()
        # Centrar en pantalla
        sw, sh = dlg.winfo_screenwidth(), dlg.winfo_screenheight()
        w_dlg, h_dlg = 480, 420
        dlg.geometry(f"{w_dlg}x{h_dlg}+{(sw - w_dlg)//2}+{(sh - h_dlg)//2}")

        tk.Label(dlg, text="Seleccione el tipo de documento:", font=("Arial", 8, "bold")).pack(pady=10)

        # Pre-fill if editing
        _existing_num = edit_obj["numero"].get() if edit_obj else ""
        _existing_tipo = edit_obj["tipo_doc"].get() if edit_obj else "Detallada"

        tipo_var = tk.StringVar(value="DECLARACION_DETALLADA")
        if edit_obj:
            t = _existing_tipo
            if t in ("Particular",): tipo_var.set("SOLICITUD_PARTICULAR")
            elif t in ("Expediente",): tipo_var.set("EXPEDIENTE")
            else: tipo_var.set("DECLARACION_DETALLADA")
        for val, txt in [("DECLARACION_DETALLADA", "Declaración Detallada (SIM/MALVINA)"), 
                         ("SOLICITUD_PARTICULAR", "Solicitud Particular"),
                         ("EXPEDIENTE", "Expediente")]:
            tk.Radiobutton(dlg, text=txt, variable=tipo_var, value=val, font=("Arial", 10)).pack(anchor="w", padx=30)

        # Frame para Declaración Detallada
        f_dd = ttk.LabelFrame(dlg, text="Datos Declaración Detallada")
        f_dd.pack(padx=20, pady=10, fill="x")

        tk.Label(f_dd, text="Año (2 díg):", font=("Arial", 9)).grid(row=0, column=0, padx=3, pady=3)
        var_anio = tk.StringVar()
        ttk.Entry(f_dd, textvariable=var_anio, width=4).grid(row=0, column=1, padx=3)

        tk.Label(f_dd, text="Aduana (3 díg):", font=("Arial", 9)).grid(row=0, column=2, padx=3)
        var_aduana = tk.StringVar()
        ttk.Entry(f_dd, textvariable=var_aduana, width=5).grid(row=0, column=3, padx=3)

        tk.Label(f_dd, text="Subrégimen:", font=("Arial", 9)).grid(row=0, column=4, padx=3)
        var_subreg = tk.StringVar(value="REMO")
        ttk.Combobox(f_dd, textvariable=var_subreg, values=self.SUBREGIMENES, state="readonly", width=7).grid(row=0, column=5, padx=3)

        tk.Label(f_dd, text="Número (hasta 6 díg):", font=("Arial", 9)).grid(row=1, column=0, columnspan=2, padx=3, pady=3)
        var_num = tk.StringVar()
        ttk.Entry(f_dd, textvariable=var_num, width=8).grid(row=1, column=2, padx=3)

        tk.Label(f_dd, text="Letra:", font=("Arial", 9)).grid(row=1, column=3, padx=3)
        var_letra = tk.StringVar()
        e_letra = ttk.Entry(f_dd, textvariable=var_letra, width=3)
        e_letra.grid(row=1, column=4, padx=3)

        # Vista previa
        var_preview = tk.StringVar(value="")
        tk.Label(f_dd, textvariable=var_preview, font=("Arial", 8, "bold"), fg="blue").grid(row=2, column=0, columnspan=6, pady=5)

        def actualizar_preview(*args):
            a = var_anio.get().zfill(2)[-2:]
            ad = var_aduana.get().zfill(3)[-3:]
            sr = var_subreg.get()
            n = var_num.get().zfill(6)[-6:]
            code = f"{a}{ad}{sr}{n}"
            letra = var_letra.get().upper().strip()
            if not letra:
                letra = self.calcular_letra_dest(f"{a}{ad}{n}")
                var_letra.set(letra)
            var_preview.set(f"{code}{letra}")

        for v in [var_anio, var_aduana, var_subreg, var_num]:
            v.trace_add("write", actualizar_preview)

        # Frame Solicitud/Expediente
        f_sp = ttk.LabelFrame(dlg, text="Número de Solicitud/Expediente")
        f_sp.pack(padx=20, pady=5, fill="x")
        var_libre = tk.StringVar()
        ttk.Entry(f_sp, textvariable=var_libre, width=40).pack(padx=10, pady=5)

        def toggle_frames(*args):
            is_dd = tipo_var.get() == "DECLARACION_DETALLADA"
            for child in f_dd.winfo_children():
                try: child.configure(state="normal" if is_dd else "disabled")
                except: pass
            for child in f_sp.winfo_children():
                try: child.configure(state="disabled" if is_dd else "normal")
                except: pass
        tipo_var.trace_add("write", toggle_frames)
        toggle_frames()

        def aceptar():
            tipo = tipo_var.get()
            if tipo == "DECLARACION_DETALLADA":
                actualizar_preview()
                desc = var_preview.get()
                tipo_doc_val = "Detallada"
            elif tipo == "SOLICITUD_PARTICULAR":
                desc = var_libre.get() or "Solicitud Particular"
                tipo_doc_val = "Particular"
            else:
                desc = var_libre.get() or "Expediente"
                tipo_doc_val = "Expediente"
            dlg.destroy()
            if edit_obj:
                # Editar en lugar de agregar
                edit_obj["numero"].set(desc)
                edit_obj["tipo_doc"].set(tipo_doc_val)
            else:
                self.agregar_ddt_row(data={"numero": desc, "tipo_doc": tipo_doc_val, "producto": "", 
                                           "pos_arancel": "", "litros": "", "kilos": "", "densidad": "",
                                           "num_planilla": "", "valor_litro": ""})

        f_bot = tk.Frame(dlg)
        f_bot.pack(pady=10)
        tk.Button(f_bot, text="ACEPTAR", bg="#27AE60", fg="white", font=("Arial", 8, "bold"), command=aceptar).pack(side="left", padx=10)
        tk.Button(f_bot, text="Cancelar", bg="#E74C3C", fg="white", font=("Arial", 10), command=dlg.destroy).pack(side="left", padx=10)

    def agregar_ddt_row(self, def_prod="", data=None):
        self.ddt_counter += 1
        did = str(self.ddt_counter)
        obj = {
            "id": did,
            "numero": tk.StringVar(value=data["numero"] if data else ""),
            "num_planilla": tk.StringVar(value=data["num_planilla"] if data and "num_planilla" in data else ""),
            "tipo_doc": tk.StringVar(value=data["tipo_doc"] if data and "tipo_doc" in data else "Detallada"),
            "producto": tk.StringVar(value=data["producto"] if data else def_prod),
            "pos_arancel": tk.StringVar(value=data["pos_arancel"] if data else ""),
            "litros": tk.StringVar(value=data["litros"] if data else ""),
            "kilos": tk.StringVar(value=data["kilos"] if data else ""),
            "densidad": tk.StringVar(value=data["densidad"] if data else ""),
            "valor_litro": tk.StringVar(value=data["valor_litro"] if data and "valor_litro" in data else ""),
            "divisa": tk.StringVar(value=data["divisa"] if data and "divisa" in data else "ARS"),
            "tipo_cambio": tk.StringVar(value=data["tipo_cambio"] if data and "tipo_cambio" in data else ""),
            "salidas": [], "main_frame": None, "salidas_frame": None
        }
        # ── Actores del documento (cada detallada puede tener su propio
        #    despachante / importador-exportador / ATA). Al agregar un doc
        #    nuevo se precargan desde el primer documento que los tenga. ──
        def _actor_ini(k):
            if data is not None:
                return data.get(k, "")
            for d_prev in self.ddt_data:
                v_prev = d_prev.get(k)
                if isinstance(v_prev, tk.StringVar) and v_prev.get().strip():
                    return v_prev.get()
            return ""
        for _ak in self.DDT_ACTOR_KEYS:
            obj[_ak] = tk.StringVar(value=_actor_ini(_ak))
        obj["litros"].trace_add("write", lambda *args: self.auto_calc_densidad(obj["litros"], obj["kilos"], obj["densidad"]))
        obj["kilos"].trace_add("write", lambda *args: self.auto_calc_densidad(obj["litros"], obj["kilos"], obj["densidad"]))

        frame = ttk.LabelFrame(self.ddt_stack, text=f"Item Documento #{self.ddt_counter}")
        frame.pack(fill="x", pady=10, padx=5)
        obj["main_frame"] = frame
        # Actualizar título del LabelFrame cuando cambia la descripción
        def update_frame_title(*args, f=frame, o=obj, n=self.ddt_counter):
            desc = o["numero"].get().strip()
            if desc:
                f.configure(text=f"Item #{n}: {desc}")
            else:
                f.configure(text=f"Item Documento #{n}")
        obj["numero"].trace_add("write", update_frame_title)
        update_frame_title()  # Actualizar de inmediato si ya tiene datos
        f_header = ttk.Frame(frame)
        f_header.pack(fill="x", padx=5, pady=5)
        # ROW 0: Descripcion | entry | Modificar | N°Planilla | entry | Producto | entry | Pos.Aranc | entry | [ELIMINAR]
        tk.Label(f_header, text="Doc:", font=("Arial", 8, "bold")).grid(row=0, column=0, sticky="e", padx=2)
        e_num = ttk.Entry(f_header, textvariable=obj["numero"], width=28, state="readonly")
        e_num.grid(row=0, column=1, padx=3, sticky="ew")
        tk.Button(f_header, text="Modificar", bg="#1976D2", fg="white", font=("Arial", 8, "bold"),
                  command=lambda o=obj: self.popup_tipo_documento(edit_obj=o)).grid(row=0, column=2, padx=3)
        tk.Label(f_header, text="Producto:", font=("Arial", 8, "bold")).grid(row=0, column=3, sticky="e", padx=2)
        ttk.Entry(f_header, textvariable=obj["producto"], width=18).grid(row=0, column=4, padx=3, sticky="ew")
        tk.Label(f_header, text="Pos.Aranc:", font=("Arial", 8, "bold")).grid(row=0, column=5, sticky="e", padx=2)
        ttk.Entry(f_header, textvariable=obj["pos_arancel"], width=22).grid(row=0, column=6, padx=3, sticky="ew")
        # ROW 1: Litros | entry | Kilos | entry | Densidad | entry | $/Litro | entry | Divisa | combo | T/C | entry
        tk.Label(f_header, text="Litros:", font=("Arial", 9)).grid(row=1, column=0, sticky="e", padx=2, pady=2)
        ttk.Entry(f_header, textvariable=obj["litros"], width=12).grid(row=1, column=1, sticky="ew")
        tk.Label(f_header, text="Kilos:", font=("Arial", 9)).grid(row=1, column=2, sticky="e", padx=2)
        ttk.Entry(f_header, textvariable=obj["kilos"], width=12).grid(row=1, column=3)
        tk.Label(f_header, text="Densidad:", font=("Arial", 8, "bold"), fg="blue").grid(row=1, column=4, sticky="e", padx=2)
        ttk.Entry(f_header, textvariable=obj["densidad"], width=12, state="readonly").grid(row=1, column=5, sticky="ew")
        tk.Label(f_header, text="$/Litro:", font=("Arial", 8, "bold"), fg="#6A1B9A").grid(row=1, column=6, sticky="e", padx=2)
        ttk.Entry(f_header, textvariable=obj["valor_litro"], width=12).grid(row=1, column=7)
        tk.Label(f_header, text="Divisa:", font=("Arial", 8, "bold"), fg="#6A1B9A").grid(row=1, column=8, sticky="e", padx=2)
        cb_divisa = ttk.Combobox(f_header, textvariable=obj["divisa"], values=["ARS", "USD", "EUR", "BRL", "GBP", "Otra"], state="readonly", width=6)
        cb_divisa.grid(row=1, column=9, padx=2)
        tk.Label(f_header, text="T/C:", font=("Arial", 9), fg="#6A1B9A").grid(row=1, column=10, sticky="e", padx=2)
        ttk.Entry(f_header, textvariable=obj["tipo_cambio"], width=10).grid(row=1, column=11, padx=2)
        # ROW 2: Descripción divisa (si Otra) + ELIMINAR al final
        tk.Button(f_header, text="  ELIMINAR  ", bg="red", fg="white", font=("Arial", 8, "bold"),
                  command=lambda: self.borrar_ddt(obj)).grid(row=2, column=9, columnspan=3, padx=8, pady=3, sticky="e")
        # Campo descripción de divisa (visible solo si "Otra")
        obj["divisa_desc"] = tk.StringVar(value=data["divisa_desc"] if data and "divisa_desc" in data else "")
        lbl_divisa_desc = tk.Label(f_header, text="Desc. Divisa:", font=("Arial", 9), fg="#6A1B9A")
        e_divisa_desc = ttk.Entry(f_header, textvariable=obj["divisa_desc"], width=12)
        def toggle_divisa_desc(*args):
            if obj["divisa"].get() == "Otra":
                lbl_divisa_desc.grid(row=2, column=0, padx=2, sticky="e", columnspan=2)
                e_divisa_desc.grid(row=2, column=2, padx=2, columnspan=5, sticky="ew")
            else:
                lbl_divisa_desc.grid_remove()
                e_divisa_desc.grid_remove()
        obj["divisa"].trace_add("write", toggle_divisa_desc)
        toggle_divisa_desc()
        # ROW 3-4: Actores del documento (despachante / imp-exp / ATA + CUITs)
        _fga = ("Arial", 8, "bold")
        tk.Label(f_header, text="Despachante:", font=_fga, fg="#1B4F72").grid(row=3, column=0, sticky="e", padx=2, pady=(8, 0))
        ttk.Entry(f_header, textvariable=obj["despachante"], width=28).grid(row=3, column=1, sticky="ew", padx=3, pady=(8, 0))
        tk.Label(f_header, text="CUIT:", font=_fga, fg="#1B4F72").grid(row=3, column=2, sticky="e", padx=2, pady=(8, 0))
        e_cd = tk.Entry(f_header, textvariable=obj["cuit_desp"], width=14)
        e_cd.grid(row=3, column=3, sticky="w", padx=3, pady=(8, 0))
        tk.Label(f_header, text="Imp/Exp:", font=_fga, fg="#1B4F72").grid(row=3, column=4, sticky="e", padx=2, pady=(8, 0))
        ttk.Entry(f_header, textvariable=obj["impexp"], width=24).grid(row=3, column=5, columnspan=2, sticky="ew", padx=3, pady=(8, 0))
        tk.Label(f_header, text="CUIT:", font=_fga, fg="#1B4F72").grid(row=3, column=7, sticky="e", padx=2, pady=(8, 0))
        e_ci = tk.Entry(f_header, textvariable=obj["cuit_impexp"], width=14)
        e_ci.grid(row=3, column=8, columnspan=2, sticky="w", padx=3, pady=(8, 0))
        tk.Label(f_header, text="ATA:", font=_fga, fg="#1B4F72").grid(row=4, column=0, sticky="e", padx=2, pady=(2, 4))
        ttk.Entry(f_header, textvariable=obj["ata"], width=28).grid(row=4, column=1, sticky="ew", padx=3, pady=(2, 4))
        tk.Label(f_header, text="CUIT:", font=_fga, fg="#1B4F72").grid(row=4, column=2, sticky="e", padx=2, pady=(2, 4))
        e_ca = tk.Entry(f_header, textvariable=obj["cuit_ata"], width=14)
        e_ca.grid(row=4, column=3, sticky="w", padx=3, pady=(2, 4))
        for _ew, _ev in ((e_cd, obj["cuit_desp"]), (e_ci, obj["cuit_impexp"]), (e_ca, obj["cuit_ata"])):
            _ew.bind("<FocusOut>", lambda ev, wdg=_ew, v=_ev: self.on_cuit_validate(wdg, v))
        def _copiar_actores(o=obj):
            src = next((d for d in self.ddt_data if d is not o and any(
                isinstance(d.get(k), tk.StringVar) and d.get(k).get().strip()
                for k in self.DDT_ACTOR_KEYS)), None)
            if not src: return
            for k in self.DDT_ACTOR_KEYS:
                sv = src.get(k)
                if isinstance(sv, tk.StringVar): o[k].set(sv.get())
        tk.Button(f_header, text="⧉ Copiar del 1er doc", bg="#5D6D7E", fg="white", font=("Arial", 8),
                  command=_copiar_actores).grid(row=4, column=4, columnspan=3, sticky="w", padx=3, pady=(2, 4))
        # T/C now in row=1 cols 10-11 above
        f_sub = ttk.Frame(frame)
        f_sub.pack(fill="x", padx=20, pady=5)
        tk.Button(f_sub, text="+ Agregar Salida", bg="#1976D2", fg="white", font=("Arial", 8), command=lambda: self.agregar_salida(obj)).pack(anchor="w")
        obj["salidas_frame"] = ttk.Frame(f_sub)
        obj["salidas_frame"].pack(fill="x", pady=5)
        f_titles = ttk.Frame(obj["salidas_frame"])
        f_titles.pack(fill="x")
        tk.Label(f_titles, text="N° Salida", width=20, fg="gray", font=("Arial", 7)).pack(side="left", padx=2)
        tk.Label(f_titles, text="Litros", width=12, fg="gray", font=("Arial", 7)).pack(side="left", padx=2)
        tk.Label(f_titles, text="Kilos", width=12, fg="gray", font=("Arial", 7)).pack(side="left", padx=2)
        tk.Label(f_titles, text="Densidad", width=12, fg="blue", font=("Arial", 7)).pack(side="left", padx=2)
        if data and "salidas" in data:
            for s_data in data["salidas"]: self.agregar_salida(obj, s_data)
        self.ddt_data.append(obj)
        self.actualizar_combos_ddt()

    def agregar_funcionario_row(self, data=None):
        self.func_counter += 1
        funciones = db_get_funciones()
        _apellido_default = data.get("apellido", "") if data else ""
        _nombre_default   = data.get("nombre",   "") if data else ""
        if data and not _apellido_default and _nombre_default:
            parts = _nombre_default.strip().split(" ", 1)
            _apellido_default = parts[0]
            _nombre_default   = parts[1] if len(parts) > 1 else ""
        obj = {
            "cuil":     tk.StringVar(value=data["cuil"]    if data else ""),
            "legajo":   tk.StringVar(value=data["legajo"]  if data else ""),
            "apellido": tk.StringVar(value=_apellido_default),
            "nombre":   tk.StringVar(value=_nombre_default),
            "funcion":  tk.StringVar(value=data["funcion"] if data else funciones[0]),
            "frame":    None,
        }
        row = ttk.Frame(self.func_stack)
        row.pack(fill="x", pady=2)
        obj["frame"] = row

        def _autocomplete_from_db(*args):
            """Al salir del campo CUIL o APELLIDO, busca en DB y completa."""
            cuil_v = obj["cuil"].get().strip()
            apell_v = obj["apellido"].get().strip()
            found = []
            if cuil_v and len(cuil_v) >= 4:
                found = db_buscar_funcionarios(cuil_v, "cuil")
            if not found and apell_v and len(apell_v) >= 3:
                found = db_buscar_funcionarios(apell_v, "apellido")
            if found:
                r = found[0]
                obj["cuil"].set(r["cuil"]); obj["legajo"].set(r["legajo"])
                obj["apellido"].set(r["apellido"]); obj["nombre"].set(r["nombre"])
                obj["funcion"].set(r["funcion"] if r["funcion"] in funciones else funciones[0])

        def _save_to_db(*args):
            """Al salir del campo LEGAJO, guarda o actualiza en DB si hay datos suficientes."""
            cuil = obj["cuil"].get().strip()
            legajo = obj["legajo"].get().strip()
            apellido = obj["apellido"].get().strip()
            nombre = obj["nombre"].get().strip()
            funcion = obj["funcion"].get()
            aduana = self.get_var("car_lugar", "").get()
            if cuil and apellido:
                db_guardar_funcionario(cuil, legajo, apellido, nombre, funcion, aduana)

        e_cuil = tk.Entry(row, textvariable=obj["cuil"], width=16, font=("Arial", 9))
        e_cuil.grid(row=0, column=0, padx=2, sticky="w")
        e_cuil.bind("<FocusOut>", lambda ev, w=e_cuil, v=obj["cuil"]: (self.on_cuit_validate(w, v), _autocomplete_from_db()))
        e_cuil.bind("<Return>", lambda ev: _autocomplete_from_db())

        e_leg = ttk.Entry(row, textvariable=obj["legajo"], width=13)
        e_leg.grid(row=0, column=1, padx=2, sticky="w")
        e_leg.bind("<FocusOut>", lambda ev: _save_to_db())

        e_apell = ttk.Entry(row, textvariable=obj["apellido"], width=22)
        e_apell.grid(row=0, column=2, padx=2, sticky="w")
        e_apell.bind("<FocusOut>", lambda ev: _autocomplete_from_db())
        e_apell.bind("<Return>", lambda ev: _autocomplete_from_db())

        ttk.Entry(row, textvariable=obj["nombre"], width=22).grid(row=0, column=3, padx=2, sticky="w")
        cb_fun = ttk.Combobox(row, textvariable=obj["funcion"], values=funciones, state="readonly", width=28)
        cb_fun.grid(row=0, column=4, padx=2, sticky="w")
        cb_fun.bind("<<ComboboxSelected>>", lambda ev: _save_to_db())

        tk.Button(row, text="X", bg="#E74C3C", fg="white",
                  command=lambda o=obj: (self.func_stack.pack_propagate(True),
                                        o["frame"].destroy(),
                                        self.funcionarios_data.remove(o))
                  ).grid(row=0, column=5, padx=2)

        self.funcionarios_data.append(obj)

    def buscar_y_agregar_funcionario_db(self):
        """Popup busqueda rapida en DB de funcionarios para agregar a caratula."""
        try:
            top = tk.Toplevel(self.root)
            top.title("Buscar Funcionario en Base de Datos")
            top.geometry("920x520")
            top.resizable(True, True)
            top.grab_set()

            fh = tk.Frame(top, bg="#1D6A39")
            fh.pack(fill="x")
            tk.Label(fh, text="BUSCAR Y AGREGAR FUNCIONARIOS A LA CARATULA",
                     bg="#1D6A39", fg="white", font=("Arial", 10, "bold")).pack(side="left", padx=14, pady=8)
            tk.Label(fh, text="Seleccion multiple con Ctrl+Click  |  Doble click = agregar y cerrar",
                     bg="#1D6A39", fg="#A9DFBF", font=("Arial", 8)).pack(side="left")

            f_srch = tk.Frame(top, bg="#EBF5FB")
            f_srch.pack(fill="x")
            tk.Label(f_srch, text="Buscar:", bg="#EBF5FB",
                     font=("Arial", 9, "bold")).pack(side="left", padx=8, pady=6)
            v_q = tk.StringVar()
            e_q = tk.Entry(f_srch, textvariable=v_q, width=34, font=("Arial", 10))
            e_q.pack(side="left", padx=4, pady=6)
            tk.Label(f_srch, text="(apellido, CUIL o funcion — vacio = todos)",
                     bg="#EBF5FB", fg="gray", font=("Arial", 8)).pack(side="left", padx=6)

            cols   = ("cuil", "legajo", "apellido", "nombre", "funcion", "aduana")
            hdrs   = ("CUIL",  "Legajo",  "Apellido",  "Nombre",   "Funcion",   "Aduana")
            widths = (120,      80,        150,          150,         140,          120)
            f_tree = tk.Frame(top)
            f_tree.pack(fill="both", expand=True, padx=10, pady=6)
            tree = ttk.Treeview(f_tree, columns=cols, show="headings",
                                selectmode="extended", height=14)
            for c, h, w in zip(cols, hdrs, widths):
                tree.heading(c, text=h)
                tree.column(c, width=w, minwidth=40)
            vsb = ttk.Scrollbar(f_tree, orient="vertical", command=tree.yview)
            tree.configure(yscrollcommand=vsb.set)
            vsb.pack(side="right", fill="y")
            tree.pack(fill="both", expand=True)
            tree.tag_configure("odd",  background="#EAF4FB")
            tree.tag_configure("even", background="white")

            def _load(q=""):
                for row in tree.get_children():
                    tree.delete(row)
                if q:
                    rows = (db_buscar_funcionarios(q, "apellido") +
                            db_buscar_funcionarios(q, "cuil") +
                            db_buscar_funcionarios(q, "funcion"))
                    # Dedup por registro completo: un agente con varias
                    # funciones aparece una vez POR FUNCIÓN
                    seen = set(); unique = []
                    for r in rows:
                        k = (r.get("cuil",""), r.get("legajo",""), r.get("funcion",""))
                        if k not in seen:
                            seen.add(k); unique.append(r)
                    rows = unique
                else:
                    rows = db_todos_funcionarios()
                for i, r in enumerate(rows):
                    tree.insert("", "end", tags=("odd" if i%2 else "even",), values=(
                        r.get("cuil",""), r.get("legajo",""),
                        r.get("apellido",""), r.get("nombre",""),
                        r.get("funcion",""), r.get("aduana","")
                    ))

            def _on_search(*_):  _load(v_q.get().strip())
            v_q.trace_add("write", _on_search)
            e_q.bind("<Return>", _on_search)

            def _agregar():
                sels = tree.selection()
                if not sels:
                    messagebox.showwarning("Sin seleccion",
                        "Seleccione al menos un funcionario.", parent=top)
                    return
                for s in sels:
                    v = tree.item(s, "values")
                    self.agregar_funcionario_row({
                        "cuil": v[0], "legajo": v[1],
                        "apellido": v[2], "nombre": v[3], "funcion": v[4]
                    })
                top.destroy()

            tree.bind("<Double-1>", lambda e: _agregar())

            f_bot = tk.Frame(top, bg="#2C3E50")
            f_bot.pack(fill="x", side="bottom")
            tk.Button(f_bot, text="Agregar seleccionados a caratula",
                      bg="#27AE60", fg="white", font=("Arial", 9, "bold"),
                      command=_agregar, cursor="hand2"
                      ).pack(side="left", padx=12, pady=8, ipadx=10, ipady=3)
            tk.Button(f_bot, text="Cancelar", bg="#7F8C8D", fg="white",
                      font=("Arial", 8), command=top.destroy
                      ).pack(side="right", padx=12, pady=8)
            _load()
            e_q.focus_set()
        except Exception as e:
            import traceback; traceback.print_exc()
            messagebox.showerror("Error", str(e))

    def abrir_gestor_funcionarios_db(self):
        """Ventana completa de gestión de la base de datos de funcionarios: listar, agregar, editar, eliminar, importar CSV."""
        try:
            top = tk.Toplevel(self.root)
            top.title("Base de Datos de Funcionarios")
            top.geometry("1000x620")
            top.resizable(True, True)

            # ── Header ──────────────────────────────────────────────────────
            fh = tk.Frame(top, bg="#1B3A5C")
            fh.pack(fill="x")
            tk.Label(fh, text="BASE DE DATOS DE FUNCIONARIOS", bg="#1B3A5C", fg="white",
                     font=("Arial", 10, "bold")).pack(side="left", padx=14, pady=8)
            tk.Label(fh, text="Agregue, edite o elimine funcionarios. Importe desde CSV.",
                     bg="#1B3A5C", fg="#AED6F1", font=("Arial", 8)).pack(side="left")

            # ── Barra de búsqueda + botones de acción ────────────────────────
            f_act = tk.Frame(top, bg="#EBF5FB", bd=1, relief="flat")
            f_act.pack(fill="x", padx=0, pady=0)
            tk.Label(f_act, text="Buscar:", bg="#EBF5FB", font=("Arial", 8, "bold")).pack(side="left", padx=8, pady=6)
            v_search = tk.StringVar()
            e_search = tk.Entry(f_act, textvariable=v_search, width=26, font=("Arial", 9))
            e_search.pack(side="left", padx=4, pady=6)
            tk.Button(f_act, text="Agregar nuevo", bg="#27AE60", fg="white",
                      font=("Arial", 8, "bold"), command=lambda: _abrir_form()).pack(side="left", padx=8, pady=6, ipadx=6, ipady=2)
            tk.Button(f_act, text="Editar seleccionado", bg="#2980B9", fg="white",
                      font=("Arial", 8, "bold"), command=lambda: _editar()).pack(side="left", padx=4, pady=6, ipadx=6, ipady=2)
            tk.Button(f_act, text="Usar en operacion", bg="#8E44AD", fg="white",
                      font=("Arial", 8, "bold"), command=lambda: _usar()).pack(side="left", padx=4, pady=6, ipadx=6, ipady=2)
            tk.Button(f_act, text="Importar CSV", bg="#D35400", fg="white",
                      font=("Arial", 8, "bold"), command=lambda: _importar_csv()).pack(side="left", padx=4, pady=6, ipadx=6, ipady=2)
            tk.Button(f_act, text="Eliminar", bg="#E74C3C", fg="white",
                      font=("Arial", 8, "bold"), command=lambda: _delete()).pack(side="left", padx=4, pady=6, ipadx=6, ipady=2)
            lbl_count = tk.Label(f_act, text="", bg="#EBF5FB", font=("Arial", 8), fg="#1B3A5C")
            lbl_count.pack(side="right", padx=12)

            # ── Treeview ─────────────────────────────────────────────────────
            f_tree = tk.Frame(top)
            f_tree.pack(fill="both", expand=True, padx=8, pady=4)
            cols = ("CUIL", "Legajo", "Apellido", "Nombre", "Funcion", "Aduana", "Lugar Op.")
            tree = ttk.Treeview(f_tree, columns=cols, show="headings", height=18, selectmode="extended")
            tree.heading("CUIL",     text="CUIL",        command=lambda: _sort("CUIL"))
            tree.heading("Legajo",   text="Legajo",      command=lambda: _sort("Legajo"))
            tree.heading("Apellido", text="Apellido",    command=lambda: _sort("Apellido"))
            tree.heading("Nombre",   text="Nombre",      command=lambda: _sort("Nombre"))
            tree.heading("Funcion",  text="Funcion",     command=lambda: _sort("Funcion"))
            tree.heading("Aduana",   text="Aduana",      command=lambda: _sort("Aduana"))
            tree.heading("Lugar Op.",text="Lugar Operativo", command=lambda: _sort("Lugar Op."))
            tree.column("CUIL",     width=120); tree.column("Legajo",   width=70)
            tree.column("Apellido", width=150); tree.column("Nombre",   width=130)
            tree.column("Funcion",  width=170); tree.column("Aduana",   width=150)
            tree.column("Lugar Op.",width=180)
            vsb = ttk.Scrollbar(f_tree, orient="vertical",   command=tree.yview)
            hsb = ttk.Scrollbar(f_tree, orient="horizontal", command=tree.xview)
            tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
            tree.grid(row=0, column=0, sticky="nsew")
            vsb.grid(row=0, column=1, sticky="ns")
            hsb.grid(row=1, column=0, sticky="ew")
            f_tree.grid_rowconfigure(0, weight=1); f_tree.grid_columnconfigure(0, weight=1)
            tree.bind("<Double-1>", lambda e: _editar())

            # ── Hint CSV ─────────────────────────────────────────────────────
            f_hint = tk.Frame(top, bg="#FEF9E7")
            f_hint.pack(fill="x", padx=8, pady=2)
            tk.Label(f_hint, text="CSV para importar: cuil,legajo,apellido,nombre,funcion,aduana,lugar_operativo  (una fila por funcionario, puede tener encabezado)",
                     bg="#FEF9E7", fg="#6E4B00", font=("Arial", 7), anchor="w").pack(fill="x", padx=8, pady=3)

            # ── Footer ───────────────────────────────────────────────────────
            f_bot = tk.Frame(top, bg="#2C3E50")
            f_bot.pack(fill="x", side="bottom")
            tk.Button(f_bot, text="Cerrar", bg="#7F8C8D", fg="white",
                      font=("Arial", 8, "bold"), command=top.destroy).pack(side="right", padx=10, pady=6, ipadx=8, ipady=2)

            # ── Sort state ───────────────────────────────────────────────────
            _sort_col = [None]; _sort_rev = [False]

            def _load(query=""):
                tree.delete(*tree.get_children())
                if query:
                    rows = db_buscar_funcionarios(query, "apellido") + db_buscar_funcionarios(query, "cuil") + db_buscar_funcionarios(query, "funcion")
                    seen = set(); unique = []
                    for r in rows:
                        k = (r["cuil"], r["legajo"], r["funcion"])
                        if k not in seen: seen.add(k); unique.append(r)
                else:
                    unique = db_todos_funcionarios()
                for r in unique:
                    tree.insert("", "end", values=(r["cuil"],r["legajo"],r["apellido"],r["nombre"],r["funcion"],r["aduana"],r.get("lugar_operativo","")))
                lbl_count.config(text=f"{len(unique)} registro(s)")

            def _sort(col):
                items = [(tree.set(iid, col), iid) for iid in tree.get_children("")]
                rev = _sort_col[0] == col and not _sort_rev[0]
                items.sort(reverse=rev)
                for i, (_, iid) in enumerate(items): tree.move(iid, "", i)
                _sort_col[0] = col; _sort_rev[0] = rev

            def _on_search(*a): _load(v_search.get().strip())
            v_search.trace_add("write", _on_search)
            e_search.bind("<Return>", _on_search)

            def _abrir_form(existing_vals=None):
                """Formulario para agregar o editar un funcionario."""
                frm = tk.Toplevel(top)
                frm.title("Nuevo Funcionario" if not existing_vals else "Editar Funcionario")
                frm.geometry("480x400")
                frm.resizable(False, False)
                frm.grab_set()
                fh2 = tk.Frame(frm, bg="#1B3A5C"); fh2.pack(fill="x")
                tk.Label(fh2, text="DATOS DEL FUNCIONARIO", bg="#1B3A5C", fg="white",
                         font=("Arial", 9, "bold")).pack(padx=12, pady=8)
                ff = tk.Frame(frm, pady=8); ff.pack(fill="both", expand=True, padx=16)
                # Opciones de aduana desde la DB
                _adu_list = db_get_aduanas()
                _adu_opts = [f"{a['codigo']} - {a['nombre']}" for a in _adu_list]
                funcion_opciones = db_get_funciones()
                vs = {}
                simple_fields = [("CUIL:", "cuil"), ("Legajo:", "legajo"),
                                  ("Apellido:", "apellido"), ("Nombre:", "nombre")]
                for i, (lbl, key) in enumerate(simple_fields):
                    tk.Label(ff, text=lbl, font=("Arial", 8, "bold"), width=14, anchor="e").grid(row=i, column=0, sticky="e", pady=3, padx=4)
                    v = tk.StringVar(value=existing_vals.get(key, "") if existing_vals else "")
                    vs[key] = v
                    tk.Entry(ff, textvariable=v, width=30, font=("Arial", 9)).grid(row=i, column=1, sticky="w", pady=3, padx=4)
                # Funcion combobox
                v_fun = tk.StringVar(value=existing_vals.get("funcion","") if existing_vals else (funcion_opciones[0] if funcion_opciones else ""))
                vs["funcion"] = v_fun
                tk.Label(ff, text="Funcion:", font=("Arial", 8, "bold"), width=14, anchor="e").grid(row=4, column=0, sticky="e", pady=3, padx=4)
                ttk.Combobox(ff, textvariable=v_fun, values=funcion_opciones, width=28, state="normal").grid(row=4, column=1, sticky="w", pady=3, padx=4)
                # Aduana combobox desde DB
                v_adu = tk.StringVar()
                vs["aduana"] = v_adu
                if existing_vals and existing_vals.get("aduana"):
                    adu_raw = existing_vals["aduana"]
                    match = [o for o in _adu_opts if adu_raw.split(" - ")[0].zfill(3) in o or adu_raw in o]
                    v_adu.set(match[0] if match else adu_raw)
                else:
                    cur_adu = self.get_var("car_lugar").get()
                    match = [o for o in _adu_opts if cur_adu.split(" - ")[0].zfill(3) in o]
                    v_adu.set(match[0] if match else (_adu_opts[0] if _adu_opts else ""))
                tk.Label(ff, text="Aduana:", font=("Arial", 8, "bold"), width=14, anchor="e").grid(row=5, column=0, sticky="e", pady=3, padx=4)
                cb_adu = ttk.Combobox(ff, textvariable=v_adu, values=_adu_opts, state="normal", width=28)
                cb_adu.grid(row=5, column=1, sticky="w", pady=3, padx=4)
                tk.Label(ff, text="(Solo aduanas registradas en ABM de Aduanas)",
                         font=("Arial", 7), fg="#888", anchor="w").grid(row=6, column=1, sticky="w", padx=4)

                # ── Lugar Operativo (filtrado por aduana seleccionada) ─────────────
                v_lop = tk.StringVar(value=existing_vals.get("lugar_operativo","") if existing_vals else "")
                vs["lugar_operativo"] = v_lop
                tk.Label(ff, text="Lugar Operativo:", font=("Arial", 8, "bold"), width=14, anchor="e").grid(row=7, column=0, sticky="e", pady=3, padx=4)
                cb_lop = ttk.Combobox(ff, textvariable=v_lop, values=[], state="normal", width=28)
                cb_lop.grid(row=7, column=1, sticky="w", pady=3, padx=4)
                tk.Label(ff, text="(Lugares operativos de la aduana seleccionada)",
                         font=("Arial", 7), fg="#888", anchor="w").grid(row=8, column=1, sticky="w", padx=4)

                def _update_lop(*a):
                    """Filtra lugares operativos según la aduana elegida."""
                    adu_sel = v_adu.get().strip()
                    adu_cod = adu_sel.split(" - ")[0].strip().zfill(3) if " - " in adu_sel else adu_sel.strip().zfill(3)
                    lops = db_get_lugares_operativos(adu_cod)
                    lop_opts = [f"{l['codigo']} - {l['descripcion']}" for l in lops]
                    cb_lop["values"] = lop_opts
                    # Mantener el valor si aún es válido, sino limpiar
                    cur_lop = v_lop.get()
                    if cur_lop and cur_lop not in lop_opts:
                        # Intentar encontrar por código
                        match_l = [o for o in lop_opts if cur_lop.split(" - ")[0] in o]
                        v_lop.set(match_l[0] if match_l else "")

                v_adu.trace_add("write", _update_lop)
                _update_lop()  # cargar al abrir

                # Validación de CUIL
                def _validar_cuil(val):
                    cuil = val.replace("-","").replace(".","").replace(" ","")
                    if len(cuil) == 11 and cuil.isdigit(): return True, cuil
                    return False, cuil
                def _guardar_form():
                    ok_cuil, cuil_clean = _validar_cuil(vs["cuil"].get())
                    if not ok_cuil:
                        messagebox.showwarning("CUIL inválido", "El CUIL debe tener 11 dígitos.", parent=frm); return
                    apellido = vs["apellido"].get().strip()
                    if not apellido:
                        messagebox.showwarning("Dato faltante", "El Apellido es obligatorio.", parent=frm); return
                    adu_val = vs["aduana"].get().strip()
                    lop_val = vs["lugar_operativo"].get().strip()
                    legajo_new = vs["legajo"].get().strip()
                    # If editing and cuil/legajo changed, delete old record first
                    if existing_vals:
                        old_cuil = existing_vals.get("cuil", "")
                        old_legajo = existing_vals.get("legajo", "")
                        old_funcion = existing_vals.get("funcion", "")
                        if (old_cuil != cuil_clean or old_legajo != legajo_new
                                or old_funcion != vs["funcion"].get().strip()):
                            db_eliminar_funcionario(old_cuil, old_legajo, old_funcion)
                    db_guardar_funcionario(cuil_clean, legajo_new,
                                          apellido, vs["nombre"].get().strip(),
                                          vs["funcion"].get().strip(), adu_val, lop_val)
                    _load(v_search.get()); frm.destroy()
                fb2 = tk.Frame(frm, bg="#2C3E50"); fb2.pack(fill="x", side="bottom")
                tk.Button(fb2, text="Guardar", bg="#27AE60", fg="white", font=("Arial", 8, "bold"),
                          command=_guardar_form).pack(side="left", padx=10, pady=6, ipadx=10, ipady=2)
                tk.Button(fb2, text="Cancelar", bg="#7F8C8D", fg="white", font=("Arial", 8),
                          command=frm.destroy).pack(side="right", padx=10, pady=6)

            def _editar():
                sel = tree.selection()
                if not sel: return
                vals = tree.item(sel[0], "values")
                existing = {"cuil":vals[0],"legajo":vals[1],"apellido":vals[2],"nombre":vals[3],"funcion":vals[4],"aduana":vals[5],"lugar_operativo":vals[6] if len(vals)>6 else ""}
                _abrir_form(existing)

            def _usar():
                sel = tree.selection()
                if not sel: return
                cur_adu_cod = ""
                cur_lugar = self.get_var("car_lugar", "").get()
                if cur_lugar and " - " in cur_lugar:
                    cur_adu_cod = cur_lugar.split(" - ")[0].strip().zfill(3)
                elif cur_lugar:
                    cur_adu_cod = cur_lugar.strip().zfill(3)
                advertencias = []
                for item in sel:
                    vals = tree.item(item, "values")
                    data = {"cuil":vals[0],"legajo":vals[1],"apellido":vals[2],"nombre":vals[3],"funcion":vals[4],"aduana":vals[5],"lugar_operativo":vals[6] if len(vals)>6 else ""}
                    # Validación aduanero: debe pertenecer a la aduana de la medición
                    if data["funcion"] == "ADUANERO" and cur_adu_cod:
                        func_adu_cod = data["aduana"].split(" - ")[0].strip().zfill(3) if " - " in data["aduana"] else data["aduana"].strip().zfill(3)
                        if func_adu_cod and func_adu_cod != cur_adu_cod:
                            advertencias.append(f"{data['apellido']}, {data['nombre']} (Aduana {data['aduana']})")
                if advertencias:
                    msg = ("⚠️ ADVERTENCIA: Los siguientes ADUANEROS pertenecen a una aduana diferente a la de la medición actual "
                           f"(Aduana {cur_adu_cod}):\n\n" + "\n".join(advertencias) +
                           "\n\n¿Desea agregarlos de todas formas?")
                    if not messagebox.askyesno("Conflicto de Aduana", msg, parent=top):
                        return
                for item in sel:
                    vals = tree.item(item, "values")
                    data = {"cuil":vals[0],"legajo":vals[1],"apellido":vals[2],"nombre":vals[3],"funcion":vals[4],"aduana":vals[5],"lugar_operativo":vals[6] if len(vals)>6 else ""}
                    self.agregar_funcionario_row(data=data)
                messagebox.showinfo("OK", f"{len(sel)} funcionario(s) agregado(s) a la operación.", parent=top)

            def _delete():
                sel = tree.selection()
                if not sel: return
                if not messagebox.askyesno("Confirmar", f"Eliminar {len(sel)} registro(s) seleccionado(s) de la base de datos?", parent=top): return
                for item in sel:
                    vals = tree.item(item, "values")
                    db_eliminar_funcionario(vals[0], vals[1], vals[4] if len(vals) > 4 else None)
                _load(v_search.get())

            def _importar_csv():
                """Importar funcionarios desde CSV."""
                f_path = filedialog.askopenfilename(
                    title="Importar Funcionarios desde CSV",
                    filetypes=[("CSV","*.csv"),("Texto","*.txt"),("Todos","*.*")],
                    parent=top)
                if not f_path: return
                try:
                    import csv as csv_mod
                    importados = 0; errores = 0
                    with open(f_path, "r", encoding="utf-8-sig") as f_csv:
                        # Detectar si tiene encabezado
                        sample = f_csv.read(512); f_csv.seek(0)
                        has_header = any(kw in sample.lower() for kw in ["cuil","apellido","legajo","nombre","funcion"])
                        reader = csv_mod.reader(f_csv)
                        if has_header:
                            header_row = next(reader, None)
                            # Map columns by name if header exists
                            if header_row:
                                hdr = [h.strip().lower().replace("ó","o").replace("ú","u").replace("í","i") for h in header_row]
                                def _idx(names):
                                    for nm in names:
                                        if nm in hdr: return hdr.index(nm)
                                    return -1
                                ci = {"cuil":_idx(["cuil"]),"legajo":_idx(["legajo","leg"]),"apellido":_idx(["apellido","apell"]),"nombre":_idx(["nombre","nom"]),"funcion":_idx(["funcion","func"]),"aduana":_idx(["aduana"]),"lugar_operativo":_idx(["lugar_operativo","lugar","lop"])}
                            else:
                                ci = {"cuil":0,"legajo":1,"apellido":2,"nombre":3,"funcion":4,"aduana":5,"lugar_operativo":6}
                        else:
                            ci = {"cuil":0,"legajo":1,"apellido":2,"nombre":3,"funcion":4,"aduana":5,"lugar_operativo":6}
                        for row in reader:
                            if not row or not any(row): continue
                            try:
                                def _g(key, default=""):
                                    idx = ci.get(key, -1)
                                    if idx < 0 or idx >= len(row): return default
                                    return row[idx].strip()
                                cuil = _g("cuil","").replace("-","").replace(".","").replace(" ","")
                                legajo = _g("legajo",""); apellido = _g("apellido",""); nombre = _g("nombre","")
                                funcion = _g("funcion","Verificador"); aduana = _g("aduana",""); lugar_operativo = _g("lugar_operativo","")
                                if len(cuil) == 11 and cuil.isdigit() and apellido:
                                    db_guardar_funcionario(cuil, legajo, apellido, nombre, funcion, aduana, lugar_operativo)
                                    importados += 1
                                else:
                                    errores += 1
                            except: errores += 1
                    _load(v_search.get())
                    messagebox.showinfo("Importacion CSV", f"Importados: {importados} funcionarios.\nFilas con error / saltadas: {errores}.", parent=top)
                except Exception as ex:
                    messagebox.showerror("Error", f"No se pudo leer el archivo:\n{ex}", parent=top)

            _load()
            e_search.focus_set()
        except Exception as e:
            traceback.print_exc()
            messagebox.showerror("Error", str(e))

    def abrir_gestor_funciones(self):
        """ABM simple para gestionar las funciones de funcionarios."""
        top = tk.Toplevel(self.root)
        top.title("Gestionar Funciones")
        top.geometry("400x420")
        top.resizable(False, False)
        top.grab_set()

        fh = tk.Frame(top, bg="#0D47A1"); fh.pack(fill="x")
        tk.Label(fh, text="FUNCIONES DE FUNCIONARIOS", bg="#0D47A1", fg="white",
                 font=("Arial", 10, "bold")).pack(padx=12, pady=8)

        frame_list = tk.Frame(top)
        frame_list.pack(fill="both", expand=True, padx=12, pady=8)

        scrollbar = tk.Scrollbar(frame_list)
        scrollbar.pack(side="right", fill="y")
        listbox = tk.Listbox(frame_list, font=("Arial", 10), yscrollcommand=scrollbar.set)
        listbox.pack(fill="both", expand=True)
        scrollbar.config(command=listbox.yview)

        def _refresh():
            listbox.delete(0, tk.END)
            for f in db_get_funciones():
                listbox.insert(tk.END, f)

        _refresh()

        frame_add = tk.Frame(top)
        frame_add.pack(fill="x", padx=12, pady=4)
        v_nueva = tk.StringVar()
        tk.Entry(frame_add, textvariable=v_nueva, width=30, font=("Arial", 10)).pack(side="left", padx=(0, 6))

        def _agregar():
            nombre = v_nueva.get().strip().upper()
            if not nombre:
                messagebox.showwarning("Aviso", "Ingrese un nombre de funcion.", parent=top)
                return
            if db_guardar_funcion(nombre):
                v_nueva.set("")
                _refresh()
            else:
                messagebox.showerror("Error", "No se pudo agregar la funcion.", parent=top)

        tk.Button(frame_add, text="Agregar", bg="#27AE60", fg="white",
                  font=("Arial", 9, "bold"), command=_agregar).pack(side="left")

        def _eliminar():
            sel = listbox.curselection()
            if not sel:
                messagebox.showwarning("Aviso", "Seleccione una funcion para eliminar.", parent=top)
                return
            nombre = listbox.get(sel[0])
            if messagebox.askyesno("Confirmar", f"Eliminar la funcion '{nombre}'?", parent=top):
                db_eliminar_funcion(nombre)
                _refresh()

        frame_btns = tk.Frame(top)
        frame_btns.pack(fill="x", padx=12, pady=(0, 10))
        tk.Button(frame_btns, text="Eliminar seleccionada", bg="#E74C3C", fg="white",
                  font=("Arial", 9, "bold"), command=_eliminar).pack(side="left")
        tk.Button(frame_btns, text="Cerrar", font=("Arial", 9),
                  command=top.destroy).pack(side="right")

    def abrir_gestor_aduanas_lop(self):
        """ABM completo de Aduanas y Lugares Operativos con SQLite."""
        try:
            top = tk.Toplevel(self.root)
            top.title("Gestión de Aduanas y Lugares Operativos")
            top.geometry("1100x680")
            top.resizable(True, True)

            # ── Header ──────────────────────────────────────────────────────────
            fh = tk.Frame(top, bg="#1B3A5C")
            fh.pack(fill="x")
            tk.Label(fh, text="GESTIÓN DE ADUANAS Y LUGARES OPERATIVOS",
                     bg="#1B3A5C", fg="white", font=("Arial", 11, "bold")).pack(side="left", padx=14, pady=10)
            tk.Label(fh, text="Administre las Aduanas habilitadas y sus Lugares Operativos asociados.",
                     bg="#1B3A5C", fg="#AED6F1", font=("Arial", 8)).pack(side="left", padx=4)

            # ── Notebook con dos pestañas ────────────────────────────────────────
            nb = ttk.Notebook(top)
            nb.pack(fill="both", expand=True, padx=6, pady=6)

            # ═══════════════════════════════════════════════════════════════════
            # PESTAÑA 1: ADUANAS
            # ═══════════════════════════════════════════════════════════════════
            tab_adu = tk.Frame(nb, bg="#F4F6F7")
            nb.add(tab_adu, text="  ADUANAS  ")

            # Toolbar aduanas
            ftb_a = tk.Frame(tab_adu, bg="#EBF5FB", bd=1, relief="flat")
            ftb_a.pack(fill="x", padx=0, pady=0)
            tk.Label(ftb_a, text="Filtrar:", bg="#EBF5FB", font=("Arial", 8, "bold")).pack(side="left", padx=8, pady=6)
            v_search_a = tk.StringVar()
            tk.Entry(ftb_a, textvariable=v_search_a, width=22, font=("Arial", 9)).pack(side="left", padx=4, pady=6)
            tk.Button(ftb_a, text="+ AGREGAR ADUANA", bg="#1A5276", fg="white",
                      font=("Arial", 8, "bold"), command=lambda: _abrir_form_aduana()).pack(side="left", padx=8, pady=6, ipadx=6, ipady=2)
            tk.Button(ftb_a, text="Editar", bg="#2980B9", fg="white",
                      font=("Arial", 8, "bold"), command=lambda: _editar_aduana()).pack(side="left", padx=4, pady=6, ipadx=6, ipady=2)
            tk.Button(ftb_a, text="Eliminar", bg="#E74C3C", fg="white",
                      font=("Arial", 8, "bold"), command=lambda: _del_aduana()).pack(side="left", padx=4, pady=6, ipadx=6, ipady=2)
            lbl_cnt_a = tk.Label(ftb_a, text="", bg="#EBF5FB", font=("Arial", 8), fg="#1B3A5C")
            lbl_cnt_a.pack(side="right", padx=12)

            # Treeview aduanas
            f_tr_a = tk.Frame(tab_adu)
            f_tr_a.pack(fill="both", expand=True, padx=8, pady=4)
            cols_a = ("Código", "Nombre")
            tr_a = ttk.Treeview(f_tr_a, columns=cols_a, show="headings", height=18, selectmode="extended")
            tr_a.heading("Código", text="Código", command=lambda: _sort_a("Código"))
            tr_a.heading("Nombre", text="Nombre de la Aduana", command=lambda: _sort_a("Nombre"))
            tr_a.column("Código", width=90); tr_a.column("Nombre", width=500)
            vsb_a = ttk.Scrollbar(f_tr_a, orient="vertical", command=tr_a.yview)
            tr_a.configure(yscrollcommand=vsb_a.set)
            tr_a.grid(row=0, column=0, sticky="nsew"); vsb_a.grid(row=0, column=1, sticky="ns")
            f_tr_a.grid_rowconfigure(0, weight=1); f_tr_a.grid_columnconfigure(0, weight=1)
            tr_a.bind("<Double-1>", lambda e: _editar_aduana())
            _sort_col_a = [None]; _sort_rev_a = [False]

            def _load_aduanas(q=""):
                tr_a.delete(*tr_a.get_children())
                rows = db_get_aduanas()
                q_lo = q.lower()
                if q_lo:
                    rows = [r for r in rows if q_lo in r["codigo"] or q_lo in r["nombre"].lower()]
                for r in rows:
                    tr_a.insert("", "end", values=(r["codigo"], r["nombre"]))
                lbl_cnt_a.config(text=f"{len(rows)} aduana(s)")

            def _sort_a(col):
                items = [(tr_a.set(iid, col), iid) for iid in tr_a.get_children("")]
                rev = _sort_col_a[0] == col and not _sort_rev_a[0]
                items.sort(reverse=rev)
                for i, (_, iid) in enumerate(items): tr_a.move(iid, "", i)
                _sort_col_a[0] = col; _sort_rev_a[0] = rev

            v_search_a.trace_add("write", lambda *a: _load_aduanas(v_search_a.get()))

            def _abrir_form_aduana(existing=None):
                frm = tk.Toplevel(top); frm.title("Nueva Aduana" if not existing else "Editar Aduana")
                frm.geometry("400x200"); frm.resizable(False, False); frm.grab_set()
                tk.Frame(frm, bg="#1B3A5C", height=40).pack(fill="x")
                tk.Label(frm, text="DATOS DE LA ADUANA", bg="#1B3A5C", fg="white",
                         font=("Arial", 9, "bold")).place(x=0, y=8, width=400)
                ff = tk.Frame(frm, pady=8); ff.pack(fill="both", expand=True, padx=16, pady=(50,0))
                v_cod  = tk.StringVar(value=existing["codigo"] if existing else "")
                v_nom  = tk.StringVar(value=existing["nombre"] if existing else "")
                tk.Label(ff, text="Código (3 dígitos):", font=("Arial", 8, "bold"), anchor="e", width=18).grid(row=0, column=0, sticky="e", pady=6)
                e_cod = tk.Entry(ff, textvariable=v_cod, width=10, font=("Arial", 9))
                e_cod.grid(row=0, column=1, sticky="w", padx=6)
                tk.Label(ff, text="Nombre:", font=("Arial", 8, "bold"), anchor="e", width=18).grid(row=1, column=0, sticky="e", pady=6)
                tk.Entry(ff, textvariable=v_nom, width=30, font=("Arial", 9)).grid(row=1, column=1, sticky="w", padx=6)
                def _guardar():
                    cod = v_cod.get().strip()
                    nom = v_nom.get().strip()
                    if not cod or not nom:
                        messagebox.showwarning("Error", "Código y Nombre son obligatorios.", parent=frm); return
                    if not cod.isdigit():
                        messagebox.showwarning("Error", "El código debe ser numérico.", parent=frm); return
                    new_cod = cod.zfill(3)
                    # If editing and codigo changed, delete the old one first
                    if existing and existing["codigo"] != new_cod:
                        db_eliminar_aduana(existing["codigo"])
                    db_guardar_aduana(new_cod, nom)
                    _load_aduanas(v_search_a.get())
                    _load_lop()   # actualizar también el combo de aduanas en LOP
                    frm.destroy()
                fb = tk.Frame(frm, bg="#2C3E50"); fb.pack(fill="x", side="bottom")
                tk.Button(fb, text="Guardar", bg="#27AE60", fg="white", font=("Arial", 8, "bold"),
                          command=_guardar).pack(side="left", padx=10, pady=6, ipadx=10, ipady=2)
                tk.Button(fb, text="Cancelar", bg="#7F8C8D", fg="white", font=("Arial", 8),
                          command=frm.destroy).pack(side="right", padx=10, pady=6)
                if not existing: e_cod.focus_set()

            def _editar_aduana():
                sel = tr_a.selection()
                if not sel: return
                vals = tr_a.item(sel[0], "values")
                _abrir_form_aduana({"codigo": vals[0], "nombre": vals[1]})

            def _del_aduana():
                sel = tr_a.selection()
                if not sel: return
                nombres = [tr_a.item(s, "values")[1] for s in sel]
                if not messagebox.askyesno("Confirmar",
                    f"Eliminar {len(sel)} aduana(s)?\n{', '.join(nombres)}\n\n"
                    "ATENCIÓN: También se eliminarán todos sus Lugares Operativos.", parent=top): return
                for s in sel:
                    vals = tr_a.item(s, "values")
                    db_eliminar_aduana(vals[0])
                _load_aduanas(v_search_a.get()); _load_lop()

            # ═══════════════════════════════════════════════════════════════════
            # PESTAÑA 2: LUGARES OPERATIVOS
            # ═══════════════════════════════════════════════════════════════════
            tab_lop = tk.Frame(nb, bg="#F4F6F7")
            nb.add(tab_lop, text="  LUGARES OPERATIVOS (LOT)  ")

            # Toolbar LOP
            ftb_l = tk.Frame(tab_lop, bg="#EBF5FB", bd=1, relief="flat")
            ftb_l.pack(fill="x", padx=0, pady=0)
            tk.Label(ftb_l, text="Filtrar por Aduana:", bg="#EBF5FB", font=("Arial", 8, "bold")).pack(side="left", padx=8, pady=6)
            v_adu_filter = tk.StringVar(value="TODAS")
            cb_adu_filter = ttk.Combobox(ftb_l, textvariable=v_adu_filter,
                                         values=["TODAS"], state="readonly", width=30, font=("Arial", 8))
            cb_adu_filter.pack(side="left", padx=4, pady=6)
            tk.Label(ftb_l, text="Buscar:", bg="#EBF5FB", font=("Arial", 8, "bold")).pack(side="left", padx=(10,2), pady=6)
            v_search_l = tk.StringVar()
            tk.Entry(ftb_l, textvariable=v_search_l, width=18, font=("Arial", 9)).pack(side="left", padx=4, pady=6)
            tk.Button(ftb_l, text="+ AGREGAR LOT", bg="#1D6A39", fg="white",
                      font=("Arial", 8, "bold"), command=lambda: _abrir_form_lop()).pack(side="left", padx=8, pady=6, ipadx=6, ipady=2)
            tk.Button(ftb_l, text="Editar", bg="#2980B9", fg="white",
                      font=("Arial", 8, "bold"), command=lambda: _editar_lop()).pack(side="left", padx=4, pady=6, ipadx=6, ipady=2)
            tk.Button(ftb_l, text="Eliminar", bg="#E74C3C", fg="white",
                      font=("Arial", 8, "bold"), command=lambda: _del_lop()).pack(side="left", padx=4, pady=6, ipadx=6, ipady=2)
            lbl_cnt_l = tk.Label(ftb_l, text="", bg="#EBF5FB", font=("Arial", 8), fg="#1B3A5C")
            lbl_cnt_l.pack(side="right", padx=12)

            # Treeview LOP
            f_tr_l = tk.Frame(tab_lop)
            f_tr_l.pack(fill="both", expand=True, padx=8, pady=4)
            cols_l = ("Código LOT", "Descripción", "Aduana")
            tr_l = ttk.Treeview(f_tr_l, columns=cols_l, show="headings", height=18, selectmode="extended")
            tr_l.heading("Código LOT",  text="Código LOT",   command=lambda: _sort_l("Código LOT"))
            tr_l.heading("Descripción", text="Descripción",  command=lambda: _sort_l("Descripción"))
            tr_l.heading("Aduana",      text="Aduana",       command=lambda: _sort_l("Aduana"))
            tr_l.column("Código LOT", width=100); tr_l.column("Descripción", width=380); tr_l.column("Aduana", width=200)
            vsb_l = ttk.Scrollbar(f_tr_l, orient="vertical", command=tr_l.yview)
            tr_l.configure(yscrollcommand=vsb_l.set)
            tr_l.grid(row=0, column=0, sticky="nsew"); vsb_l.grid(row=0, column=1, sticky="ns")
            f_tr_l.grid_rowconfigure(0, weight=1); f_tr_l.grid_columnconfigure(0, weight=1)
            tr_l.bind("<Double-1>", lambda e: _editar_lop())
            _sort_col_l = [None]; _sort_rev_l = [False]

            def _get_adu_opts():
                ads = db_get_aduanas()
                return ["TODAS"] + [f"{a['codigo']} - {a['nombre']}" for a in ads]

            def _load_lop(q="", adu_filter=None):
                tr_l.delete(*tr_l.get_children())
                # Actualizar combo aduanas
                opts = _get_adu_opts()
                cb_adu_filter["values"] = opts
                if v_adu_filter.get() not in opts: v_adu_filter.set("TODAS")
                # Filtro por aduana
                filt_adu = v_adu_filter.get()
                cod_adu = None
                if filt_adu and filt_adu != "TODAS" and " - " in filt_adu:
                    cod_adu = filt_adu.split(" - ", 1)[0]
                rows = db_get_lugares_operativos(cod_adu)
                q_lo = (q or v_search_l.get()).lower()
                if q_lo:
                    rows = [r for r in rows if q_lo in r["codigo"].lower() or q_lo in r["descripcion"].lower()]
                ads_map = {a["codigo"]: a["nombre"] for a in db_get_aduanas()}
                for r in rows:
                    adu_str = f"{r['aduana_codigo']} - {ads_map.get(r['aduana_codigo'], r['aduana_codigo'])}"
                    tr_l.insert("", "end", values=(r["codigo"], r["descripcion"], adu_str),
                                tags=(r["aduana_codigo"],))
                lbl_cnt_l.config(text=f"{len(rows)} lugar(es)")

            def _sort_l(col):
                items = [(tr_l.set(iid, col), iid) for iid in tr_l.get_children("")]
                rev = _sort_col_l[0] == col and not _sort_rev_l[0]
                items.sort(reverse=rev)
                for i, (_, iid) in enumerate(items): tr_l.move(iid, "", i)
                _sort_col_l[0] = col; _sort_rev_l[0] = rev

            v_search_l.trace_add("write", lambda *a: _load_lop())
            v_adu_filter.trace_add("write", lambda *a: _load_lop())

            def _abrir_form_lop(existing=None):
                frm = tk.Toplevel(top); frm.title("Nuevo LOT" if not existing else "Editar LOT")
                frm.geometry("460x240"); frm.resizable(False, False); frm.grab_set()
                tk.Frame(frm, bg="#1D6A39", height=40).pack(fill="x")
                tk.Label(frm, text="DATOS DEL LOT (Lugar Operativo de Tráfico)", bg="#1D6A39", fg="white",
                         font=("Arial", 9, "bold")).place(x=0, y=8, width=460)
                ff = tk.Frame(frm, pady=8); ff.pack(fill="both", expand=True, padx=16, pady=(50,0))
                v_cod_l = tk.StringVar(value=existing["codigo"] if existing else "")
                v_desc_l = tk.StringVar(value=existing["descripcion"] if existing else "")
                v_adu_l  = tk.StringVar()
                ads = db_get_aduanas()
                adu_opts = [f"{a['codigo']} - {a['nombre']}" for a in ads]
                # Pre-seleccionar aduana actual o la del existing
                if existing:
                    match = [o for o in adu_opts if o.startswith(existing["aduana_codigo"])]
                    v_adu_l.set(match[0] if match else (adu_opts[0] if adu_opts else ""))
                else:
                    cur_adu = self.get_var("car_lugar").get()
                    match = [o for o in adu_opts if cur_adu.split(" - ")[0].zfill(3) in o]
                    v_adu_l.set(match[0] if match else (adu_opts[0] if adu_opts else ""))
                tk.Label(ff, text="Código LOT:", font=("Arial", 8, "bold"), anchor="e", width=16).grid(row=0, column=0, sticky="e", pady=5)
                e_cod_l = tk.Entry(ff, textvariable=v_cod_l, width=12, font=("Arial", 9))
                e_cod_l.grid(row=0, column=1, sticky="w", padx=6)
                tk.Label(ff, text="Descripción:", font=("Arial", 8, "bold"), anchor="e", width=16).grid(row=1, column=0, sticky="e", pady=5)
                tk.Entry(ff, textvariable=v_desc_l, width=32, font=("Arial", 9)).grid(row=1, column=1, sticky="w", padx=6)
                tk.Label(ff, text="Aduana:", font=("Arial", 8, "bold"), anchor="e", width=16).grid(row=2, column=0, sticky="e", pady=5)
                ttk.Combobox(ff, textvariable=v_adu_l, values=adu_opts, state="readonly", width=30, font=("Arial", 8)).grid(row=2, column=1, sticky="w", padx=6)
                def _guardar_lop():
                    cod  = v_cod_l.get().strip()
                    desc = v_desc_l.get().strip()
                    adu  = v_adu_l.get().strip()
                    if not cod or not desc:
                        messagebox.showwarning("Error", "Código y Descripción son obligatorios.", parent=frm); return
                    if not adu or " - " not in adu:
                        messagebox.showwarning("Error", "Seleccione una Aduana.", parent=frm); return
                    adu_cod = adu.split(" - ", 1)[0]
                    # If editing and the key changed, delete the old record first
                    if existing:
                        old_cod = existing["codigo"]
                        old_adu = existing["aduana_codigo"]
                        if old_cod != cod or old_adu != adu_cod:
                            db_eliminar_lugar_operativo(old_cod, old_adu)
                    db_guardar_lugar_operativo(cod, desc, adu_cod)
                    _load_lop(); frm.destroy()
                fb = tk.Frame(frm, bg="#2C3E50"); fb.pack(fill="x", side="bottom")
                tk.Button(fb, text="Guardar", bg="#27AE60", fg="white", font=("Arial", 8, "bold"),
                          command=_guardar_lop).pack(side="left", padx=10, pady=6, ipadx=10, ipady=2)
                tk.Button(fb, text="Cancelar", bg="#7F8C8D", fg="white", font=("Arial", 8),
                          command=frm.destroy).pack(side="right", padx=10, pady=6)
                if not existing: e_cod_l.focus_set()

            def _editar_lop():
                sel = tr_l.selection()
                if not sel: return
                vals = tr_l.item(sel[0], "values")
                adu_cod = vals[2].split(" - ")[0] if " - " in vals[2] else vals[2]
                _abrir_form_lop({"codigo": vals[0], "descripcion": vals[1], "aduana_codigo": adu_cod})

            def _del_lop():
                sel = tr_l.selection()
                if not sel: return
                if not messagebox.askyesno("Confirmar", f"Eliminar {len(sel)} Lugar(es) Operativo(s)?", parent=top): return
                for s in sel:
                    vals = tr_l.item(s, "values")
                    adu_cod = vals[2].split(" - ")[0] if " - " in vals[2] else vals[2]
                    db_eliminar_lugar_operativo(vals[0], adu_cod)
                _load_lop()

            # ── Hint ────────────────────────────────────────────────────────────
            f_note = tk.Frame(tab_lop, bg="#FEF9E7"); f_note.pack(fill="x", padx=8, pady=2)
            tk.Label(f_note, text="Los Lugares Operativos están coordinados por la Aduana correspondiente. "
                     "Solo se pueden asignar Aduaneros a las Aduanas que figuran en la tabla de Aduanas.",
                     bg="#FEF9E7", fg="#6E4B00", font=("Arial", 7), anchor="w").pack(fill="x", padx=8, pady=3)

            # ── Footer ───────────────────────────────────────────────────────────
            f_bot = tk.Frame(top, bg="#2C3E50")
            f_bot.pack(fill="x", side="bottom")
            tk.Button(f_bot, text="Cerrar", bg="#7F8C8D", fg="white",
                      font=("Arial", 8, "bold"), command=top.destroy).pack(side="right", padx=10, pady=6, ipadx=8, ipady=2)
            tk.Button(f_bot, text="Aplicar aduana actual al LOT",
                      bg="#1D6A39", fg="white", font=("Arial", 8),
                      command=lambda: (nb.select(tab_lop), _load_lop())).pack(side="left", padx=10, pady=6, ipadx=6, ipady=2)

            # Carga inicial
            _load_aduanas(); _load_lop()

        except Exception as e:
            traceback.print_exc()
            messagebox.showerror("Error ABM", str(e))

    def borrar_funcionario(self, obj):
        if obj in self.funcionarios_data:
            self.funcionarios_data.remove(obj)
        if obj["frame"]:
            obj["frame"].destroy()

    def borrar_ddt(self, obj):
        if len(self.ddt_data) <= 1:
            messagebox.showwarning("Aviso", "Debe quedar al menos un Documento.")
            return
        if messagebox.askyesno("Confirmar", "¿Eliminar este Documento?"):
            obj["main_frame"].destroy()
            if obj in self.ddt_data: self.ddt_data.remove(obj)
            self.actualizar_combos_ddt()

    def agregar_salida(self, ddt_obj, data=None):
        salida = {
            "numero": tk.StringVar(value=data["numero"] if data else ""),
            "litros": tk.StringVar(value=data["litros"] if data else ""),
            "kilos": tk.StringVar(value=data["kilos"] if data else ""),
            "densidad": tk.StringVar(value=data["densidad"] if data else ""),
            "frame": None
        }
        salida["litros"].trace_add("write", lambda *args: self.auto_calc_densidad(salida["litros"], salida["kilos"], salida["densidad"]))
        salida["kilos"].trace_add("write", lambda *args: self.auto_calc_densidad(salida["litros"], salida["kilos"], salida["densidad"]))
        f_row = ttk.Frame(ddt_obj["salidas_frame"])
        f_row.pack(fill="x", pady=2)
        salida["frame"] = f_row
        ttk.Entry(f_row, textvariable=salida["numero"], width=20).pack(side="left", padx=2)
        ttk.Entry(f_row, textvariable=salida["litros"], width=12).pack(side="left", padx=2)
        ttk.Entry(f_row, textvariable=salida["kilos"], width=12).pack(side="left", padx=2)
        ttk.Entry(f_row, textvariable=salida["densidad"], width=12, state="readonly").pack(side="left", padx=2)
        tk.Button(f_row, text="x", bg="#ffcccc", width=2, command=lambda: self.borrar_salida(ddt_obj, salida)).pack(side="left", padx=5)
        ddt_obj["salidas"].append(salida)

    def borrar_salida(self, ddt_obj, salida):
        salida["frame"].destroy()
        if salida in ddt_obj["salidas"]: ddt_obj["salidas"].remove(salida)

    def actualizar_combos_ddt(self, event=None):
        lista = [d["numero"].get() for d in self.ddt_data if d["numero"].get()]
        lista.insert(0, "") 
        for cb in self.combos_ddt: 
            try: cb['values'] = lista
            except: pass

    def check_combos(self, event):
        self.actualizar_combos_ddt()

    # --- CALCULO LOGICA ---
    def on_ddt_selected(self, etapa, tanque):
        if self.is_loading_data: return
        ddt_num = self.get_var(f"{etapa}_{tanque}_ddt_assign").get()
        if not ddt_num:
            self.get_var(f"{etapa}_{tanque}_prod_name").set("")
            self.get_var(f"{etapa}_{tanque}_dens_doc").set("")
            self.get_var(f"{etapa}_{tanque}_dens_salida").set("")
            self.calc_volumen_prod_ui(etapa, tanque)
            return
        found = next((d for d in self.ddt_data if d["numero"].get() == ddt_num), None)
        if found:
            prod_val = found["producto"].get()
            dens_doc = found["densidad"].get()
            self.get_var(f"{etapa}_{tanque}_prod_name").set(prod_val)
            self.get_var(f"{etapa}_{tanque}_dens_doc").set(dens_doc)
            if not self.get_var(f"{etapa}_{tanque}_dens_lab").get():
                self.get_var(f"{etapa}_{tanque}_dens_lab").set(dens_doc)
            salidas = found["salidas"]
            avg_sal = 0.0
            if salidas:
                total_mass = 0.0
                total_liters = 0.0
                for s in salidas:
                    l = self.parse_float(s["litros"].get())
                    d = self.parse_float(s["densidad"].get())
                    total_liters += l
                    total_mass += (l * d)
                if total_liters > 0:
                    avg_sal = total_mass / total_liters
                else:
                    avg_sal = 0.0
            if avg_sal > 0:
                self.get_var(f"{etapa}_{tanque}_dens_salida").set(f"{avg_sal:.5f}")
            else:
                self.get_var(f"{etapa}_{tanque}_dens_salida").set(dens_doc)
            self.calc_volumen_prod_ui(etapa, tanque)

