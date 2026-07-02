"""Solapas inicial/final, ficha de tanque, tablas de calibrado e interpolación, draft survey, tributos.

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


class TanquesUIMixin:
    def on_tab_changed(self, event):
        current_tab_index = self.notebook.index(self.notebook.select())
        if current_tab_index in self.tabs_built and not self.tabs_built[current_tab_index]:
            self.root.after(50, lambda: self.build_specific_tab(current_tab_index))

    def _update_tab_titles(self):
        """Actualiza los títulos de las solapas con el tipo de medición activo."""
        try:
            _tm = self.get_tipo_medio()
            _tipo_abrev = {
                "BUQUE":              "⚓ BUQ",
                "BARCAZA":            "⚓ BAR",
                "BUQUE GASERO/GLP":   "⚙ GLP",
                "BUQUE QUIMIQUERO":   "⚗ QUI",
                "BUQUE METANERO/GNL": "❄ GNL",
                "DRAFT SURVEY":       "⚓ DFT",
                "TANQUE FIJO":        "🛢 TF",
                "TANQUE FLOTANTE":    "🛢 TTF",
                "ESFERA DE GAS":      "⚙ ESF",
                "CAMION CISTERNA":    "🚛 CAM",
                "CAMION GAS/GLP":     "🚛 CGP",
                "OLEODUCTO":          "≋ OLE",
                "GASODUCTO":          "≋ GAS",
                "POLIDUCTO":          "≋ POL",
                "ELECTRICO":          "⚡ ELC",
            }.get(_tm, _tm[:6])
            self.notebook.tab(1, text=f" 2. INICIAL [{_tipo_abrev}] ")
            self.notebook.tab(2, text=f" 3. FINAL   [{_tipo_abrev}] ")
        except:
            pass

    def build_specific_tab(self, index):
        if index == 1:
            self.construir_pantalla_unificada("inicial", self.tab_ini_prod)
        elif index == 2:
            self.construir_pantalla_unificada("final", self.tab_fin_prod)
        elif index == 3:
            self.construir_preview_tab()
        self.tabs_built[index] = True
        self.actualizar_combos_ddt()
        self._update_tab_titles()

    def _limpiar_vars_tipo_anterior(self):
        """Limpia variables de medición que no corresponden al tipo actual, evitando datos fantasma."""
        tm = self.get_tipo_medio()
        # Keys del tipo actual
        current_tanks = set(self.lista_tanques + self.lista_carbonera)
        # Prefijos de variables de tanque para los stages
        ETAPAS = ["ini", "fin"]
        # Sufijos que son exclusivos de tipos específicos — se limpian al cambiar de tipo
        SUFIJOS_MARITIMO  = ["_alt_uti","_num_uti","_alt_ref","_s_corr","_prod_s1","_prod_l1","_prod_s2","_prod_l2","_agua_s1","_agua_l1","_agua_s2","_agua_l2","_agua_lectura","_agua_desc","_agua_s_real","_vol_nat_agua"]
        SUFIJOS_TIERRA    = ["_s_tierra","_tf_offset","_vol_bruto"]
        SUFIJOS_CAMION    = ["_ticket_l","_ticket_k"]
        SUFIJOS_GAS       = ["_presion","_temp_liq","_factor_z","_dens_vapor","_fase","_vol_liq","_vol_vap","_masa_liq","_masa_vap","_pres_gnl","_temp_vap"]
        SUFIJOS_ELECTRICO = ["_el_ini_act","_el_fin_act","_el_kwh_act","_el_ini_rea","_el_fin_rea","_el_kwh_rea","_el_const","_el_fp","_el_dem","_el_V","_el_A","_el_VA","_el_fp_med","_el_fases"]
        SUFIJOS_DUCTO     = ["_cont_ini","_cont_fin","_vol_linea","_caudal_mh","_coriolis_kgh","_masa_coriolis","_P_lin","_T_lin","_Z","_vol_base","_vol_base_km3","_pig_diam","_pig_largo","_pig_vol","_pig_vel","_pig_obs"]
        SUFIJOS_ESFERA    = ["_esf_pres","_esf_temp","_esf_dens","_esf_vol_gas","_esf_masa","_esf_fase"]
        SUFIJOS_CAMION_GAS= ["_cg_pres","_cg_temp","_cg_dens","_cg_masa","_cg_vol","_cg_vol_gas"]
        SUFIJOS_GNL_MOL   = ["_gc_CH4","_gc_C2H6","_gc_C3H8","_gc_C4H10","_gc_N2","_gc_CO2","_gc_iC4","_gc_nC5","_gc_H2S","_gc_sum","_gc_PM"]

        # Sufijos comunes de medición — se limpian cuando el TIPO CAMBIA entre familias
        # (evita que datos de buque aparezcan en camión o viceversa)
        SUFIJOS_COMUNES_MEDICION = [
            "_dens_lab","_dens_doc","_dens_salida","_v15_lab","_kv_lab","_v15_doc","_kv_doc",
            "_v15_sal","_kv_sal","_vol_nat_prod","_vol_nat_agua","_prod_name","_ddt_assign",
            "_tabla_vcf","_temp","_num_uti","_desc_tubo","_alt_uti","_alt_ref"
        ]

        _mar  = self.es_maritimo()
        _tie  = self.es_tierra()
        _cam  = self.es_camion()
        _gas  = self.es_gasero() and not ("METANERO" in tm or "GNL" in tm)
        _met  = "METANERO" in tm or "GNL" in tm
        _esf  = self.es_esfera()
        _duc  = self.es_ducto()
        _el   = self.es_electrico()
        _cgb  = self.es_camion_gas()

        # Decide qué sufijos limpiar según el tipo ACTUAL
        sufijos_a_limpiar = []
        if not _mar:                  sufijos_a_limpiar += SUFIJOS_MARITIMO
        if not _tie:                  sufijos_a_limpiar += SUFIJOS_TIERRA
        if not _cam:                  sufijos_a_limpiar += SUFIJOS_CAMION
        if not (_gas or _met or _esf or _cgb): sufijos_a_limpiar += SUFIJOS_GAS
        if not _el:                   sufijos_a_limpiar += SUFIJOS_ELECTRICO
        if not _duc:                  sufijos_a_limpiar += SUFIJOS_DUCTO
        if not _esf:                  sufijos_a_limpiar += SUFIJOS_ESFERA
        if not _cgb:                  sufijos_a_limpiar += SUFIJOS_CAMION_GAS
        if not _met:                  sufijos_a_limpiar += SUFIJOS_GNL_MOL

        if not sufijos_a_limpiar: return
        sufijos_a_limpiar_set = set(sufijos_a_limpiar)

        # Pre-compute prefixes and suffix tuples for fast matching
        prefixes = {f"{et}_": len(f"{et}_") for et in ETAPAS}
        sufijos_tuple = tuple(sufijos_a_limpiar_set)

        # Limpiar variables: buscar claves que coincidan con etapa_tanque_sufijo
        # IMPORTANTE: se limpian TODOS los tanques (no solo los que ya no existen)
        # para evitar datos fantasma cuando el tipo cambia
        keys_to_clear = set()
        all_keys = list(self.vars.keys())
        for k in all_keys:
            if not k.endswith(sufijos_tuple):
                continue
            for prefix, plen in prefixes.items():
                if k.startswith(prefix):
                    for suf in sufijos_a_limpiar_set:
                        if k.endswith(suf) and len(k) > plen + len(suf):
                            keys_to_clear.add(k)
                            break
                    break
        for k in keys_to_clear:
            if k in self.vars:
                self.vars[k].set("")

        # Limpiar también los tanques que ya no existen — incluye sufijos comunes
        sufijos_no_existentes = sufijos_a_limpiar_set | set(SUFIJOS_COMUNES_MEDICION)
        sufijos_ne_tuple = tuple(sufijos_no_existentes)
        keys_to_clear2 = set()
        for k in all_keys:
            if k in keys_to_clear:
                continue
            if not k.endswith(sufijos_ne_tuple):
                continue
            for prefix, plen in prefixes.items():
                if k.startswith(prefix):
                    for suf in sufijos_no_existentes:
                        if k.endswith(suf) and len(k) > plen + len(suf):
                            tank_part = k[plen:-len(suf)]
                            if tank_part and tank_part not in current_tanks:
                                keys_to_clear2.add(k)
                                break
                    break
        for k in keys_to_clear2:
            if k in self.vars:
                self.vars[k].set("")

        # Limpiar variables de cabecera de etapa que no aplican al tipo actual
        vars_header_maritimo = [
            "ini_Calados Proa","ini_Calados Popa","ini_Calados Babor","ini_Calados Estribor",
            "ini_Trimación","ini_Lista",
            "fin_Calados Proa","fin_Calados Popa","fin_Calados Babor","fin_Calados Estribor",
            "fin_Trimación","fin_Lista",
        ]
        vars_header_tierra = [
            "ini_Temp_Amb","fin_Temp_Amb","ini_Modo_Sondaje","fin_Modo_Sondaje",
        ]
        vars_header_ducto = [
            "ini_P_linea","ini_T_linea","ini_Cond_base","fin_P_linea","fin_T_linea","fin_Cond_base",
        ]
        if not _mar:
            for vk in vars_header_maritimo:
                if vk in self.vars: self.vars[vk].set("")
        if not (_tie or _cam):
            for vk in vars_header_tierra:
                if vk in self.vars: self.vars[vk].set("")
        if not _duc:
            for vk in vars_header_ducto:
                if vk in self.vars: self.vars[vk].set("")

    def rebuild_all_tabs(self):
        # Limpiar variables que no corresponden al tipo actual
        self._limpiar_vars_tipo_anterior()
        for idx in [1, 2, 3]:
            self.tabs_built[idx] = False
            if idx == 1: tab_frame = self.tab_ini_prod
            elif idx == 2: tab_frame = self.tab_fin_prod
            else: tab_frame = self.tab_preview
            for w in tab_frame.winfo_children(): w.destroy()
        self.combos_ddt = []
        current = self.notebook.index(self.notebook.select())
        if current in self.tabs_built:
            self.build_specific_tab(current)
        self._update_tab_titles()

    # --- UI TABLA PRINCIPAL UNIFICADA ---
    def construir_pantalla_unificada(self, etapa, parent):
        main_frame = ttk.Frame(parent)
        main_frame.pack(fill="both", expand=True)

        canvas = tk.Canvas(main_frame, bg="white")
        vbar = ttk.Scrollbar(main_frame, orient="vertical", command=canvas.yview)
        hbar = ttk.Scrollbar(main_frame, orient="horizontal", command=canvas.xview)
        scroll_f = ttk.Frame(canvas)
        scroll_f.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=scroll_f, anchor="nw")
        canvas.configure(yscrollcommand=vbar.set, xscrollcommand=hbar.set)
        canvas.grid(row=0, column=0, sticky="nsew")
        def _pu_mw(event): canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        def _pu_up(event): canvas.yview_scroll(-3, "units")
        def _pu_down(event): canvas.yview_scroll(3, "units")
        def _pu_bind(e):
            canvas.bind_all("<MouseWheel>", _pu_mw)
            canvas.bind_all("<Button-4>", _pu_up)
            canvas.bind_all("<Button-5>", _pu_down)
        def _pu_unbind(e):
            canvas.unbind_all("<MouseWheel>")
            canvas.unbind_all("<Button-4>")
            canvas.unbind_all("<Button-5>")
        canvas.bind("<Enter>", _pu_bind)
        canvas.bind("<Leave>", _pu_unbind)
        vbar.grid(row=0, column=1, sticky="ns")
        hbar.grid(row=1, column=0, sticky="ew")
        main_frame.grid_rowconfigure(0, weight=1)
        main_frame.grid_columnconfigure(0, weight=1)

        # Header Global
        f_top = ttk.Frame(scroll_f)
        f_top.pack(fill="x", padx=10, pady=10)
        font_style = ("Arial", 10)
        lbl_font = ("Arial", 8, "bold")

        # FILA 1: FECHA Y HORA
        f_row1 = tk.Frame(f_top)
        f_row1.pack(fill="x", pady=2)
        
        # Registrar validaciones
        vcmd_fecha = (f_row1.register(self.validar_fecha), '%P')
        vcmd_hora = (f_row1.register(self.validar_hora), '%P')
        
        ttk.Label(f_row1, text="Fecha:", font=lbl_font).pack(side="left", padx=5)
        var_fecha = self.get_var(f"{etapa}_Fecha")
        e_fecha = ttk.Entry(f_row1, textvariable=var_fecha, width=12, font=font_style, validate="key", validatecommand=vcmd_fecha)
        e_fecha.pack(side="left")
        e_fecha.bind("<FocusIn>", lambda ev, v=var_fecha: self.on_fecha_focus_in(ev, v))
        e_fecha.bind("<FocusOut>", lambda ev, v=var_fecha: self.on_fecha_focus_out(ev, v))
        if not var_fecha.get(): var_fecha.set("DD/MM/AAAA")

        ttk.Label(f_row1, text="Hora:", font=lbl_font).pack(side="left", padx=5)
        var_hora = self.get_var(f"{etapa}_Hora")
        e_hora = ttk.Entry(f_row1, textvariable=var_hora, width=8, font=font_style, validate="key", validatecommand=vcmd_hora)
        e_hora.pack(side="left")
        e_hora.bind("<FocusIn>", lambda ev, v=var_hora: self.on_hora_focus_in(ev, v))
        e_hora.bind("<FocusOut>", lambda ev, v=var_hora: self.on_hora_focus_out(ev, v))
        if not var_hora.get(): var_hora.set("00:00")

        # FILA 2: LONGITUDINAL (solo maritimos) / temperatura ambiente (tierra/camion)
        _tm_pu = self.get_tipo_medio()
        _mar_pu = self.es_maritimo()

        if _mar_pu:
            ttk.Label(f_row1, text="Proa:", font=lbl_font).pack(side="left", padx=5)
            ttk.Entry(f_row1, textvariable=self.get_var(f"{etapa}_Calados Proa"), width=8, font=font_style).pack(side="left")
            ttk.Label(f_row1, text="Popa:", font=lbl_font).pack(side="left", padx=5)
            ttk.Entry(f_row1, textvariable=self.get_var(f"{etapa}_Calados Popa"), width=8, font=font_style).pack(side="left")
            ttk.Label(f_row1, text="Trim:", font=lbl_font).pack(side="left", padx=5)
            tk.Label(f_row1, textvariable=self.get_var(f"{etapa}_Trimación"), width=8, bg="#e0e0e0", relief="sunken", font=font_style).pack(side="left")
            ttk.Label(f_row1, text="Babor:", font=lbl_font).pack(side="left", padx=5)
            ttk.Entry(f_row1, textvariable=self.get_var(f"{etapa}_Calados Babor"), width=8, font=font_style).pack(side="left")
            ttk.Label(f_row1, text="Estribor:", font=lbl_font).pack(side="left", padx=5)
            ttk.Entry(f_row1, textvariable=self.get_var(f"{etapa}_Calados Estribor"), width=8, font=font_style).pack(side="left")
            ttk.Label(f_row1, text="Escora:", font=lbl_font).pack(side="left", padx=5)
            tk.Label(f_row1, textvariable=self.get_var(f"{etapa}_Lista"), width=8, bg="#e0e0e0", relief="sunken", font=font_style).pack(side="left")
            self.get_var(f"{etapa}_Calados Popa").trace_add("write", lambda *args, e=etapa: self.calc_trim(e))
            self.get_var(f"{etapa}_Calados Proa").trace_add("write", lambda *args, e=etapa: self.calc_trim(e))
            self.get_var(f"{etapa}_Calados Babor").trace_add("write", lambda *args, e=etapa: self.calc_trim(e))
            self.get_var(f"{etapa}_Calados Estribor").trace_add("write", lambda *args, e=etapa: self.calc_trim(e))
        else:
            # Para tierra y camion: temperatura ambiente + modo sondaje
            ttk.Label(f_row1, text="Temp.Ambiente (°C):", font=lbl_font).pack(side="left", padx=5)
            ttk.Entry(f_row1, textvariable=self.get_var(f"{etapa}_Temp_Amb",""), width=8, font=font_style).pack(side="left")
            if self.es_tierra():
                ttk.Label(f_row1, text="Modo Sondaje:", font=lbl_font).pack(side="left", padx=5)
                _modo_var = self.get_var(f"{etapa}_Modo_Sondaje","INNAGE")
                cb_modo = ttk.Combobox(f_row1, textvariable=_modo_var,
                    values=["INNAGE (desde el fondo)","ULLAGE (espacio libre)"],
                    state="readonly", width=22, font=font_style)
                cb_modo.pack(side="left", padx=3)
                if "FLOTANTE" in _tm_pu:
                    ttk.Label(f_row1, text="Offset Techo (mm):", font=lbl_font).pack(side="left", padx=5)
                    ttk.Entry(f_row1, textvariable=self.get_var("car_tf_offset","0"),
                              width=8, font=font_style).pack(side="left")
            if self.es_ducto():
                ttk.Label(f_row1, text="P.Linea(kPa):", font=lbl_font).pack(side="left", padx=5)
                ttk.Entry(f_row1, textvariable=self.get_var(f"{etapa}_P_linea",""), width=8, font=font_style).pack(side="left")
                ttk.Label(f_row1, text="T.Linea(C):", font=lbl_font).pack(side="left", padx=5)
                ttk.Entry(f_row1, textvariable=self.get_var(f"{etapa}_T_linea",""), width=8, font=font_style).pack(side="left")
                ttk.Label(f_row1, text="Cond.base:", font=lbl_font).pack(side="left", padx=5)
                ttk.Combobox(f_row1, textvariable=self.get_var(f"{etapa}_Cond_base","15C/101.325kPa"),
                    values=["15C/101.325kPa","20C/101.325kPa","0C/101.325kPa"],
                    state="readonly", width=18, font=font_style).pack(side="left", padx=3)

        # --- TABLA EXTENDIDA --- (columnas adaptadas al tipo de medición)
        f_table = ttk.Frame(scroll_f)
        f_table.pack(fill="x", padx=10, pady=5)
        
        table_widgets = []
        
        # ── Determinar qué columnas mostrar según tipo de medio ──────────────
        _tm_tab   = self.get_tipo_medio()
        _is_mar_t = self.es_maritimo()
        _is_tie_t = self.es_tierra()
        _is_cam_t = self.es_camion()
        _is_gas_t = self.es_gasero()
        _is_esf_t = self.es_esfera()
        _is_duc_t = self.es_ducto()
        _is_el_t  = self.es_electrico()
        _is_cgb_t = self.es_camion_gas()
        _is_liq_t = _is_mar_t or _is_tie_t or (_is_cam_t and not _is_cgb_t)  # medición de líquidos clásica
        _is_gas_only = _is_gas_t or _is_esf_t or _is_cgb_t or ("METANERO" in _tm_tab)
        _show_dens_cols = not (_is_duc_t or _is_el_t)
        _show_prod_col  = not _is_el_t
        # Agua: solo para marítimos de líquidos + tierra + camión cisterna
        # Gasero/Metanero son marítimos pero NO usan UTI de agua
        _es_liq_mar_t   = _tm_tab in ("BUQUE", "BARCAZA", "BUQUE QUIMIQUERO", "DRAFT SURVEY")
        _show_agua_col  = _es_liq_mar_t or _is_tie_t or (_is_cam_t and not _is_cgb_t)

        # Encabezados fijos
        headers = [("TANQUE", "#ddd"), ("EDITAR", "#ddd")]
        headers.append(("DOCUMENTO", "#ddd"))
        if _show_prod_col:
            headers.append(("PRODUCTO", "#ddd"))

        if _is_el_t:
            # Electricidad: kWh activa, reactiva, cosfi
            headers += [
                ("kWh ACTIVA", "#d5f5e3"), ("kWh REACTIVA", "#d5f5e3"),
                ("COS FI", "#d5f5e3"), ("DEMANDA (kW)", "#d5f5e3"),
            ]
        elif _is_duc_t:
            # Ducto: volumen linea, volumen base, caudal
            headers += [
                ("VOL.LINEA (m3)", "#d6eaf8"), ("VOL.BASE (m3)", "#d6eaf8"),
                ("VOL.BASE (Km3)", "#d6eaf8"), ("CAUDAL (m3/h)", "#d6eaf8"),
            ]
        elif _show_dens_cols:
            # Líquidos y gas licuado: densidades y volúmenes
            headers += [
                ("DENS. LAB", "#ffffcc"), ("DENS. DOC", "#dcebf7"), ("DENS. SAL", "#dcf7dc"),
                ("VOL. LAB (L)", "#ffffcc"), ("KILOS LAB", "#ffffcc"),
                ("VOL. DOC (L)", "#dcebf7"), ("KILOS DOC", "#dcebf7"),
                ("VOL. SAL (L)", "#dcf7dc"), ("KILOS SAL", "#dcf7dc"),
            ]

        if _show_agua_col:
            headers.append(("AGUA (L)", "#ccffcc"))

        # Columna de volumen natural (siempre al final)
        headers.append(("VOL. NATURAL", "#e8e8e8"))

        for i, (h, bg_c) in enumerate(headers):
            lbl = tk.Label(f_table, text=h, font=("Arial", 8, "bold"), bg=bg_c, relief="raised", padx=5, anchor="center")
            lbl.grid(row=0, column=i, sticky="nsew")
            table_widgets.append(("header", lbl))
            f_table.grid_columnconfigure(i, weight=1)


        # Botón "Agregar" para tipos de tierra/esfera
        _es_tierra_esf = self.es_tierra() or self.es_esfera()
        if _es_tierra_esf:
            _btn_frame = tk.Frame(f_table, bg="#f0f0f0")
            _btn_frame.grid(row=0, column=14, rowspan=200, sticky="ns", padx=4)
            _tipo_str = "ESFERA" if self.es_esfera() else "TANQUE"
            _tank_bg = "#1D6A39" if not self.es_esfera() else "#6A1B9A"
            def _add_tank(tipo=_tipo_str, tab_frame=parent, tab_etapa=etapa, tab_bg=_tank_bg):
                n_existing = len([t for t in self.lista_tanques if tipo.split()[0] in t.upper()])
                self.lista_tanques.append(f"{tipo} {n_existing+1}")
                self.rebuild_all_tabs()
            def _del_tank():
                if len(self.lista_tanques) > 1:
                    self.lista_tanques.pop()
                    self.rebuild_all_tabs()
            tk.Button(_btn_frame, text=f"+ {_tipo_str}", bg=_tank_bg, fg="white",
                      font=("Arial", 7, "bold"), relief="flat", cursor="hand2",
                      command=_add_tank).pack(fill="x", padx=2, pady=(6,2), ipadx=3, ipady=4)
            tk.Button(_btn_frame, text="− Quitar", bg="#C0392B", fg="white",
                      font=("Arial", 7), relief="flat", cursor="hand2",
                      command=_del_tank).pack(fill="x", padx=2, pady=2, ipadx=3, ipady=3)

        # FILAS
        total_list = self.lista_tanques + self.lista_carbonera
        for idx, tk_name in enumerate(total_list):
            r = idx + 1
            bg_tk = "#fff9c4" if tk_name in self.lista_carbonera else "white"
            lbl_tk = tk.Label(f_table, text=tk_name, font=("Arial", 8, "bold"), bg=bg_tk, relief="solid")
            lbl_tk.grid(row=r, column=0, sticky="nsew")
            table_widgets.append(("name", lbl_tk))
            
            # Boton Lapiz (la interp × asiento se carga desde la ficha del tanque)
            f_btns = tk.Frame(f_table, bg="#eee")
            f_btns.grid(row=r, column=1, sticky="nsew", padx=1, pady=1)
            btn_edit = tk.Button(f_btns, text="Ed.", bg="#eee", font=("Arial", 10), command=lambda t=tk_name, e=etapa: self.abrir_popup_detalle(e, t))
            btn_edit.pack(side="left", fill="both", expand=True)
            table_widgets.append(("btn", f_btns))
            table_widgets.append(("btn", btn_edit))

            # Campos Resumen — DINÁMICOS según tipo (deben coincidir EXACTAMENTE con los headers)
            if _is_el_t:
                # Electricidad: documento, kWh activa, reactiva, cos fi, demanda, vol nat
                vars_resumen = [
                    ("ddt_assign",   30, "white"),
                    ("el_kwh_act",   12, "#d5f5e3"),
                    ("el_kwh_rea",   12, "#d5f5e3"),
                    ("el_fp",        10, "#d5f5e3"),
                    ("el_dem",       10, "#d5f5e3"),
                    ("vol_nat_prod", 12, "#e8e8e8"),
                ]
            elif _is_duc_t:
                # Ductos: documento, producto, vol linea, vol base, vol base km3, caudal, vol nat
                vars_resumen = [
                    ("ddt_assign",    30, "white"),
                    ("prod_name",     20, "white"),
                    ("vol_linea",     12, "#d6eaf8"),
                    ("vol_base",      12, "#d6eaf8"),
                    ("vol_base_km3",  12, "#d6eaf8"),
                    ("caudal_mh",     10, "#d6eaf8"),
                    ("vol_nat_prod",  12, "#e8e8e8"),
                ]
            else:
                # Líquidos y gas: documento, producto, densidades, volúmenes, [agua], vol nat
                vars_resumen = [
                    ("ddt_assign",  30, "white"),
                    ("prod_name",   24, "white"),
                    ("dens_lab",    10, "#ffffcc"), ("dens_doc", 10, "#dcebf7"), ("dens_salida", 10, "#dcf7dc"),
                    ("v15_lab",     10, "#ffffcc"), ("kv_lab",   10, "#ffffcc"),
                    ("v15_doc",     10, "#dcebf7"), ("kv_doc",   10, "#dcebf7"),
                    ("v15_sal",     10, "#dcf7dc"), ("kv_sal",   10, "#dcf7dc"),
                ]
                if _show_agua_col:
                    vars_resumen.append(("vol_nat_agua", 10, "#ccffcc"))
                vars_resumen.append(("vol_nat_prod", 12, "#e8e8e8"))
            
            for c_idx, (var_key, w_size, bg_c) in enumerate(vars_resumen):
                val_var = self.get_var(f"{etapa}_{tk_name}_{var_key}")
                e = tk.Entry(f_table, textvariable=val_var, state="readonly", justify="center", font=("Arial", 8), width=w_size, readonlybackground=bg_c)
                e.grid(row=r, column=c_idx+2, sticky="nsew", padx=1, pady=1)
                table_widgets.append(("cell", e))

        # --- ESCALAR FUENTES SEGÚN ANCHO DE VENTANA ---
        self._last_font_size = [8]
        def scale_fonts(event=None):
            try:
                w = self.root.winfo_width()
                # Escalar: 6 para 800px, 8 para 1200px, 10 para 1600px, max 11
                new_size = max(6, min(11, int(w / 160)))
                if new_size != self._last_font_size[0]:
                    self._last_font_size[0] = new_size
                    for wtype, widget in table_widgets:
                        try:
                            if wtype == "header":
                                widget.configure(font=("Arial", min(8, new_size), "bold"))
                            elif wtype == "name":
                                widget.configure(font=("Arial", min(8, new_size), "bold"))
                            elif wtype == "btn":
                                widget.configure(font=("Arial", new_size + 2))
                            else:
                                widget.configure(font=("Arial", new_size))
                        except: pass
            except: pass
        self._scale_fonts_pending = None
        def _scale_fonts_debounced(event=None):
            if self._scale_fonts_pending is not None:
                try: self.root.after_cancel(self._scale_fonts_pending)
                except: pass
            self._scale_fonts_pending = self.root.after(100, scale_fonts)
        self.root.bind("<Configure>", _scale_fonts_debounced)

    def abrir_tabla_calibrado(self, etapa, tk_name, label_col2="LITROS", es_buque=False):
        """Gestiona la tabla de calibrado (sondaje -> litros) con CSV import/export, ordenar.
        Para buques (es_buque=True) agrega columna de corrección de trim (L/m de asiento)."""
        import json, csv as csv_mod
        top = tk.Toplevel(self.root)
        top.title(f"Tabla de Calibrado — {tk_name} ({etapa.upper()})")
        top.geometry("980x640" if es_buque else "720x620")
        top.resizable(True, True)
        var_key = f"{etapa}_{tk_name}_tabla_cal_json"

        fh = tk.Frame(top, bg="#4A235A", height=50)
        fh.pack(fill="x"); fh.pack_propagate(False)
        tk.Label(fh, text=f"TABLA DE CALIBRADO  |  {tk_name}  |  {etapa.upper()}",
                 bg="#4A235A", fg="white", font=("Arial",10,"bold")).pack(side="left", padx=16, pady=12)
        col2_info = f"Col.2: {label_col2}" + ("  |  Col.3: CORR.TRIM (L/m asiento)" if es_buque else "")
        tk.Label(fh, text=col2_info, bg="#4A235A", fg="#CE93D8", font=("Arial",8)).pack(side="right", padx=12)

        if es_buque:
            f_info = tk.Frame(top, bg="#EBF5FB", bd=1, relief="flat")
            f_info.pack(fill="x")
            tk.Label(f_info,
                     text="BUQUE / BARCAZA — Col.3 CORR.TRIM: litros a sumar por cada metro de asiento (trim) positivo "
                          "(popa más hundida que proa). Negativo si el tanque está a proa del LCF. "
                          "Dejar en 0 si no aplica corrección de trim.",
                     bg="#EBF5FB", fg="#1A5276", font=("Arial", 7), anchor="w",
                     wraplength=940, justify="left").pack(fill="x", padx=10, pady=4)

        f_ctrl = tk.Frame(top, bg="#EDE7F6", pady=6)
        f_ctrl.pack(fill="x")
        tk.Button(f_ctrl, text="Cargar CSV", bg="#8E44AD", fg="white", font=("Arial",8,"bold"),
                  command=lambda: _cargar_csv()).pack(side="left", padx=10, pady=4, ipadx=8, ipady=3)
        tk.Button(f_ctrl, text="Exportar CSV", bg="#2980B9", fg="white", font=("Arial",8),
                  command=lambda: _exportar_csv()).pack(side="left", padx=4, pady=4, ipadx=6, ipady=3)
        tk.Button(f_ctrl, text="+ Agregar fila", bg="#16A085", fg="white", font=("Arial",8),
                  command=lambda: _add_row("","","")).pack(side="left", padx=4, pady=4, ipadx=6, ipady=3)
        tk.Button(f_ctrl, text="Ordenar", bg="#7F8C8D", fg="white", font=("Arial",8),
                  command=lambda: _ordenar()).pack(side="left", padx=4, pady=4, ipadx=6, ipady=3)
        tk.Button(f_ctrl, text="Limpiar todo", bg="#C0392B", fg="white", font=("Arial",8),
                  command=lambda: _limpiar()).pack(side="left", padx=4, pady=4, ipadx=6, ipady=3)
        lbl_pts = tk.Label(f_ctrl, text="0 puntos", bg="#EDE7F6", font=("Arial",8), fg="#6A1B9A")
        lbl_pts.pack(side="right", padx=12)
        csv_hint = "CSV: sondaje_mm, litros, corr_trim" if es_buque else "CSV: sondaje_mm, litros"
        tk.Label(f_ctrl, text=csv_hint, bg="#EDE7F6", font=("Arial",7), fg="#6A1B9A").pack(side="right", padx=4)

        f_tbl = tk.Frame(top, bg="white")
        f_tbl.pack(fill="both", expand=True, padx=10, pady=6)
        canvas_t = tk.Canvas(f_tbl, bg="white", highlightthickness=0)
        sb_t = ttk.Scrollbar(f_tbl, orient="vertical", command=canvas_t.yview)
        scroll_inner = tk.Frame(canvas_t, bg="white")
        scroll_inner.bind("<Configure>", lambda e: canvas_t.configure(scrollregion=canvas_t.bbox("all")))
        win_id = canvas_t.create_window((0,0), window=scroll_inner, anchor="nw")
        canvas_t.bind("<Configure>", lambda e: canvas_t.itemconfig(win_id, width=e.width))
        canvas_t.configure(yscrollcommand=sb_t.set)
        sb_t.pack(side="right", fill="y"); canvas_t.pack(fill="both", expand=True)
        canvas_t.bind("<MouseWheel>", lambda e: canvas_t.yview_scroll(int(-1*(e.delta/120)) if e.delta else (1 if e.num==5 else -1), "units"))
        canvas_t.bind("<Button-4>", lambda e: canvas_t.yview_scroll(-1,"units"))
        canvas_t.bind("<Button-5>", lambda e: canvas_t.yview_scroll(1,"units"))

        hdr = tk.Frame(scroll_inner, bg="#4A235A")
        hdr.pack(fill="x")
        tk.Label(hdr, text="#", width=5, bg="#4A235A", fg="white", font=("Arial",8,"bold")).pack(side="left", padx=2, pady=3)
        tk.Label(hdr, text="SONDAJE (mm)", width=18, bg="#4A235A", fg="white", font=("Arial",8,"bold")).pack(side="left", padx=2)
        tk.Label(hdr, text=label_col2, width=18, bg="#4A235A", fg="white", font=("Arial",8,"bold")).pack(side="left", padx=2)
        if es_buque:
            tk.Label(hdr, text="CORR.TRIM (L/m asiento)", width=22, bg="#1A5276",
                     fg="white", font=("Arial",8,"bold")).pack(side="left", padx=2)
        tk.Label(hdr, text="Quitar", width=6, bg="#4A235A", fg="white", font=("Arial",8,"bold")).pack(side="left", padx=2)

        rows_data = []

        def _update_count():
            n = len([r for r in rows_data if r["sond"].get().strip() and r["lits"].get().strip()])
            lbl_pts.config(text=f"{n} puntos")

        def _render_rows():
            for w in scroll_inner.winfo_children():
                if hasattr(w, "_cal_row"): w.destroy()
            for i, rd in enumerate(rows_data):
                rf = tk.Frame(scroll_inner, bg="#F3E5F5" if i%2==0 else "white")
                rf._cal_row = True
                rf.pack(fill="x")
                tk.Label(rf, text=str(i+1), width=5, bg=rf["bg"], font=("Arial",7)).pack(side="left", padx=2, pady=2)
                e1 = tk.Entry(rf, textvariable=rd["sond"], width=18, justify="center", font=("Arial",9), bg="#FDFEFE")
                e1.pack(side="left", padx=2)
                e2 = tk.Entry(rf, textvariable=rd["lits"], width=18, justify="center", font=("Arial",9), bg="#FDFEFE")
                e2.pack(side="left", padx=2)
                e1.bind("<KeyRelease>", lambda ev: _update_count())
                e2.bind("<KeyRelease>", lambda ev: _update_count())
                if es_buque:
                    e3 = tk.Entry(rf, textvariable=rd["trim"], width=22, justify="center",
                                  font=("Arial",9), bg="#EBF5FB")
                    e3.pack(side="left", padx=2)
                    e3.bind("<KeyRelease>", lambda ev: _update_count())
                tk.Button(rf, text="X", bg="#E74C3C", fg="white", width=4, font=("Arial",7),
                          command=lambda idx=i: _del_row(idx)).pack(side="left", padx=2)
            _update_count()

        def _add_row(s_val="", l_val="", t_val="0"):
            rows_data.append({"sond": tk.StringVar(value=str(s_val)),
                               "lits": tk.StringVar(value=str(l_val)),
                               "trim": tk.StringVar(value=str(t_val))})
            _render_rows()

        def _del_row(idx):
            if 0 <= idx < len(rows_data): del rows_data[idx]
            _render_rows()

        def _limpiar():
            rows_data.clear(); _render_rows()

        def _ordenar():
            pts = []
            for rd in rows_data:
                s = rd["sond"].get().strip().replace(",",".")
                l = rd["lits"].get().strip().replace(",",".")
                t = rd["trim"].get().strip().replace(",",".") if es_buque else "0"
                try:
                    pts.append((float(s), float(l), float(t) if t else 0.0))
                except: pass
            pts.sort(key=lambda x: x[0])
            rows_data.clear()
            for s, l, t in pts:
                rows_data.append({"sond": tk.StringVar(value=str(s)),
                                   "lits": tk.StringVar(value=str(l)),
                                   "trim": tk.StringVar(value=str(t))})
            _render_rows()

        def _parse_line(line):
            line = line.strip()
            if not line or line.startswith("#"): return None
            for sep in [",",";","\t","  "," "]:
                parts = line.split(sep)
                if len(parts) >= 2:
                    try:
                        s_v = parts[0].strip().replace(",",".")
                        l_v = parts[1].strip().replace(",",".")
                        t_v = parts[2].strip().replace(",",".") if len(parts) >= 3 else "0"
                        float(s_v); float(l_v); float(t_v)
                        return s_v, l_v, t_v
                    except: pass
            return None

        def _cargar_csv():
            f_path = filedialog.askopenfilename(
                title="Cargar tabla de calibrado",
                filetypes=[("CSV/TXT","*.csv *.txt"),("Todos","*.*")], parent=top)
            if not f_path: return
            try:
                nuevos = []
                with open(f_path, "r", encoding="utf-8-sig") as fcsv:
                    for line in fcsv:
                        parsed = _parse_line(line)
                        if parsed: nuevos.append(parsed)
                if not nuevos:
                    messagebox.showwarning("Sin datos", "No se encontraron pares numericos en el archivo.", parent=top); return
                if rows_data and any(r["sond"].get().strip() for r in rows_data):
                    if messagebox.askyesno("Reemplazar o agregar", "Reemplazar la tabla actual?\n(No = agregar a la existente)", parent=top):
                        rows_data.clear()
                for s_v, l_v, t_v in nuevos:
                    rows_data.append({"sond": tk.StringVar(value=s_v),
                                       "lits": tk.StringVar(value=l_v),
                                       "trim": tk.StringVar(value=t_v)})
                _render_rows()
                messagebox.showinfo("OK", f"Cargados {len(nuevos)} puntos.", parent=top)
            except Exception as ex:
                messagebox.showerror("Error", f"No se pudo leer el archivo:\n{ex}", parent=top)


        def _exportar_csv():
            if es_buque:
                pts = [(r["sond"].get().strip(), r["lits"].get().strip(), r["trim"].get().strip() or "0")
                       for r in rows_data if r["sond"].get().strip() and r["lits"].get().strip()]
            else:
                pts = [(r["sond"].get().strip(), r["lits"].get().strip())
                       for r in rows_data if r["sond"].get().strip() and r["lits"].get().strip()]
            if not pts:
                messagebox.showwarning("Sin datos", "No hay puntos para exportar.", parent=top); return
            f_path = filedialog.asksaveasfilename(
                title="Exportar tabla de calibrado", defaultextension=".csv",
                filetypes=[("CSV","*.csv"),("Texto","*.txt")],
                initialfile=f"calibrado_{tk_name}_{etapa}.csv", parent=top)
            if not f_path: return
            try:
                with open(f_path, "w", newline="", encoding="utf-8") as fc:
                    writer = csv_mod.writer(fc)
                    if es_buque:
                        writer.writerow(["sondaje_mm", label_col2.lower().replace(" ","_"), "corr_trim_L_m"])
                        for row in pts: writer.writerow(row)
                    else:
                        writer.writerow(["sondaje_mm", label_col2.lower().replace(" ","_")])
                        for s, l in pts: writer.writerow([s, l])
                messagebox.showinfo("Exportado", f"Exportados {len(pts)} puntos.\n{f_path}", parent=top)
            except Exception as ex:
                messagebox.showerror("Error", f"No se pudo exportar:\n{ex}", parent=top)

        existing = self.get_var(var_key).get()
        if existing:
            try:
                for pt in json.loads(existing):
                    _add_row(pt[0], pt[1], pt[2] if len(pt) > 2 else "0")
            except: pass
        if not rows_data:
            for _ in range(10): _add_row("", "", "0")
        _render_rows()

        f_foot = tk.Frame(top, bg="#2C3E50", height=50)
        f_foot.pack(fill="x", side="bottom"); f_foot.pack_propagate(False)

        def _guardar():
            pts = []
            for rd in rows_data:
                s = rd["sond"].get().strip().replace(",",".")
                l = rd["lits"].get().strip().replace(",",".")
                t = rd["trim"].get().strip().replace(",",".") if es_buque else "0"
                if not s or not l: continue
                try:
                    entry = [float(s), float(l)]
                    if es_buque: entry.append(float(t) if t else 0.0)
                    pts.append(entry)
                except: pass
            if not pts:
                self.get_var(var_key).set(""); top.destroy(); return
            pts.sort(key=lambda x: x[0])
            self.get_var(var_key).set(json.dumps(pts))
            top.destroy()
            messagebox.showinfo("Guardado", f"Tabla guardada: {len(pts)} puntos.\nRango: {pts[0][0]:.0f} mm -> {pts[-1][0]:.0f} mm")

        tk.Button(f_foot, text="  [OK] GUARDAR TABLA  ", bg="#27AE60", fg="white",
                  font=("Arial",9,"bold"), relief="flat", cursor="hand2",
                  command=_guardar).pack(side="left", padx=16, pady=8, ipadx=12, ipady=4)
        tk.Button(f_foot, text="Cancelar", bg="#7F8C8D", fg="white", font=("Arial",8), relief="flat",
                  command=top.destroy).pack(side="right", padx=8, pady=8, ipadx=6, ipady=3)
        tk.Label(f_foot, text="Ordenar antes de guardar para mejor interpolacion",
                 bg="#2C3E50", fg="#AED6F1", font=("Arial",7)).pack(side="right", padx=12)

    def abrir_interp_trim_rapida(self, etapa, tk_name, agua=False):
        """Carga manual rápida para interpolar por asiento (trim) en buques.
        El usuario lee de la tabla de calibrado impresa los dos sondajes que
        rodean su medición y los litros en las dos páginas de asiento que
        rodean el asiento real (p.ej. 0 y 0.5). Interpola en 2D y guarda en
        {etapa}_{tanque}_tabla_trim[_agua]_json (mismo formato que el editor
        completo). Con agua=True opera sobre el sondaje de agua de fondo."""
        import json
        _que = "AGUA" if agua else "PRODUCTO"
        _hbg = "#117864" if agua else "#1A5276"
        top = tk.Toplevel(self.root)
        top.title(f"Interpolación × Asiento ({_que}) — {tk_name} ({etapa.upper()})")
        top.geometry("640x470")
        top.resizable(False, False)
        var_key = f"{etapa}_{tk_name}_tabla_trim{'_agua' if agua else ''}_json"

        _s_key = f"{etapa}_{tk_name}_agua_s_real" if agua else f"{etapa}_{tk_name}_s_corr"
        s_act = self.parse_float(self.get_var(_s_key).get())
        trim_act = self.parse_float(self.get_var(f"{etapa}_Trimación").get() or "0")

        fh = tk.Frame(top, bg=_hbg, height=46)
        fh.pack(fill="x"); fh.pack_propagate(False)
        tk.Label(fh, text=f"INTERPOLACIÓN × ASIENTO ({_que})  |  {tk_name}  |  {etapa.upper()}",
                 bg=_hbg, fg="white", font=("Arial",10,"bold")).pack(side="left", padx=14, pady=10)
        tk.Label(fh, text=f"Sondaje{' agua' if agua else ''}: {s_act:.0f} mm   Asiento: {trim_act:+.2f} m",
                 bg=_hbg, fg="#AED6F1", font=("Arial",9,"bold")).pack(side="right", padx=12)

        tk.Label(top, text="Cargá el sondaje de la tabla y sus litros en los 2 asientos que rodean el asiento real "
                           "del buque. La 2da fila es opcional: usala solo si tu sondaje medido cae entre dos "
                           "filas de la tabla (interpola también por sondaje).",
                 bg="#EBF5FB", fg="#1A5276", font=("Arial",8), anchor="w", wraplength=610,
                 justify="left").pack(fill="x", padx=0, pady=(0,4), ipadx=10, ipady=4)

        # Prefill desde tabla guardada (si es chica) o valores por defecto
        tA, tB = 0.0, 0.5
        pre = [["",""],["",""]]   # [fila][col] litros
        pre_s = ["",""]
        existing = self.get_var(var_key).get()
        if existing:
            try:
                obj0 = json.loads(existing)
                tr0 = [float(t) for t in obj0.get("trims", [])]
                rw0 = obj0.get("rows", [])
                if len(tr0) >= 2: tA, tB = tr0[0], tr0[1]
                for i in range(min(2, len(rw0))):
                    pre_s[i] = f"{rw0[i][0]:g}"
                    if len(rw0[i]) > 1 and rw0[i][1] is not None: pre[i][0] = f"{rw0[i][1]:g}"
                    if len(rw0[i]) > 2 and rw0[i][2] is not None: pre[i][1] = f"{rw0[i][2]:g}"
            except: pass

        f_g = tk.Frame(top, bg="white", padx=14, pady=8); f_g.pack(fill="both", expand=True)
        v_tA = tk.StringVar(value=f"{tA:g}"); v_tB = tk.StringVar(value=f"{tB:g}")
        v_s  = [tk.StringVar(value=pre_s[0]), tk.StringVar(value=pre_s[1])]
        v_l  = [[tk.StringVar(value=pre[0][0]), tk.StringVar(value=pre[0][1])],
                [tk.StringVar(value=pre[1][0]), tk.StringVar(value=pre[1][1])]]

        fbh = ("Arial", 9, "bold")
        tk.Label(f_g, text="", bg="white").grid(row=0, column=0)
        tk.Label(f_g, text="ASIENTO A (m)", bg="#D6EAF8", font=fbh, width=16).grid(row=0, column=1, padx=3, pady=3, sticky="ew")
        tk.Label(f_g, text="ASIENTO B (m)", bg="#D6EAF8", font=fbh, width=16).grid(row=0, column=2, padx=3, pady=3, sticky="ew")
        tk.Label(f_g, text="Asiento →", bg="white", font=fbh, anchor="e").grid(row=1, column=0, sticky="e", padx=3)
        e_tA = tk.Entry(f_g, textvariable=v_tA, justify="center", font=("Arial",11,"bold"), bg="#EBF5FB", width=14)
        e_tA.grid(row=1, column=1, padx=3, pady=2, ipady=3)
        e_tB = tk.Entry(f_g, textvariable=v_tB, justify="center", font=("Arial",11,"bold"), bg="#EBF5FB", width=14)
        e_tB.grid(row=1, column=2, padx=3, pady=2, ipady=3)

        tk.Label(f_g, text="SONDAJE (mm)", bg="#D5DBDB", font=fbh).grid(row=2, column=0, padx=3, pady=(10,3), sticky="ew")
        _lit = "LTS.AGUA" if agua else "LITROS"
        tk.Label(f_g, text=f"{_lit} @ A", bg="#D6EAF8", font=fbh).grid(row=2, column=1, padx=3, pady=(10,3), sticky="ew")
        tk.Label(f_g, text=f"{_lit} @ B", bg="#D6EAF8", font=fbh).grid(row=2, column=2, padx=3, pady=(10,3), sticky="ew")

        entries = []
        for i in range(2):
            e_s = tk.Entry(f_g, textvariable=v_s[i], justify="center", font=("Arial",12), bg="#FDFEFE", width=14)
            e_s.grid(row=3+i, column=0, padx=3, pady=3, ipady=4)
            e_a = tk.Entry(f_g, textvariable=v_l[i][0], justify="center", font=("Arial",12), bg="#F4FAFF", width=14)
            e_a.grid(row=3+i, column=1, padx=3, pady=3, ipady=4)
            e_b = tk.Entry(f_g, textvariable=v_l[i][1], justify="center", font=("Arial",12), bg="#F4FAFF", width=14)
            e_b.grid(row=3+i, column=2, padx=3, pady=3, ipady=4)
            entries += [e_s, e_a, e_b]

        lbl_res = tk.Label(f_g, text="—", bg="#FEF9E7", fg="#7D6608",
                           font=("Arial",11,"bold"), relief="groove", pady=8)
        lbl_res.grid(row=5, column=0, columnspan=3, sticky="ew", padx=3, pady=(14,4))
        lbl_det = tk.Label(f_g, text="", bg="white", fg="#616A6B", font=("Arial",8), wraplength=580, justify="left")
        lbl_det.grid(row=6, column=0, columnspan=3, sticky="ew", padx=3)

        def _build_obj():
            try:
                ta = float(v_tA.get().strip().replace(",","."))
                tb = float(v_tB.get().strip().replace(",","."))
            except: return None
            rows = []
            for i in range(2):
                s = v_s[i].get().strip().replace(",",".")
                la = v_l[i][0].get().strip().replace(",",".")
                lb = v_l[i][1].get().strip().replace(",",".")
                if not s: continue
                try:
                    rows.append([float(s),
                                 float(la) if la else None,
                                 float(lb) if lb else None])
                except: pass
            if not rows: return None
            return {"trims": [ta, tb], "rows": rows}

        def _preview(*_a):
            obj = _build_obj()
            if not obj:
                lbl_res.config(text="—"); lbl_det.config(text=""); return
            vol, det = self._interp_trim_table(obj, s_act, trim_act)
            if vol is None:
                lbl_res.config(text="Faltan datos"); lbl_det.config(text=str(det)); return
            lbl_res.config(text=f"VOLUMEN INTERPOLADO:  {vol:,.0f} L".replace(",","."))
            lbl_det.config(text=det)

        for vv in [v_tA, v_tB] + v_s + v_l[0] + v_l[1]:
            vv.trace_add("write", _preview)
        _preview()

        f_foot = tk.Frame(top, bg="#154360", height=48)
        f_foot.pack(fill="x", side="bottom"); f_foot.pack_propagate(False)

        def _guardar():
            obj = _build_obj()
            if not obj:
                self.get_var(var_key).set("")
            else:
                obj["rows"].sort(key=lambda r: r[0])
                self.get_var(var_key).set(json.dumps(obj))
            top.destroy()
            if agua: self.calc_volumen_agua_ui(etapa, tk_name)
            else: self.calc_volumen_prod_ui(etapa, tk_name)

        tk.Button(f_foot, text="  [OK] GUARDAR Y APLICAR  ", bg="#27AE60", fg="white",
                  font=("Arial",9,"bold"), relief="flat", cursor="hand2",
                  command=_guardar).pack(side="left", padx=14, pady=8, ipadx=10, ipady=4)
        tk.Button(f_foot, text="Tabla completa / CSV…", bg="#5D6D7E", fg="white", font=("Arial",8), relief="flat",
                  command=lambda: (top.destroy(), self.abrir_tabla_calibrado_trim(etapa, tk_name, agua=agua))
                  ).pack(side="left", padx=6, pady=8, ipadx=6, ipady=3)
        tk.Button(f_foot, text="Cancelar", bg="#7F8C8D", fg="white", font=("Arial",8), relief="flat",
                  command=top.destroy).pack(side="right", padx=10, pady=8, ipadx=6, ipady=3)

    def abrir_tabla_calibrado_trim(self, etapa, tk_name, label_col2="LITROS", agua=False):
        """Editor de tabla de calibrado con múltiples columnas de asiento (trim) para
        buques/barcazas. Cada sondaje tiene un volumen por cada asiento (p.ej. 0, 0.5,
        1.0, 1.5 m de diferencia popa-proa). El volumen final se interpola en 2D
        (sondaje × asiento real). Se guarda en {etapa}_{tanque}_tabla_trim[_agua]_json."""
        import json, csv as csv_mod
        if agua and label_col2 == "LITROS": label_col2 = "LTS.AGUA"
        top = tk.Toplevel(self.root)
        top.title(f"Calibrado × Asiento (Trim{', AGUA' if agua else ''}) — {tk_name} ({etapa.upper()})")
        top.geometry("1040x660")
        top.resizable(True, True)
        var_key = f"{etapa}_{tk_name}_tabla_trim{'_agua' if agua else ''}_json"

        fh = tk.Frame(top, bg="#1A5276", height=50)
        fh.pack(fill="x"); fh.pack_propagate(False)
        tk.Label(fh, text=f"CALIBRADO × ASIENTO  |  {tk_name}  |  {etapa.upper()}",
                 bg="#1A5276", fg="white", font=("Arial",10,"bold")).pack(side="left", padx=16, pady=12)
        tk.Label(fh, text=f"Col.2+: {label_col2} por asiento (m)", bg="#1A5276", fg="#AED6F1",
                 font=("Arial",8)).pack(side="right", padx=12)

        f_info = tk.Frame(top, bg="#EBF5FB"); f_info.pack(fill="x")
        tk.Label(f_info,
                 text="BUQUE / BARCAZA — La tabla de sondaje trae un volumen por cada 'asiento' (diferencia popa-proa, en metros). "
                      "Cargá una columna por cada asiento de tu tabla (típico: 0, 0.5, 1.0, 1.5). El programa interpola el volumen "
                      "según el sondaje corregido y el asiento (Trimación = Calado Popa − Calado Proa) real de la medición.",
                 bg="#EBF5FB", fg="#1A5276", font=("Arial",7), anchor="w",
                 wraplength=1000, justify="left").pack(fill="x", padx=10, pady=4)

        # ── Configuración de columnas de asiento ───────────────────────────
        f_cols = tk.Frame(top, bg="#D6EAF8", pady=4); f_cols.pack(fill="x")
        tk.Label(f_cols, text="Asientos (m), separados por coma:", bg="#D6EAF8",
                 font=("Arial",8,"bold"), fg="#1A5276").pack(side="left", padx=(12,4))
        var_trims = tk.StringVar(value="0, 0.5, 1.0, 1.5")
        e_trims = tk.Entry(f_cols, textvariable=var_trims, width=30, font=("Arial",9), justify="center")
        e_trims.pack(side="left", padx=4)
        tk.Button(f_cols, text="Aplicar columnas", bg="#2874A6", fg="white", font=("Arial",8,"bold"),
                  command=lambda: _aplicar_columnas()).pack(side="left", padx=8, ipadx=6, ipady=2)
        lbl_pts = tk.Label(f_cols, text="0 filas", bg="#D6EAF8", font=("Arial",8), fg="#1A5276")
        lbl_pts.pack(side="right", padx=12)

        f_ctrl = tk.Frame(top, bg="#EAF2F8", pady=6); f_ctrl.pack(fill="x")
        tk.Button(f_ctrl, text="Cargar CSV", bg="#1A5276", fg="white", font=("Arial",8,"bold"),
                  command=lambda: _cargar_csv()).pack(side="left", padx=10, pady=4, ipadx=8, ipady=3)
        tk.Button(f_ctrl, text="Exportar CSV", bg="#2980B9", fg="white", font=("Arial",8),
                  command=lambda: _exportar_csv()).pack(side="left", padx=4, pady=4, ipadx=6, ipady=3)
        tk.Button(f_ctrl, text="+ Agregar fila", bg="#16A085", fg="white", font=("Arial",8),
                  command=lambda: _add_row()).pack(side="left", padx=4, pady=4, ipadx=6, ipady=3)
        tk.Button(f_ctrl, text="Ordenar", bg="#7F8C8D", fg="white", font=("Arial",8),
                  command=lambda: _ordenar()).pack(side="left", padx=4, pady=4, ipadx=6, ipady=3)
        tk.Button(f_ctrl, text="Limpiar todo", bg="#C0392B", fg="white", font=("Arial",8),
                  command=lambda: _limpiar()).pack(side="left", padx=4, pady=4, ipadx=6, ipady=3)
        tk.Label(f_ctrl, text="CSV: sondaje_mm, v_asiento0, v_asiento1, ...  (1ra fila = encabezado con asientos)",
                 bg="#EAF2F8", font=("Arial",7), fg="#1A5276").pack(side="right", padx=8)

        f_tbl = tk.Frame(top, bg="white"); f_tbl.pack(fill="both", expand=True, padx=10, pady=6)
        canvas_t = tk.Canvas(f_tbl, bg="white", highlightthickness=0)
        sb_t = ttk.Scrollbar(f_tbl, orient="vertical", command=canvas_t.yview)
        scroll_inner = tk.Frame(canvas_t, bg="white")
        scroll_inner.bind("<Configure>", lambda e: canvas_t.configure(scrollregion=canvas_t.bbox("all")))
        win_id = canvas_t.create_window((0,0), window=scroll_inner, anchor="nw")
        canvas_t.bind("<Configure>", lambda e: canvas_t.itemconfig(win_id, width=e.width))
        canvas_t.configure(yscrollcommand=sb_t.set)
        sb_t.pack(side="right", fill="y"); canvas_t.pack(fill="both", expand=True)
        canvas_t.bind("<MouseWheel>", lambda e: canvas_t.yview_scroll(int(-1*(e.delta/120)) if e.delta else (1 if e.num==5 else -1), "units"))
        canvas_t.bind("<Button-4>", lambda e: canvas_t.yview_scroll(-1,"units"))
        canvas_t.bind("<Button-5>", lambda e: canvas_t.yview_scroll(1,"units"))

        state = {"trims": [0.0, 0.5, 1.0, 1.5]}
        rows_data = []   # cada fila: {"sond": StringVar, "vols": [StringVar, ...]}

        def _parse_trims():
            raw = var_trims.get().replace(";", ",")
            out = []
            for tok in raw.split(","):
                tok = tok.strip().replace(",", ".")
                if not tok: continue
                try: out.append(float(tok))
                except: pass
            return out or [0.0]

        def _update_count():
            n = len([r for r in rows_data if r["sond"].get().strip()])
            lbl_pts.config(text=f"{n} filas × {len(state['trims'])} asientos")

        def _render_rows():
            for w in scroll_inner.winfo_children(): w.destroy()
            hdr = tk.Frame(scroll_inner, bg="#1A5276"); hdr.pack(fill="x")
            tk.Label(hdr, text="#", width=4, bg="#1A5276", fg="white", font=("Arial",8,"bold")).pack(side="left", padx=2, pady=3)
            tk.Label(hdr, text="SONDAJE (mm)", width=14, bg="#1A5276", fg="white", font=("Arial",8,"bold")).pack(side="left", padx=2)
            for tval in state["trims"]:
                tk.Label(hdr, text=f"{label_col2} @ {tval:g}m", width=13, bg="#21618C",
                         fg="white", font=("Arial",8,"bold")).pack(side="left", padx=2)
            tk.Label(hdr, text="Quitar", width=6, bg="#1A5276", fg="white", font=("Arial",8,"bold")).pack(side="left", padx=2)
            for i, rd in enumerate(rows_data):
                rf = tk.Frame(scroll_inner, bg="#EBF5FB" if i%2==0 else "white"); rf.pack(fill="x")
                tk.Label(rf, text=str(i+1), width=4, bg=rf["bg"], font=("Arial",7)).pack(side="left", padx=2, pady=2)
                tk.Entry(rf, textvariable=rd["sond"], width=14, justify="center", font=("Arial",9),
                         bg="#FDFEFE").pack(side="left", padx=2)
                for vv in rd["vols"]:
                    tk.Entry(rf, textvariable=vv, width=13, justify="center", font=("Arial",9),
                             bg="#F4FAFF").pack(side="left", padx=2)
                tk.Button(rf, text="X", bg="#E74C3C", fg="white", width=4, font=("Arial",7),
                          command=lambda idx=i: _del_row(idx)).pack(side="left", padx=2)
            _update_count()

        def _add_row(s_val="", v_vals=None):
            v_vals = v_vals or []
            vols = [tk.StringVar(value=str(v_vals[c]) if c < len(v_vals) else "")
                    for c in range(len(state["trims"]))]
            rows_data.append({"sond": tk.StringVar(value=str(s_val)), "vols": vols})
            _render_rows()

        def _del_row(idx):
            if 0 <= idx < len(rows_data): del rows_data[idx]
            _render_rows()

        def _limpiar():
            rows_data.clear(); _render_rows()

        def _aplicar_columnas():
            new_trims = _parse_trims()
            old_n = len(state["trims"])
            state["trims"] = new_trims
            for rd in rows_data:
                cur = rd["vols"]
                if len(new_trims) > len(cur):
                    cur.extend(tk.StringVar(value="") for _ in range(len(new_trims) - len(cur)))
                elif len(new_trims) < len(cur):
                    del cur[len(new_trims):]
            var_trims.set(", ".join(f"{t:g}" for t in new_trims))
            _render_rows()

        def _ordenar():
            def _key(rd):
                try: return float(rd["sond"].get().strip().replace(",","."))
                except: return float("inf")
            rows_data.sort(key=_key)
            _render_rows()

        def _cargar_csv():
            f_path = filedialog.askopenfilename(
                title="Cargar tabla de calibrado × asiento",
                filetypes=[("CSV/TXT","*.csv *.txt"),("Todos","*.*")], parent=top)
            if not f_path: return
            try:
                raw_rows = []
                with open(f_path, "r", encoding="utf-8-sig") as fcsv:
                    for line in fcsv:
                        line = line.strip()
                        if not line or line.startswith("#"): continue
                        for sep in [",",";","\t"]:
                            if sep in line: parts = [p.strip() for p in line.split(sep)]; break
                        else: parts = line.split()
                        raw_rows.append(parts)
                if not raw_rows:
                    messagebox.showwarning("Sin datos", "Archivo vacío.", parent=top); return
                # ¿Primera fila es encabezado de asientos? (col0 no numérica)
                hdr_trims = None
                try: float(raw_rows[0][0].replace(",","."))
                except:
                    hdr_trims = []
                    for c in raw_rows[0][1:]:
                        cc = "".join(ch for ch in c.replace(",",".") if (ch.isdigit() or ch in ".-"))
                        try: hdr_trims.append(float(cc))
                        except: pass
                    raw_rows = raw_rows[1:]
                if hdr_trims:
                    state["trims"] = hdr_trims
                    var_trims.set(", ".join(f"{t:g}" for t in hdr_trims))
                rows_data.clear()
                for parts in raw_rows:
                    try:
                        s_v = parts[0].strip().replace(",",".")
                        float(s_v)
                    except: continue
                    v_vals = [p.strip().replace(",",".") for p in parts[1:]]
                    _add_row(s_v, v_vals)
                if not rows_data: _add_row()
                _render_rows()
                messagebox.showinfo("OK", f"Cargadas {len(raw_rows)} filas, {len(state['trims'])} asientos.", parent=top)
            except Exception as ex:
                messagebox.showerror("Error", f"No se pudo leer:\n{ex}", parent=top)

        def _exportar_csv():
            filas = []
            for rd in rows_data:
                s = rd["sond"].get().strip()
                if not s: continue
                filas.append([s] + [vv.get().strip() for vv in rd["vols"]])
            if not filas:
                messagebox.showwarning("Sin datos", "No hay filas para exportar.", parent=top); return
            f_path = filedialog.asksaveasfilename(
                title="Exportar calibrado × asiento", defaultextension=".csv",
                filetypes=[("CSV","*.csv"),("Texto","*.txt")],
                initialfile=f"calibrado_trim_{tk_name}_{etapa}.csv", parent=top)
            if not f_path: return
            try:
                with open(f_path, "w", newline="", encoding="utf-8") as fc:
                    writer = csv_mod.writer(fc)
                    writer.writerow(["sondaje_mm"] + [f"{t:g}" for t in state["trims"]])
                    for row in filas: writer.writerow(row)
                messagebox.showinfo("Exportado", f"Exportadas {len(filas)} filas.\n{f_path}", parent=top)
            except Exception as ex:
                messagebox.showerror("Error", f"No se pudo exportar:\n{ex}", parent=top)

        # Cargar datos existentes
        existing = self.get_var(var_key).get()
        if existing:
            try:
                obj = json.loads(existing)
                state["trims"] = [float(t) for t in obj.get("trims", [0.0])] or [0.0]
                var_trims.set(", ".join(f"{t:g}" for t in state["trims"]))
                for r in obj.get("rows", []):
                    if not r: continue
                    _add_row(r[0], r[1:])
            except: pass
        if not rows_data:
            for _ in range(8): _add_row()
        _render_rows()

        f_foot = tk.Frame(top, bg="#154360", height=50); f_foot.pack(fill="x", side="bottom")
        f_foot.pack_propagate(False)

        def _guardar():
            trims = _parse_trims()
            state["trims"] = trims
            rows = []
            for rd in rows_data:
                s = rd["sond"].get().strip().replace(",",".")
                if not s: continue
                try: s_f = float(s)
                except: continue
                vols = []
                any_v = False
                for c in range(len(trims)):
                    raw = rd["vols"][c].get().strip().replace(",",".") if c < len(rd["vols"]) else ""
                    if raw:
                        try: vols.append(float(raw)); any_v = True
                        except: vols.append(None)
                    else:
                        vols.append(None)
                if any_v: rows.append([s_f] + vols)
            _recalc = self.calc_volumen_agua_ui if agua else self.calc_volumen_prod_ui
            if not rows:
                self.get_var(var_key).set(""); top.destroy()
                _recalc(etapa, tk_name); return
            rows.sort(key=lambda r: r[0])
            self.get_var(var_key).set(json.dumps({"trims": trims, "rows": rows}))
            top.destroy()
            _recalc(etapa, tk_name)
            messagebox.showinfo("Guardado",
                f"Tabla × asiento guardada: {len(rows)} sondajes × {len(trims)} asientos.\n"
                f"Asientos: {', '.join(f'{t:g}' for t in trims)} m\n"
                f"Rango sondaje: {rows[0][0]:.0f} → {rows[-1][0]:.0f} mm")

        tk.Button(f_foot, text="  [OK] GUARDAR TABLA  ", bg="#27AE60", fg="white",
                  font=("Arial",9,"bold"), relief="flat", cursor="hand2",
                  command=_guardar).pack(side="left", padx=16, pady=8, ipadx=12, ipady=4)
        tk.Button(f_foot, text="Cancelar", bg="#7F8C8D", fg="white", font=("Arial",8), relief="flat",
                  command=top.destroy).pack(side="right", padx=8, pady=8, ipadx=6, ipady=3)
        tk.Label(f_foot, text="El volumen se interpola por sondaje y por asiento (Popa−Proa) real",
                 bg="#154360", fg="#AED6F1", font=("Arial",7)).pack(side="right", padx=12)

    def crear_interp_trim_inline(self, etapa, tk_name, parent, start_row, agua=False):
        """Sección embebida en la ficha del tanque para cargar la interpolación
        × asiento (trim) sin abrir el diálogo aparte. Mismo formato y variable
        que abrir_interp_trim_rapida ({etapa}_{tanque}_tabla_trim[_agua]_json).
        Aplica y recalcula en vivo al tipear. Devuelve las filas de grilla usadas."""
        import json
        var_key = f"{etapa}_{tk_name}_tabla_trim{'_agua' if agua else ''}_json"
        _hbg = "#117864" if agua else "#1A5276"
        _titulo = "AGUA" if agua else "PRODUCTO"
        _lit = "Lts.Agua" if agua else "Litros"
        _bgl = "#D1F2EB" if agua else "#D6EAF8"
        fb = ("Arial", 8, "bold")

        # Prefill desde la tabla guardada (si es chica, igual que el diálogo rápido)
        tA, tB = 0.0, 0.5
        pre = [["", ""], ["", ""]]
        pre_s = ["", ""]
        existing = self.get_var(var_key).get()
        if existing:
            try:
                obj0 = json.loads(existing)
                tr0 = [float(t) for t in obj0.get("trims", [])]
                rw0 = obj0.get("rows", [])
                if len(tr0) >= 2: tA, tB = tr0[0], tr0[1]
                for i in range(min(2, len(rw0))):
                    pre_s[i] = f"{rw0[i][0]:g}"
                    if len(rw0[i]) > 1 and rw0[i][1] is not None: pre[i][0] = f"{rw0[i][1]:g}"
                    if len(rw0[i]) > 2 and rw0[i][2] is not None: pre[i][1] = f"{rw0[i][2]:g}"
            except: pass

        v_tA = tk.StringVar(value=f"{tA:g}"); v_tB = tk.StringVar(value=f"{tB:g}")
        v_s = [tk.StringVar(value=pre_s[0]), tk.StringVar(value=pre_s[1])]
        v_l = [[tk.StringVar(value=pre[0][0]), tk.StringVar(value=pre[0][1])],
               [tk.StringVar(value=pre[1][0]), tk.StringVar(value=pre[1][1])]]
        v_res = tk.StringVar(value="—")

        r = start_row
        tk.Label(parent, text=f"── INTERPOLACIÓN × ASIENTO ({_titulo}) — 2da fila opcional ──",
                 font=fb, fg="white", bg=_hbg).grid(row=r, column=0, columnspan=8, pady=(8,2), sticky="ew")
        tk.Button(parent, text="Tabla completa/CSV…", bg="#5D6D7E", fg="white", font=("Arial", 7),
                  relief="flat", cursor="hand2",
                  command=lambda: self.abrir_tabla_calibrado_trim(etapa, tk_name, agua=agua)
                  ).grid(row=r, column=8, sticky="ew", padx=1, pady=(8, 2))
        r += 1
        _cols = [("Asiento A (m)", v_tA), ("Asiento B (m)", v_tB),
                 ("Sondaje 1 (mm)", v_s[0]), (f"{_lit} 1 @A", v_l[0][0]), (f"{_lit} 1 @B", v_l[0][1]),
                 ("Sondaje 2 (mm)", v_s[1]), (f"{_lit} 2 @A", v_l[1][0]), (f"{_lit} 2 @B", v_l[1][1])]
        for ci, (lbl_t, _v) in enumerate(_cols):
            tk.Label(parent, text=lbl_t, font=fb, bg=_bgl, anchor="w").grid(
                row=r, column=ci, sticky="ew", padx=1, pady=(2, 0))
            tk.Entry(parent, textvariable=_v, justify="center", bg="white").grid(
                row=r + 1, column=ci, sticky="ew", padx=1)
        tk.Label(parent, text="Vol. interp. (L)", font=fb, bg=_bgl, anchor="w").grid(
            row=r, column=8, sticky="ew", padx=1, pady=(2, 0))
        tk.Entry(parent, textvariable=v_res, justify="center", state="readonly",
                 readonlybackground="#FEF9E7").grid(row=r + 1, column=8, sticky="ew", padx=1)

        def _build_obj():
            try:
                ta = float(v_tA.get().strip().replace(",", "."))
                tb = float(v_tB.get().strip().replace(",", "."))
            except: return None
            rows = []
            for i in range(2):
                s = v_s[i].get().strip().replace(",", ".")
                la = v_l[i][0].get().strip().replace(",", ".")
                lb = v_l[i][1].get().strip().replace(",", ".")
                if not s: continue
                try:
                    rows.append([float(s),
                                 float(la) if la else None,
                                 float(lb) if lb else None])
                except: pass
            if not rows: return None
            return {"trims": [ta, tb], "rows": rows}

        def _recalc():
            if agua: self.calc_volumen_agua_ui(etapa, tk_name)
            else: self.calc_volumen_prod_ui(etapa, tk_name)

        def _preview(obj):
            _s_key = f"{etapa}_{tk_name}_agua_s_real" if agua else f"{etapa}_{tk_name}_s_corr"
            s_act = self.parse_float(self.get_var(_s_key).get())
            trim_act = self.parse_float(self.get_var(f"{etapa}_Trimación").get() or "0")
            vol, _det = self._interp_trim_table(obj, s_act, trim_act)
            v_res.set(f"{vol:,.0f}".replace(",", ".") if vol is not None else "—")

        def _aplicar(*_a):
            obj = _build_obj()
            if obj is None:
                v_res.set("—")
                # Solo borrar la tabla guardada si el usuario vació los campos
                _vacio = not any(vv.get().strip() for vv in v_s + v_l[0] + v_l[1])
                if _vacio and self.get_var(var_key).get():
                    self.get_var(var_key).set("")
                    _recalc()
                return
            obj["rows"].sort(key=lambda rr: rr[0])
            self.get_var(var_key).set(json.dumps(obj))
            _recalc()
            _preview(obj)

        for vv in [v_tA, v_tB] + v_s + v_l[0] + v_l[1]:
            vv.trace_add("write", _aplicar)
        # Vista previa inicial sin tocar lo guardado
        _obj_ini = _build_obj()
        if _obj_ini: _preview(_obj_ini)
        return 3

    def abrir_popup_detalle(self, etapa, tk_name):
        try:
            popup = tk.Toplevel(self.root)
            popup.title(f"Ficha de Carga: {tk_name} ({etapa.upper()})")
            popup.geometry("1120x680")
            popup.resizable(True, True)

            # Footer PRIMERO (fix pack order)
            f_bot_fixed = tk.Frame(popup, bg="#2C3E50", bd=0, height=50)
            f_bot_fixed.pack(side="bottom", fill="x")
            f_bot_fixed.pack_propagate(False)

            # ── Banner de tipo de medición (HEADER) ───────────────────────────
            _tm_now   = self.get_tipo_medio()
            _tipo_colores = {
                "BUQUE":              ("#1A3A5C","#5DADE2","⚓  BUQUE — Medición Marítima de Líquidos"),
                "BARCAZA":            ("#1A3A5C","#5DADE2","⚓  BARCAZA — Medición Marítima"),
                "BUQUE GASERO/GLP":   ("#4A235A","#A569BD","⚙  BUQUE GASERO/GLP — Presión/Temperatura/Factor Z"),
                "BUQUE QUIMIQUERO":   ("#1A3A5C","#76D7C4","⚗  BUQUE QUIMIQUERO — Productos Químicos"),
                "BUQUE METANERO/GNL": ("#1C2756","#85C1E9","❄  BUQUE METANERO/GNL — Gas Natural Licuado"),
                "DRAFT SURVEY":       ("#1A3A5C","#F4D03F","⚓  DRAFT SURVEY — Estimación por Calados"),
                "TANQUE FIJO":        ("#1A3B1A","#58D68D","🛢  TANQUE TECHO FIJO — Medición Terrestre"),
                "TANQUE FLOTANTE":    ("#1A3B1A","#58D68D","🛢  TANQUE TECHO FLOTANTE — Sondaje c/Pontón"),
                "ESFERA DE GAS":      ("#3A2010","#F0B429","⚙  ESFERA DE GAS — Almacenamiento Presurizado"),
                "CAMION CISTERNA":    ("#2C1810","#E59866","🚛  CAMION CISTERNA — Medición Automotor"),
                "CAMION GAS/GLP":     ("#2C1810","#E59866","🚛  CAMION GAS/GLP — Transporte de Gas"),
                "OLEODUCTO":          ("#1C1C2C","#A9CCE3","≋  OLEODUCTO — Línea de Líquidos"),
                "GASODUCTO":          ("#1C1C2C","#A9CCE3","≋  GASODUCTO — Línea de Gas"),
                "POLIDUCTO":          ("#1C1C2C","#A9CCE3","≋  POLIDUCTO — Línea Múltiple"),
                "ELECTRICO":          ("#1A1A1A","#F9E79F","⚡  ELÉCTRICO — Medición de Energía"),
            }
            _tbg, _tfg, _tlbl = _tipo_colores.get(_tm_now,
                                 ("#222222","#FFFFFF", f"■  {_tm_now}"))
            f_banner = tk.Frame(popup, bg=_tbg, height=32)
            f_banner.pack(side="top", fill="x")
            f_banner.pack_propagate(False)
            # Ícono+tipo a la izquierda
            tk.Label(f_banner, text=_tlbl,
                     bg=_tbg, fg=_tfg,
                     font=("Arial", 9, "bold"), pady=0).pack(side="left", padx=12)
            # Tanque y etapa a la derecha
            _etapa_colors = {"ini": "#27AE60", "fin": "#E74C3C"}
            _etapa_lbl = "INICIAL" if etapa.lower() in ("ini","inicial") else "FINAL" if etapa.lower() in ("fin","final") else etapa.upper()
            _etapa_col = _etapa_colors.get(etapa.lower()[:3], "#AED6F1")
            tk.Label(f_banner, text=f"[ {etapa.upper()} ]  {tk_name}",
                     bg=_tbg, fg=_etapa_col,
                     font=("Arial", 9, "bold")).pack(side="right", padx=12)

            # Canvas + scroll
            canvas = tk.Canvas(popup, bg="#f5f5f5", highlightthickness=0)
            v_scroll = ttk.Scrollbar(popup, orient="vertical", command=canvas.yview)
            canvas.configure(yscrollcommand=v_scroll.set)
            v_scroll.pack(side="right", fill="y")
            canvas.pack(side="left", fill="both", expand=True)

            frame_main = ttk.Frame(canvas)
            cv_win = canvas.create_window((0, 0), window=frame_main, anchor="nw")

            def _fc(e): canvas.configure(scrollregion=canvas.bbox("all"))
            def _cc(e): canvas.itemconfig(cv_win, width=e.width)
            frame_main.bind("<Configure>", _fc)
            canvas.bind("<Configure>", _cc)
            def _mw(e): canvas.yview_scroll(int(-1*(e.delta/120)) if e.delta else (1 if e.num==5 else -1), "units")
            canvas.bind("<MouseWheel>", _mw)
            canvas.bind("<Button-4>", _mw)
            canvas.bind("<Button-5>", _mw)

            for i in range(9): frame_main.grid_columnconfigure(i, weight=1)
            fb = ("Arial", 8, "bold")

            # ── Flags de tipo ─────────────────────────────────────────────────
            _tm   = self.get_tipo_medio()
            _mar  = self.es_maritimo()
            _tie  = self.es_tierra()
            _cam  = self.es_camion()
            _gas  = self.es_gasero() and not ("METANERO" in _tm or "GNL" in _tm)
            _met  = "METANERO" in _tm or "GNL" in _tm
            _esf  = self.es_esfera()
            _duc  = self.es_ducto()
            _el   = self.es_electrico()
            _cgb  = self.es_camion_gas()
            _flot = "FLOTANTE" in _tm
            # UTI (sondaje con UTI): SOLO para buques con carga LIQUIDA convencional
            # (BUQUE, BARCAZA, QUIMIQUERO). NO para gaseros, metaneros, esferas, gas.
            _es_maritimo_liq = _tm in ("BUQUE", "BARCAZA", "BUQUE QUIMIQUERO", "DRAFT SURVEY")
            _show_uti  = _es_maritimo_liq            # Sondaje UTI solo para líquidos marítimos
            _show_vcf  = not (_el or _duc or _cgb or _gas or _met or _esf)  # VCF para líquidos
            _show_prod = not _el                      # Producto no aplica a electricidad
            # Agua: solo para mediciones de líquidos (no gas, no eléctrico, no ducto)
            _show_agua_flag = _es_maritimo_liq or _tie or (_cam and not _cgb)

            # ══════════════════════════════════════════════════════════════════
            # SECCIÓN 1: Documento / Producto / Tabla VCF  (fila 0-1)
            # ══════════════════════════════════════════════════════════════════
            _s1_fields = [
                ("Documento Asignado", "ddt_assign", "combo", 3),
            ]
            if _show_prod:
                _s1_fields.append(("Producto", "prod_name", "entry", 3))
            if _show_vcf:
                _s1_fields.append(("Tabla VCF", "tabla_vcf", "combo_vcf", 3))
            self.crear_fila_popup(etapa, tk_name, frame_main, 0, _s1_fields, bg_row="#ddd")

            # ══════════════════════════════════════════════════════════════════
            # SECCIÓN 2: Sondaje UTI  (fila 2-3) — solo para tipos de sondaje
            # ══════════════════════════════════════════════════════════════════
            if _show_uti:
                self.crear_fila_popup(etapa, tk_name, frame_main, 2, [
                    ("Nro Uti",              "num_uti",   "entry",    2),
                    ("Medida Uti",           "alt_uti",   "entry",    2),
                    ("Desc.Tubo Sondaje",    "desc_tubo", "entry",    2),
                    ("Sondaje Corregido",    "s_corr",    "entry_ro", 2),
                    ("Temperatura UTI",      "temp",      "entry",    1),
                ], bg_row="#eee")

            # ══════════════════════════════════════════════════════════════════
            # SECCIÓN 3: Alturas / Sondajes 1 y 2  (fila 4-5) — solo sondaje
            # ══════════════════════════════════════════════════════════════════
            if _show_uti:
                self.crear_fila_popup(etapa, tk_name, frame_main, 4, [
                    ("Alt.Referencia",  "alt_ref",       "entry",    2),
                    ("Sondaje 1",       "prod_s1",       "entry",    1),
                    ("Litros 1",        "prod_l1",       "entry",    1),
                    ("Sondaje 2",       "prod_s2",       "entry",    1),
                    ("Litros 2",        "prod_l2",       "entry",    1),
                    ("Litros Naturales","vol_nat_prod",   "entry_ro", 3),
                ], bg_row="#eee")

            # ═══════════════════════════════════════════════════════════════
            # A partir de aquí usamos _cur_row dinámico
            # ═══════════════════════════════════════════════════════════════
            _cur_row = 6 if _show_uti else 2

            # ── Interp × asiento (PRODUCTO) embebida — buques líquidos ─────
            if _es_maritimo_liq:
                _cur_row += self.crear_interp_trim_inline(etapa, tk_name, frame_main, _cur_row, agua=False)

            # ── Tierra / Camión cisterna ──────────────────────────────────
            if _tie or (_cam and not _cgb):
                tk.Label(frame_main, text="── SONDAJE Y VOLUMEN ──",
                         font=fb, fg="#1B3A5C", bg="#D6EAF8").grid(
                         row=_cur_row, column=0, columnspan=9, pady=(8,2), sticky="ew")
                _cur_row += 1
                if _cam:
                    _tf = [
                        ("Varilla / Nivel (mm)", f"{etapa}_{tk_name}_s_tierra"),
                        ("Vol. Bruto (L)",        f"{etapa}_{tk_name}_vol_bruto"),
                        ("Ticket Planta (L)",     f"{etapa}_{tk_name}_ticket_l"),
                        ("Ticket Planta (Kg)",    f"{etapa}_{tk_name}_ticket_k"),
                    ]
                else:
                    _tf = [
                        ("Sondaje (mm)",             f"{etapa}_{tk_name}_s_tierra"),
                        ("Sondaje Corregido (mm)",   f"{etapa}_{tk_name}_s_corr"),
                        ("Vol. Bruto (L)",            f"{etapa}_{tk_name}_vol_bruto"),
                    ]
                    if _flot:
                        _tf.insert(1, ("Offset Techo (mm)", f"{etapa}_{tk_name}_tf_offset"))
                for ci, (lbl_t, var_t) in enumerate(_tf):
                    ro_t = "s_corr" in var_t or "vol_bruto" in var_t
                    tk.Label(frame_main, text=lbl_t, font=fb, bg="#D6EAF8", anchor="w").grid(
                        row=_cur_row, column=ci, sticky="ew", padx=1, pady=(2,0))
                    ent = tk.Entry(frame_main, textvariable=self.get_var(var_t),
                                   justify="center",
                                   state="readonly" if ro_t else "normal",
                                   bg="#dceeff" if ro_t else "white")
                    ent.grid(row=_cur_row+1, column=ci, sticky="ew", padx=1)
                    def _ct(*_a, _e=etapa, _t2=tk_name):
                        try:
                            s = self.parse_float(self.get_var(f"{_e}_{_t2}_s_tierra").get())
                            off = self.parse_float(self.get_var(f"{_e}_{_t2}_tf_offset").get() or self.get_var("car_tf_offset").get() or "0")
                            r  = self.parse_float(self.get_var("car_radio_m").get() or "0")
                            sc = s - off if "FLOTANTE" in self.get_tipo_medio() else s
                            self.get_var(f"{_e}_{_t2}_s_corr").set(str(int(sc)))
                            if r > 0:
                                vol = self.calc_volumen_geometrico_tierra(sc, r)
                                self.get_var(f"{_e}_{_t2}_vol_bruto").set(f"{vol:,.0f}")
                                self.get_var(f"{_e}_{_t2}_vol_nat_prod").set(f"{vol:,.0f}")
                        except: pass
                    if "s_tierra" in var_t or "tf_offset" in var_t:
                        ent.bind("<KeyRelease>", _ct)
                    if _cam:
                        def _cc2(*_a, _e=etapa, _t2=tk_name):
                            try:
                                s2  = self.parse_float(self.get_var(f"{_e}_{_t2}_s_tierra").get())
                                r2  = self.parse_float(self.get_var("car_radio_camion").get() or "0")
                                L2  = self.parse_float(self.get_var("car_largo_camion").get() or "0")
                                if r2 > 0 and L2 > 0:
                                    v2 = self.calc_volumen_cilindro_horizontal(s2, r2, L2)
                                    self.get_var(f"{_e}_{_t2}_vol_bruto").set(f"{v2:,.0f}")
                                    self.get_var(f"{_e}_{_t2}_vol_nat_prod").set(f"{v2:,.0f}")
                            except: pass
                        if "s_tierra" in var_t: ent.bind("<KeyRelease>", _cc2)
                _cur_row += 2

            # ── Gasero/GLP (presión, T, Z - cols 4-8, misma fila que tierra) ─
            if _gas:
                _gr = _cur_row - 2  # misma altura que sección tierra o section 3
                if not (_tie or _cam): _gr = _cur_row; _cur_row += 2
                tk.Label(frame_main, text="── DATOS GAS/PROCESO ──",
                         font=fb, fg="#721c24", bg="#f8d7da").grid(
                         row=_gr, column=4 if (_tie or _cam) else 0, columnspan=5 if (_tie or _cam) else 9,
                         pady=(8,2), sticky="ew")
                _gf = [
                    ("Presion (kPa)",        f"{etapa}_{tk_name}_presion"),
                    ("Temp.Liq (C)",         f"{etapa}_{tk_name}_temp_liq"),
                    ("Factor Z",             f"{etapa}_{tk_name}_factor_z"),
                    ("Dens.Vapor (kg/m3)",   f"{etapa}_{tk_name}_dens_vapor"),
                    ("Fase",                 f"{etapa}_{tk_name}_fase"),
                ]
                _col_off = 4 if (_tie or _cam) else 0
                for ci5, (lg, vg) in enumerate(_gf):
                    tk.Label(frame_main, text=lg, font=fb, bg="#f8d7da").grid(
                        row=_gr, column=_col_off+ci5, sticky="ew", padx=1, pady=(5,0))
                    tk.Entry(frame_main, textvariable=self.get_var(vg),
                             justify="center", bg="#fff0f0").grid(
                             row=_gr+1, column=_col_off+ci5, sticky="ew", padx=1)

            # ── GNL / Metanero: composición molar + fases ─────────────────
            if _met:
                tk.Label(frame_main, text="── COMPOSICION MOLAR GNL ──",
                         font=fb, fg="#1A5276", bg="#D6EAF8").grid(
                         row=_cur_row, column=0, columnspan=9, pady=(10,2), sticky="ew")
                _cur_row += 1
                GNL_C = [
                    ("Metano(CH4)%mol",    f"{etapa}_{tk_name}_gc_CH4"),
                    ("Etano(C2H6)%mol",    f"{etapa}_{tk_name}_gc_C2H6"),
                    ("Propano(C3H8)%mol",  f"{etapa}_{tk_name}_gc_C3H8"),
                    ("Butano(C4H10)%mol",  f"{etapa}_{tk_name}_gc_C4H10"),
                    ("N2 %mol",            f"{etapa}_{tk_name}_gc_N2"),
                    ("CO2 %mol",           f"{etapa}_{tk_name}_gc_CO2"),
                    ("i-C4 %mol",          f"{etapa}_{tk_name}_gc_iC4"),
                    ("n-C5 %mol",          f"{etapa}_{tk_name}_gc_nC5"),
                    ("H2S %mol",           f"{etapa}_{tk_name}_gc_H2S"),
                ]
                _COLS = 5
                for ci, (lc, vc) in enumerate(GNL_C):
                    col = ci % _COLS; roff = ci // _COLS
                    tk.Label(frame_main, text=lc, font=fb, bg="#EBF5FB", anchor="w").grid(
                        row=_cur_row+roff*2, column=col, sticky="ew", padx=1, pady=(4,0))
                    tk.Entry(frame_main, textvariable=self.get_var(vc),
                             justify="center", bg="#EAF4FD", width=10).grid(
                             row=_cur_row+roff*2+1, column=col, sticky="ew", padx=1)
                _n_comp_rows = ((len(GNL_C)-1)// _COLS + 1) * 2
                _cur_row += _n_comp_rows
                # Suma y PM
                v_sum = self.get_var(f"{etapa}_{tk_name}_gc_sum")
                v_PM  = self.get_var(f"{etapa}_{tk_name}_gc_PM")
                def _upd_gnl(*_a, _e=etapa, _t2=tk_name):
                    try:
                        MW = {"CH4":16.04,"C2H6":30.07,"C3H8":44.10,"C4H10":58.12,
                              "iC4":58.12,"nC5":72.15,"N2":28.01,"CO2":44.01,"H2S":34.08}
                        tot=0; PM=0
                        for k,mw in MW.items():
                            p = self.parse_float(self.get_var(f"{_e}_{_t2}_gc_{k}").get() or "0")
                            tot+=p; PM+=p/100*mw
                        self.get_var(f"{_e}_{_t2}_gc_sum").set(f"{tot:.2f}%")
                        self.get_var(f"{_e}_{_t2}_gc_PM").set(f"{PM:.4f}")
                    except: pass
                for _, vc in GNL_C: self.get_var(vc).trace_add("write", _upd_gnl)
                tk.Label(frame_main, text="Suma %mol", font=fb, bg="#EBF5FB").grid(
                    row=_cur_row, column=0, sticky="ew", padx=1, pady=(4,0))
                tk.Label(frame_main, textvariable=v_sum, bg="#dceeff", relief="sunken", font=fb).grid(
                    row=_cur_row+1, column=0, sticky="ew", padx=1)
                tk.Label(frame_main, text="PM calculado", font=fb, bg="#EBF5FB").grid(
                    row=_cur_row, column=1, sticky="ew", padx=1, pady=(4,0))
                tk.Label(frame_main, textvariable=v_PM, bg="#dceeff", relief="sunken").grid(
                    row=_cur_row+1, column=1, sticky="ew", padx=1)
                _cur_row += 2
                # Fases
                tk.Label(frame_main, text="── FASES ──", font=fb, fg="#1A5276", bg="#D5F5E3").grid(
                    row=_cur_row, column=0, columnspan=9, pady=(8,2), sticky="ew")
                _cur_row += 1
                _fase_f = [
                    ("Vol.Liq(m3)",      f"{etapa}_{tk_name}_vol_liq"),
                    ("Vol.Vap(m3)",      f"{etapa}_{tk_name}_vol_vap"),
                    ("Masa Liq(t)",      f"{etapa}_{tk_name}_masa_liq"),
                    ("Masa Vap(kg)",     f"{etapa}_{tk_name}_masa_vap"),
                    ("Dens.Liq(kg/m3)", f"{etapa}_{tk_name}_dens_liq"),
                    ("Dens.Vap(kg/m3)", f"{etapa}_{tk_name}_dens_vap"),
                    ("T Liq (C)",        f"{etapa}_{tk_name}_temp_liq"),
                    ("T Vap (C)",        f"{etapa}_{tk_name}_temp_vap"),
                    ("Presion (kPa)",    f"{etapa}_{tk_name}_pres_gnl"),
                ]
                for ci3, (lf, vf) in enumerate(_fase_f):
                    col3=ci3%_COLS; ro3=ci3//_COLS
                    ro_f = "masa_" in vf
                    tk.Label(frame_main, text=lf, font=fb, bg="#D5F5E3", anchor="w").grid(
                        row=_cur_row+ro3*2, column=col3, sticky="ew", padx=1, pady=(4,0))
                    tk.Entry(frame_main, textvariable=self.get_var(vf),
                             justify="center", bg="#EAFAF1" if not ro_f else "#dceeff",
                             state="readonly" if ro_f else "normal").grid(
                             row=_cur_row+ro3*2+1, column=col3, sticky="ew", padx=1)
                _n_fase_rows = ((len(_fase_f)-1)//_COLS+1)*2
                def _upd_fas(*_a, _e=etapa, _t2=tk_name):
                    try:
                        vl=self.parse_float(self.get_var(f"{_e}_{_t2}_vol_liq").get() or "0")
                        vv=self.parse_float(self.get_var(f"{_e}_{_t2}_vol_vap").get() or "0")
                        dl=self.parse_float(self.get_var(f"{_e}_{_t2}_dens_liq").get() or "0")
                        dv=self.parse_float(self.get_var(f"{_e}_{_t2}_dens_vap").get() or "0")
                        if dl>0: self.get_var(f"{_e}_{_t2}_masa_liq").set(f"{vl*dl/1000:.3f}")
                        if dv>0: self.get_var(f"{_e}_{_t2}_masa_vap").set(f"{vv*dv:.1f}")
                        if vl+vv>0: self.get_var(f"{_e}_{_t2}_vol_nat_prod").set(f"{(vl+vv)*1000:.0f}")
                    except: pass
                for vk in [f"{etapa}_{tk_name}_vol_liq",f"{etapa}_{tk_name}_vol_vap",
                            f"{etapa}_{tk_name}_dens_liq",f"{etapa}_{tk_name}_dens_vap"]:
                    self.get_var(vk).trace_add("write", _upd_fas)
                _cur_row += _n_fase_rows

            # ── Esfera de gas ──────────────────────────────────────────────
            if _esf:
                tk.Label(frame_main, text="── ESFERA DE GAS / PRESION ──",
                         font=fb, fg="#784212", bg="#FEF9E7").grid(
                         row=_cur_row, column=0, columnspan=9, pady=(10,2), sticky="ew")
                _cur_row += 1
                _esf_f = [
                    ("Presion (kPa)",       f"{etapa}_{tk_name}_esf_pres"),
                    ("Temperatura (C)",     f"{etapa}_{tk_name}_esf_temp"),
                    ("Dens.liq(kg/m3)",     f"{etapa}_{tk_name}_esf_dens"),
                    ("Vol.Liq(m3)",         f"{etapa}_{tk_name}_vol_liq"),
                    ("Vol.Gas Base(m3)",    f"{etapa}_{tk_name}_esf_vol_gas"),
                    ("Masa (t)",            f"{etapa}_{tk_name}_esf_masa"),
                    ("Fase",               f"{etapa}_{tk_name}_esf_fase"),
                    ("Producto",           f"{etapa}_{tk_name}_prod_name"),
                ]
                for ci4, (le, ve) in enumerate(_esf_f):
                    ro_e = "vol_gas" in ve or "esf_masa" in ve or "esf_fase" in ve
                    tk.Label(frame_main, text=le, font=fb, bg="#FEF9E7", anchor="w").grid(
                        row=_cur_row, column=ci4, sticky="ew", padx=1, pady=(4,0))
                    tk.Entry(frame_main, textvariable=self.get_var(ve),
                             justify="center",
                             state="readonly" if ro_e else "normal",
                             bg="#dceeff" if ro_e else "#FFFDE7").grid(
                             row=_cur_row+1, column=ci4, sticky="ew", padx=1)
                def _upd_esf(*_a, _e=etapa, _t2=tk_name):
                    try:
                        P  = self.parse_float(self.get_var(f"{_e}_{_t2}_esf_pres").get() or "101.325")
                        T  = self.parse_float(self.get_var(f"{_e}_{_t2}_esf_temp").get() or "15")
                        d  = self.parse_float(self.get_var(f"{_e}_{_t2}_esf_dens").get() or "500")
                        vl = self.parse_float(self.get_var(f"{_e}_{_t2}_vol_liq").get() or "0")
                        prod = self.get_var(f"{_e}_{_t2}_prod_name").get() or "GLP"
                        Z = self.calc_factor_z(P, T)
                        if d>0 and vl>0:
                            self.get_var(f"{_e}_{_t2}_esf_vol_gas").set(f"{self.calc_volumen_base_gas(vl,P,T,Z):.3f}")
                            self.get_var(f"{_e}_{_t2}_esf_masa").set(f"{vl*d/1000:.3f}")
                        self.get_var(f"{_e}_{_t2}_esf_fase").set(self.calc_gas_fase(P,T,prod))
                        self.get_var(f"{_e}_{_t2}_vol_nat_prod").set(f"{vl*1000:.0f}")
                    except: pass
                for fld in ["esf_pres","esf_temp","esf_dens","vol_liq"]:
                    self.get_var(f"{etapa}_{tk_name}_{fld}").trace_add("write", _upd_esf)
                _cur_row += 2

            # ── Ductos ────────────────────────────────────────────────────
            if _duc:
                tk.Label(frame_main, text="── CONTADORES Y CAUDAL ──",
                         font=fb, fg="#1B3A5C", bg="#D6EAF8").grid(
                         row=_cur_row, column=0, columnspan=9, pady=(8,2), sticky="ew")
                _cur_row += 1
                _duc1 = [
                    ("Contador Ini(m3)",  f"{etapa}_{tk_name}_cont_ini"),
                    ("Contador Fin(m3)",  f"{etapa}_{tk_name}_cont_fin"),
                    ("Vol.Linea(m3)",     f"{etapa}_{tk_name}_vol_linea"),
                    ("Caudal(m3/h)",      f"{etapa}_{tk_name}_caudal_mh"),
                    ("Coriolis(kg/h)",    f"{etapa}_{tk_name}_coriolis_kgh"),
                    ("Masa Coriolis(kg)", f"{etapa}_{tk_name}_masa_coriolis"),
                ]
                for ci, (ld, vd) in enumerate(_duc1[:9]):
                    ro_d = "vol_linea" in vd or "masa_coriolis" in vd
                    tk.Label(frame_main, text=ld, font=fb, bg="#D6EAF8", anchor="w").grid(
                        row=_cur_row, column=ci, sticky="ew", padx=1, pady=(4,0))
                    ed = tk.Entry(frame_main, textvariable=self.get_var(vd),
                                  justify="center",
                                  state="readonly" if ro_d else "normal",
                                  bg="#dceeff" if ro_d else "white")
                    ed.grid(row=_cur_row+1, column=ci, sticky="ew", padx=1)
                    def _udv(*a, _e=etapa, _t2=tk_name):
                        try:
                            i2=self.parse_float(self.get_var(f"{_e}_{_t2}_cont_ini").get())
                            f2=self.parse_float(self.get_var(f"{_e}_{_t2}_cont_fin").get())
                            self.get_var(f"{_e}_{_t2}_vol_linea").set(f"{f2-i2:,.3f}")
                        except: pass
                    if "cont_" in vd or "coriolis_kgh" in vd: ed.bind("<KeyRelease>", _udv)
                _cur_row += 2
                # P/T/Z
                tk.Label(frame_main, text="── CORRECCION P/T/Z ──",
                         font=fb, fg="#1B3A5C", bg="#EBF5FB").grid(
                         row=_cur_row, column=0, columnspan=9, pady=(8,2), sticky="ew")
                _cur_row += 1
                _duc2 = [
                    ("P linea(kPa)",   f"{etapa}_{tk_name}_P_lin"),
                    ("T linea(C)",     f"{etapa}_{tk_name}_T_lin"),
                    ("Factor Z",       f"{etapa}_{tk_name}_Z"),
                    ("Vol Base(m3)",   f"{etapa}_{tk_name}_vol_base"),
                    ("Vol Base(Km3)",  f"{etapa}_{tk_name}_vol_base_km3"),
                ]
                for ci2, (ld2, vd2) in enumerate(_duc2):
                    ro2 = "vol_base" in vd2 or vd2.endswith("_Z")
                    tk.Label(frame_main, text=ld2, font=fb, bg="#EBF5FB", anchor="w").grid(
                        row=_cur_row, column=ci2, sticky="ew", padx=1, pady=(4,0))
                    e2 = tk.Entry(frame_main, textvariable=self.get_var(vd2),
                                  justify="center",
                                  state="readonly" if ro2 else "normal",
                                  bg="#dceeff" if ro2 else "white")
                    e2.grid(row=_cur_row+1, column=ci2, sticky="ew", padx=1)
                    def _uz(*a, _e=etapa, _t2=tk_name):
                        try:
                            P2=self.parse_float(self.get_var(f"{_e}_{_t2}_P_lin").get() or self.get_var("car_presion_op").get() or "101.325")
                            T2=self.parse_float(self.get_var(f"{_e}_{_t2}_T_lin").get() or self.get_var("car_temp_op").get() or "15")
                            comp=self._get_cromatografia(f"{_e}_{_t2}")
                            Z2=self.calc_factor_z(P2,T2,composicion_pct=comp if comp else None)
                            self.get_var(f"{_e}_{_t2}_Z").set(f"{Z2:.5f}")
                            vl2=self.parse_float(self.get_var(f"{_e}_{_t2}_vol_linea").get() or "0")
                            vb=self.calc_volumen_base_gas(vl2,P2,T2,Z2)
                            self.get_var(f"{_e}_{_t2}_vol_base").set(f"{vb:,.3f}")
                            self.get_var(f"{_e}_{_t2}_vol_base_km3").set(f"{vb/1000:,.6f}")
                            self.get_var(f"{_e}_{_t2}_vol_nat_prod").set(f"{vb*1000:,.0f}")
                        except: pass
                    if "P_lin" in vd2 or "T_lin" in vd2: e2.bind("<KeyRelease>", _uz)
                _cur_row += 2
                # Cromatografía (gasoducto)
                if self.es_gasoducto():
                    tk.Label(frame_main, text="── CROMATOGRAFIA (% mol) ──",
                             font=fb, fg="#721c24", bg="#f8d7da").grid(
                             row=_cur_row, column=0, columnspan=9, pady=(8,2), sticky="ew")
                    _cur_row += 1
                    for ci_c, cn in enumerate(["CH4","C2H6","C3H8","iC4","nC4","iC5","nC5","C6+","N2"][:9]):
                        tk.Label(frame_main, text=cn, font=fb, bg="#f8d7da").grid(
                            row=_cur_row, column=ci_c, sticky="ew", padx=1, pady=(4,0))
                        ec = tk.Entry(frame_main, textvariable=self.get_var(f"{etapa}_{tk_name}_gc_{cn}",""),
                                      justify="center", bg="#fff0f0", width=7)
                        ec.grid(row=_cur_row+1, column=ci_c, sticky="ew", padx=1)
                        ec.bind("<KeyRelease>", _uz)
                    _cur_row += 2
                # PIG
                tk.Label(frame_main, text="── PIG CALIBRACION ──",
                         font=fb, fg="#6E4B00", bg="#FEF9E7").grid(
                         row=_cur_row, column=0, columnspan=9, pady=(8,2), sticky="ew")
                _cur_row += 1
                _pig = [
                    ("Diam.Nom(pulg)", f"{etapa}_{tk_name}_pig_diam"),
                    ("Long.Tramo(m)",  f"{etapa}_{tk_name}_pig_largo"),
                    ("Vol.Nom(m3)",    f"{etapa}_{tk_name}_pig_vol"),
                    ("Vel.Pig(m/s)",   f"{etapa}_{tk_name}_pig_vel"),
                    ("Obs/Resultado",  f"{etapa}_{tk_name}_pig_obs"),
                ]
                for ci_p, (lp, vp) in enumerate(_pig[:9]):
                    ro_p = "pig_vol" in vp
                    tk.Label(frame_main, text=lp, font=fb, bg="#FEF9E7").grid(
                        row=_cur_row, column=ci_p, sticky="ew", padx=1, pady=(4,0))
                    ep2 = tk.Entry(frame_main, textvariable=self.get_var(vp),
                                   justify="center",
                                   state="readonly" if ro_p else "normal",
                                   bg="#fff9e0" if ro_p else "white")
                    ep2.grid(row=_cur_row+1, column=ci_p, sticky="ew", padx=1)
                    def _upig(*a, _e=etapa, _t2=tk_name):
                        try:
                            d2=self.parse_float(self.get_var(f"{_e}_{_t2}_pig_diam").get() or "0")
                            l2=self.parse_float(self.get_var(f"{_e}_{_t2}_pig_largo").get() or "0")
                            self.get_var(f"{_e}_{_t2}_pig_vol").set(f"{self.calc_pig_volumen_m3(d2,l2):,.4f}")
                        except: pass
                    if "pig_diam" in vp or "pig_largo" in vp: ep2.bind("<KeyRelease>", _upig)
                _cur_row += 2

            # ── Medición eléctrica ─────────────────────────────────────────
            if _el:
                tk.Label(frame_main, text="── MEDICION ELECTRICA ──",
                         font=fb, fg="#1B3A5C", bg="#D5E8D4").grid(
                         row=_cur_row, column=0, columnspan=9, pady=(8,2), sticky="ew")
                _cur_row += 1
                _el1 = [
                    ("Lect.Ini kWh Act",  f"{etapa}_{tk_name}_el_ini_act"),
                    ("Lect.Fin kWh Act",  f"{etapa}_{tk_name}_el_fin_act"),
                    ("kWh Activa",        f"{etapa}_{tk_name}_el_kwh_act"),
                    ("Lect.Ini kWh Rea",  f"{etapa}_{tk_name}_el_ini_rea"),
                    ("Lect.Fin kWh Rea",  f"{etapa}_{tk_name}_el_fin_rea"),
                    ("kWh Reactiva",      f"{etapa}_{tk_name}_el_kwh_rea"),
                    ("Cte Medidor",       f"{etapa}_{tk_name}_el_const"),
                    ("cos fi calc",       f"{etapa}_{tk_name}_el_fp"),
                    ("Dem.Max.(kW)",      f"{etapa}_{tk_name}_el_dem"),
                ]
                for ci_e, (le2, ve2) in enumerate(_el1[:9]):
                    ro_e2 = "kwh_" in ve2 or "el_fp" in ve2
                    tk.Label(frame_main, text=le2, font=fb, bg="#D5E8D4", anchor="w").grid(
                        row=_cur_row, column=ci_e, sticky="ew", padx=1, pady=(4,0))
                    ee = tk.Entry(frame_main, textvariable=self.get_var(ve2),
                                  justify="center",
                                  state="readonly" if ro_e2 else "normal",
                                  bg="#d5f5e3" if ro_e2 else "white")
                    ee.grid(row=_cur_row+1, column=ci_e, sticky="ew", padx=1)
                    def _ue(*a, _e=etapa, _t2=tk_name):
                        try:
                            ct=self.parse_float(self.get_var(f"{_e}_{_t2}_el_const").get() or "1")
                            ia=self.parse_float(self.get_var(f"{_e}_{_t2}_el_ini_act").get() or "0")
                            fa=self.parse_float(self.get_var(f"{_e}_{_t2}_el_fin_act").get() or "0")
                            ir=self.parse_float(self.get_var(f"{_e}_{_t2}_el_ini_rea").get() or "0")
                            fr=self.parse_float(self.get_var(f"{_e}_{_t2}_el_fin_rea").get() or "0")
                            ka=self.calc_energia_electrica(ia,fa,ct)
                            kr=self.calc_energia_electrica(ir,fr,ct)
                            self.get_var(f"{_e}_{_t2}_el_kwh_act").set(f"{ka:,.3f}")
                            self.get_var(f"{_e}_{_t2}_el_kwh_rea").set(f"{kr:,.3f}")
                            self.get_var(f"{_e}_{_t2}_el_fp").set(f"{self.calc_fp_kwh(ka,kr):.4f}")
                            self.get_var(f"{_e}_{_t2}_vol_nat_prod").set(f"{ka:,.3f}")
                        except: pass
                    if any(x in ve2 for x in ["ini_","fin_","el_const"]): ee.bind("<KeyRelease>", _ue)
                _cur_row += 2
                tk.Label(frame_main, text="── TENSION / CORRIENTE ──",
                         font=fb, fg="#1B3A5C", bg="#D5E8D4").grid(
                         row=_cur_row, column=0, columnspan=9, pady=(5,2), sticky="ew")
                _cur_row += 1
                _el2 = [
                    ("Tension(V)",     f"{etapa}_{tk_name}_el_V"),
                    ("Corriente(A)",   f"{etapa}_{tk_name}_el_A"),
                    ("Pot.Apar.(VA)",  f"{etapa}_{tk_name}_el_VA"),
                    ("cos fi medido",  f"{etapa}_{tk_name}_el_fp_med"),
                    ("N fases",        f"{etapa}_{tk_name}_el_fases"),
                ]
                for ci_e2, (le3, ve3) in enumerate(_el2[:9]):
                    ro_e3 = "el_VA" in ve3
                    tk.Label(frame_main, text=le3, font=fb, bg="#D5E8D4").grid(
                        row=_cur_row, column=ci_e2, sticky="ew", padx=1, pady=(4,0))
                    ee3 = tk.Entry(frame_main, textvariable=self.get_var(ve3),
                                   justify="center",
                                   state="readonly" if ro_e3 else "normal",
                                   bg="#d5f5e3" if ro_e3 else "white")
                    ee3.grid(row=_cur_row+1, column=ci_e2, sticky="ew", padx=1)
                    def _uva(*a, _e=etapa, _t2=tk_name):
                        try:
                            V2=self.parse_float(self.get_var(f"{_e}_{_t2}_el_V").get() or "0")
                            A2=self.parse_float(self.get_var(f"{_e}_{_t2}_el_A").get() or "0")
                            self.get_var(f"{_e}_{_t2}_el_VA").set(f"{self.calc_potencia_aparente(V2,A2):,.1f}")
                        except: pass
                    if "el_V" in ve3 or "el_A" in ve3: ee3.bind("<KeyRelease>", _uva)
                _cur_row += 2

            # ── Camión gas/GLP ────────────────────────────────────────────
            if _cgb:
                tk.Label(frame_main, text="── CAMION GAS/GLP ──",
                         font=fb, fg="#721c24", bg="#f8d7da").grid(
                         row=_cur_row, column=0, columnspan=9, pady=(8,2), sticky="ew")
                _cur_row += 1
                _cg = [
                    ("Presion(kPa)",   f"{etapa}_{tk_name}_cg_pres"),
                    ("Temp(C)",        f"{etapa}_{tk_name}_cg_temp"),
                    ("Dens.liq(kg/m3)",f"{etapa}_{tk_name}_cg_dens"),
                    ("Masa(kg)",       f"{etapa}_{tk_name}_cg_masa"),
                    ("Vol.Liq(L)",     f"{etapa}_{tk_name}_cg_vol"),
                    ("Vol.Gas 15C(m3)",f"{etapa}_{tk_name}_cg_vol_gas"),
                ]
                for ci_cg, (lc2, vc2) in enumerate(_cg[:9]):
                    ro_cg = "cg_vol" in vc2
                    tk.Label(frame_main, text=lc2, font=fb, bg="#f8d7da").grid(
                        row=_cur_row, column=ci_cg, sticky="ew", padx=1, pady=(4,0))
                    ecg = tk.Entry(frame_main, textvariable=self.get_var(vc2),
                                   justify="center",
                                   state="readonly" if ro_cg else "normal",
                                   bg="#fff0f0" if ro_cg else "white")
                    ecg.grid(row=_cur_row+1, column=ci_cg, sticky="ew", padx=1)
                    def _ucg(*a, _e=etapa, _t2=tk_name):
                        try:
                            masa=self.parse_float(self.get_var(f"{_e}_{_t2}_cg_masa").get() or "0")
                            dens=self.parse_float(self.get_var(f"{_e}_{_t2}_cg_dens").get() or "500")
                            P3=self.parse_float(self.get_var(f"{_e}_{_t2}_cg_pres").get() or "101.325")
                            T3=self.parse_float(self.get_var(f"{_e}_{_t2}_cg_temp").get() or "15")
                            prod=self.get_var(f"{_e}_{_t2}_prod_name").get() or "GLP"
                            if masa>0 and dens>0:
                                vl3=self.calc_volumen_camion_gas(masa,dens)
                            else:
                                var=self.parse_float(self.get_var(f"{_e}_{_t2}_s_tierra").get() or "0")
                                r3=self.parse_float(self.get_var("car_radio_camion").get() or "0")
                                L3=self.parse_float(self.get_var("car_largo_camion").get() or "0")
                                vl3=self.calc_volumen_cilindro_horizontal(var,r3,L3) if r3>0 and L3>0 and var>0 else 0
                            if vl3>0:
                                Z3=self.calc_factor_z(P3,T3)
                                self.get_var(f"{_e}_{_t2}_cg_vol").set(f"{vl3:,.1f}")
                                self.get_var(f"{_e}_{_t2}_cg_vol_gas").set(f"{self.calc_volumen_base_gas(vl3/1000,P3,T3,Z3):,.3f}")
                                self.get_var(f"{_e}_{_t2}_vol_nat_prod").set(f"{vl3:,.0f}")
                                self.get_var(f"{_e}_{_t2}_fase").set(self.calc_gas_fase(P3,T3,prod))
                        except: pass
                    if any(x in vc2 for x in ["cg_masa","cg_dens","cg_pres","cg_temp"]): ecg.bind("<KeyRelease>", _ucg)
                _cur_row += 2

            # ══════════════════════════════════════════════════════════════
            # AGUA  (solo para mediciones de líquidos — NO para gas/eléctrico/ducto)
            # ══════════════════════════════════════════════════════════════
            _show_agua = _show_agua_flag
            if _show_agua:
                tk.Label(frame_main, text="── CALCULO DE AGUA ──",
                         font=fb, fg="blue", bg="#ccffcc").grid(
                         row=_cur_row, column=0, columnspan=9, pady=(14,4), sticky="ew")
                _cur_row += 1
                _hdrs_a = ["Sondaje 1(Agua)","Litros 1","Sondaje 2(Agua)","Litros 2",
                           "Lectura Agua","Desc.Tubo","Sond.Real","Litros Agua Nat."]
                _keys_a = ["agua_s1","agua_l1","agua_s2","agua_l2",
                           "agua_lectura","agua_desc","agua_s_real","vol_nat_agua"]
                for i2, h2 in enumerate(_hdrs_a):
                    tk.Label(frame_main, text=h2, font=fb, bg="#ccffcc").grid(
                        row=_cur_row, column=i2, sticky="ew", padx=1)
                for i2, k2 in enumerate(_keys_a):
                    st_a = "readonly" if k2 in ("agua_s_real","vol_nat_agua") else "normal"
                    va = self.get_var(f"{etapa}_{tk_name}_{k2}")
                    ea = tk.Entry(frame_main, textvariable=va,
                                  justify="center", state=st_a, bg="#eeffee")
                    ea.grid(row=_cur_row+1, column=i2, sticky="ew", padx=1, pady=(0,8))
                    if k2 in ("agua_lectura","agua_desc"):
                        ea.bind("<KeyRelease>", lambda ev,t=tk_name,ep=etapa: self.calc_sondaje_agua(ep,t))
                    if k2 in ("agua_s1","agua_l1","agua_s2","agua_l2"):
                        ea.bind("<KeyRelease>", lambda ev,t=tk_name,ep=etapa: self.calc_volumen_agua_ui(ep,t))
                _cur_row += 2

                # ── Interp × asiento (AGUA) embebida — buques líquidos ─────
                if _es_maritimo_liq:
                    _cur_row += self.crear_interp_trim_inline(etapa, tk_name, frame_main, _cur_row, agua=True)

            # ══════════════════════════════════════════════════════════════
            # DENSIDADES / VOLÚMENES (solo para mediciones de producto líquido)
            # ══════════════════════════════════════════════════════════════
            _show_dens = not (_el or _duc)
            if _show_dens:
                self.crear_fila_popup(etapa, tk_name, frame_main, _cur_row, [
                    ("Densidad Lab",          "dens_lab",  "entry",    2),
                    ("Litros a 15 Lab",       "v15_lab",   "entry_ro", 2),
                    ("Kilos Vacio Lab",       "kv_lab",    "entry_ro", 2),
                    ("Kilos al Aire Lab",     "ka_lab",    "entry_ro", 3),
                ], bg_row="#ffffcc")
                self.crear_fila_popup(etapa, tk_name, frame_main, _cur_row+2, [
                    ("Densidad Doc",          "dens_doc",  "entry_ro", 2),
                    ("Litros a 15 Doc",       "v15_doc",   "entry_ro", 2),
                    ("Kilos Vacio Doc",       "kv_doc",    "entry_ro", 2),
                    ("Kilos al Aire Doc",     "ka_doc",    "entry_ro", 3),
                ], bg_row="#dcebf7")
                self.crear_fila_popup(etapa, tk_name, frame_main, _cur_row+4, [
                    ("Densidad Salida",       "dens_salida","entry_ro", 2),
                    ("Litros a 15 Salida",    "v15_sal",   "entry_ro", 2),
                    ("Kilos Vacio Salida",    "kv_sal",    "entry_ro", 2),
                    ("Kilos al Aire Salida",  "ka_sal",    "entry_ro", 3),
                ], bg_row="#dcf7dc")

            # ══════════════════════════════════════════════════════════════
            # Botón Guardar y Cerrar
            # ══════════════════════════════════════════════════════════════
            tk.Button(f_bot_fixed, text="  Guardar y Cerrar  ", bg="#27AE60", fg="white",
                      font=fb, command=popup.destroy,
                      relief="flat", cursor="hand2"
                      ).pack(side="left", padx=16, pady=8, ipadx=10, ipady=4)
            if not (_duc or _el):
                tk.Button(f_bot_fixed, text="  Tabla Calibrado  ", bg="#8E44AD", fg="white",
                          font=fb, relief="flat", cursor="hand2",
                          command=lambda: self.abrir_tabla_calibrado(etapa, tk_name, es_buque=_mar)
                          ).pack(side="left", padx=8, pady=8, ipadx=8, ipady=4)
            if _mar:
                tk.Button(f_bot_fixed, text="  Interp × Asiento  ", bg="#1A5276", fg="white",
                          font=fb, relief="flat", cursor="hand2",
                          command=lambda: self.abrir_interp_trim_rapida(etapa, tk_name)
                          ).pack(side="left", padx=8, pady=8, ipadx=8, ipady=4)
                if _tm in ("BUQUE", "BARCAZA", "BUQUE QUIMIQUERO", "DRAFT SURVEY"):
                    tk.Button(f_bot_fixed, text="  Interp Agua  ", bg="#117864", fg="white",
                              font=fb, relief="flat", cursor="hand2",
                              command=lambda: self.abrir_interp_trim_rapida(etapa, tk_name, agua=True)
                              ).pack(side="left", padx=8, pady=8, ipadx=8, ipady=4)
            tk.Label(f_bot_fixed, text=f"{tk_name}  |  {etapa.upper()}",
                     bg="#2C3E50", fg="#AED6F1", font=("Arial",9)).pack(side="right", padx=12)

            popup.update_idletasks()

        except Exception as e:
            import traceback
            traceback.print_exc()
            import tkinter.messagebox as messagebox
            messagebox.showerror("Error", f"Error al abrir ficha:\n{e}")

    def crear_fila_popup(self, etapa, tk_name, parent, start_row, fields, bg_row="#eee"):
        col_cursor = 0
        font_bold = ("Arial", 8, "bold")
        for item in fields:
            lbl, key, w_type, span = item
            tk.Label(parent, text=lbl, font=font_bold, bg=bg_row, anchor="w").grid(row=start_row, column=col_cursor, columnspan=span, sticky="ew", padx=1, pady=(5,0))
            col_cursor += span
        col_cursor = 0
        for item in fields:
            lbl, key, w_type, span = item
            var_name = f"{etapa}_{tk_name}_{key}"
            widget = None
            if w_type == "combo":
                # 1. Obtenemos la lista de documentos que tienen número
                lista_docs = [d["numero"].get() for d in self.ddt_data if d["numero"].get()]
                
                # 2. AGREGA ESTA LINEA: Insertamos una opción vacía al principio
                values_docs = [""] + lista_docs 
                
                widget = ttk.Combobox(parent, textvariable=self.get_var(var_name), values=values_docs, state="readonly")
                widget.bind("<<ComboboxSelected>>", lambda event, t=tk_name, e=etapa: self.on_ddt_selected(e, t))
                        
            elif w_type == "combo_vcf":
                vcf_v = self.get_var(var_name)
                if not vcf_v.get(): vcf_v.set("54B (Combustibles)")
                widget = ttk.Combobox(parent, textvariable=vcf_v, values=[
                "54B (Combustibles)", "54A (Crudos)", "54D (Lubricantes)",
                "Químico (Lineal)", "GLP/Propano (tabla 54E)", "GNL/Criogénico",
                "Amoniaco/Refrigerante", "Sin corrección (VCF=1)"
            ], state="readonly")
                widget.bind("<<ComboboxSelected>>", lambda event, t=tk_name, e=etapa: self.calc_volumen_prod_ui(e, t))
            else:
                st = "readonly" if "ro" in w_type else "normal"
                widget = tk.Entry(parent, textvariable=self.get_var(var_name), justify="center", state=st)
                if key in ["alt_uti", "desc_tubo", "alt_ref"]:
                    widget.bind("<KeyRelease>", lambda event, t=tk_name, e=etapa: self.calc_sondaje_prod(e, t))
                elif "prod_" in key or key == "temp" or "dens_lab" in key:
                    widget.bind("<KeyRelease>", lambda event, t=tk_name, e=etapa: self.calc_volumen_prod_ui(e, t))
            if widget:
                widget.grid(row=start_row+1, column=col_cursor, columnspan=span, sticky="ew", padx=1, pady=(0,5))
            col_cursor += span

    def get_tributos_activos(self):
        """Devuelve lista de (nombre, alicuota) de tributos activos."""
        if not hasattr(self, "_tributos_sesion") or not self._tributos_sesion:
            # Default: Derechos + Estadística + Ganancias
            self._tributos_sesion = [
                {"nombre": t[0], "alicuota": t[1], "activo": t[2]}
                for t in self.TRIBUTOS_CATALOGO
            ]
        return [(t["nombre"], t["alicuota"]) for t in self._tributos_sesion if t["activo"]]

    def dialogo_tributos(self, parent=None):
        """Abre diálogo interactivo para seleccionar y configurar tributos."""
        if not hasattr(self, "_tributos_sesion") or not self._tributos_sesion:
            self._tributos_sesion = [
                {"nombre": t[0], "alicuota": t[1], "activo": t[2]}
                for t in self.TRIBUTOS_CATALOGO
            ]
        resultado = {"ok": False}
        dlg = tk.Toplevel(parent or self.root)
        dlg.title("Configurar Tributos para Cargo/Denuncia")
        dlg.grab_set()
        dlg.transient(parent or self.root)
        dlg.update_idletasks()
        sw, sh = dlg.winfo_screenwidth(), dlg.winfo_screenheight()
        dlg.geometry(f"620x480+{(sw-620)//2}+{(sh-480)//2}")

        tk.Label(dlg, text="TRIBUTOS A INCLUIR EN EL CÁLCULO", bg="#1B3A5C", fg="white",
                 font=("Arial", 9, "bold")).pack(fill="x", ipady=7)
        tk.Label(dlg, text="Seleccioná los tributos y ajustá los porcentajes según el caso.",
                 font=("Arial", 9), fg="#555").pack(pady=(6,2))

        # Headers
        fhdr = tk.Frame(dlg, bg="#DEE2E6")
        fhdr.pack(fill="x", padx=15, pady=(4,0))
        for txt, w in [("Incluir", 6), ("Concepto", 34), ("Alícuota (%)", 14), ("", 6)]:
            tk.Label(fhdr, text=txt, bg="#DEE2E6", font=("Arial", 8, "bold"),
                     width=w, anchor="w").pack(side="left", padx=3, pady=3)

        # Scrollable rows
        cf = tk.Frame(dlg); cf.pack(fill="both", expand=True, padx=15, pady=2)
        cv_t = tk.Canvas(cf, bg="white"); sb_t = ttk.Scrollbar(cf, orient="v", command=cv_t.yview)
        sf_t = tk.Frame(cv_t, bg="white")
        cv_t.create_window((0,0), window=sf_t, anchor="nw")
        sf_t.bind("<Configure>", lambda e: cv_t.configure(scrollregion=cv_t.bbox("all")))
        cv_t.configure(yscrollcommand=sb_t.set)
        cv_t.pack(side="left", fill="both", expand=True)
        sb_t.pack(side="right", fill="y")

        row_vars = []  # (activo_var, nombre_var, alicuota_var)
        for trib in self._tributos_sesion:
            v_act  = tk.BooleanVar(value=trib["activo"])
            v_nom  = tk.StringVar(value=trib["nombre"])
            v_alic = tk.StringVar(value=str(trib["alicuota"]))
            row_vars.append((v_act, v_nom, v_alic))
            row = tk.Frame(sf_t, bg="white")
            row.pack(fill="x", pady=1)
            tk.Checkbutton(row, variable=v_act, bg="white").pack(side="left", padx=4)
            tk.Label(row, textvariable=v_nom, bg="white", font=("Arial", 9),
                     width=32, anchor="w").pack(side="left")
            e_alic = tk.Entry(row, textvariable=v_alic, width=10, font=("Arial", 9),
                              justify="center")
            e_alic.pack(side="left", padx=6)
            tk.Label(row, text="%", bg="white", font=("Arial", 9)).pack(side="left")

        # Custom tributo row
        sep = ttk.Separator(dlg, orient="horizontal")
        sep.pack(fill="x", padx=15, pady=4)
        f_custom = tk.Frame(dlg); f_custom.pack(fill="x", padx=15)
        tk.Label(f_custom, text="+ Agregar concepto:", font=("Arial", 8, "bold")).pack(side="left")
        v_custom_nom  = tk.StringVar()
        v_custom_alic = tk.StringVar(value="0.0")
        tk.Entry(f_custom, textvariable=v_custom_nom, width=28,
                 font=("Arial", 9)).pack(side="left", padx=6)
        tk.Entry(f_custom, textvariable=v_custom_alic, width=8,
                 font=("Arial", 9)).pack(side="left")
        tk.Label(f_custom, text="%", font=("Arial", 9)).pack(side="left", padx=2)

        def _add_custom():
            nom = v_custom_nom.get().strip()
            if not nom: return
            try: alic = float(v_custom_alic.get())
            except: alic = 0.0
            new_t = {"nombre": nom, "alicuota": alic, "activo": True}
            self._tributos_sesion.append(new_t)
            v_act  = tk.BooleanVar(value=True)
            v_nom  = tk.StringVar(value=nom)
            v_alic = tk.StringVar(value=str(alic))
            row_vars.append((v_act, v_nom, v_alic))
            row = tk.Frame(sf_t, bg="white"); row.pack(fill="x", pady=1)
            tk.Checkbutton(row, variable=v_act, bg="white").pack(side="left", padx=4)
            tk.Label(row, textvariable=v_nom, bg="white", font=("Arial",9), width=32, anchor="w").pack(side="left")
            tk.Entry(row, textvariable=v_alic, width=10, font=("Arial",9), justify="center").pack(side="left", padx=6)
            tk.Label(row, text="%", bg="white", font=("Arial",9)).pack(side="left")
            v_custom_nom.set(""); v_custom_alic.set("0.0")

        tk.Button(f_custom, text="Agregar", bg="#2196F3", fg="white",
                  font=("Arial", 8, "bold"), command=_add_custom).pack(side="left", padx=8)

        def _confirmar():
            for i, (v_act, v_nom, v_alic) in enumerate(row_vars):
                if i < len(self._tributos_sesion):
                    self._tributos_sesion[i]["activo"]   = v_act.get()
                    self._tributos_sesion[i]["alicuota"] = float(v_alic.get() or "0")
            resultado["ok"] = True
            dlg.destroy()

        fbot_t = tk.Frame(dlg); fbot_t.pack(fill="x", padx=15, pady=8)
        tk.Button(fbot_t, text="Confirmar y Continuar", bg="#27AE60", fg="white",
                  font=("Arial", 9, "bold"), command=_confirmar).pack(side="right", padx=6)
        tk.Button(fbot_t, text="Cancelar", bg="#E74C3C", fg="white",
                  font=("Arial", 9), command=dlg.destroy).pack(side="right", padx=4)

        dlg.wait_window()
        return resultado["ok"]

    def abrir_draft_survey(self):
        """Ventana completa de Draft Survey."""
        try:
            top = tk.Toplevel(self.root)
            top.title("Draft Survey — Estimación de Peso por Calados")
            top.geometry("1020x820")
            top.resizable(True, True)
            top.transient(self.root)

            fnt_b = ("Arial", 8, "bold")
            fnt_n = ("Arial", 8)

            # ── Canvas scrollable ─────────────────────────────────────────────
            main_frame = tk.Frame(top)
            main_frame.pack(fill="both", expand=True)
            canvas_ds = tk.Canvas(main_frame)
            sb_ds = ttk.Scrollbar(main_frame, orient="vertical", command=canvas_ds.yview)
            sf = ttk.Frame(canvas_ds)
            sf.bind("<Configure>", lambda e: canvas_ds.configure(scrollregion=canvas_ds.bbox("all")))
            canvas_ds.create_window((0,0), window=sf, anchor="nw")
            canvas_ds.configure(yscrollcommand=sb_ds.set)
            canvas_ds.pack(side="left", fill="both", expand=True)
            sb_ds.pack(side="right", fill="y")
            canvas_ds.bind("<MouseWheel>", lambda e: canvas_ds.yview_scroll(int(-1*(e.delta/120)),"units"))

            def make_section(parent, title, color="#1B3A5C"):
                lf = tk.LabelFrame(parent, text=f"  {title}  ", bg="#F8F9FA",
                                   font=fnt_b, fg=color, relief="groove", bd=2)
                lf.pack(fill="x", padx=15, pady=6)
                return lf

            def fv(default=""):
                return tk.StringVar(value=str(default))

            # ── SECCIÓN 1: Datos del buque ─────────────────────────────────────
            s1 = make_section(sf, "DATOS DEL BUQUE")
            buque_fields = [
                ("Nombre del Buque:", self.get_var("car_buque")),
                ("LBP (m):",          fv("0")),
                ("LCF desde popa (m):", fv("0")),
                ("Constante Buque (t):", fv("0")),
            ]
            _lbp_v  = buque_fields[1][1]
            _lcf_v  = buque_fields[2][1]
            for ci, (lbl, var) in enumerate(buque_fields):
                tk.Label(s1, text=lbl, bg="#F8F9FA", font=fnt_b).grid(row=0, column=ci*2, sticky="e", padx=6, pady=6)
                tk.Entry(s1, textvariable=var, width=14, font=fnt_n).grid(row=0, column=ci*2+1, sticky="w", padx=4)

            # ── SECCIÓN 2: Calados ─────────────────────────────────────────────
            def make_calados_section(parent, etiqueta, prefix, color):
                s = make_section(parent, etiqueta, color)
                vs = {}
                for ri, pos in enumerate(["proa","medio","popa"]):
                    tk.Label(s, text=f"{pos.upper()}:", bg="#F8F9FA", font=fnt_b, width=8
                             ).grid(row=ri, column=0, sticky="e", padx=6, pady=3)
                    for ci_s, (side, lbl_s) in enumerate([("b","Babor (m)"),("e","Estribor (m)")]):
                        k = f"{prefix}_{pos}_{side}"
                        v = fv("0"); vs[k] = v
                        tk.Label(s, text=lbl_s, bg="#F8F9FA", font=fnt_n).grid(row=ri, column=ci_s*2+1, sticky="e", padx=3)
                        tk.Entry(s, textvariable=v, width=9, font=fnt_n).grid(row=ri, column=ci_s*2+2, sticky="w", padx=3)
                        v.trace_add("write", lambda *a, px=prefix: _recalc(px))
                tk.Label(s, text="Cal. corr.:", bg="#F8F9FA", font=fnt_b).grid(row=3, column=0, sticky="e", padx=6, pady=3)
                vs[f"{prefix}_calado_corr"] = fv()
                tk.Label(s, textvariable=vs[f"{prefix}_calado_corr"], bg="#dceeff", relief="sunken",
                         font=fnt_n, width=20, anchor="w").grid(row=3, column=1, columnspan=3, sticky="w", padx=3)
                tk.Label(s, text="Hog/Sag:", bg="#F8F9FA", font=fnt_b).grid(row=3, column=4, sticky="e", padx=6)
                vs[f"{prefix}_hog_sag"] = fv()
                tk.Label(s, textvariable=vs[f"{prefix}_hog_sag"], bg="#fff3cd", relief="sunken",
                         font=fnt_n, width=18, anchor="w").grid(row=3, column=5, sticky="w", padx=3)
                tk.Label(s, text="Desplaz. (t):", bg="#F8F9FA", font=fnt_b).grid(row=4, column=0, sticky="e", padx=6, pady=3)
                vs[f"{prefix}_desp"] = fv()
                tk.Label(s, textvariable=vs[f"{prefix}_desp"], bg="#d4edda", relief="sunken",
                         font=(fnt_b[0], fnt_b[1]+1, "bold"), width=14, anchor="center"
                         ).grid(row=4, column=1, columnspan=2, sticky="w", padx=3)
                tk.Label(s, text="TPC:", bg="#F8F9FA", font=fnt_b).grid(row=4, column=4, sticky="e", padx=6)
                vs[f"{prefix}_tpc"] = fv()
                tk.Label(s, textvariable=vs[f"{prefix}_tpc"], bg="#dceeff", relief="sunken",
                         font=fnt_n, width=10, anchor="w").grid(row=4, column=5, sticky="w", padx=3)
                return s, vs

            s2, vs_ini = make_calados_section(sf, "CALADOS INICIALES (ANTES DE CARGA/DESCARGA)", "ini", "#1B3A5C")
            s3, vs_fin = make_calados_section(sf, "CALADOS FINALES (DESPUÉS DE CARGA/DESCARGA)", "fin", "#1D6A39")

            # ── SECCIÓN 3: Tabla hidrostática ──────────────────────────────────
            s4 = make_section(sf, "TABLA HIDROSTÁTICA (Calado → Desplazamiento/TPC/LCF)")
            f_hidro_btns = tk.Frame(s4, bg="#F8F9FA")
            f_hidro_btns.pack(anchor="w", padx=8, pady=4)
            hidro_data = []  # lista de [calado, desp, tpc, lcf]

            def _parse_hidro():
                rows = []
                for row in hidro_data:
                    try:
                        rows.append((float(row[0].get()), float(row[1].get()),
                                     float(row[2].get()), float(row[3].get())))
                    except: pass
                return sorted(rows, key=lambda r: r[0])

            hidro_frame = tk.Frame(s4, bg="#F8F9FA")
            hidro_frame.pack(fill="x", padx=8)
            for ci_h, htxt in enumerate(["Calado (m)","Desplaz. (t)","TPC (t/cm)","LCF desde popa (m)"]):
                tk.Label(hidro_frame, text=htxt, bg="#E8EAF6", font=fnt_b, width=18, relief="groove"
                         ).grid(row=0, column=ci_h, padx=2, pady=2)

            def _add_hidro_row(vals=None):
                ri = len(hidro_data)+1
                row_vars = []
                for ci in range(4):
                    v = fv(vals[ci] if vals else "0")
                    row_vars.append(v)
                    tk.Entry(hidro_frame, textvariable=v, width=18, font=fnt_n
                             ).grid(row=ri, column=ci, padx=2, pady=1)
                hidro_data.append(row_vars)

            for _ in range(6): _add_hidro_row()

            def _exportar_hidro_csv():
                import csv, tkinter.filedialog as fd2
                path2 = fd2.asksaveasfilename(defaultextension=".csv",
                    filetypes=[("CSV","*.csv")], initialfile="hidrostatica.csv", parent=top)
                if not path2: return
                with open(path2, "w", newline="", encoding="utf-8") as f2:
                    w2c = csv.writer(f2)
                    w2c.writerow(["Calado(m)","Desplaz(t)","TPC","LCF"])
                    for row in hidro_data:
                        try: w2c.writerow([r.get() for r in row])
                        except: pass
                messagebox.showinfo("Exportado", f"Tabla exportada: {path2}", parent=top)

            def _importar_hidro_csv():
                import csv, tkinter.filedialog as fd2
                path2 = fd2.askopenfilename(filetypes=[("CSV","*.csv")], parent=top)
                if not path2: return
                with open(path2, newline="", encoding="utf-8") as f2:
                    reader = csv.reader(f2)
                    rows_csv = [r for r in reader if r and r[0] != "Calado(m)"]
                while len(hidro_data) < len(rows_csv): _add_hidro_row()
                for ri2, row_vals in enumerate(rows_csv):
                    if ri2 >= len(hidro_data): break
                    for ci2, v2 in enumerate(row_vals[:4]):
                        hidro_data[ri2][ci2].set(v2)

            tk.Button(f_hidro_btns, text="+ Fila", bg="#1B3A5C", fg="white", font=("Arial",7,"bold"),
                      command=_add_hidro_row).pack(side="left", padx=4, ipadx=4, ipady=1)
            tk.Button(f_hidro_btns, text="Exportar CSV", bg="#455A64", fg="white", font=("Arial",7,"bold"),
                      command=_exportar_hidro_csv).pack(side="right", padx=4, ipadx=4, ipady=1)
            tk.Button(f_hidro_btns, text="Importar CSV", bg="#546E7A", fg="white", font=("Arial",7,"bold"),
                      command=_importar_hidro_csv).pack(side="right", padx=4, ipadx=4, ipady=1)

            # ═══════════════════════════════════════════════════════════════════
            # BALLAST WATERS — dinámica (agregar / quitar tanques)
            # ═══════════════════════════════════════════════════════════════════
            s_bw = make_section(sf, "BALLAST WATERS (Lastre)", "#1D6A39")
            f_bw_btns = tk.Frame(s_bw, bg="#F8F9FA")
            f_bw_btns.pack(anchor="w", padx=8, pady=4)

            bw_frame = tk.Frame(s_bw, bg="#F8F9FA")
            bw_frame.pack(fill="x", padx=8, pady=2)
            bw_rows = []   # lista de dicts: {name_var, bb_ini, bb_fin, es_ini, es_fin, widgets}

            # Cabecera fija
            for ci_h, htxt in enumerate(["TANQUE","BABOR ini(t)","BABOR fin(t)","ESTRIBOR ini(t)","ESTRIBOR fin(t)",""]):
                tk.Label(bw_frame, text=htxt, bg="#C8E6C9", font=fnt_b,
                         width=14 if ci_h==0 else (3 if ci_h==5 else 12), relief="groove"
                         ).grid(row=0, column=ci_h, padx=2, pady=2)

            def _bw_rebuild_totals():
                _recalc_final()

            def _bw_remove_row(row_dict):
                for w in row_dict["widgets"]:
                    try: w.grid_forget(); w.destroy()
                    except: pass
                bw_rows.remove(row_dict)
                # Re-grid remaining rows
                for ri3, rd in enumerate(bw_rows, 1):
                    for w in rd["widgets"]:
                        info = w.grid_info()
                        if info:
                            w.grid(row=ri3, column=info["column"])
                _bw_rebuild_totals()

            def _bw_add_row(name=""):
                ri = len(bw_rows) + 1
                row_dict = {}
                row_widgets = []
                name_v = fv(name or f"TK {ri} BALLAST")
                row_dict["name_var"] = name_v
                e_name = tk.Entry(bw_frame, textvariable=name_v, width=14, font=fnt_n, bg="#EAF4FC")
                e_name.grid(row=ri, column=0, padx=2, pady=2)
                row_widgets.append(e_name)
                for ci_s, key_s in enumerate(["bb_ini","bb_fin","es_ini","es_fin"]):
                    v = fv("0")
                    row_dict[key_s] = v
                    bg_e = "#E8F8EF" if "fin" in key_s else "#FFFDE7"
                    ew = tk.Entry(bw_frame, textvariable=v, width=12, font=fnt_n, bg=bg_e)
                    ew.grid(row=ri, column=ci_s+1, padx=2, pady=2)
                    row_widgets.append(ew)
                    v.trace_add("write", lambda *a: _recalc_final())
                btn_del = tk.Button(bw_frame, text="✕", font=("Arial",7), bg="#E53935", fg="white",
                                    width=2, cursor="hand2",
                                    command=lambda rd=row_dict: _bw_remove_row(rd))
                btn_del.grid(row=ri, column=5, padx=2, pady=2)
                row_widgets.append(btn_del)
                row_dict["widgets"] = row_widgets
                bw_rows.append(row_dict)

            # 8 tanques por defecto
            for i in range(1, 9):
                _bw_add_row(f"TK {i} BALLAST")

            tk.Button(f_bw_btns, text="+ Agregar tanque", bg="#1D6A39", fg="white", font=("Arial",7,"bold"),
                      command=_bw_add_row).pack(side="left", padx=4, ipadx=6, ipady=2)
            tk.Label(f_bw_btns, text="  (podés agregar o quitar tanques con ✕)", bg="#F8F9FA",
                     font=("Arial",7), fg="#555").pack(side="left")

            # ═══════════════════════════════════════════════════════════════════
            # DEDUCCIONES
            # ═══════════════════════════════════════════════════════════════════
            s5 = make_section(sf, "DEDUCCIONES ADICIONALES (Combustible, Agua Dulce, Otros)")
            ded_fields = [
                ("Constante Buque (t)",  "ded_cte_buque_ini"),
                ("FO inicio (t)",  "ded_fo_ini"),
                ("FO final (t)",   "ded_fo_fin"),
                ("DO inicio (t)",  "ded_do_ini"),
                ("DO final (t)",   "ded_do_fin"),
                ("FW inicio (t)",  "ded_fw_ini"),
                ("FW final (t)",   "ded_fw_fin"),
                ("Otros ini (t)",  "ded_ot_ini"),
                ("Otros fin (t)",  "ded_ot_fin"),
            ]
            ded_vs = {}
            for ci, (lbl, key) in enumerate(ded_fields):
                r, c = divmod(ci, 4)
                tk.Label(s5, text=lbl, bg="#F8F9FA", font=fnt_b).grid(row=r, column=c*2, sticky="e", padx=6, pady=3)
                v = fv("0"); ded_vs[key] = v
                tk.Entry(s5, textvariable=v, width=10, font=fnt_n).grid(row=r, column=c*2+1, sticky="w", padx=3)
                v.trace_add("write", lambda *a: _recalc_final())

            # ── Resultados ─────────────────────────────────────────────────────
            s6 = make_section(sf, "RESULTADO FINAL", "#7B1FA2")
            res_labels = [
                ("Desplaz. Inicial Corregido (t)", "res_desp_ini"),
                ("Desplaz. Final Corregido (t)",   "res_desp_fin"),
                ("Δ Desplazamiento (t)",            "res_delta_desp"),
                ("Total Deducciones (t)",           "res_deducs"),
                ("BW Total Inicio (t)",             "res_bw_ini"),
                ("BW Total Final (t)",              "res_bw_fin"),
                ("Constante Buque (t)",             "res_cte"),
                ("PESO CARGA ESTIMADO (t)",         "res_peso"),
                ("Obs.",                             "res_obs"),
            ]
            res_vs = {}
            for ri, (lbl, key) in enumerate(res_labels):
                r, c = divmod(ri, 2)
                bold = key == "res_peso"
                bg = "#D5E8D4" if bold else "#dceeff"
                tk.Label(s6, text=lbl, bg="#F8F9FA",
                         font=fnt_b if bold else ("Arial",8),
                         fg="#7B1FA2" if bold else "#222"
                         ).grid(row=r, column=c*2, sticky="e", padx=8, pady=4)
                v = fv("—"); res_vs[key] = v
                tk.Label(s6, textvariable=v, bg=bg, relief="sunken",
                         font=("Arial",11,"bold") if bold else fnt_n,
                         width=16, anchor="center"
                         ).grid(row=r, column=c*2+1, sticky="w", padx=4)

            # ── Cálculo ────────────────────────────────────────────────────────
            def _recalc(prefix):
                try:
                    vs = vs_ini if prefix == "ini" else vs_fin
                    pb = self.parse_float(vs.get(f"{prefix}_proa_b", fv()).get())
                    pe = self.parse_float(vs.get(f"{prefix}_proa_e", fv()).get())
                    mb = self.parse_float(vs.get(f"{prefix}_medio_b", fv()).get())
                    me = self.parse_float(vs.get(f"{prefix}_medio_e", fv()).get())
                    ab = self.parse_float(vs.get(f"{prefix}_popa_b", fv()).get())
                    ae = self.parse_float(vs.get(f"{prefix}_popa_e", fv()).get())
                    proa, popa, medio, trim = self.calc_draft_trim(pb,pe,ab,ae,mb,me)
                    _lbp_val = self.parse_float(_lbp_v.get())
                    if _lbp_val <= 0:
                        _lbp_v.set(""); return
                    calado_corr = self.calc_draft_corr_trim(proa, popa, medio, _lbp_val)
                    tipo_hs, mm_hs = self.calc_draft_hog_sag(proa, popa, medio)
                    tabla = _parse_hidro()
                    desp, tpc, lcf = self.calc_desplazamiento_interpolado(calado_corr, tabla)
                    lbp = _lbp_val
                    lcf_v = self.parse_float(_lcf_v.get()) or lcf
                    desp_corr = self.calc_draft_desp_trimado(desp, trim, tpc, lcf_v, lbp)
                    vs[f"{prefix}_calado_corr"].set(f"{calado_corr:.3f} m  (trim: {trim:+.3f})")
                    vs[f"{prefix}_hog_sag"].set(f"{tipo_hs} {mm_hs} mm")
                    vs[f"{prefix}_desp"].set(f"{desp_corr:,.1f}")
                    vs[f"{prefix}_tpc"].set(f"{tpc:.2f}")
                except Exception:
                    pass
                _recalc_final()

            def _recalc_final():
                try:
                    d_ini = self.parse_float(vs_ini.get("ini_desp", fv()).get().replace(",","") or "0")
                    d_fin = self.parse_float(vs_fin.get("fin_desp", fv()).get().replace(",","") or "0")
                    fo_i = self.parse_float(ded_vs["ded_fo_ini"].get())
                    fo_f = self.parse_float(ded_vs["ded_fo_fin"].get())
                    do_i = self.parse_float(ded_vs["ded_do_ini"].get())
                    do_f = self.parse_float(ded_vs["ded_do_fin"].get())
                    fw_i = self.parse_float(ded_vs["ded_fw_ini"].get())
                    fw_f = self.parse_float(ded_vs["ded_fw_fin"].get())
                    ot_i = self.parse_float(ded_vs["ded_ot_ini"].get())
                    ot_f = self.parse_float(ded_vs["ded_ot_fin"].get())
                    cte  = self.parse_float(ded_vs.get("ded_cte_buque_ini", fv("0")).get())
                    bw_i = 0.0; bw_f = 0.0
                    for rd in bw_rows:
                        bw_i += self.parse_float(rd["bb_ini"].get()) + self.parse_float(rd["es_ini"].get())
                        bw_f += self.parse_float(rd["bb_fin"].get()) + self.parse_float(rd["es_fin"].get())
                    comb_ini = fo_i + do_i
                    comb_fin = fo_f + do_f
                    agua_ini = fw_i + bw_i
                    agua_fin = fw_f + bw_f
                    peso, delta_d, delta_ded = self.calc_draft_peso_carga(
                        d_fin, d_ini, cte, comb_ini, comb_fin, agua_ini, agua_fin, ot_i, ot_f)
                    res_vs["res_desp_ini"].set(f"{d_ini:,.1f}")
                    res_vs["res_desp_fin"].set(f"{d_fin:,.1f}")
                    res_vs["res_delta_desp"].set(f"{delta_d:+,.1f}")
                    res_vs["res_deducs"].set(f"{delta_ded:+,.1f}")
                    res_vs["res_peso"].set(f"{peso:,.2f} t")
                    res_vs["res_obs"].set("CARGANDO" if peso > 0 else "DESCARGANDO")
                    res_vs["res_bw_ini"].set(f"{bw_i:,.1f}")
                    res_vs["res_bw_fin"].set(f"{bw_f:,.1f}")
                    res_vs["res_cte"].set(f"{cte:,.1f}")
                except Exception:
                    pass

            # ── PDF export ─────────────────────────────────────────────────────
            def _export_pdf():
                try:
                    from reportlab.lib.pagesizes import A4
                    from reportlab.pdfgen import canvas as rlc
                    import tkinter.filedialog as fd
                    from datetime import datetime

                    buque_nombre = self.get_var("car_buque").get() or "buque"
                    path = fd.asksaveasfilename(
                        defaultextension=".pdf",
                        filetypes=[("PDF","*.pdf")],
                        initialfile=f"DraftSurvey_{buque_nombre}.pdf",
                        parent=top)
                    if not path: return

                    cw, ch = A4
                    M = 45
                    c2 = rlc.Canvas(path, pagesize=A4)

                    def new_page():
                        nonlocal y2
                        c2.showPage()
                        y2 = ch - 50

                    def check_page(needed=25):
                        nonlocal y2
                        if y2 < needed:
                            new_page()

                    # Header
                    c2.setFillColorRGB(0.106, 0.227, 0.361)
                    c2.rect(M, ch-72, cw-2*M, 50, fill=1, stroke=0)
                    c2.setFillColorRGB(1,1,1)
                    c2.setFont("Helvetica-Bold", 15)
                    c2.drawCentredString(cw/2, ch-50, "DRAFT SURVEY — ESTIMACIÓN DE PESO DE CARGA")
                    c2.setFont("Helvetica", 9)
                    c2.drawCentredString(cw/2, ch-64,
                        f"Buque: {buque_nombre}   |   Fecha: {datetime.now().strftime('%d/%m/%Y %H:%M')}")
                    y2 = ch - 90

                    def draw_section_title(text, color=(0.11,0.23,0.36)):
                        nonlocal y2
                        check_page(30)
                        c2.setFillColorRGB(*color)
                        c2.rect(M, y2-12, cw-2*M, 16, fill=1, stroke=0)
                        c2.setFillColorRGB(1,1,1)
                        c2.setFont("Helvetica-Bold", 9)
                        c2.drawString(M+6, y2-6, text)
                        y2 -= 20
                        c2.setFillColorRGB(0,0,0)
                        c2.setFont("Helvetica", 9)

                    def two_fields(l1, v1, l2="", v2=""):
                        nonlocal y2
                        check_page()
                        c2.setFont("Helvetica-Bold", 8); c2.setFillColorRGB(0.2,0.2,0.2)
                        c2.drawString(M, y2, str(l1))
                        c2.setFont("Helvetica", 8); c2.setFillColorRGB(0,0,0)
                        c2.drawString(M+130, y2, str(v1))
                        if l2:
                            c2.setFont("Helvetica-Bold", 8); c2.setFillColorRGB(0.2,0.2,0.2)
                            c2.drawString(cw/2+10, y2, str(l2))
                            c2.setFont("Helvetica", 8); c2.setFillColorRGB(0,0,0)
                            c2.drawString(cw/2+140, y2, str(v2))
                        y2 -= 12

                    def draw_field(label, val):
                        nonlocal y2
                        check_page()
                        c2.setFont("Helvetica-Bold", 8); c2.setFillColorRGB(0.2,0.2,0.2)
                        c2.drawString(M, y2, str(label))
                        c2.setFont("Helvetica", 8); c2.setFillColorRGB(0,0,0)
                        c2.drawString(M+130, y2, str(val))
                        y2 -= 12

                    # Datos buque
                    draw_section_title("DATOS DEL BUQUE")
                    two_fields("Nombre:", buque_nombre, "LBP (m):", _lbp_v.get())
                    two_fields("LCF desde popa (m):", _lcf_v.get(),
                               "Constante Buque (t):", ded_vs.get("ded_cte_buque_ini", fv("0")).get())
                    y2 -= 4

                    # Calados
                    for pref, label_c, vs_d in [("ini","CALADOS INICIALES", vs_ini),
                                                ("fin","CALADOS FINALES",   vs_fin)]:
                        draw_section_title(label_c)
                        for pos in ["proa","medio","popa"]:
                            pb2 = vs_d.get(f"{pref}_{pos}_b", fv()).get()
                            pe2 = vs_d.get(f"{pref}_{pos}_e", fv()).get()
                            two_fields(f"  {pos.upper()} babor:", pb2, f"  {pos.upper()} estribor:", pe2)
                        draw_field("  Calado corregido:", vs_d.get(f"{pref}_calado_corr", fv()).get())
                        draw_field("  Hog/Sag:", vs_d.get(f"{pref}_hog_sag", fv()).get())
                        draw_field("  Desplazamiento (t):", vs_d.get(f"{pref}_desp", fv()).get())
                        draw_field("  TPC:", vs_d.get(f"{pref}_tpc", fv()).get())
                        y2 -= 4

                    # Ballast Waters dinámico
                    draw_section_title("BALLAST WATERS", color=(0.11,0.42,0.24))
                    bw_col_x = [M, M+110, M+185, M+260, M+335]
                    c2.setFont("Helvetica-Bold", 7); c2.setFillColorRGB(0,0,0)
                    for ci_h2, htx in enumerate(["TANQUE","BABOR ini(t)","BABOR fin(t)","ESTRIBOR ini(t)","ESTRIBOR fin(t)"]):
                        c2.drawString(bw_col_x[ci_h2], y2, htx)
                    y2 -= 11
                    bw_total_ini = 0.0; bw_total_fin = 0.0
                    for rd in bw_rows:
                        check_page()
                        c2.setFont("Helvetica", 7)
                        c2.drawString(bw_col_x[0], y2, rd["name_var"].get())
                        for ci_s2, key_s2 in enumerate(["bb_ini","bb_fin","es_ini","es_fin"]):
                            val_str = rd[key_s2].get()
                            c2.drawString(bw_col_x[ci_s2+1], y2, val_str)
                            try:
                                fval = float(val_str)
                                if "ini" in key_s2: bw_total_ini += fval
                                else:               bw_total_fin += fval
                            except: pass
                        y2 -= 10
                    c2.setFont("Helvetica-Bold", 8)
                    c2.drawString(M, y2, f"TOTAL ini: {bw_total_ini:,.1f} t   |   TOTAL fin: {bw_total_fin:,.1f} t")
                    y2 -= 16

                    # Deducciones
                    draw_section_title("DEDUCCIONES ADICIONALES")
                    ded_show = [
                        ("FO inicio (t)", ded_vs["ded_fo_ini"].get()),
                        ("FO final (t)",  ded_vs["ded_fo_fin"].get()),
                        ("DO inicio (t)", ded_vs["ded_do_ini"].get()),
                        ("DO final (t)",  ded_vs["ded_do_fin"].get()),
                        ("FW inicio (t)", ded_vs["ded_fw_ini"].get()),
                        ("FW final (t)",  ded_vs["ded_fw_fin"].get()),
                        ("Otros ini (t)", ded_vs["ded_ot_ini"].get()),
                        ("Otros fin (t)", ded_vs["ded_ot_fin"].get()),
                    ]
                    for ii_d in range(0, len(ded_show), 2):
                        l1d, v1d = ded_show[ii_d]
                        l2d, v2d = ded_show[ii_d+1] if ii_d+1 < len(ded_show) else ("","")
                        two_fields(f"  {l1d}", v1d, f"  {l2d}", v2d)
                    y2 -= 6

                    # Resultado
                    draw_section_title("RESULTADO FINAL", color=(0.48,0.11,0.63))
                    for lbl_r, key_r in [
                        ("Desplaz. Inicial Corregido (t):", "res_desp_ini"),
                        ("Desplaz. Final Corregido (t):",   "res_desp_fin"),
                        ("Δ Desplazamiento (t):",           "res_delta_desp"),
                        ("Total Deducciones (t):",          "res_deducs"),
                        ("BW Total Inicial (t):",           "res_bw_ini"),
                        ("BW Total Final (t):",             "res_bw_fin"),
                        ("Constante Buque (t):",            "res_cte"),
                    ]:
                        draw_field(f"  {lbl_r}", res_vs.get(key_r, fv("—")).get())
                    y2 -= 4
                    check_page(30)
                    c2.setFillColorRGB(0.11,0.42,0.24)
                    c2.setFont("Helvetica-Bold", 13)
                    peso_txt = res_vs.get("res_peso", fv("—")).get()
                    obs_txt  = res_vs.get("res_obs",  fv("—")).get()
                    c2.drawString(M, y2, f"PESO DE CARGA ESTIMADO: {peso_txt}  —  {obs_txt}")
                    c2.setFillColorRGB(0,0,0)
                    y2 -= 20
                    
                    c2.save()
                    messagebox.showinfo("Draft Survey", f"PDF guardado:\n{path}", parent=top)
                except Exception as ex:
                    import traceback as tb2; tb2.print_exc()
                    messagebox.showerror("Error al exportar", str(ex), parent=top)

            # ── Botones ────────────────────────────────────────────────────────
            fbot = tk.Frame(top, bg="#1B3A5C")
            fbot.pack(fill="x", side="bottom")
            tk.Button(fbot, text="RECALCULAR TODO", bg="#2196F3", fg="white",
                      font=("Arial", 8, "bold"),
                      command=lambda: [_recalc("ini"), _recalc("fin")]
                      ).pack(side="left", padx=10, pady=6)
            tk.Button(fbot, text="EXPORTAR PDF", bg="#27AE60", fg="white",
                      font=("Arial", 8, "bold"),
                      command=_export_pdf
                      ).pack(side="left", padx=6, pady=6)
            tk.Button(fbot, text="CERRAR", font=("Arial", 8, "bold"),
                      command=top.destroy).pack(side="right", padx=10, pady=6)

        except Exception as e:
            traceback.print_exc()
            messagebox.showerror("Error Draft Survey", str(e))

