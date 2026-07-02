"""Generación de PDFs: reporte técnico global, planillas, dibujos ReportLab.

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


class PdfReportsMixin:
    def preview_pdf_temp(self):
        """Genera PDF temporal con TODOS los reportes y lo abre."""
        import tempfile
        try:
            tmpdir = tempfile.gettempdir()
            tmp_path = os.path.join(tmpdir, "_preview_medicion.pdf")
            c_pdf = canvas.Canvas(tmp_path, pagesize=landscape(A4))
            all_tanks = self.lista_tanques + self.lista_carbonera
            report_count = 0

            # 1. Reporte técnico global
            try:
                self.generar_reporte_tecnico_global("PREVIEW", "", shared_canvas=c_pdf)
                report_count += 1
            except: pass

            # 2. Reporte general
            try:
                self.generar_un_reporte("PREVIEW", all_tanks, is_partial=False, output_folder="", shared_canvas=c_pdf)
                report_count += 1
            except: pass

            # 3. Reportes por documento
            mapa = {}
            for tk_name in all_tanks:
                d_ini = self.get_var(f"inicial_{tk_name}_ddt_assign").get()
                d_fin = self.get_var(f"final_{tk_name}_ddt_assign").get()
                if d_ini:
                    if d_ini not in mapa: mapa[d_ini] = []
                    if tk_name not in mapa[d_ini]: mapa[d_ini].append(tk_name)
                if d_fin and d_fin != d_ini:
                    if d_fin not in mapa: mapa[d_fin] = []
                    if tk_name not in mapa[d_fin]: mapa[d_fin].append(tk_name)
            modes = [("SEGÚN_LAB", "dens_lab"), ("SEGÚN_DOC", "dens_doc"), ("SEGÚN_SAL", "dens_salida")]
            for ddt_num, tanks in mapa.items():
                ddt_obj = next((d for d in self.ddt_data if d["numero"].get() == ddt_num), None)
                if not ddt_obj: continue
                for suffix, mode_key in modes:
                    try:
                        self.generar_un_reporte(f"P_{suffix}", tanks, is_partial=True, ddt_obj=ddt_obj, output_folder="", density_mode_key=mode_key, shared_canvas=c_pdf)
                        report_count += 1
                    except: pass

            c_pdf.save()
            if report_count == 0:
                messagebox.showwarning("Vista Previa", "No se pudo generar ningún reporte.")
                return
            if platform.system() == 'Windows': os.startfile(tmp_path)
            elif platform.system() == 'Darwin': subprocess.call(('open', tmp_path))
            else: subprocess.call(('xdg-open', tmp_path))
        except Exception as e:
            traceback.print_exc()
            messagebox.showerror("Error", f"No se pudo generar la vista previa:\n{e}")

    def generar_con_seleccion(self):
        """Diálogo para seleccionar qué reportes generar."""
        dlg = tk.Toplevel(self.root)
        dlg.title("Seleccionar Reportes a Generar")
        dlg.transient(self.root)
        dlg.grab_set()
        dlg.update_idletasks()
        try:
            dlg.state("zoomed")
        except:
            try:
                dlg.attributes("-zoomed", True)
            except:
                _sw, _sh = dlg.winfo_screenwidth(), dlg.winfo_screenheight()
                dlg.geometry(f"{_sw}x{_sh}+0+0")

        tk.Label(dlg, text="Seleccione los reportes a incluir en el PDF:", font=("Arial", 8, "bold"), bg="#1B3A5C", fg="white").pack(fill="x", ipady=10)

        # --- BARRA INFERIOR PRIMERO ---
        f_bot = tk.Frame(dlg, bg="#2C3E50", height=60)
        f_bot.pack(side="bottom", fill="x")
        f_bot.pack_propagate(False)

        # --- ÁREA PRINCIPAL: 2 columnas izq/der ---
        f_main = tk.Frame(dlg)
        f_main.pack(fill="both", expand=True, padx=15, pady=8)
        f_main.columnconfigure(0, weight=1)
        f_main.columnconfigure(1, weight=1)

        # COLUMNA IZQUIERDA: Globales + Control
        f_izq = ttk.LabelFrame(f_main, text=" Opciones Generales ", padding=10)
        f_izq.grid(row=0, column=0, sticky="nsew", padx=(0,8), pady=4)

        # COLUMNA DERECHA: Documentos (se rellena abajo)
        f_der = ttk.LabelFrame(f_main, text=" Reportes por Documento ", padding=10)
        f_der.grid(row=0, column=1, sticky="nsew", padx=(8,0), pady=4)

        # Alias sf → f_izq para el código existente de checkboxes globales y control
        sf = f_izq

        var_global = tk.BooleanVar(value=True)
        var_general = tk.BooleanVar(value=True)

        ttk.Checkbutton(sf, text="Reporte Técnico Global (Memoria de Cálculo)", variable=var_global).pack(anchor="w", pady=6)
        ttk.Checkbutton(sf, text="Reporte General (Todos los tanques)", variable=var_general).pack(anchor="w", pady=6)

        # --- TIPO DE CONTROL ---
        ttk.Separator(sf, orient="horizontal").pack(fill="x", pady=6)
        f_ctrl = ttk.LabelFrame(sf, text="Tipo de Control (afecta planillas y reportes de cargo)")
        f_ctrl.pack(fill="x", padx=5, pady=4)
        tk.Label(f_ctrl, text="Seleccione según qué se realizó el control:", font=("Arial", 9)).pack(anchor="w", padx=10, pady=2)
        var_ctrl_doc = tk.BooleanVar(value=True)
        var_ctrl_sal = tk.BooleanVar(value=False)
        var_ctrl_lab = tk.BooleanVar(value=False)
        ttk.Checkbutton(f_ctrl, text="Por Documento (planillas y cargos segun documento declarado)", variable=var_ctrl_doc).pack(anchor="w", padx=20)
        ttk.Checkbutton(f_ctrl, text="Por Salida de Zona Primaria (planillas y cargos segun salida)", variable=var_ctrl_sal).pack(anchor="w", padx=20)
        ttk.Checkbutton(f_ctrl, text="Por Analisis de Laboratorio (planillas y cargos segun lab)", variable=var_ctrl_lab).pack(anchor="w", padx=20)

        # ── COLUMNA DERECHA: Documentos ──
        # redirigir a f_der
        sf_doc = f_der
        ttk.Label(sf_doc, text="Reportes por Documento:", font=("Arial", 8, "bold")).pack(anchor="w", pady=(0,4))
        all_tanks = self.lista_tanques + self.lista_carbonera
        mapa = {}
        for tk_name in all_tanks:
            d_ini = self.get_var(f"inicial_{tk_name}_ddt_assign").get()
            d_fin = self.get_var(f"final_{tk_name}_ddt_assign").get()
            if d_ini:
                if d_ini not in mapa: mapa[d_ini] = []
                if tk_name not in mapa[d_ini]: mapa[d_ini].append(tk_name)
            if d_fin and d_fin != d_ini:
                if d_fin not in mapa: mapa[d_fin] = []
                if tk_name not in mapa[d_fin]: mapa[d_fin].append(tk_name)

        doc_vars = {}
        mode_vars = {}
        for ddt_num in mapa:
            ddt_obj = next((d for d in self.ddt_data if d["numero"].get() == ddt_num), None)
            if not ddt_obj: continue
            tipo = ddt_obj["tipo_doc"].get() if "tipo_doc" in ddt_obj else "Detallada"
            prod = ddt_obj["producto"].get()
            n_tanks = len(mapa[ddt_num])

            f_doc = ttk.LabelFrame(sf_doc, text=f"Doc: {ddt_num} ({tipo}) - {prod} - {n_tanks} tanques")
            f_doc.pack(fill="x", pady=4, padx=5)

            var_lab = tk.BooleanVar(value=True)
            var_doc = tk.BooleanVar(value=True)
            var_sal = tk.BooleanVar(value=True)
            ttk.Checkbutton(f_doc, text="Según Laboratorio", variable=var_lab).pack(anchor="w", padx=10)
            ttk.Checkbutton(f_doc, text="Según Documento", variable=var_doc).pack(anchor="w", padx=10)
            ttk.Checkbutton(f_doc, text="Según Salida", variable=var_sal).pack(anchor="w", padx=10)

            doc_vars[ddt_num] = True  # siempre incluido si tiene modos
            mode_vars[ddt_num] = {"lab": var_lab, "doc": var_doc, "sal": var_sal}

        if not mapa:
            tk.Label(sf_doc, text="(No hay documentos asignados a tanques)", fg="gray", font=("Arial", 9, "italic")).pack(anchor="w", padx=10, pady=5)

        # Botones en f_bot (ya creado arriba)
        def seleccionar_todos():
            var_global.set(True); var_general.set(True)
            for mvs in mode_vars.values():
                for v in mvs.values(): v.set(True)
        def deseleccionar_todos():
            var_global.set(False); var_general.set(False)
            for mvs in mode_vars.values():
                for v in mvs.values(): v.set(False)

        tk.Button(f_bot, text="Seleccionar Todo", font=("Arial", 10), bg="#5D6D7E", fg="white", command=seleccionar_todos).pack(side="left", padx=10, pady=10)
        tk.Button(f_bot, text="Deseleccionar Todo", font=("Arial", 9), bg="#5D6D7E", fg="white", command=deseleccionar_todos).pack(side="left", padx=5, pady=10)

        def generar():
            # Detectar REMO que NO se pueden resolver automáticamente
            # (cuando el número no tiene el código de aduana embebido)
            remo_decisions = {}
            for ddt_num in mapa:
                ddt_obj_chk = next((d for d in self.ddt_data if d["numero"].get() == ddt_num), None)
                if ddt_obj_chk:
                    info = self.inferir_tipo_operacion(ddt_obj_chk)
                    if info["necesita_pregunta"]:
                        # Solo llega aquí si no pudo determinarse automáticamente
                        dlg_remo = tk.Toplevel(dlg)
                        dlg_remo.title("REMO - Confirmar direccion")
                        dlg_remo.transient(dlg)
                        dlg_remo.grab_set()
                        dlg_remo.update_idletasks()
                        sw2, sh2 = dlg_remo.winfo_screenwidth(), dlg_remo.winfo_screenheight()
                        dlg_remo.geometry(f"540x260+{(sw2-540)//2}+{(sh2-260)//2}")
                        tk.Label(dlg_remo, text=f"REMO: {ddt_num}", font=("Arial", 8, "bold"), bg="#1B3A5C", fg="white").pack(fill="x", ipady=6)
                        tk.Label(dlg_remo, text="No se pudo determinar la direccion automaticamente.\nIndique si la operacion REMO es a la CARGA o DESCARGA:",
                                 font=("Arial", 10), wraplength=500, justify="center").pack(pady=10)
                        var_remo_d = tk.StringVar(value="remo_descarga")
                        f_remo_d = ttk.Frame(dlg_remo); f_remo_d.pack(pady=5)
                        tk.Radiobutton(f_remo_d, text="A la DESCARGA (aduana origen distinta - Art. 954 C.A.)",
                                       variable=var_remo_d, value="remo_descarga", font=("Arial", 10)).pack(anchor="w", padx=20)
                        tk.Radiobutton(f_remo_d, text="A la CARGA (misma aduana - Art. 959 C.A.)",
                                       variable=var_remo_d, value="remo_carga", font=("Arial", 10)).pack(anchor="w", padx=20)
                        def _ok_remo_d(key=ddt_num):
                            remo_decisions[key] = var_remo_d.get()
                            dlg_remo.destroy()
                        tk.Button(dlg_remo, text="Confirmar", bg="#2E7D32", fg="white",
                                  font=("Arial", 8, "bold"), command=_ok_remo_d).pack(pady=8)
                        dlg_remo.wait_window()
                        if ddt_num not in remo_decisions:
                            remo_decisions[ddt_num] = "remo_descarga"
            dlg.destroy()
            self._generar_reportes_seleccionados(var_global.get(), var_general.get(), mapa, mode_vars,
                                                  ctrl_doc=var_ctrl_doc.get(), ctrl_sal=var_ctrl_sal.get(),
                                                  ctrl_lab=var_ctrl_lab.get(), remo_decisions=remo_decisions)

        def _generar_con_tributos():
            generar()   # first calls generar() which destroys dlg

        tk.Button(f_bot, text="  GENERAR PDF", bg="#27AE60", fg="white", font=("Arial", 8, "bold"),
                  command=generar, cursor="hand2").pack(side="right", padx=20, pady=8, ipadx=14, ipady=5)
        tk.Button(f_bot, text="⚖ TRIBUTOS", bg="#7B1FA2", fg="white", font=("Arial", 8, "bold"),
                  command=lambda: self.dialogo_tributos(dlg)).pack(side="right", padx=6, pady=8)
        tk.Button(f_bot, text="Cancelar", font=("Arial", 9), bg="#E74C3C", fg="white",
                  command=dlg.destroy).pack(side="right", padx=5, pady=10)

    def _generar_reportes_seleccionados(self, inc_global, inc_general, mapa, mode_vars, ctrl_doc=True, ctrl_sal=False, ctrl_lab=False, remo_decisions=None):
        """Genera solo los reportes seleccionados."""
        target_dir = filedialog.askdirectory(title="Seleccione carpeta destino")
        if not target_dir: return
        errors = []
        all_tanks = self.lista_tanques + self.lista_carbonera

        clean_buque = self.clean_filename(self.get_var('car_buque').get())
        if not clean_buque: clean_buque = "Reporte"
        _fecha_str = datetime.now().strftime("%Y%m%d")
        unified_path = os.path.join(target_dir, f"Reporte_Completo_{clean_buque}_{_fecha_str}.pdf")

        # === PASO 1: PRE-CALCULAR CARGOS/DENUNCIAS ANTES DE ABRIR EL CANVAS ===
        # Determinar modo_comp desde ctrl flags
        if ctrl_lab:
            modo_forzado = "laboratorio"
        elif ctrl_sal:
            modo_forzado = "salida"
        else:
            modo_forzado = "documento"

        # Pre-calcular diferencias para todos los documentos
        cargos_pendientes = []
        for ddt_num, tanks in mapa.items():
            ddt_obj = next((d for d in self.ddt_data if d["numero"].get() == ddt_num), None)
            if not ddt_obj: continue
            try:
                # Kilos vacío: para líquidos se calculan acá igual que la planilla
                # (NETO = bruto − agua, × VCF × densidad según modo) para que el
                # cargo/denuncia coincida exactamente con el PDF. Para otros tipos
                # se usan los kv_* pre-calculados de la UI.
                _tm_cp = self.get_tipo_medio()
                _es_liq_cp = _tm_cp in ("BUQUE","BARCAZA","BUQUE QUIMIQUERO","DRAFT SURVEY",
                                        "TANQUE FIJO","TANQUE FLOTANTE","CAMION CISTERNA")
                dens_key_cp = "dens_lab" if modo_forzado == "laboratorio" else ("dens_salida" if modo_forzado == "salida" else "dens_doc")
                kv_suffix = "kv_lab" if modo_forzado == "laboratorio" else ("kv_sal" if modo_forzado == "salida" else "kv_doc")
                sum_kv_i = 0; sum_kv_f = 0
                for tk_name in tanks:
                    for etapa in ["inicial", "final"]:
                        if _es_liq_cp:
                            d_raw = self.get_var(f"{etapa}_{tk_name}_{dens_key_cp}").get()
                            if not d_raw: d_raw = self.get_var(f"{etapa}_{tk_name}_dens_lab").get()
                            d_v = self.parse_float(d_raw)
                            tbl_v = self.get_var(f"{etapa}_{tk_name}_tabla_vcf").get() or "54B (Combustibles)"
                            t_v = self.parse_float(self.get_var(f"{etapa}_{tk_name}_temp").get())
                            neto_v = self.interpolar_prod(etapa, tk_name) - self.interpolar_agua(etapa, tk_name)
                            vcf_v = self.calc_vcf(d_v, t_v, tbl_v) if d_v > 0 else 1.0
                            _dg = d_v / 1000.0 if d_v > 2.0 else d_v
                            val_kv = neto_v * vcf_v * _dg if _dg > 0 else 0.0
                        else:
                            raw_kv = self.get_var(f"{etapa}_{tk_name}_{kv_suffix}").get()
                            try: val_kv = float(str(raw_kv).replace(",","")) if raw_kv and str(raw_kv).replace(".","").replace("-","").replace(",","").isdigit() else 0.0
                            except: val_kv = 0.0
                        if etapa == "inicial": sum_kv_i += val_kv
                        else:                  sum_kv_f += val_kv
                dif_kv = sum_kv_i - sum_kv_f
                doc_k = self.parse_float(ddt_obj["kilos"].get())
                sal_k = sum(self.parse_float(s["kilos"].get()) for s in ddt_obj["salidas"]) if ddt_obj.get("salidas") else 0
                # LAB: kv_lab vs salidas | SAL/DOC: kv vs documento
                target_k = sal_k if (modo_forzado == "laboratorio" and sal_k > 0) else (doc_k if doc_k > 0 else 1)
                diff_k = dif_kv - target_k
                permil_k_val = (diff_k / target_k * 1000) if target_k != 0 else 0
                if abs(permil_k_val) > 6.0:
                    cargos_pendientes.append({
                        "ddt_obj": ddt_obj, "dif_kv": dif_kv,
                        "target_k": target_k, "modo": modo_forzado
                    })
            except Exception as _precalc_err:
                traceback.print_exc()
                messagebox.showerror("Error pre-calculo cargo", f"Error calculando diferencias para {ddt_num}:\n{_precalc_err}")

        # Resolver tipo de operación para cargos (REMO automático o remo_decisions)
        if remo_decisions is None: remo_decisions = {}
        for cp in cargos_pendientes:
            info_op = self.inferir_tipo_operacion(cp["ddt_obj"])
            if info_op["necesita_pregunta"]:
                num_doc = cp["ddt_obj"]["numero"].get()
                remo_tipo = remo_decisions.get(num_doc, "remo_descarga")
                info_op["tipo"] = remo_tipo
                if remo_tipo == "remo_carga":
                    info_op["art_principal"] = "Art. 959 del Código Aduanero"
                    info_op["art_inc"] = "Art. 959 inc. c) C.A."
                    info_op["descripcion"] = "TRANSFERENCIA DE COMBUSTIBLE A LA CARGA (REMO)"
                else:
                    info_op["descripcion"] = "TRANSFERENCIA DE COMBUSTIBLE A LA DESCARGA (REMO)"
            cp["tipo_operacion_info"] = info_op

        # === PASO 2: SI HAY CARGOS, PREGUNTAR FORMATO ===
        modo_cargo_export = "pdf"   # default: embebido en PDF
        if cargos_pendientes:
            _dlg_fmt = tk.Toplevel(self.root)
            _dlg_fmt.title("Formato de Informes de Cargo/Denuncia")
            _dlg_fmt.transient(self.root)
            _dlg_fmt.grab_set()
            _dlg_fmt.update_idletasks()
            _sw, _sh = _dlg_fmt.winfo_screenwidth(), _dlg_fmt.winfo_screenheight()
            _dlg_fmt.geometry(f"500x220+{(_sw-500)//2}+{(_sh-220)//2}")
            _n_inf = len(cargos_pendientes)
            _tipos = sum(1 for cp in cargos_pendientes if cp["target_k"] and abs((cp["dif_kv"]-cp["target_k"])/cp["target_k"]*100) >= 2.0)
            _tipos_str = []
            for cp in cargos_pendientes:
                _dk = cp["dif_kv"] - cp["target_k"]
                _pct = abs(_dk/cp["target_k"]*100) if cp["target_k"] else 0
                _tipos_str.append("Denuncia" if _pct >= 2.0 else "Cargo")
            _resumen = ", ".join(f"{cp['ddt_obj']['numero'].get()} ({t})" for cp, t in zip(cargos_pendientes, _tipos_str))
            tk.Label(_dlg_fmt, text=f"Se generarán {_n_inf} informe(s):", font=("Arial", 8, "bold"), bg="#1B3A5C", fg="white").pack(fill="x", ipady=6)
            tk.Label(_dlg_fmt, text=_resumen, font=("Arial", 9), wraplength=480, justify="center", fg="#333").pack(pady=6)
            tk.Label(_dlg_fmt, text="¿Cómo desea los informes de cargo/denuncia?", font=("Arial", 10)).pack(pady=(4,2))
            _var_fmt = tk.StringVar(value="pdf")
            _f_opts = ttk.Frame(_dlg_fmt); _f_opts.pack(pady=4)
            tk.Radiobutton(_f_opts, text="[PDF]  Embebidos al inicio del PDF unificado",
                           variable=_var_fmt, value="pdf", font=("Arial", 10)).pack(anchor="w", padx=30)
            tk.Radiobutton(_f_opts, text="[WORD] Documentos Word/LibreOffice (.docx) separados",
                           variable=_var_fmt, value="docx", font=("Arial", 10)).pack(anchor="w", padx=30)
            _fmt_ok = [False]
            def _fmt_aceptar():
                _fmt_ok[0] = True; _dlg_fmt.destroy()
            tk.Button(_dlg_fmt, text="Continuar →", bg="#27AE60", fg="white", font=("Arial", 8, "bold"),
                      command=_fmt_aceptar).pack(pady=8)
            _dlg_fmt.wait_window()
            if not _fmt_ok[0]: return  # usuario cerró el diálogo
            modo_cargo_export = _var_fmt.get()
            # ── Paso 2b: Configurar tributos ────────────────────────────
            if not self.dialogo_tributos():
                return  # usuario canceló

        # === PASO 3: CREAR CANVAS ===
        try:
            c = canvas.Canvas(unified_path, pagesize=A4)  # portrait para cargos primero
        except Exception as e:
            traceback.print_exc()
            messagebox.showerror("Error", f"No se pudo crear el PDF:\n{e}")
            return

        report_count = 0
        cargo_count = 0

        # === PASO 4a: CARGOS EN PDF (si modo pdf, al principio) ===
        if modo_cargo_export == "pdf":
            for cp in cargos_pendientes:
                info_op = cp.get("tipo_operacion_info", {})
                try:
                    self._generar_cargo_en_canvas(
                        c,
                        cp["ddt_obj"], cp["dif_kv"],
                        cp["target_k"],
                        ctrl_doc=ctrl_doc, ctrl_sal=ctrl_sal, ctrl_lab=ctrl_lab,
                        modo_comp_forzado=cp["modo"],
                        tipo_operacion=info_op.get("tipo","importacion"),
                        tipo_operacion_info=info_op
                    )
                    cargo_count += 1
                except Exception as _cargo_err:
                    traceback.print_exc()
                    messagebox.showerror("Error en Cargo/Denuncia",
                        f"Error generando cargo para {cp['ddt_obj']['numero'].get()}:\n{_cargo_err}")

        # === PASO 4b: CAMBIAR A LANDSCAPE Y GENERAR REPORTES ===
        # Cambiar tamaño de página para los reportes (landscape A4)
        c.setPageSize(landscape(A4))

        modes_map = [
            ("lab", "SEGÚN_LABORATORIO", "dens_lab"),
            ("doc", "SEGÚN_DOCUMENTO", "dens_doc"),
            ("sal", "SEGÚN_SALIDA", "dens_salida")
        ]

        if inc_global:
            try:
                self.generar_reporte_tecnico_global("DETALLE_TECNICO_GLOBAL", target_dir, shared_canvas=c)
                report_count += 1
            except Exception as e:
                traceback.print_exc()
                errors.append(f"Reporte Técnico Global: {str(e)}")

        if inc_general:
            try:
                self.generar_un_reporte("GENERAL", all_tanks, is_partial=False, output_folder=target_dir, shared_canvas=c)
                report_count += 1
            except Exception as e:
                traceback.print_exc()
                errors.append(f"Reporte General: {str(e)}")

        for ddt_num, tanks in mapa.items():
            ddt_obj = next((d for d in self.ddt_data if d["numero"].get() == ddt_num), None)
            if not ddt_obj: continue
            safe_doc_num = self.clean_filename(ddt_num)
            if not safe_doc_num: safe_doc_num = "SinNombre"
            mvars = mode_vars.get(ddt_num, {})
            for mode_key, suffix, density_key in modes_map:
                if mode_key in mvars and mvars[mode_key].get():
                    try:
                        self.generar_un_reporte(f"DOC_{safe_doc_num}_{suffix}", tanks, is_partial=True, ddt_obj=ddt_obj, output_folder=target_dir, density_mode_key=density_key, shared_canvas=c)
                        report_count += 1
                    except Exception as e:
                        traceback.print_exc()
                        errors.append(f"Reporte {ddt_num} ({suffix}): {str(e)}")



        # === PASO 5: GUARDAR PDF ===
        c.save()

        if errors:
            msg = "Algunos reportes fallaron:\n" + "\n".join(errors[:5])
            if len(errors) > 5: msg += "\n..."
            messagebox.showerror("Errores de Generación", msg)

        # === PASO 6: SI DOCX, GENERAR WORD PARA CADA CARGO ===
        docx_paths = []
        if modo_cargo_export == "docx" and cargos_pendientes:
            for cp in cargos_pendientes:
                info_op = cp.get("tipo_operacion_info", {})
                try:
                    docx_path = self._generar_cargo_docx(
                        cp["ddt_obj"], cp["dif_kv"], cp["target_k"],
                        ctrl_doc=ctrl_doc, ctrl_sal=ctrl_sal, ctrl_lab=ctrl_lab,
                        modo_comp_forzado=cp["modo"],
                        tipo_operacion=info_op.get("tipo", "importacion"),
                        tipo_operacion_info=info_op,
                        output_folder=target_dir
                    )
                    if docx_path:
                        docx_paths.append(docx_path)
                        cargo_count += 1
                except Exception as _docx_err:
                    traceback.print_exc()
                    messagebox.showerror("Error Word", f"Error generando .docx para {cp['ddt_obj']['numero'].get()}:\n{_docx_err}")

        total = report_count + cargo_count
        if total == 0:
            messagebox.showwarning("Atención", "No se generaron reportes.")
        else:
            if modo_cargo_export == "docx" and docx_paths:
                extra = f" + {len(docx_paths)} cargo(s)/denuncia(s) en Word"
            elif cargo_count > 0:
                extra = f" ({cargo_count} cargo(s)/denuncia(s) al inicio del PDF)"
            else:
                extra = " (sin cargos/denuncias)"
            messagebox.showinfo("Listo", f"PDF: {report_count} reporte(s){extra}\n{os.path.basename(unified_path)}")
            try:
                if platform.system() == 'Windows': os.startfile(unified_path)
                elif platform.system() == 'Darwin': subprocess.call(('open', unified_path))
                else: subprocess.call(('xdg-open', unified_path))
            except: pass
            # Abrir los .docx también
            for dp in docx_paths:
                try:
                    if platform.system() == 'Windows': os.startfile(dp)
                    elif platform.system() == 'Darwin': subprocess.call(('open', dp))
                    else: subprocess.call(('xdg-open', dp))
                except: pass

    def generar_todos_reportes(self):
        target_dir = filedialog.askdirectory(title="Seleccione carpeta destino")
        if not target_dir: return
        errors = []
        
        all_tanks = self.lista_tanques + self.lista_carbonera
        
        # --- CREAR UN SOLO PDF UNIFICADO ---
        clean_buque = self.clean_filename(self.get_var('car_buque').get())
        if not clean_buque: clean_buque = "Reporte"
        unified_path = os.path.join(target_dir, f"Reporte_Completo_{clean_buque}.pdf")
        
        try:
            c = canvas.Canvas(unified_path, pagesize=landscape(A4))
        except Exception as e:
            traceback.print_exc()
            messagebox.showerror("Error", f"No se pudo crear el PDF:\n{unified_path}\n\nError: {str(e)}")
            return
        
        report_count = 0
        
        # 1. REPORTE TECNICO GLOBAL
        try:
            self.generar_reporte_tecnico_global("DETALLE_TECNICO_GLOBAL", target_dir, shared_canvas=c)
            report_count += 1
        except Exception as e:
            traceback.print_exc()
            errors.append(f"Reporte Técnico Global: {str(e)}")
        
        # 2. REPORTE GENERAL (incluye carbonera)
        try:
            self.generar_un_reporte("GENERAL", all_tanks, is_partial=False, output_folder=target_dir, shared_canvas=c)
            report_count += 1
        except Exception as e:
            traceback.print_exc()
            errors.append(f"Reporte General: {str(e)}")
        
        # 3. REPORTES POR DOCUMENTO (incluye carbonera en el mapa)
        mapa = {} 
        for tk_name in all_tanks:
            d_ini = self.get_var(f"inicial_{tk_name}_ddt_assign").get()
            d_fin = self.get_var(f"final_{tk_name}_ddt_assign").get()
            if d_ini:
                if d_ini not in mapa: mapa[d_ini] = []
                if tk_name not in mapa[d_ini]: mapa[d_ini].append(tk_name)
            if d_fin and d_fin != d_ini:
                if d_fin not in mapa: mapa[d_fin] = []
                if tk_name not in mapa[d_fin]: mapa[d_fin].append(tk_name)
        modes = [
            ("SEGÚN_LABORATORIO", "dens_lab"),
            ("SEGÚN_DOCUMENTO", "dens_doc"),
            ("SEGÚN_SALIDA", "dens_salida")
        ]
        for ddt_num, tanks in mapa.items():
            ddt_obj = next((d for d in self.ddt_data if d["numero"].get() == ddt_num), None)
            if not ddt_obj: continue
            safe_doc_num = self.clean_filename(ddt_num)
            if not safe_doc_num: safe_doc_num = "SinNombre"
            for suffix, mode_key in modes:
                try:
                    self.generar_un_reporte(f"DOC_{safe_doc_num}_{suffix}", tanks, is_partial=True, ddt_obj=ddt_obj, output_folder=target_dir, density_mode_key=mode_key, shared_canvas=c)
                    report_count += 1
                except Exception as e: 
                    traceback.print_exc()
                    errors.append(f"Reporte Parcial {ddt_num} ({suffix}): {str(e)}")
        
        # --- GUARDAR EL PDF UNIFICADO ---
        c.save()
        
        if errors:
            msg = "Algunos reportes fallaron:\n" + "\n".join(errors[:5]) 
            if len(errors) > 5: msg += "\n..."
            messagebox.showerror("Errores de Generación", msg)
        
        if report_count == 0:
            messagebox.showwarning("Atención", "No se generaron reportes. Verifique que no tenga los archivos abiertos.")
        else:
            messagebox.showinfo("Listo", f"Se generaron {report_count} reportes en un solo PDF:\n{os.path.basename(unified_path)}")
            try:
                if platform.system() == 'Windows': os.startfile(unified_path)
                elif platform.system() == 'Darwin': subprocess.call(('open', unified_path))
                else: subprocess.call(('xdg-open', unified_path))
            except: pass

    @staticmethod
    def _pdf_polygon(c, pts, fill=1, stroke=0):
        """Draw a polygon on a ReportLab canvas from a flat list of coordinates [x0,y0,x1,y1,...]."""
        if len(pts) < 4:
            return
        p = c.beginPath()
        p.moveTo(pts[0], pts[1])
        for i in range(2, len(pts), 2):
            p.lineTo(pts[i], pts[i+1])
        p.close()
        c.drawPath(p, fill=fill, stroke=stroke)

    def _pdf_prod_color(self, tk_name, etapa_key):
        """Return ReportLab HexColor for product (same palette as TK, never blue)."""
        from reportlab.lib import colors
        rgb_fill, rgb_out = self.get_prod_color(tk_name, etapa_key)
        try:
            return colors.HexColor(rgb_fill), colors.HexColor(rgb_out)
        except:
            return colors.HexColor("#F0B429"), colors.HexColor("#D4880A")

    def _pdf_draw_vertical_tank(self, c, x, y, W, H, etapa_key, title):
        """ReportLab vertical tank — versión ultra-realista con perspectiva 3D cilíndrica y elipses."""
        from reportlab.lib import colors
        tank_names = self.lista_tanques or ["TK 1"]
        flotante = "FLOTANTE" in self.get_tipo_medio()
        n = max(len(tank_names), 1)
        pad = 10
        TK_W = max(24, (W - 2*pad) // n)
        TK_H = H * 0.58
        # Real storage tanks: diameter ≈ 80-100% of height
        # For single tank, use wider proportions; for many tanks, narrower
        if n == 1:
            MAX_TK_W = TK_H * 1.0  # 1:1 ratio for single tank
        elif n <= 3:
            MAX_TK_W = TK_H * 0.75
        else:
            MAX_TK_W = TK_H * 0.55
        TK_W = min(TK_W, int(MAX_TK_W))
        # Center tanks horizontally
        total_tanks_w = n * TK_W
        x_offset = (W - total_tanks_w) / 2
        y_base = y + H * 0.14
        y_top  = y_base + TK_H
        # Radio vertical de la elipse de perspectiva del cilindro
        EL_RY = max(3, TK_H * 0.052)
        BUND_H = TK_H * 0.12

        c.saveState()
        # ── Fondo neutro ─────────────────────────────────────────────────
        c.setFillColor(colors.HexColor("#F7F9FC")); c.setLineWidth(0)
        c.rect(x, y, W, H, fill=1, stroke=0)
        # Suelo
        c.setFillColor(colors.HexColor("#5A6370")); c.setLineWidth(0)
        c.rect(x, y, W, H*0.12, fill=1, stroke=0)

        # Dique de contención
        c.setFillColor(colors.HexColor("#C2C6C9")); c.setStrokeColor(colors.HexColor("#7F8C8D"))
        c.setLineWidth(1.2); c.rect(x+pad//2, y_base-BUND_H, W-pad, BUND_H, fill=1, stroke=1)
        c.setFillColor(colors.HexColor("#9EA5A8")); c.setLineWidth(0)
        c.rect(x+pad//2, y_base-BUND_H, W-pad, 2.5, fill=1, stroke=0)
        c.setStrokeColor(colors.HexColor("#A8ADB0")); c.setLineWidth(0.4)
        for li in range(0, int(W-pad), max(5, int(W-pad)//14)):
            c.line(x+pad//2+li, y_base-BUND_H+2, x+pad//2+li+4, y_base)

        # Título
        # Título dentro del área de dibujo con fondo para legibilidad
        c.setFont("Helvetica-Bold", 6.5)
        label = "TANQUE TECHO FLOTANTE" if flotante else "TANQUE TECHO FIJO"
        instalacion = self.get_var("car_buque").get() or ""
        title_txt = f"{label}  —  {title}" + (f"  ({instalacion})" if instalacion else "")
        _tw = c.stringWidth(title_txt, "Helvetica-Bold", 6.5)
        c.setFillColor(colors.HexColor("#F7F9FC")); c.setLineWidth(0)
        c.rect(x+W/2 - _tw/2 - 4, y+H-14-4, _tw+8, 12, fill=1, stroke=0)
        c.setFillColor(colors.HexColor("#1B3A5C"))
        c.drawCentredString(x+W/2, y+H-14, title_txt)

        for i, tn in enumerate(tank_names[:n]):
            tx = x + x_offset + i*TK_W; tw = TK_W - 5
            mid_x = tx + tw/2

            # Base de hormigón
            base_h = max(3, TK_H*0.04)
            base_x = tx - max(2, tw*0.09)
            base_w = tw + max(4, tw*0.18)
            c.setFillColor(colors.HexColor("#AAB2B5")); c.setStrokeColor(colors.HexColor("#8D9498"))
            c.setLineWidth(0.5); c.rect(base_x, y_base-base_h, base_w, base_h, fill=1, stroke=1)
            # Detalle base
            c.setStrokeColor(colors.HexColor("#9EA8B0")); c.setLineWidth(0.3); c.setDash([2,3])
            c.rect(base_x+3, y_base-base_h+2, base_w-6, base_h-4, fill=0, stroke=1)
            c.setDash()

            # ── Cuerpo cilíndrico: franjas verticales detalladas ──────────
            stripe_defs_pdf = [
                (0.00, 0.08, "#7E8A94"),
                (0.08, 0.20, "#96A2AC"),
                (0.20, 0.38, "#B2BEC8"),
                (0.38, 0.55, "#D2DAE0"),
                (0.55, 0.66, "#E0E8EC"),  # brillo máximo
                (0.66, 0.78, "#D8DFE3"),
                (0.78, 0.90, "#C4CDD4"),
                (0.90, 1.00, "#9EA8B2"),
            ]
            for s_from, s_to, sc_p in stripe_defs_pdf:
                c.setFillColor(colors.HexColor(sc_p)); c.setLineWidth(0)
                c.rect(tx + tw*s_from, y_base+EL_RY, tw*(s_to-s_from)+0.5, TK_H-EL_RY*2, fill=1, stroke=0)

            # ── Juntas de soldadura entre virolas (líneas horizontales) ───
            c.setStrokeColor(colors.HexColor("#6B7880")); c.setLineWidth(0.4)
            c.setDash([3, 2])
            for sc_frac in [0.15, 0.30, 0.45, 0.60, 0.75]:
                sc_y = y_base + TK_H * sc_frac
                c.line(tx, sc_y, tx + tw, sc_y)
            c.setDash()

            # ── Nivel de llenado ─────────────────────────────────────────
            vp, wp = self._get_fill_pct(tn, etapa_key)
            pnm = self.get_var(f"{etapa_key}_{tn}_prod_name").get() if etapa_key else ""
            vlit = self.get_var(f"{etapa_key}_{tn}_vol_nat_prod").get() if etapa_key else ""
            if vp > 0.02:
                fc, oc = self._pdf_prod_color(tn, etapa_key)
                fill_y = y_base + TK_H*wp
                fill_h = TK_H*(vp-wp)
                # Agua (si corresponde)
                if wp > 0:
                    c.setFillColor(colors.HexColor("#5DADE2")); c.setLineWidth(0)
                    c.rect(tx+2, y_base+EL_RY, tw-4, TK_H*wp-EL_RY, fill=1, stroke=0)
                    # Elipse del nivel de agua
                    c.setFillColor(colors.HexColor("#2E86C1"))
                    c.ellipse(tx+2, y_base+TK_H*wp-EL_RY, tx+tw-2, y_base+TK_H*wp+EL_RY, fill=1, stroke=0)
                # Producto
                c.setFillColor(fc); c.setLineWidth(0)
                c.rect(tx+2, fill_y+EL_RY, tw-4, fill_h-EL_RY*2, fill=1, stroke=0)
                # Reflejo superior del producto
                c.setFillColor(colors.HexColor("#FFFFFF")); c.setFillAlpha(0.30)
                c.rect(tx+2, fill_y+fill_h-fill_h*0.12, tw-4, fill_h*0.10, fill=1, stroke=0)
                c.setFillAlpha(1.0)
                # Elipse de la SUPERFICIE del producto (perspectiva)
                c.setFillColor(fc)
                c.ellipse(tx+2, fill_y+fill_h-EL_RY, tx+tw-2, fill_y+fill_h+EL_RY, fill=1, stroke=0)
                c.setStrokeColor(oc); c.setLineWidth(0.8)
                c.ellipse(tx+2, fill_y+fill_h-EL_RY, tx+tw-2, fill_y+fill_h+EL_RY, fill=0, stroke=1)
                # Porcentaje — color con contraste correcto
                fc_hex = self.get_prod_color(tn, etapa_key)[0]
                txt_col_pdf = colors.HexColor(self.contrast_text(fc_hex))
                c.setFillColor(txt_col_pdf)
                c.setFont("Helvetica-Bold", 6)
                c.drawCentredString(mid_x, fill_y + fill_h*0.45, f"{vp*100:.1f}%")
                if pnm:
                    c.setFont("Helvetica", 5); c.setFillColor(txt_col_pdf)
                    c.drawCentredString(mid_x, fill_y + fill_h*0.22, pnm[:12])

            # ── Elipse BASE del cilindro (perspectiva inferior) ───────────
            # La parte inferior de la elipse simula el fondo del cilindro visible
            c.setFillColor(colors.HexColor("#808D97")); c.setLineWidth(0)
            c.ellipse(tx, y_base-EL_RY, tx+tw, y_base+EL_RY, fill=1, stroke=0)
            # Línea de contorno de la elipse base
            c.setStrokeColor(colors.HexColor("#5D6D7E")); c.setLineWidth(1)
            c.ellipse(tx, y_base-EL_RY, tx+tw, y_base+EL_RY, fill=0, stroke=1)

            # ── Anillos de rigidización — virolas delgadas ────────────────
            for ri in [0.18, 0.36, 0.54, 0.72]:
                ry = y_base + TK_H * ri
                c.setFillColor(colors.HexColor("#9EA9B3")); c.setLineWidth(0)
                c.ellipse(tx, ry-1.2, tx+tw, ry+1.2, fill=1, stroke=0)
                c.setStrokeColor(colors.HexColor("#7F8C8D")); c.setLineWidth(0.5)
                c.ellipse(tx, ry-1.2, tx+tw, ry+1.2, fill=0, stroke=1)

            # ── Viento girder — anillo prominente techo fijo a 82% ────────
            if not flotante:
                wg_y = y_base + TK_H * 0.82
                c.setFillColor(colors.HexColor("#8C9BA5")); c.setLineWidth(0)
                c.ellipse(tx-2, wg_y-3.5, tx+tw+2, wg_y+3.5, fill=1, stroke=0)
                c.setStrokeColor(colors.HexColor("#5D6D7E")); c.setLineWidth(1.0)
                c.ellipse(tx-2, wg_y-3.5, tx+tw+2, wg_y+3.5, fill=0, stroke=1)
                # Orejetas del wind girder
                c.setFillColor(colors.HexColor("#8C9BA5")); c.setLineWidth(0)
                c.rect(tx-5, wg_y-2.5, 5, 5, fill=1, stroke=0)
                c.rect(tx+tw, wg_y-2.5, 5, 5, fill=1, stroke=0)

            # ── Techo con tapa elíptica superior ─────────────────────────
            if flotante:
                # ── FÍSICA CORRECTA DEL TECHO FLOTANTE ───────────────────────
                # Patas estándar ≈ 1.8m → float level ≈ 15% del tanque
                # Por debajo: techo apoyado en patas (posición fija)
                # Por encima: techo flota exactamente al nivel del líquido
                PATAS_FRAC = 0.15
                ponton_h = max(3, EL_RY*0.95)
                inner_h = TK_H - 2*EL_RY

                liq_y   = y_base + TK_H * vp
                patas_y = y_base + inner_h * PATAS_FRAC + EL_RY

                if vp <= PATAS_FRAC:
                    deck_y = patas_y   # apoyado en patas
                else:
                    deck_y = liq_y     # flotando en el líquido

                # ── Patas (siempre visibles, desde base del pontón hasta fondo) ──
                pata_base_y = deck_y - ponton_h
                c.setStrokeColor(colors.HexColor("#7F8C8D")); c.setLineWidth(1.2)
                for pi_frac in [0.15, 0.38, 0.62, 0.85]:
                    px = tx + tw * pi_frac
                    c.line(px, pata_base_y, px, y_base + EL_RY)
                    # Zapata (foot plate)
                    c.setFillColor(colors.HexColor("#95A5A6")); c.setLineWidth(0)
                    c.rect(px-2.5, y_base+EL_RY-1.5, 5, 3, fill=1, stroke=0)

                # ── Pontón perimetral ──────────────────────────────────────
                c.setFillColor(colors.HexColor("#5B7B8A"))
                c.setStrokeColor(colors.HexColor("#4A6270")); c.setLineWidth(1)
                c.ellipse(tx, deck_y-ponton_h, tx+tw, deck_y+ponton_h, fill=1, stroke=1)
                c.setFillColor(colors.HexColor("#6D92A1")); c.setLineWidth(0)
                c.ellipse(tx+ponton_h+2, deck_y-ponton_h+1.5, tx+tw-ponton_h-2, deck_y+ponton_h-1.5, fill=1, stroke=0)
                # Brillo del pontón
                c.setFillColor(colors.HexColor("#A8C4CF")); c.setLineWidth(0)
                c.ellipse(tx+ponton_h+4, deck_y-ponton_h+2, tx+tw*0.45, deck_y-ponton_h*0.2, fill=1, stroke=0)
                # Rim seal (sello perimetral) — elemento clave del techo flotante
                c.setStrokeColor(colors.HexColor("#4A5568")); c.setLineWidth(1.5); c.setDash([2,2])
                c.ellipse(tx-2, deck_y-ponton_h-3, tx+tw+2, deck_y+ponton_h-1, fill=0, stroke=1)
                c.setDash()
                # Cables guía
                c.setStrokeColor(colors.HexColor("#95A5A6")); c.setLineWidth(0.5); c.setDash([3,4])
                for cg_f in [0.22, 0.5, 0.78]:
                    cgx = tx + tw*cg_f
                    c.line(cgx, deck_y+ponton_h, cgx, y_base+TK_H)
                c.setDash()
                # ── Flecha de SONDAJE (datum→pontón) ────────────────────────
                _pdf_s_x = tx + tw*0.12
                _pdf_s_bot = y_base + EL_RY + 2
                _pdf_s_top = deck_y - ponton_h - 1
                if _pdf_s_top > _pdf_s_bot + 8:
                    c.setStrokeColor(colors.HexColor("#F4D03F"))
                    c.setFillColor(colors.HexColor("#F4D03F"))
                    c.setLineWidth(0.8)
                    c.setDash([2,3])
                    c.line(_pdf_s_x, _pdf_s_bot, _pdf_s_x, _pdf_s_top)
                    c.setDash()
                    # Flechas en los extremos
                    _arr = c.beginPath()
                    _arr.moveTo(_pdf_s_x-2, _pdf_s_top-4)
                    _arr.lineTo(_pdf_s_x, _pdf_s_top)
                    _arr.lineTo(_pdf_s_x+2, _pdf_s_top-4)
                    c.drawPath(_arr, fill=1, stroke=0)
                    _arr2 = c.beginPath()
                    _arr2.moveTo(_pdf_s_x-2, _pdf_s_bot+4)
                    _arr2.lineTo(_pdf_s_x, _pdf_s_bot)
                    _arr2.lineTo(_pdf_s_x+2, _pdf_s_bot+4)
                    c.drawPath(_arr2, fill=1, stroke=0)
                    # Placa datum en la base
                    c.setFillColor(colors.HexColor("#F4D03F"))
                    c.rect(_pdf_s_x-3, _pdf_s_bot-2, 6, 2, fill=1, stroke=0)
                    # Label "S" centrado
                    _mid_s = (_pdf_s_bot + _pdf_s_top) / 2
                    c.setFont("Helvetica-Bold", max(3, int(TK_H*0.04)))
                    c.setFillColor(colors.HexColor("#D4AC0D"))
                    c.drawCentredString(_pdf_s_x, _mid_s, "⌇")
                # Indicador de nivel lateral
                lv_x_pdf = tx + tw*0.88
                c.setStrokeColor(colors.HexColor("#E74C3C")); c.setLineWidth(1.2); c.setDash([3,3])
                c.line(lv_x_pdf, deck_y-ponton_h, lv_x_pdf, y_base)
                c.setDash()
                c.setFillColor(colors.HexColor("#E74C3C")); c.setLineWidth(0)
                c.rect(lv_x_pdf-2.5, deck_y-ponton_h-4, 5, 4, fill=1, stroke=0)
            else:
                # Techo cónico
                apex_y = y_base + TK_H + EL_RY + max(5, TK_H*0.09)
                # Cara iluminada del cono
                p = c.beginPath()
                p.moveTo(tx, y_base+TK_H); p.lineTo(mid_x, apex_y); p.lineTo(tx+tw*0.55, y_base+TK_H); p.close()
                c.setFillColor(colors.HexColor("#D2D9DE")); c.drawPath(p, fill=1, stroke=0)
                # Cara sombreada
                p2 = c.beginPath()
                p2.moveTo(tx+tw*0.45, y_base+TK_H); p2.lineTo(mid_x, apex_y); p2.lineTo(tx+tw, y_base+TK_H); p2.close()
                c.setFillColor(colors.HexColor("#A8B5B8")); c.drawPath(p2, fill=1, stroke=0)
                # Contorno cono
                c.setStrokeColor(colors.HexColor("#7A8896")); c.setLineWidth(1.2)
                c.line(tx, y_base+TK_H, mid_x, apex_y)
                c.line(tx+tw, y_base+TK_H, mid_x, apex_y)
                # Nervaduras
                c.setStrokeColor(colors.HexColor("#95A5A6")); c.setLineWidth(0.6)
                for ri2 in [0.3, 0.7]:
                    c.line(tx+tw*ri2, y_base+TK_H, mid_x, apex_y)
                # Tapa ELÍPTICA superior del cilindro (collar del techo — efecto 3D clave)
                c.setFillColor(colors.HexColor("#CAD2D7"))
                c.ellipse(tx, y_base+TK_H-EL_RY, tx+tw, y_base+TK_H+EL_RY, fill=1, stroke=0)
                c.setStrokeColor(colors.HexColor("#808B96")); c.setLineWidth(1.2)
                c.ellipse(tx, y_base+TK_H-EL_RY, tx+tw, y_base+TK_H+EL_RY, fill=0, stroke=1)
                # Brillo en la tapa
                c.setFillColor(colors.HexColor("#E2E8EC")); c.setLineWidth(0)
                c.ellipse(tx+tw*0.15, y_base+TK_H-EL_RY*0.5, tx+tw*0.55, y_base+TK_H+EL_RY*0.3, fill=1, stroke=0)

            # ── Tobera de venteo ──────────────────────────────────────────
            if not flotante:
                vnt_x = tx + tw*0.70
                vnt_base = y_base + TK_H + EL_RY
                c.setFillColor(colors.HexColor("#808B96")); c.setLineWidth(0)
                c.rect(vnt_x-2.5, vnt_base, 5, max(6, TK_H*0.07), fill=1, stroke=0)
                c.setFillColor(colors.HexColor("#4A5568"))
                c.rect(vnt_x-3, vnt_base+TK_H*0.07, 6, 2, fill=1, stroke=0)
                p3 = c.beginPath()
                p3.moveTo(vnt_x-5, vnt_base+TK_H*0.07); p3.lineTo(vnt_x, vnt_base+TK_H*0.10+5); p3.lineTo(vnt_x+5, vnt_base+TK_H*0.07); p3.close()
                c.setFillColor(colors.HexColor("#95A5A6")); c.drawPath(p3, fill=1, stroke=0)

            # ── Escalera cat ladder ───────────────────────────────────────
            esc_x = tx + tw + 3.5
            if esc_x < x + W - 4:
                c.setStrokeColor(colors.HexColor("#95A5A6")); c.setLineWidth(1)
                c.line(esc_x-1.5, y_base, esc_x-1.5, y_base+TK_H)
                c.line(esc_x+2.5, y_base, esc_x+2.5, y_base+TK_H)
                c.setLineWidth(0.5)
                sy2 = y_base
                step_h = max(4, TK_H/10)
                while sy2 < y_base+TK_H:
                    c.line(esc_x-2.5, sy2, esc_x+3.5, sy2)
                    sy2 += step_h
                # Plataforma en la cima
                c.setFillColor(colors.HexColor("#808B96")); c.setLineWidth(0)
                c.rect(esc_x-4, y_base+TK_H+EL_RY, 9, 2.5, fill=1, stroke=0)

            # ── Tubería base con válvula ──────────────────────────────────
            pipe_y = y_base - base_h - 2
            pipe_x = tx + tw*0.28
            c.setStrokeColor(colors.HexColor("#5D6D7E")); c.setLineWidth(2.5)
            c.line(pipe_x, y_base, pipe_x, pipe_y)
            c.line(pipe_x, pipe_y, tx - 9, pipe_y)
            c.setFillColor(colors.HexColor("#4A5568")); c.setLineWidth(0)
            c.rect(pipe_x-3, y_base-2, 6, 3, fill=1, stroke=0)
            # Válvula (mariposa)
            vv_y = pipe_y
            c.setFillColor(colors.HexColor("#2C3E50")); c.setStrokeColor(colors.HexColor("#1B2631")); c.setLineWidth(0.8)
            p4 = c.beginPath()
            p4.moveTo(pipe_x-4, vv_y-3.5); p4.lineTo(pipe_x+4, vv_y+3.5); p4.lineTo(pipe_x+4, vv_y-3.5); p4.lineTo(pipe_x-4, vv_y+3.5); p4.close()
            c.drawPath(p4, fill=1, stroke=1)
            c.setStrokeColor(colors.HexColor("#5D6D7E")); c.setLineWidth(0.8)
            c.line(pipe_x, vv_y-3.5, pipe_x, vv_y-8)
            c.circle(pipe_x, vv_y-9.5, 2.5, stroke=1, fill=0)
            # Tubería de retorno
            ret_x2 = tx + tw*0.72
            c.setStrokeColor(colors.HexColor("#5D6D7E")); c.setLineWidth(2)
            c.line(ret_x2, y_base, ret_x2, pipe_y-1)
            c.setFillColor(colors.HexColor("#4A5568")); c.setLineWidth(0)
            c.rect(ret_x2-3, y_base-2, 6, 3, fill=1, stroke=0)

            # ── Indicador de nivel lateral ────────────────────────────────
            c.setStrokeColor(colors.HexColor("#BDC3C7")); c.setLineWidth(0.8); c.setDash([1.5,2])
            c.line(tx-5, y_base, tx-5, y_base+TK_H)
            c.setDash()
            if vp > 0:
                lv_y = y_base + TK_H*vp
                c.setFillColor(colors.HexColor("#E74C3C")); c.setLineWidth(0)
                c.rect(tx-8, lv_y-2, 6, 4, fill=1, stroke=0)
            c.setStrokeColor(colors.HexColor("#5D6D7E")); c.setLineWidth(0.5)
            for mk in [0.2, 0.4, 0.6, 0.8]:
                my = y_base + TK_H*mk
                c.line(tx-7, my, tx-3, my)

            # ── Contorno final ────────────────────────────────────────────
            c.setFillColor(colors.white); c.setStrokeColor(colors.HexColor("#4A5568")); c.setLineWidth(1.8)
            c.rect(tx, y_base+EL_RY, tw, TK_H-EL_RY*2, fill=0, stroke=1)

            # ── Etiqueta ──────────────────────────────────────────────────
            c.setFillColor(colors.HexColor("#2C3E50")); c.setFont("Helvetica-Bold", 5.5)
            c.drawCentredString(mid_x, y_base - 9, tn[:10])
            if vlit:
                c.setFont("Helvetica", 4.5); c.setFillColor(colors.HexColor("#5D6D7E"))
                c.drawCentredString(mid_x, y_base - 15, f"{vlit} L")

        c.restoreState()

    def _pdf_draw_spheres(self, c, x, y, W, H, etapa_key, title):
        """ReportLab sphere drawing — versión premium con gradiente 3D."""
        from reportlab.lib import colors
        tank_names = self.lista_tanques or ["ESFERA 1"]
        n = max(len(tank_names), 1)
        instalacion = self.get_var("car_buque").get() or ""

        c.saveState()
        c.setFillColor(colors.HexColor("#F5F7FA")); c.setStrokeColor(colors.HexColor("#1B3A5C")); c.setLineWidth(1.5)
        c.rect(x, y, W, H, fill=1, stroke=1)
        c.setFillColor(colors.HexColor("#1B3A5C")); c.setFont("Helvetica-Bold", min(8, max(6, H*0.04)))
        title_txt = f"ESFERAS DE GAS - {title}" + (f" ({instalacion})" if instalacion else "")
        max_chars = int(W / 4.5)
        if len(title_txt) > max_chars:
            title_txt = title_txt[:max_chars-3] + "..."
        c.drawCentredString(x+W/2, y+H-10, title_txt)

        # Suelo
        c.setFillColor(colors.HexColor("#CCD1D9")); c.setLineWidth(0)
        c.rect(x+1, y+2, W-2, H*0.07, fill=1, stroke=0)

        sph_zone = W / n; ground_y = y + H*0.12
        for i, tn in enumerate(tank_names[:n]):
            cx_s = x + i*sph_zone + sph_zone/2
            # Cap sphere radius: max 22% of H, max 35% of zone, hard max 65pt
            sph_r = min(H*0.22, sph_zone*0.35, 65)
            # Center sphere vertically between ground and top
            cy_s = ground_y + (y + H - 18 - ground_y) * 0.55
            lsp = sph_r*0.68; lh = sph_r*0.65

            # Patas (2 delanteras, 2 traseras)
            c.setStrokeColor(colors.HexColor("#5D6D7E")); c.setLineWidth(max(1.5, sph_r*0.07))
            c.line(cx_s-lsp*0.65, cy_s+sph_r*0.78, cx_s-lsp*0.65, ground_y)
            c.line(cx_s+lsp*0.65, cy_s+sph_r*0.78, cx_s+lsp*0.65, ground_y)
            c.setLineWidth(max(2, sph_r*0.09))
            c.line(cx_s-lsp, cy_s+sph_r*0.82, cx_s-lsp, ground_y)
            c.line(cx_s+lsp, cy_s+sph_r*0.82, cx_s+lsp, ground_y)
            # Anillo base
            c.setFillColor(colors.HexColor("#4A5568")); c.setLineWidth(0)
            c.ellipse(cx_s-lsp-4, ground_y-3, cx_s+lsp+4, ground_y+2, fill=1, stroke=0)
            # Arriostramiento
            c.setStrokeColor(colors.HexColor("#7F8C8D")); c.setLineWidth(0.8)
            c.setDash([4,3])
            c.line(cx_s-lsp, cy_s+sph_r*0.82, cx_s+lsp, ground_y)
            c.line(cx_s+lsp, cy_s+sph_r*0.82, cx_s-lsp, ground_y)
            c.setDash()
            # Anillo horizontal
            mid_leg_y = cy_s + sph_r*0.60
            c.setStrokeColor(colors.HexColor("#5D6D7E")); c.setLineWidth(1.5)
            c.line(cx_s-lsp-2, mid_leg_y, cx_s+lsp+2, mid_leg_y)

            # Gradiente esfera (capas concéntricas — gris-plata industrial, sin azules)
            sphere_gradient = [
                ("#2C3E50", 1.00), ("#3D5166", 0.92), ("#4A6174", 0.83),
                ("#5D7585", 0.74), ("#7B8D9A", 0.64), ("#9EADB7", 0.53),
                ("#C4CDD3", 0.42), ("#E0E6E9", 0.30),
            ]
            for sg_col, sg_frac in sphere_gradient:
                sr = sph_r * sg_frac
                offset_x = int(sph_r * (1-sg_frac) * 0.4)
                offset_y = int(sph_r * (1-sg_frac) * 0.5)
                c.setFillColor(colors.HexColor(sg_col)); c.setLineWidth(0)
                c.circle(cx_s + offset_x*0.5, cy_s - offset_y*0.5, sr, fill=1, stroke=0)
            c.setFillColor(colors.HexColor("#1A4F6E")); c.setLineWidth(0); c.setStrokeColor(colors.HexColor("#1A4F6E")); c.setLineWidth(2)
            c.circle(cx_s, cy_s, sph_r, fill=0, stroke=1)

            # Llenado
            try:
                vol = self.parse_float(self.get_var(f"{etapa_key}_{tn}_vol_nat_prod").get() or
                                       self.get_var(f"{etapa_key}_{tn}_vol_liq").get() or "0")
                cap = self.parse_float(self.get_var(f"{etapa_key}_{tn}_alt_ref").get() or "1")
                vp = min(max(vol/(cap if cap>0 else 1), 0), 1)
            except: vp = 0.0
            if vp > 0.02:
                fc, oc = self._pdf_prod_color(tn, etapa_key)
                fill_h = sph_r * 2 * vp
                fill_bot = cy_s - sph_r
                fill_top = fill_bot + fill_h
                # Clip al contorno circular de la esfera
                c.saveState()
                clip_path = c.beginPath()
                clip_path.circle(cx_s, cy_s, sph_r)
                c.clipPath(clip_path, stroke=0)
                c.setFillColor(fc); c.setLineWidth(0)
                c.rect(cx_s-sph_r, fill_bot, sph_r*2, fill_h, fill=1, stroke=0)
                c.restoreState()
                c.setStrokeColor(colors.HexColor("#1A4F6E")); c.setLineWidth(2)
                c.circle(cx_s, cy_s, sph_r, fill=0, stroke=1)
                c.setStrokeColor(oc); c.setLineWidth(1); c.setDash([4,3])
                c.line(cx_s-sph_r+2, fill_top, cx_s+sph_r-2, fill_top); c.setDash()
                c.setFillColor(colors.white); c.setFont("Helvetica-Bold", max(5, int(sph_r*0.25)))
                c.drawCentredString(cx_s, cy_s, f"{vp*100:.0f}%")

            # Toberas cima (3 nozzle pipes on top)
            c.setFillColor(colors.HexColor("#4A5568")); c.setLineWidth(0)
            for nxi in [-sph_r*0.3, 0, sph_r*0.3]:
                c.rect(cx_s+nxi-2, cy_s+sph_r, 4, sph_r*0.18, fill=1, stroke=0)

            # Top access platform
            plat_y = cy_s + sph_r + sph_r*0.18 + 2
            plat_hw = sph_r * 0.5
            c.setFillColor(colors.HexColor("#4A5568")); c.setLineWidth(0)
            c.rect(cx_s - plat_hw, plat_y, plat_hw*2, 2, fill=1, stroke=0)

            # Handrail posts (2 thin vertical lines rising from platform ends)
            c.setStrokeColor(colors.HexColor("#4A5568")); c.setLineWidth(0.75)
            c.line(cx_s - plat_hw + 1, plat_y + 2, cx_s - plat_hw + 1, plat_y + 5)
            c.line(cx_s + plat_hw - 1, plat_y + 2, cx_s + plat_hw - 1, plat_y + 5)

            # Central access trunk (thin dashed line from platform down through sphere center to bottom)
            c.setStrokeColor(colors.HexColor("#4A5568")); c.setLineWidth(0.5); c.setDash([3, 2])
            c.line(cx_s, plat_y, cx_s, cy_s - sph_r)
            c.setDash()

            # Etiqueta
            c.setFillColor(colors.HexColor("#1B3A5C")); c.setFont("Helvetica-Bold", max(4, min(7, int(sph_r*0.15))))
            c.drawCentredString(cx_s, ground_y-6, tn[:12])
        c.restoreState()

    def _pdf_draw_liquid_truck(self, c, x, y, W, H, etapa_key, title):
        """ReportLab cistern truck — versión premium con cabina, ruedas y detalles industriales."""
        from reportlab.lib import colors
        import math
        tank_names = self.lista_tanques or ["TK 1"]
        n = max(len(tank_names), 1)
        pat = self.get_var("car_patente").get() or ""

        c.saveState()
        # Fondo neutro
        c.setFillColor(colors.HexColor("#F5F7FA")); c.setStrokeColor(colors.HexColor("#5D6D7E")); c.setLineWidth(1.5)
        c.rect(x, y, W, H, fill=1, stroke=1)
        # Suelo simple
        c.setFillColor(colors.HexColor("#808B96")); c.setLineWidth(0)
        c.rect(x+1, y+2, W-2, H*0.10, fill=1, stroke=0)

        c.setFillColor(colors.HexColor("#1B3A5C")); c.setFont("Helvetica-Bold", min(8, max(6, H*0.04)))
        hdr = f"CAMION CISTERNA - {title}" + (f" | Patente: {pat}" if pat else "")
        max_chars = int(W / 4.5)
        if len(hdr) > max_chars:
            hdr = hdr[:max_chars-3] + "..."
        c.drawCentredString(x+W/2, y+H-10, hdr)

        # Proporciones
        AXLE_R   = max(7, H*0.085)
        GND_Y    = y + H*0.12 + AXLE_R*2   # nivel de suelo (Y en ReportLab crece hacia arriba)
        CIS_BOT  = GND_Y + AXLE_R*0.3
        CIS_H    = H * 0.40
        CIS_TOP  = CIS_BOT + CIS_H
        PAD_L    = W * 0.03
        CAB_W    = W * 0.17
        CAB_X    = x + PAD_L
        CIS_X    = CAB_X + CAB_W + W*0.01
        CIS_W    = W - PAD_L - CAB_W - W*0.01 - W*0.03
        COMP_W   = CIS_W / n
        # Dome radius capped: no wider than 18% of compartment, and max 40% of cistern height
        DOME_R   = min(CIS_H * 0.40, COMP_W * 0.18)
        ch_h     = H * 0.04

        # Chasis
        c.setFillColor(colors.HexColor("#4A5568")); c.setLineWidth(0)
        c.rect(CAB_X+CAB_W*0.3, CIS_BOT-ch_h, CIS_W+CIS_X-CAB_X-CAB_W*0.3, ch_h, fill=1, stroke=0)

        # Compartimentos
        PROD_COLS = [
            "#C0392B","#E67E22","#27AE60","#D4AC0D","#784212","#2471A3","#8E44AD","#E74C3C",
        ]
        for i, tn in enumerate(tank_names[:n]):
            cx2 = CIS_X + i*COMP_W; cw2 = COMP_W
            is_first = (i==0); is_last = (i==n-1)
            bx1 = cx2 + (DOME_R if is_first else 0)
            bx2 = cx2 + cw2 - (DOME_R if is_last else 0)

            # Gradiente acero
            STRIPS = ["#D5D8DC","#CDD4D8","#C5CDD2","#BFC8CC","#BAC3C8","#D2D8DC"]
            sh = CIS_H / len(STRIPS)
            for si, sc in enumerate(STRIPS):
                c.setFillColor(colors.HexColor(sc)); c.setLineWidth(0)
                c.rect(bx1, CIS_BOT+si*sh, bx2-bx1, sh+1, fill=1, stroke=0)
            c.setFillColor(colors.white); c.setStrokeColor(colors.HexColor("#7F8C8D")); c.setLineWidth(1.5)
            c.rect(bx1, CIS_BOT, bx2-bx1, CIS_H, fill=0, stroke=1)

            # Cabezas esféricas
            if is_first:
                for ki, kc in enumerate(["#A9B2BC","#B8C4CC","#CDD4D8","#D5DCE0"]):
                    mg = ki*1.2
                    c.setFillColor(colors.HexColor(kc)); c.setLineWidth(0)
                    c.ellipse(cx2+mg, CIS_BOT+mg, cx2+2*DOME_R-mg, CIS_BOT+CIS_H-mg, fill=1, stroke=0)
                c.setFillColor(colors.white); c.setStrokeColor(colors.HexColor("#7F8C8D")); c.setLineWidth(1.5)
                c.ellipse(cx2, CIS_BOT, cx2+2*DOME_R, CIS_BOT+CIS_H, fill=0, stroke=1)
            if is_last:
                for ki, kc in enumerate(["#D5DCE0","#CDD4D8","#B8C4CC","#A9B2BC"]):
                    mg = ki*1.2
                    c.setFillColor(colors.HexColor(kc)); c.setLineWidth(0)
                    c.ellipse(cx2+cw2-2*DOME_R+mg, CIS_BOT+mg, cx2+cw2-mg, CIS_BOT+CIS_H-mg, fill=1, stroke=0)
                c.setFillColor(colors.white); c.setStrokeColor(colors.HexColor("#7F8C8D")); c.setLineWidth(1.5)
                c.ellipse(cx2+cw2-2*DOME_R, CIS_BOT, cx2+cw2, CIS_BOT+CIS_H, fill=0, stroke=1)

            # Llenado
            vp, wp = self._get_fill_pct(tn, etapa_key)
            pnm = self.get_var(f"{etapa_key}_{tn}_prod_name").get() if etapa_key else ""
            ci_c = abs(hash(pnm)) % len(PROD_COLS) if pnm else i % len(PROD_COLS)
            prod_col = colors.HexColor(PROD_COLS[ci_c])
            if vp > 0.02:
                fill_y = CIS_BOT; fill_h2 = CIS_H * vp
                # Fill ONLY the body rect area (between domes) to avoid clip bleeding
                # Agua
                if wp > 0:
                    c.setFillColor(colors.HexColor("#5DADE2")); c.setLineWidth(0)
                    c.rect(bx1+1, CIS_BOT+1, max(1, bx2-bx1-2), CIS_H*wp-1, fill=1, stroke=0)
                    fill_y = CIS_BOT + CIS_H*wp; fill_h2 = CIS_H*(vp-wp)
                # Producto (body area only)
                c.setFillColor(prod_col); c.setLineWidth(0)
                c.rect(bx1+1, fill_y, max(1, bx2-bx1-2), fill_h2, fill=1, stroke=0)
                # Reflejo
                c.setFillColor(colors.Color(1,1,1,alpha=0.35))
                c.rect(bx1+1, fill_y+fill_h2*0.85, max(1, bx2-bx1-2), fill_h2*0.10, fill=1, stroke=0)
                # Recontorno body
                c.setFillColor(colors.white); c.setStrokeColor(colors.HexColor("#7F8C8D")); c.setLineWidth(1.5)
                c.rect(bx1, CIS_BOT, bx2-bx1, CIS_H, fill=0, stroke=1)
                # Recontorno domes
                if is_first:
                    c.setFillColor(colors.white); c.setStrokeColor(colors.HexColor("#7F8C8D")); c.setLineWidth(1.5)
                    c.ellipse(cx2, CIS_BOT, cx2+2*DOME_R, CIS_BOT+CIS_H, fill=0, stroke=1)
                if is_last:
                    c.setFillColor(colors.white); c.setStrokeColor(colors.HexColor("#7F8C8D")); c.setLineWidth(1.5)
                    c.ellipse(cx2+cw2-2*DOME_R, CIS_BOT, cx2+cw2, CIS_BOT+CIS_H, fill=0, stroke=1)
                c.setFillColor(colors.white if vp>0.35 else colors.HexColor("#1B3A5C"))
                c.setFont("Helvetica-Bold", max(4.5, min(6.5, COMP_W*0.12)))
                c.drawCentredString((bx1+bx2)/2, CIS_BOT+CIS_H*vp*0.45, f"{vp*100:.0f}%")

            # Divisor entre compartimentos
            if not is_last:
                c.setFillColor(colors.HexColor("#5D6D7E")); c.setLineWidth(0)
                c.rect(bx2-1.5, CIS_BOT, 3, CIS_H, fill=1, stroke=0)

            # Boca de hombre
            mh_r = max(4, COMP_W*0.10); mh_x = (bx1+bx2)/2
            c.setFillColor(colors.HexColor("#B2BEC3")); c.setStrokeColor(colors.HexColor("#636E72")); c.setLineWidth(1)
            c.circle(mh_x, CIS_TOP, mh_r, fill=1, stroke=1)
            c.setFillColor(colors.HexColor("#C0C8CC")); c.setLineWidth(0)
            c.circle(mh_x, CIS_TOP, mh_r*0.6, fill=1, stroke=0)
            # PRV
            c.setFillColor(colors.HexColor("#E74C3C")); c.setLineWidth(0)
            c.rect(mh_x+mh_r+2, CIS_TOP-3, 4, max(6, H*0.05), fill=1, stroke=0)

            # Etiqueta compartimento
            short = tn.replace("COMPARTIMENTO ","C.").replace("TK ","").strip()[:5]
            c.setFillColor(colors.HexColor("#2C3E50")); c.setFont("Helvetica-Bold", max(4, min(5.5, COMP_W*0.10)))
            c.drawCentredString((bx1+bx2)/2, CIS_TOP+4, short)
            if pnm:
                c.setFont("Helvetica", 4); c.setFillColor(colors.HexColor("#5D6D7E"))
                c.drawCentredString((bx1+bx2)/2, CIS_BOT+CIS_H*0.08, pnm[:10])

        # Tubería inferior (manifold)
        c.setStrokeColor(colors.HexColor("#4A5568")); c.setLineWidth(3)
        c.line(CIS_X+DOME_R, CIS_BOT-ch_h*0.5, CIS_X+CIS_W-DOME_R, CIS_BOT-ch_h*0.5)

        # ── CABINA ──────────────────────────────────────────────────────────
        CAB_BOT  = CIS_BOT; CAB_H = CIS_H + H*0.15; CAB_TOP = CAB_BOT + CAB_H
        slope    = CAB_W * 0.14

        # Cuerpo cabina
        c.setFillColor(colors.HexColor("#4A5568")); c.setLineWidth(0)
        self._pdf_polygon(c,[CAB_X, CAB_BOT, CAB_X+CAB_W, CAB_BOT, CAB_X+CAB_W, CAB_BOT+CAB_H*0.82,
                   CAB_X+CAB_W-slope, CAB_TOP, CAB_X+slope, CAB_TOP, CAB_X, CAB_BOT+CAB_H*0.82],
                  fill=1)
        c.setFillColor(colors.white); c.setStrokeColor(colors.HexColor("#2C3E50")); c.setLineWidth(1.5)
        self._pdf_polygon(c,[CAB_X, CAB_BOT, CAB_X+CAB_W, CAB_BOT, CAB_X+CAB_W, CAB_BOT+CAB_H*0.82,
                   CAB_X+CAB_W-slope, CAB_TOP, CAB_X+slope, CAB_TOP, CAB_X, CAB_BOT+CAB_H*0.82],
                  fill=0)

        # Parabrisas
        wm = CAB_W*0.13; wh = CAB_H*0.32; wy = CAB_BOT+CAB_H*0.60
        c.setFillColor(colors.HexColor("#AED6F1")); c.setStrokeColor(colors.HexColor("#2C3E50")); c.setLineWidth(1)
        c.rect(CAB_X+wm, wy, CAB_W-2*wm, wh, fill=1, stroke=1)
        # División
        c.setLineWidth(1); c.line(CAB_X+CAB_W/2, wy, CAB_X+CAB_W/2, wy+wh)
        # Reflejo parabrisas
        c.setFillColor(colors.Color(1,1,1,alpha=0.5)); c.setLineWidth(0)
        _pt2 = c.beginPath(); _pt2.moveTo(CAB_X+wm+1, wy+wh-1); _pt2.lineTo(CAB_X+wm+CAB_W*0.28, wy+wh-1); _pt2.lineTo(CAB_X+wm+1, wy+wh*0.45); _pt2.close()
        c.drawPath(_pt2, fill=1, stroke=0)

        # Parrilla
        gr_h = CAB_H*0.22; gr_x = CAB_X-CAB_W*0.22; gr_y = CAB_BOT+gr_h*0.15
        c.setFillColor(colors.HexColor("#2C3E50")); c.setLineWidth(0)
        c.rect(gr_x, gr_y, CAB_W*0.22, gr_h, fill=1, stroke=0)
        for li in range(4):
            gy2 = gr_y + li*gr_h/4
            c.setFillColor(colors.HexColor("#4A5568")); c.rect(gr_x+1, gy2+1, CAB_W*0.22-2, gr_h/4-2, fill=1, stroke=0)
        # Faro
        c.setFillColor(colors.HexColor("#F9E79F")); c.setStrokeColor(colors.HexColor("#D4AC0D")); c.setLineWidth(0.8)
        hl_r = gr_h*0.3
        c.circle(gr_x+CAB_W*0.11, gr_y+gr_h-hl_r-2, hl_r, fill=1, stroke=1)
        # Espejo lateral
        c.setFillColor(colors.HexColor("#5D6D7E")); c.setLineWidth(0)
        c.rect(CAB_X+CAB_W+2, wy+wh*0.2, CAB_W*0.09, wh*0.33, fill=1, stroke=0)
        # Caño de escape (clamped to stay within drawing area)
        ex_x = CAB_X+CAB_W-CAB_W*0.09; ex_h = CAB_H*0.45
        ex_top = min(CAB_TOP + ex_h, y+H-15)
        c.setFillColor(colors.HexColor("#4A5568")); c.rect(ex_x-3, CAB_TOP, 6, ex_top-CAB_TOP, fill=1, stroke=0)
        c.setFillColor(colors.HexColor("#3D4B56")); c.circle(ex_x, ex_top, 5, fill=1, stroke=0)

        # ── RUEDAS ──────────────────────────────────────────────────────────
        AXLE_Y   = GND_Y + AXLE_R
        wheel_xs = [CAB_X+CAB_W*0.62]
        rc2 = CIS_X+CIS_W*0.72
        wheel_xs += [rc2-AXLE_R*0.4, rc2+AXLE_R*0.4]
        if CIS_W > W*0.4:
            wheel_xs.insert(1, CIS_X+CIS_W*0.44)
        for wx in wheel_xs:
            # Neumático
            c.setFillColor(colors.HexColor("#1B2631")); c.setStrokeColor(colors.HexColor("#0E1A27")); c.setLineWidth(1)
            c.circle(wx, AXLE_Y, AXLE_R, fill=1, stroke=1)
            # Llanta
            rim_r = AXLE_R*0.58
            c.setFillColor(colors.HexColor("#7F8C8D")); c.setStrokeColor(colors.HexColor("#5D6D7E")); c.setLineWidth(0.8)
            c.circle(wx, AXLE_Y, rim_r, fill=1, stroke=1)
            # Rayos
            c.setStrokeColor(colors.HexColor("#5D6D7E")); c.setLineWidth(0.8)
            for ang_d in [0, 60, 120, 180, 240, 300]:
                ar = math.radians(ang_d)
                c.line(wx+math.cos(ar)*rim_r*0.25, AXLE_Y+math.sin(ar)*rim_r*0.25,
                       wx+math.cos(ar)*rim_r*0.9,  AXLE_Y+math.sin(ar)*rim_r*0.9)
            # Centro
            c.setFillColor(colors.HexColor("#4A5568")); c.setLineWidth(0)
            c.circle(wx, AXLE_Y, AXLE_R*0.12, fill=1, stroke=0)
            # Guardabarro
            c.setFillColor(colors.white); c.setStrokeColor(colors.HexColor("#5D6D7E")); c.setLineWidth(1)
            c.arc(wx-AXLE_R-2, AXLE_Y-AXLE_R-2, wx+AXLE_R+2, AXLE_Y+AXLE_R+2, startAng=30, extent=120)

        # ── HAZMAT PLACARD (diamond) ─────────────────────────────────────────
        plaq_cx = CIS_X + CIS_W - DOME_R - 10  # near right end of cistern body
        plaq_cy = (CIS_BOT + CIS_TOP) / 2      # vertically centred on tank
        plaq_s  = 8.5                           # half-diagonal (~12×12 pt visible)
        c.saveState()
        c.setFillColor(colors.HexColor("#E74C3C"))
        c.setStrokeColor(colors.white)
        c.setLineWidth(1.2)
        _ph = c.beginPath()
        _ph.moveTo(plaq_cx,          plaq_cy + plaq_s)  # top
        _ph.lineTo(plaq_cx + plaq_s, plaq_cy)            # right
        _ph.lineTo(plaq_cx,          plaq_cy - plaq_s)  # bottom
        _ph.lineTo(plaq_cx - plaq_s, plaq_cy)            # left
        _ph.close()
        c.drawPath(_ph, fill=1, stroke=1)
        c.setFillColor(colors.white)
        c.setFont("Helvetica-Bold", 7)
        c.drawCentredString(plaq_cx, plaq_cy - 2.5, "3")
        c.restoreState()
        # ─────────────────────────────────────────────────────────────────────

        c.restoreState()

    def _pdf_draw_pressure_truck(self, c, x, y, W, H, etapa_key, title):
        """ReportLab pressure vessel truck GLP — recipiente toriesférico premium."""
        from reportlab.lib import colors
        import math
        tank_names = self.lista_tanques or ["TK 1"]
        n = max(len(tank_names), 1)
        pat = self.get_var("car_patente").get() or ""

        c.saveState()
        c.setFillColor(colors.HexColor("#F5F7FA")); c.setStrokeColor(colors.HexColor("#D4AC0D")); c.setLineWidth(2)
        c.rect(x, y, W, H, fill=1, stroke=1)
        # Suelo simple
        c.setFillColor(colors.HexColor("#808B96")); c.setLineWidth(0)
        c.rect(x+1, y+2, W-2, H*0.10, fill=1, stroke=0)
        c.setFillColor(colors.HexColor("#784212")); c.setFont("Helvetica-Bold", min(8, max(6, H*0.04)))
        hdr = f"CAMION GAS/GLP - {title}" + (f" | Patente: {pat}" if pat else "")
        max_chars = int(W / 4.5)
        if len(hdr) > max_chars:
            hdr = hdr[:max_chars-3] + "..."
        c.drawCentredString(x+W/2, y+H-10, hdr)

        AXLE_R  = max(7, H*0.085); GND_Y = y+H*0.12+AXLE_R*2
        CIS_BOT = GND_Y+AXLE_R*0.3; CIS_H = H*0.40; CIS_TOP = CIS_BOT+CIS_H
        PAD_L   = W*0.03; CAB_W = W*0.17; CAB_X = x+PAD_L
        CIS_X   = CAB_X+CAB_W+W*0.01; CIS_W = W-PAD_L-CAB_W-W*0.01-W*0.03
        COMP_W  = CIS_W/n
        # Cap dome radius: max 22% of cistern height and 15% of compartment width, hard max 25pt
        DOME_R  = min(CIS_H*0.22, COMP_W*0.15, 25)
        ch_h = H*0.04

        c.setFillColor(colors.HexColor("#6E4B00")); c.setLineWidth(0)
        c.rect(CAB_X+CAB_W*0.3, CIS_BOT-ch_h, CIS_X+CIS_W-CAB_X-CAB_W*0.3, ch_h, fill=1, stroke=0)

        for i, tn in enumerate(tank_names[:n]):
            cx2 = CIS_X+i*COMP_W; cw2 = COMP_W
            is_first=(i==0); is_last=(i==n-1)
            bx1 = cx2+(DOME_R if is_first else 0); bx2 = cx2+cw2-(DOME_R if is_last else 0)

            # Gradiente dorado (acero de alta presión)
            STRIPS = ["#FEF9E7","#FDEBD0","#FDEBD0","#FCEBD0","#FAE5C0","#F5DBA8"]
            sh = CIS_H/len(STRIPS)
            for si, sc in enumerate(STRIPS):
                c.setFillColor(colors.HexColor(sc)); c.setLineWidth(0)
                c.rect(bx1, CIS_BOT+si*sh, bx2-bx1, sh+1, fill=1, stroke=0)
            c.setFillColor(colors.white); c.setStrokeColor(colors.HexColor("#D4AC0D")); c.setLineWidth(2)
            c.rect(bx1, CIS_BOT, bx2-bx1, CIS_H, fill=0, stroke=1)

            # Cabezas hemisféricas doradas
            for is_side, start_x in [(is_first, cx2), (is_last, cx2+cw2-2*DOME_R)]:
                if not is_side: continue
                hemi_cols = ["#B8860B","#C9960C","#D4AC0D","#E8C44B","#F0D060","#FEF9E7"]
                if not is_first: hemi_cols = list(reversed(hemi_cols))
                for ki, kc in enumerate(hemi_cols):
                    mg = ki*1.2
                    c.setFillColor(colors.HexColor(kc)); c.setLineWidth(0)
                    c.ellipse(start_x+mg, CIS_BOT+mg, start_x+2*DOME_R-mg, CIS_BOT+CIS_H-mg, fill=1, stroke=0)
                c.setFillColor(colors.white); c.setStrokeColor(colors.HexColor("#D4AC0D")); c.setLineWidth(2)
                c.ellipse(start_x, CIS_BOT, start_x+2*DOME_R, CIS_BOT+CIS_H, fill=0, stroke=1)

            # Anillos de refuerzo
            n_rings = max(2, int(cw2/40))
            c.setStrokeColor(colors.HexColor("#B8860B")); c.setFillColor(colors.HexColor("#C9960C"))
            for ri in range(1, n_rings+1):
                rx = bx1+(bx2-bx1)*ri/(n_rings+1)
                c.setLineWidth(0); c.rect(rx-2, CIS_BOT, 4, CIS_H, fill=1, stroke=0)

            # Llenado GLP
            try:
                vol = self.parse_float(self.get_var(f"{etapa_key}_{tn}_vol_nat_prod").get() or "0")
                cap = self.parse_float(self.get_var(f"{etapa_key}_{tn}_alt_ref").get() or "1")
                vp  = min(max(vol/(cap if cap>0 else 1),0),1)
            except: vp = 0.0
            if vp > 0.02:
                fill_h = CIS_H * vp
                # Fill ONLY the body rect area (between domes) — no bleeding
                c.setFillColor(colors.HexColor("#FF6B35")); c.setLineWidth(0)
                c.rect(bx1+1, CIS_BOT+1, max(1, bx2-bx1-2), fill_h-2, fill=1, stroke=0)
                # Reflejo
                c.setFillColor(colors.Color(1,1,1,alpha=0.35))
                c.rect(bx1+1, CIS_BOT+fill_h*0.85, max(1, bx2-bx1-2), fill_h*0.10, fill=1, stroke=0)
                # Redraw body contour over fill
                c.setFillColor(colors.white); c.setStrokeColor(colors.HexColor("#D4AC0D")); c.setLineWidth(2)
                c.rect(bx1, CIS_BOT, bx2-bx1, CIS_H, fill=0, stroke=1)
                for is_side_r, start_x_r in [(is_first, cx2), (is_last, cx2+cw2-2*DOME_R)]:
                    if is_side_r:
                        c.ellipse(start_x_r, CIS_BOT, start_x_r+2*DOME_R, CIS_BOT+CIS_H, fill=0, stroke=1)
                c.setFillColor(colors.white); c.setFont("Helvetica-Bold", max(4,min(6, COMP_W*0.12)))
                c.drawCentredString((bx1+bx2)/2, CIS_BOT+CIS_H*vp*0.45, f"{vp*100:.0f}%")

            # PRV (válvulas de seguridad) en la cima
            pnm = self.get_var(f"{etapa_key}_{tn}_prod_name").get() if etapa_key else ""
            pres = self.get_var(f"{etapa_key}_{tn}_esf_pres").get() if etapa_key else ""
            for vvi in range(2):
                vvx = bx1+(bx2-bx1)*(vvi+1)/3
                c.setFillColor(colors.HexColor("#E74C3C")); c.setLineWidth(0)
                c.rect(vvx-2.5, CIS_TOP, 5, max(5,H*0.04), fill=1, stroke=0)
                c.rect(vvx-4, CIS_TOP+max(5,H*0.04)-1, 8, 3, fill=1, stroke=0)

            # Manómetro
            g_x = (bx1+bx2)/2; g_r = max(7, H*0.065); g_y = CIS_TOP+g_r+max(3,H*0.02)
            c.setStrokeColor(colors.HexColor("#5D6D7E")); c.setLineWidth(1)
            c.line(g_x, CIS_TOP, g_x, g_y-g_r)
            c.setFillColor(colors.white); c.setStrokeColor(colors.HexColor("#E74C3C")); c.setLineWidth(1.5)
            c.circle(g_x, g_y, g_r, fill=1, stroke=1)
            try: p_frac = min(float((pres or "0").replace(",","."))/1000, 1.0)
            except: p_frac = 0.3
            ang = math.radians(-30+240*p_frac)
            c.setStrokeColor(colors.HexColor("#C0392B")); c.setLineWidth(1.2)
            c.line(g_x, g_y, g_x+math.cos(ang)*g_r*0.75, g_y+math.sin(ang)*g_r*0.75)
            if pres:
                c.setFillColor(colors.HexColor("#784212")); c.setFont("Helvetica", 4)
                c.drawCentredString(g_x, g_y-g_r-4, f"{pres[:5]}kPa")

            # Etiqueta
            short = tn.replace("COMPARTIMENTO ","C.").strip()[:5]
            c.setFillColor(colors.HexColor("#784212")); c.setFont("Helvetica-Bold", max(4,min(5.5,COMP_W*0.10)))
            c.drawCentredString((bx1+bx2)/2, CIS_TOP+g_r*2+6, short)
            if pnm:
                c.setFont("Helvetica", 4); c.setFillColor(colors.HexColor("#8E6915"))
                c.drawCentredString((bx1+bx2)/2, CIS_BOT+CIS_H*0.08, pnm[:10])

        # ── CABINA ─────────────────────────────────────────────────────────
        CAB_BOT=CIS_BOT; CAB_H=CIS_H+H*0.15; CAB_TOP=CAB_BOT+CAB_H; slope=CAB_W*0.14
        c.setFillColor(colors.HexColor("#6E4B00")); c.setLineWidth(0)
        self._pdf_polygon(c,[CAB_X,CAB_BOT,CAB_X+CAB_W,CAB_BOT,CAB_X+CAB_W,CAB_BOT+CAB_H*0.82,
                   CAB_X+CAB_W-slope,CAB_TOP,CAB_X+slope,CAB_TOP,CAB_X,CAB_BOT+CAB_H*0.82],fill=1)
        c.setFillColor(colors.white); c.setStrokeColor(colors.HexColor("#5D3D00")); c.setLineWidth(1.5)
        self._pdf_polygon(c,[CAB_X,CAB_BOT,CAB_X+CAB_W,CAB_BOT,CAB_X+CAB_W,CAB_BOT+CAB_H*0.82,
                   CAB_X+CAB_W-slope,CAB_TOP,CAB_X+slope,CAB_TOP,CAB_X,CAB_BOT+CAB_H*0.82],fill=0)
        wm=CAB_W*0.13; wh=CAB_H*0.32; wy=CAB_BOT+CAB_H*0.60
        c.setFillColor(colors.HexColor("#AED6F1")); c.setStrokeColor(colors.HexColor("#2C3E50")); c.setLineWidth(1)
        c.rect(CAB_X+wm,wy,CAB_W-2*wm,wh,fill=1,stroke=1)
        c.setLineWidth(1); c.line(CAB_X+CAB_W/2,wy,CAB_X+CAB_W/2,wy+wh)
        gr_h=CAB_H*0.22; gr_x=CAB_X-CAB_W*0.22; gr_y=CAB_BOT+gr_h*0.15
        c.setFillColor(colors.HexColor("#5D3D00")); c.setLineWidth(0)
        c.rect(gr_x,gr_y,CAB_W*0.22,gr_h,fill=1,stroke=0)
        c.setFillColor(colors.HexColor("#F9E79F")); c.setStrokeColor(colors.HexColor("#D4AC0D")); c.setLineWidth(0.8)
        c.circle(gr_x+CAB_W*0.11, gr_y+gr_h-gr_h*0.35-2, gr_h*0.3, fill=1, stroke=1)

        # Ruedas
        AXLE_Y=GND_Y+AXLE_R
        for wx in [CAB_X+CAB_W*0.62, CIS_X+CIS_W*0.72-AXLE_R*0.4, CIS_X+CIS_W*0.72+AXLE_R*0.4]:
            c.setFillColor(colors.HexColor("#1B2631")); c.setStrokeColor(colors.HexColor("#0E1A27")); c.setLineWidth(1)
            c.circle(wx,AXLE_Y,AXLE_R,fill=1,stroke=1)
            rim_r=AXLE_R*0.58
            c.setFillColor(colors.HexColor("#7F8C8D")); c.setStrokeColor(colors.HexColor("#5D6D7E")); c.setLineWidth(0.8)
            c.circle(wx,AXLE_Y,rim_r,fill=1,stroke=1)
            c.setStrokeColor(colors.HexColor("#5D6D7E")); c.setLineWidth(0.8)
            for ang_d in [0,60,120,180,240,300]:
                ar=math.radians(ang_d)
                c.line(wx+math.cos(ar)*rim_r*0.25,AXLE_Y+math.sin(ar)*rim_r*0.25,
                       wx+math.cos(ar)*rim_r*0.9,AXLE_Y+math.sin(ar)*rim_r*0.9)
            c.setFillColor(colors.HexColor("#4A5568")); c.setLineWidth(0); c.circle(wx,AXLE_Y,AXLE_R*0.12,fill=1,stroke=0)
        c.restoreState()

    def _pdf_draw_pipeline(self, c, x, y, W, H, etapa_key, title):
        """ReportLab pipeline drawing — versión industrial premium con gradientes y detalles."""
        from reportlab.lib import colors
        import math as _pm
        tm = self.get_tipo_medio()
        instalacion = self.get_var("car_buque").get() or ""
        STYLES = {
            "GASODUCTO": ("#D6EAF8","#1A5276","#AED6F1","#2874A6","#1A5276"),
            "OLEODUCTO": ("#FEF9E7","#784212","#F0B429","#D4880A","#784212"),
            "POLIDUCTO": ("#EAFAF1","#1D6A39","#A9DFBF","#27AE60","#1D6A39"),
        }
        bg, tc, pf, po, dark = STYLES.get(tm, STYLES["GASODUCTO"])

        c.saveState()
        # ── Fondo neutro ──────────────────────────────────────────────────
        c.setFillColor(colors.HexColor("#F5F7FA")); c.setLineWidth(0)
        c.rect(x, y, W, H, fill=1, stroke=0)
        # Border
        c.setStrokeColor(colors.HexColor(dark)); c.setLineWidth(1.5)
        c.rect(x, y, W, H, fill=0, stroke=1)
        # Header bar with title
        hdr_h = 14
        c.setFillColor(colors.HexColor(tc)); c.setLineWidth(0)
        c.rect(x+1, y+H-hdr_h, W-2, hdr_h-1, fill=1, stroke=0)

        # ── Terreno (simple) ──────────────────────────────────────────────
        GROUND_Y = y + H * 0.22
        c.setFillColor(colors.HexColor("#D5D8DC")); c.setLineWidth(0)
        c.rect(x+1, y+1, W-2, GROUND_Y-y-2, fill=1, stroke=0)

        # ── Parámetros de la tubería ──────────────────────────────────────────
        PIPE_Y  = y + H*0.55
        PIPE_R  = max(9, H*0.13)
        PAD_L   = max(28, W*0.08); PAD_R = PAD_L
        P_LEFT  = x + PAD_L; P_RIGHT = x + W - PAD_R
        PIPE_W  = P_RIGHT - P_LEFT

        n_pipes = 2 if "POLI" in tm else 1
        pipe_offsets = [0] if n_pipes == 1 else [-PIPE_R-3, PIPE_R+3]

        for pi, p_off in enumerate(pipe_offsets):
            py = PIPE_Y + p_off
            _rc = int(pf[1:3],16); _gc = int(pf[3:5],16); _bc = int(pf[5:7],16)
            pc_use = pf if pi == 0 else "#7D3C98"
            if pi == 1: _rc,_gc,_bc = 125,60,152

            # Cuerpo principal
            c.setFillColor(colors.HexColor(pc_use)); c.setLineWidth(0)
            c.rect(P_LEFT, py-PIPE_R, PIPE_W, PIPE_R*2, fill=1, stroke=0)
            # Gradiente cilíndrico
            strips = [(0.00,0.10,0.60),(0.10,0.22,0.75),(0.22,0.38,0.95),(0.38,0.52,1.25),(0.52,0.65,1.08),(0.65,0.80,0.80),(0.80,1.00,0.53)]
            for s1,s2,bright in strips:
                rr2=min(255,int(_rc*bright)); gg2=min(255,int(_gc*bright)); bb2=min(255,int(_bc*bright))
                sc2=f"#{rr2:02x}{gg2:02x}{bb2:02x}"
                c.setFillColor(colors.HexColor(sc2)); c.setLineWidth(0)
                c.rect(P_LEFT+2, py-PIPE_R+int(s1*2*PIPE_R), PIPE_W-4, max(1,int((s2-s1)*2*PIPE_R)), fill=1, stroke=0)
            # Brillo especular
            hl_y = py-PIPE_R+max(2,PIPE_R//5)
            c.setFillColor(colors.white); c.setLineWidth(0)
            c.rect(P_LEFT+PIPE_W//8, hl_y, PIPE_W*3//4, max(1,PIPE_R//6), fill=1, stroke=0)
            # Contorno
            c.setStrokeColor(colors.HexColor(dark)); c.setLineWidth(1.5)
            c.rect(P_LEFT, py-PIPE_R, PIPE_W, PIPE_R*2, fill=0, stroke=1)
            # Tapas elípticas
            c.setFillColor(colors.HexColor("#4A5568")); c.setStrokeColor(colors.HexColor(dark)); c.setLineWidth(1.2)
            c.ellipse(P_LEFT-PIPE_R//2, py-PIPE_R, P_LEFT+PIPE_R//2, py+PIPE_R, fill=1, stroke=1)
            c.ellipse(P_RIGHT-PIPE_R//2, py-PIPE_R, P_RIGHT+PIPE_R//2, py+PIPE_R, fill=1, stroke=1)
            # Soportes al suelo
            for sx in [P_LEFT+PIPE_W//4, P_LEFT+PIPE_W//2, P_LEFT+3*PIPE_W//4]:
                c.setFillColor(colors.HexColor("#7F8C8D")); c.setStrokeColor(colors.HexColor("#5D6D7E")); c.setLineWidth(0.8)
                c.rect(sx-3, GROUND_Y, 6, max(1, (py - PIPE_R) - GROUND_Y), fill=1, stroke=1)
                c.setFillColor(colors.HexColor("#5D6D7E")); c.setLineWidth(0)
                c.rect(sx-7, GROUND_Y-3, 14, 4, fill=1, stroke=0)
            # Bridas
            n_fl = max(2, min(5, int(PIPE_W//60)))
            fl_step = PIPE_W//(n_fl+1)
            for fi in range(n_fl):
                fx = P_LEFT + (fi+1)*fl_step
                c.setFillColor(colors.HexColor("#5D6D7E")); c.setStrokeColor(colors.HexColor("#4A5568")); c.setLineWidth(0.8)
                c.rect(fx-2, py-PIPE_R-3, 4, PIPE_R*2+6, fill=1, stroke=1)

        # ── Tramo subterráneo ────────────────────────────────────────────────
        sg_w = max(20, PIPE_W//8)
        sg_x = x + W - PAD_R - sg_w - 8
        ug_depth = max(8, PIPE_R*2)
        c.setFillColor(colors.HexColor("#9E8A6E")); c.setLineWidth(0)
        c.rect(sg_x-4, y+1, sg_w+14, GROUND_Y-y, fill=1, stroke=0)
        c.setFillColor(colors.HexColor("#7A6350")); c.setLineWidth(0)
        c.rect(sg_x-2, y+2, sg_w+10, ug_depth*0.4, fill=1, stroke=0)
        py0 = PIPE_Y + pipe_offsets[0]
        c.setFillColor(colors.HexColor(pf)); c.setStrokeColor(colors.HexColor(dark)); c.setLineWidth(1.5)
        c.rect(sg_x, py0-PIPE_R, sg_w, PIPE_R*2, fill=1, stroke=1)
        # Tapa izquierda
        c.setFillColor(colors.HexColor("#4A5568"))
        c.ellipse(sg_x-PIPE_R//2, py0-PIPE_R, sg_x+PIPE_R//2, py0+PIPE_R, fill=1, stroke=1)
        c.setFillColor(colors.HexColor("#2C3E50")); c.setFont("Helvetica", max(4,int(PIPE_R//3)))
        c.drawCentredString(sg_x+sg_w//2, (GROUND_Y + y+2) / 2, "─ ─ ─")

        # ── Flechas de dirección de flujo ────────────────────────────────────
        arr_y = PIPE_Y + pipe_offsets[0]
        c.setFillColor(colors.HexColor(tc)); c.setStrokeColor(colors.HexColor(tc)); c.setLineWidth(0)
        for afx in [P_LEFT+PIPE_W//5, P_LEFT+PIPE_W*2//5, P_LEFT+PIPE_W*3//5]:
            arr = c.beginPath()
            arr.moveTo(afx-4, arr_y-2); arr.lineTo(afx+5, arr_y); arr.lineTo(afx-4, arr_y+2); arr.close()
            c.drawPath(arr, fill=1, stroke=0)

        # ── Instrumento de presión ────────────────────────────────────────────
        inst_x = P_LEFT + PIPE_W//2; inst_y = PIPE_Y + pipe_offsets[0] - PIPE_R
        inst_r = max(6, PIPE_R*0.65)
        # Línea de conexión
        c.setStrokeColor(colors.HexColor(dark)); c.setLineWidth(1.2)
        c.line(inst_x, inst_y, inst_x, inst_y-inst_r*0.6)
        # Cuerpo del manómetro
        c.setFillColor(colors.HexColor("#D5DBDB")); c.setStrokeColor(colors.HexColor(dark)); c.setLineWidth(1)
        c.circle(inst_x, inst_y-inst_r*0.6-inst_r, inst_r, fill=1, stroke=1)
        c.setFillColor(colors.white); c.setLineWidth(0)
        c.circle(inst_x, inst_y-inst_r*0.6-inst_r, inst_r*0.7, fill=1, stroke=0)
        # Aguja
        c.setStrokeColor(colors.HexColor("#E74C3C")); c.setLineWidth(0.8)
        ang_p = _pm.radians(45)
        c.line(inst_x, inst_y-inst_r*0.6-inst_r,
               inst_x+inst_r*0.55*_pm.cos(ang_p), inst_y-inst_r*0.6-inst_r+inst_r*0.55*_pm.sin(ang_p))
        c.setFillColor(colors.HexColor("#1B3A5C")); c.setFont("Helvetica-Bold", max(4,int(inst_r*0.55)))
        c.drawCentredString(inst_x, inst_y-inst_r*0.6-inst_r*2-3, "P")

        # ── Válvula en el extremo ─────────────────────────────────────────────
        vx = P_LEFT + PIPE_W//6; vy = PIPE_Y + pipe_offsets[0]
        vr = max(4, PIPE_R*0.75)
        c.setFillColor(colors.HexColor("#4A5568")); c.setStrokeColor(colors.HexColor(dark)); c.setLineWidth(1)
        c.rect(vx-2, vy-vr, 4, vr*2, fill=1, stroke=1)
        # Forma de mariposa
        v_pts = [vx-vr, vy-1, vx-2, vy-vr+1, vx+2, vy-vr+1, vx+vr, vy-1,
                 vx+vr, vy+1, vx+2, vy+vr-1, vx-2, vy+vr-1, vx-vr, vy+1]
        c.setFillColor(colors.HexColor("#7F8C8D")); c.setLineWidth(0)
        self._pdf_polygon(c,v_pts, fill=1)
        c.setStrokeColor(colors.HexColor(dark)); c.setLineWidth(0.8)
        self._pdf_polygon(c,v_pts, fill=0)
        # Tope de la válvula
        c.setFillColor(colors.HexColor("#2C3E50")); c.setLineWidth(0)
        c.rect(vx-3, vy-vr-5, 6, 5, fill=1, stroke=0)
        c.rect(vx-6, vy-vr-7, 12, 2, fill=1, stroke=0)

        # ── Cross-section inset (upper-left) ───────────────────────────────
        cs_r = max(12, min(22, H*0.07, W*0.035))
        cs_cx = x + PAD_L + cs_r + 8; cs_cy = y + H - hdr_h - cs_r - 8
        # Background circle
        c.setFillColor(colors.HexColor("#E8EBF0")); c.setStrokeColor(colors.HexColor(dark)); c.setLineWidth(1)
        c.circle(cs_cx, cs_cy, cs_r+4, fill=1, stroke=1)
        # Outer coating (FBE - dark green)
        c.setFillColor(colors.HexColor("#1D6A39")); c.setLineWidth(0)
        c.circle(cs_cx, cs_cy, cs_r, fill=1, stroke=0)
        # Steel wall
        c.setFillColor(colors.HexColor("#7F8C8D")); c.setLineWidth(0)
        c.circle(cs_cx, cs_cy, cs_r*0.85, fill=1, stroke=0)
        # Internal lining
        c.setFillColor(colors.HexColor("#F0E68C")); c.setLineWidth(0)
        c.circle(cs_cx, cs_cy, cs_r*0.70, fill=1, stroke=0)
        # Product flow (inside)
        flow_col = "#5D4037" if "OLEO" in tm else ("#AED6F1" if "GAS" in tm else "#82E0AA")
        c.setFillColor(colors.HexColor(flow_col)); c.setLineWidth(0)
        c.circle(cs_cx, cs_cy, cs_r*0.62, fill=1, stroke=0)
        # Flow direction arrow
        c.setFillColor(colors.white); c.setLineWidth(0)
        arr_s = cs_r * 0.3
        arr = c.beginPath()
        arr.moveTo(cs_cx-arr_s*0.6, cs_cy-arr_s*0.4); arr.lineTo(cs_cx+arr_s*0.8, cs_cy)
        arr.lineTo(cs_cx-arr_s*0.6, cs_cy+arr_s*0.4); arr.close()
        c.drawPath(arr, fill=1, stroke=0)
        # Label
        c.setFillColor(colors.HexColor(dark)); c.setFont("Helvetica-Bold", max(3.5, cs_r*0.22))
        c.drawCentredString(cs_cx, cs_cy-cs_r-7, "SECCION")

        # ── Título (centrado en la barra de header) ─────────────────────────
        c.setFillColor(colors.white); c.setFont("Helvetica-Bold", 7)
        title_txt = f"{tm}" + (f" - {instalacion}" if instalacion else "") + f" - {title}"
        max_chars = int(W / 4.2)
        if len(title_txt) > max_chars:
            title_txt = title_txt[:max_chars-3] + "..."
        c.drawCentredString(x+W/2, y+H-11, title_txt)

        c.restoreState()

    def _pdf_draw_electric(self, c, x, y, W, H, etapa_key, title):
        """ReportLab electrical metering drawing — versión industrial premium con panel de control."""
        from reportlab.lib import colors
        import math as _pm
        tank_names = self.lista_tanques or ["MED 1"]
        n = max(len(tank_names), 1)
        instalacion = self.get_var("car_buque").get() or ""

        c.saveState()
        # ── Fondo claro (sala eléctrica) ──────────────────────────────────
        c.setFillColor(colors.HexColor("#F0F2F5")); c.setLineWidth(0)
        c.rect(x, y, W, H, fill=1, stroke=0)
        # Borde
        c.setStrokeColor(colors.HexColor("#4A235A")); c.setLineWidth(1.5)
        c.rect(x, y, W, H, fill=0, stroke=1)
        # Header con color solido
        hdr_h = 14
        c.setFillColor(colors.HexColor("#4A235A")); c.setLineWidth(0)
        c.rect(x+1, y+H-hdr_h, W-2, hdr_h-1, fill=1, stroke=0)
        # Título
        c.setFillColor(colors.white); c.setFont("Helvetica-Bold", min(8, max(5, H*0.04)))
        title_txt = f"MEDICION ELECTRICA" + (f" | {instalacion}" if instalacion else "") + f" - {title}"
        max_chars = int(W / 4.5)
        if len(title_txt) > max_chars:
            title_txt = title_txt[:max_chars-3] + "..."
        c.drawCentredString(x+W/2, y+H-11, title_txt)

        # ── Panel de control principal ─────────────────────────────────────
        px = x+8; pw = W-16; py_p = y+8; ph = H-hdr_h-18
        c.setFillColor(colors.HexColor("#E8EBF0")); c.setStrokeColor(colors.HexColor("#4A235A")); c.setLineWidth(1.5)
        c.roundRect(px, py_p, pw, ph, 4, fill=1, stroke=1)
        # Tornillos de panel (4 esquinas)
        c.setFillColor(colors.HexColor("#4A5568")); c.setLineWidth(0)
        for sx2,sy2 in [(px+4,py_p+4),(px+pw-6,py_p+4),(px+4,py_p+ph-6),(px+pw-6,py_p+ph-6)]:
            c.circle(sx2, sy2, 2.5, fill=1, stroke=0)
            c.setStrokeColor(colors.HexColor("#2C3E50")); c.setLineWidth(0.6)
            c.line(sx2-1.5,sy2,sx2+1.5,sy2)

        # ── LEDs de estado ────────────────────────────────────────────────
        leds = [("#27AE60","ON"),("#F4D03F","WARN"),("#E74C3C","ALM")]
        for li2, (lc2,lt2) in enumerate(leds):
            lx2 = px+10+li2*22; ly2 = py_p+ph-10
            c.setFillColor(colors.HexColor(lc2)); c.setLineWidth(0)
            c.circle(lx2, ly2, 4, fill=1, stroke=0)
            # Halo del LED (glow effect)
            c.setFillColor(colors.HexColor(lc2))
            c.circle(lx2, ly2, 5, fill=1, stroke=0)
            c.setFillColor(colors.HexColor(lc2)); c.circle(lx2, ly2, 3.5, fill=1, stroke=0)
            c.setFillColor(colors.HexColor("#BDC3C7")); c.setFont("Helvetica", max(3,H*0.027))
            c.drawCentredString(lx2, ly2-8, lt2)

        # ── Medidores individuales ────────────────────────────────────────
        mt_w = max(24, (pw-20)//n)
        mt_pad = 4
        for i, tn in enumerate(tank_names[:n]):
            mx = px+10+i*mt_w; my_bot = py_p+8; mw = mt_w-mt_pad*2; mh = ph-22

            # Marco del medidor
            c.setFillColor(colors.HexColor("#D5D8DC")); c.setStrokeColor(colors.HexColor("#4A235A")); c.setLineWidth(1)
            c.roundRect(mx, my_bot, mw, mh, 3, fill=1, stroke=1)

            # === Proportional layout: divide available height into zones ===
            mhdr = min(12, max(8, mh*0.04))
            # Header del medidor (top of meter)
            c.setFillColor(colors.HexColor("#4A235A")); c.setLineWidth(0)
            c.roundRect(mx, my_bot+mh-mhdr, mw, mhdr, 3, fill=1, stroke=0)
            c.setFillColor(colors.white); c.setFont("Helvetica-Bold", min(6, max(4.5, mhdr*0.55)))
            c.drawCentredString(mx+mw//2, my_bot+mh-mhdr+mhdr*0.25, tn[:10])

            # Usable content area (below header, above bottom margin)
            content_bot = my_bot + 4
            content_top_y = my_bot + mh - mhdr - 3
            ch = content_top_y - content_bot  # total content height

            # Proportional zones: LCD_INI(25%) + LCD_FIN(25%) + BAR(10%) + GAUGES(30%) + gaps(10%)
            gap = max(3, ch * 0.025)
            lcd_h = max(14, ch * 0.20)
            bar_h = max(6, ch * 0.06)
            gauge_zone = max(20, ch * 0.30)
            gr = min(gauge_zone * 0.42, mw * 0.18, 22)
            label_fs = min(5, max(3.5, ch * 0.018))
            lcd_fs = max(5, min(9, mw * 0.10, lcd_h * 0.45))

            # Content data
            kwh_ini = self.get_var(f"{etapa_key}_{tn}_el_ini_act").get() if etapa_key else ""
            kwh_fin = self.get_var(f"{etapa_key}_{tn}_el_fin_act").get() if etapa_key else ""

            # ── kWh INICIAL: label + LCD ──
            cur_y = content_top_y
            c.setFillColor(colors.HexColor("#2C3E50")); c.setFont("Helvetica-Bold", label_fs)
            c.drawCentredString(mx+mw//2, cur_y - label_fs - 1, "kWh INICIAL")
            cur_y -= label_fs + 3
            lcd_y = cur_y - lcd_h
            c.setFillColor(colors.HexColor("#0D4D3E")); c.setStrokeColor(colors.HexColor("#1ABC9C")); c.setLineWidth(1)
            c.roundRect(mx+4, lcd_y, mw-8, lcd_h, 2, fill=1, stroke=1)
            c.setFillColor(colors.HexColor("#1ABC9C")); c.setFont("Courier-Bold", lcd_fs)
            c.drawCentredString(mx+mw//2, lcd_y+lcd_h*0.35, kwh_ini[:9] if kwh_ini else "---")
            cur_y = lcd_y - gap

            # ── kWh FINAL: label + LCD ──
            c.setFillColor(colors.HexColor("#2C3E50")); c.setFont("Helvetica-Bold", label_fs)
            c.drawCentredString(mx+mw//2, cur_y - label_fs - 1, "kWh FINAL")
            cur_y -= label_fs + 3
            lcd2_y = cur_y - lcd_h
            c.setFillColor(colors.HexColor("#2C0808")); c.setStrokeColor(colors.HexColor("#E74C3C")); c.setLineWidth(1)
            c.roundRect(mx+4, lcd2_y, mw-8, lcd_h, 2, fill=1, stroke=1)
            c.setFillColor(colors.HexColor("#E74C3C")); c.setFont("Courier-Bold", lcd_fs)
            c.drawCentredString(mx+mw//2, lcd2_y+lcd_h*0.35, kwh_fin[:9] if kwh_fin else "---")
            cur_y = lcd2_y - gap

            # ── Consumption bar ──
            bar_w = mw - 12
            bar_y = cur_y - bar_h
            c.setFillColor(colors.HexColor("#BDC3C7")); c.setStrokeColor(colors.HexColor("#4A235A")); c.setLineWidth(0.8)
            c.rect(mx+6, bar_y, bar_w, bar_h, fill=1, stroke=1)
            c.setFillColor(colors.HexColor("#2C3E50")); c.setFont("Helvetica-Bold", min(4, label_fs))
            c.drawCentredString(mx+mw//2, bar_y + bar_h + 1, "CONSUMO")
            try:
                ini_v = float(kwh_ini.replace(",",".")) if kwh_ini else 0.0
                fin_v = float(kwh_fin.replace(",",".")) if kwh_fin else 0.0
                if fin_v > ini_v > 0:
                    pct_b = min((fin_v-ini_v)/max(fin_v,1), 1.0)
                    bar_c = "#27AE60" if pct_b < 0.7 else ("#F39C12" if pct_b < 0.9 else "#E74C3C")
                    c.setFillColor(colors.HexColor(bar_c)); c.setLineWidth(0)
                    c.rect(mx+6, bar_y, int(bar_w*pct_b), bar_h, fill=1, stroke=0)
                    c.setFillColor(colors.white); c.setFont("Helvetica-Bold", min(5, bar_h*0.7))
                    c.drawCentredString(mx+mw//2, bar_y+bar_h*0.2, f"D{fin_v-ini_v:.0f}")
            except: pass
            cur_y = bar_y - gap

            # ── Voltímetro y Amperímetro analógicos ──
            gauge_y = cur_y - gr - 2
            # Center gauges vertically in remaining space
            remaining = gauge_y - gr - content_bot
            if remaining > gr:
                gauge_y = content_bot + (cur_y - content_bot) * 0.45 + gr * 0.5
            for gi2,(gl2,gc2,gvk) in enumerate([("V","#F4D03F","el_V"),("A","#E74C3C","el_A")]):
                gx3 = mx + mw//4 + gi2*(mw//2); gy3 = gauge_y
                c.setFillColor(colors.HexColor("#1A252F")); c.setStrokeColor(colors.HexColor("#5D6D7E")); c.setLineWidth(0.8)
                c.circle(gx3, gy3, gr, fill=1, stroke=1)
                # Marcas de la esfera
                c.setStrokeColor(colors.HexColor("#85929E")); c.setLineWidth(0.5)
                for am in range(0,180,30):
                    ar2 = _pm.radians(180+am)
                    c.line(gx3+_pm.cos(ar2)*gr*0.7,gy3+_pm.sin(ar2)*gr*0.7,gx3+_pm.cos(ar2)*gr*0.9,gy3+_pm.sin(ar2)*gr*0.9)
                # Aguja
                gval = self.get_var(f"{etapa_key}_{tn}_{gvk}").get() if etapa_key else ""
                try:
                    gfrac = min(float(gval.replace(",","."))/500.0,1.0) if gval else 0.0
                except: gfrac = 0.0
                ang3 = _pm.radians(180+gfrac*180)
                c.setStrokeColor(colors.HexColor(gc2)); c.setLineWidth(1)
                c.line(gx3,gy3,gx3+_pm.cos(ang3)*gr*0.75,gy3+_pm.sin(ang3)*gr*0.75)
                c.setFillColor(colors.HexColor("#2C3E50")); c.setLineWidth(0)
                c.circle(gx3,gy3,2,fill=1,stroke=0)
                c.setFillColor(colors.HexColor(gc2)); c.setFont("Helvetica-Bold", max(4, min(6, gr*0.4)))
                c.drawCentredString(gx3, gy3-gr-max(4, min(6, gr*0.4))-1, gl2)

        # ── Barras de cables en la parte inferior ─────────────────────────
        cab_h = max(6, min(10, H*0.03))
        c.setFillColor(colors.HexColor("#17202A")); c.setLineWidth(0)
        c.rect(x+1, y+1, W-2, cab_h, fill=1, stroke=0)
        cable_cols = ["#E74C3C","#F4D03F","#3498DB","#ECF0F1","#27AE60"]
        n_cables = int(max(6, W//15))
        cw = (W-8)//n_cables
        for ci2 in range(n_cables):
            cc2 = cable_cols[ci2 % len(cable_cols)]
            c.setFillColor(colors.HexColor(cc2)); c.setLineWidth(0)
            c.roundRect(x+4+ci2*cw, y+2, max(3,cw-2), cab_h-3, 1, fill=1, stroke=0)
        c.setFillColor(colors.HexColor("#BDC3C7")); c.setFont("Helvetica", max(3, H*0.027))
        c.drawCentredString(x+W//2, y+cab_h//2, "BARRAS Y CABLEADO")

        c.restoreState()

    def _pdf_draw_gasero_ship(self, c, x, y, W, H, etapa_key, title):
        """Buque gasero/GLP — casco con hasta 4 tanques esféricos MOSS sobre cubierta."""
        from reportlab.lib import colors
        import math
        c.saveState()
        tank_names = [t for t in self.lista_tanques if not t.startswith("CARBONERA")]
        n = max(len(tank_names), 1)

        # Fondo neutro
        c.setFillColor(colors.HexColor("#E8F0FE")); c.setLineWidth(0)
        c.rect(x, y, W, H, fill=1, stroke=0)

        # Título
        c.setFont("Helvetica-Bold", min(8, max(6, H*0.04)))
        c.setFillColor(colors.HexColor("#1D6A39"))
        _gtxt = f"BUQUE GASERO/GLP - {title}"
        max_chars = int(W / 4.5)
        if len(_gtxt) > max_chars:
            _gtxt = _gtxt[:max_chars-3] + "..."
        c.drawCentredString(x+W/2, y+H-10, _gtxt)

        # Dimensiones casco
        M = 20
        hull_bot = y + H*0.10
        hull_top = y + H*0.52
        hull_h   = hull_top - hull_bot
        bow_x    = x + W - M
        stern_x  = x + M
        mid_y    = hull_bot + hull_h*0.45

        # Casco (proa puntiaguda, popa cuadrada)
        p = c.beginPath()
        p.moveTo(stern_x, hull_top)
        p.lineTo(bow_x - 20, hull_top)
        p.curveTo(bow_x+10, hull_top, bow_x+15, mid_y+8, bow_x+5, mid_y)
        p.lineTo(stern_x, mid_y)
        p.close()
        c.setFillColor(colors.HexColor("#BDC3C7")); c.setLineWidth(1.5)
        c.setStrokeColor(colors.HexColor("#7F8C8D"))
        c.drawPath(p, fill=1, stroke=1)

        # Obra viva
        p2 = c.beginPath()
        p2.moveTo(stern_x, mid_y)
        p2.lineTo(bow_x+5, mid_y)
        p2.curveTo(bow_x+15, mid_y, bow_x+10, hull_bot+5, bow_x-10, hull_bot)
        p2.lineTo(stern_x+5, hull_bot)
        p2.curveTo(stern_x-5, hull_bot, stern_x-5, mid_y-5, stern_x, mid_y)
        p2.close()
        c.setFillColor(colors.HexColor("#E74C3C")); c.drawPath(p2, fill=1, stroke=0)
        # Franja azul sobre línea de flotación
        c.setFillColor(colors.HexColor("#1B3A5C")); c.setLineWidth(0)
        c.rect(stern_x, mid_y-2, bow_x-stern_x, 4, fill=1, stroke=0)

        # Cubierta (plataforma entre caseta y proa)
        c.setFillColor(colors.HexColor("#95A5A6")); c.setLineWidth(0)
        c.rect(stern_x+50, hull_top-3, bow_x-stern_x-65, 4, fill=1, stroke=0)

        # Caseta de popa
        c.setFillColor(colors.HexColor("#ECF0F1")); c.setStrokeColor(colors.HexColor("#BDC3C7")); c.setLineWidth(0.8)
        c.roundRect(stern_x, hull_top, 52, 22, 2, fill=1, stroke=1)
        c.setFillColor(colors.HexColor("#D5D8DC"))
        c.roundRect(stern_x+4, hull_top+22, 44, 12, 2, fill=1, stroke=1)
        c.roundRect(stern_x-3, hull_top+30, 58, 6, 1, fill=1, stroke=1)
        # Chimenea corta
        c.setFillColor(colors.HexColor("#C0392B")); c.setLineWidth(0)
        c.roundRect(stern_x+18, hull_top+36, 12, 14, 2, fill=1, stroke=0)

        # ── TANQUES ESFÉRICOS MOSS ─────────────────────────────────────────────
        sphere_zone_x1 = stern_x + 55
        sphere_zone_x2 = bow_x - 15
        zone_w = sphere_zone_x2 - sphere_zone_x1
        sphere_spacing = zone_w / n
        sphere_r = min(hull_h * 0.70, sphere_spacing * 0.42)
        sphere_cy = hull_top + sphere_r * 0.80   # centro esferas sobre cubierta

        for i, tn in enumerate(tank_names[:n]):
            cx_s = sphere_zone_x1 + i * sphere_spacing + sphere_spacing / 2

            # Falda (skirt)
            skirt_w = sphere_r * 0.55
            skirt_h = sphere_r * 0.55
            c.setFillColor(colors.HexColor("#7F8C8D")); c.setLineWidth(0)
            c.rect(cx_s - skirt_w/2, hull_top, skirt_w, skirt_h, fill=1, stroke=0)
            # Plataforma cubierta
            c.setFillColor(colors.HexColor("#5D6D7E"))
            c.rect(cx_s - sphere_r*0.65, hull_top-2, sphere_r*1.3, 4, fill=1, stroke=0)

            # Nivel de llenado
            try:
                vn_val = self.parse_float(self.get_var(f"{etapa_key}_{tn}_vol_nat_prod").get() or "0")
                ar_val = self.parse_float(self.get_var(f"{etapa_key}_{tn}_alt_ref").get() or "1")
                pct = min(vn_val / (ar_val if ar_val > 0 else 1), 1.0)
            except: pct = 0.0
            prod_name = self.get_var(f"{etapa_key}_{tn}_prod_name").get() if etapa_key else ""

            # Esfera gradiente (capas de blanco-aluminio)
            sphere_layers = [
                ("#1A4F6E",1.00),("#2471A3",0.92),("#2E86C1",0.82),
                ("#5DADE2",0.70),("#AED6F1",0.55),("#D6EAF8",0.38),
            ]
            for sc, sf in sphere_layers:
                c.setFillColor(colors.HexColor(sc)); c.setLineWidth(0)
                c.circle(cx_s, sphere_cy, sphere_r*sf, fill=1, stroke=0)

            # Color del producto — nunca azul (azul=agua)
            glp_col = self.get_prod_color(tn, etapa_key)[0] if etapa_key else "#FF6B35"
            if glp_col.upper() in ("#3498DB","#5DADE2","#2E86C1","#2471A3","#AED6F1","#85C1E9","#E8E8F0"):
                glp_col = "#FF6B35"

            # Llenado (producto dentro de la esfera)
            if pct > 0.02:
                fill_h = sphere_r * 2 * pct
                fill_y = sphere_cy - sphere_r
                clip_h = min(fill_h, sphere_r * 2 - 1)
                c.setFillColor(colors.HexColor(glp_col)); c.setLineWidth(0)
                c.saveState()
                p_clip = c.beginPath()
                p_clip.circle(cx_s, sphere_cy, sphere_r-1)
                c.clipPath(p_clip, stroke=0)
                c.rect(cx_s-sphere_r, fill_y, sphere_r*2, clip_h, fill=1, stroke=0)
                c.restoreState()

            # Contorno esfera
            c.setFillColor(colors.white); c.setStrokeColor(colors.HexColor("#5D6D7E")); c.setLineWidth(1.5)
            c.circle(cx_s, sphere_cy, sphere_r, fill=0, stroke=1)
            # Anillo ecuatorial
            c.setStrokeColor(colors.HexColor("#2C3E50")); c.setLineWidth(0.8)
            c.ellipse(cx_s-sphere_r, sphere_cy-sphere_r*0.1, cx_s+sphere_r, sphere_cy+sphere_r*0.1, fill=0, stroke=1)

            # Tuberías y válvulas en la cima
            c.setStrokeColor(colors.HexColor("#5D6D7E")); c.setLineWidth(1.2)
            c.line(cx_s, sphere_cy+sphere_r, cx_s, sphere_cy+sphere_r+8)
            c.setFillColor(colors.HexColor("#E74C3C")); c.setLineWidth(0)
            c.rect(cx_s-3, sphere_cy+sphere_r+6, 6, 4, fill=1, stroke=0)  # PRV

            # Etiqueta
            lbl_bg = glp_col if pct > 0.02 else "#7B8D9A"
            lbl_txt = self.contrast_text(lbl_bg)
            c.setFillColor(colors.HexColor(lbl_txt)); c.setFont("Helvetica-Bold", max(4.5, sphere_r*0.12))
            short = tn.replace("TK ","T").replace(" BABOR","B").replace(" ESTRIBOR","E")
            c.drawCentredString(cx_s, sphere_cy, short)
            if pct > 0:
                c.setFont("Helvetica", max(4, sphere_r*0.10))
                c.drawCentredString(cx_s, sphere_cy-sphere_r*0.18, f"{pct*100:.0f}%")
            if prod_name:
                c.setFillColor(colors.HexColor("#2C3E50"))
                c.setFont("Helvetica", max(3.5, sphere_r*0.09))
                c.drawCentredString(cx_s, hull_top - 8, prod_name[:14])

        # Mastil de proa
        c.setStrokeColor(colors.HexColor("#626567")); c.setLineWidth(1.2)
        c.line(bow_x-18, hull_top, bow_x-18, hull_top+28)
        c.line(bow_x-26, hull_top+20, bow_x-10, hull_top+20)
        c.setFillColor(colors.HexColor("#F4D03F")); c.setLineWidth(0)
        c.circle(bow_x-18, hull_top+28, 2, fill=1, stroke=0)

        # Línea de flotación
        c.setStrokeColor(colors.HexColor("#2E86C1")); c.setLineWidth(1)
        c.setDash(5, 2); c.line(stern_x-8, mid_y, bow_x+15, mid_y); c.setDash()

        c.restoreState()

    def _pdf_draw_metanero_ship(self, c, x, y, W, H, etapa_key, title):
        """Buque metanero/GNL — casco con hasta 4 tanques Kvaerner Moss o prisma."""
        from reportlab.lib import colors
        import math
        c.saveState()
        tank_names = [t for t in self.lista_tanques if not t.startswith("CARBONERA")]
        n = max(len(tank_names), 1)

        # Fondo neutro
        c.setFillColor(colors.HexColor("#E8F0FE")); c.setLineWidth(0)
        c.rect(x, y, W, H, fill=1, stroke=0)

        # Título
        c.setFont("Helvetica-Bold", min(8, max(6, H*0.04)))
        c.setFillColor(colors.HexColor("#1B3A5C"))
        _mtxt = f"BUQUE METANERO/GNL - {title}"
        max_chars = int(W / 4.5)
        if len(_mtxt) > max_chars:
            _mtxt = _mtxt[:max_chars-3] + "..."
        c.drawCentredString(x+W/2, y+H-10, _mtxt)

        M = 20
        hull_bot = y + H*0.10
        hull_top = y + H*0.50
        hull_h   = hull_top - hull_bot
        bow_x    = x + W - M
        stern_x  = x + M
        mid_y    = hull_bot + hull_h * 0.45

        # Casco obra muerta + obra viva (forma de LNG con popa recta)
        p = c.beginPath()
        p.moveTo(stern_x, hull_top)
        p.lineTo(bow_x-15, hull_top)
        p.curveTo(bow_x+12, hull_top, bow_x+15, mid_y+10, bow_x+5, mid_y)
        p.lineTo(stern_x, mid_y); p.close()
        c.setFillColor(colors.HexColor("#D5D8DC")); c.setStrokeColor(colors.HexColor("#7F8C8D")); c.setLineWidth(1.5)
        c.drawPath(p, fill=1, stroke=1)

        p2 = c.beginPath()
        p2.moveTo(stern_x, mid_y)
        p2.lineTo(bow_x+5, mid_y)
        p2.curveTo(bow_x+14, mid_y, bow_x+8, hull_bot+5, bow_x-12, hull_bot)
        p2.lineTo(stern_x+4, hull_bot)
        p2.curveTo(stern_x-4, hull_bot, stern_x-4, mid_y-4, stern_x, mid_y); p2.close()
        c.setFillColor(colors.HexColor("#D35400")); c.drawPath(p2, fill=1, stroke=0)
        c.setFillColor(colors.HexColor("#2C3E50")); c.setLineWidth(0)
        c.rect(stern_x, mid_y-2, bow_x-stern_x, 4, fill=1, stroke=0)

        # Cubierta (aislada = blanca)
        c.setFillColor(colors.HexColor("#F0F3F4")); c.setLineWidth(0)
        c.rect(stern_x+48, hull_top-2, bow_x-stern_x-60, 4, fill=1, stroke=0)

        # Caseta popa
        c.setFillColor(colors.HexColor("#ECF0F1")); c.setStrokeColor(colors.HexColor("#BDC3C7")); c.setLineWidth(0.8)
        c.roundRect(stern_x, hull_top, 48, 20, 2, fill=1, stroke=1)
        c.setFillColor(colors.HexColor("#D5D8DC"))
        c.roundRect(stern_x+4, hull_top+20, 40, 12, 2, fill=1, stroke=1)
        c.roundRect(stern_x-2, hull_top+28, 52, 6, 1, fill=1, stroke=1)
        c.setFillColor(colors.HexColor("#154360")); c.setLineWidth(0)
        c.roundRect(stern_x+14, hull_top+34, 10, 12, 2, fill=1, stroke=0)

        # ── TANQUES PRISMÁTICOS GNL (tipo Membrane) ────────────────────────────
        # Forma: trapezoide con esquinas biseladas
        tz_x1 = stern_x + 52
        tz_x2 = bow_x - 12
        tz_w   = tz_x2 - tz_x1
        tk_w_each = tz_w / n
        gap = 4
        tank_h_gnl = hull_h * 1.30   # tanques sobresalen sobre cubierta
        tank_bot_y = hull_top - hull_h * 0.80

        for i, tn in enumerate(tank_names[:n]):
            tx = tz_x1 + i * tk_w_each + gap/2
            tw = tk_w_each - gap
            ty_bot = hull_top - hull_h * 0.75
            ty_top = hull_top + hull_h * 0.95

            try:
                vn_val = self.parse_float(self.get_var(f"{etapa_key}_{tn}_vol_nat_prod").get() or "0")
                ar_val = self.parse_float(self.get_var(f"{etapa_key}_{tn}_alt_ref").get() or "1")
                pct = min(vn_val / (ar_val if ar_val > 0 else 1), 1.0)
            except: pct = 0.0
            prod_name = self.get_var(f"{etapa_key}_{tn}_prod_name").get() if etapa_key else ""
            tank_inner_h = ty_top - ty_bot

            # Cuerpo aislado (blanco-azulado)
            c.setFillColor(colors.HexColor("#EBF5FB")); c.setStrokeColor(colors.HexColor("#2E86C1")); c.setLineWidth(1.2)
            c.roundRect(tx, ty_bot, tw, tank_inner_h, 5, fill=1, stroke=1)

            # Color del producto — nunca azul (azul es SOLO para agua)
            gnl_col = self.get_prod_color(tn, etapa_key)[0] if etapa_key else "#E8E8F0"
            if gnl_col.upper() in ("#3498DB","#5DADE2","#2E86C1","#2471A3","#AED6F1","#85C1E9"):
                gnl_col = "#D5D8DC"

            # Llenado GNL (plata criogénica)
            if pct > 0.01:
                fill_px = tank_inner_h * pct
                c.setFillColor(colors.HexColor(gnl_col)); c.setLineWidth(0)
                c.saveState()
                p_clip2 = c.beginPath()
                p_clip2.roundRect(tx+1, ty_bot+1, tw-2, tank_inner_h-2, 4)
                c.clipPath(p_clip2, stroke=0)
                c.rect(tx+1, ty_bot+1, tw-2, fill_px-2, fill=1, stroke=0)
                # Brillo criogénico (franja clara en la superficie)
                c.setFillColor(colors.HexColor("#F0F3F4")); c.setLineWidth(0)
                c.rect(tx+1, ty_bot+fill_px-4, tw-2, 3, fill=1, stroke=0)
                c.restoreState()

            # Borde
            c.setFillColor(colors.white); c.setStrokeColor(colors.HexColor("#7F8C8D")); c.setLineWidth(1.2)
            c.roundRect(tx, ty_bot, tw, tank_inner_h, 5, fill=0, stroke=1)

            # Aislamiento (líneas diagonales)
            c.setStrokeColor(colors.HexColor("#BDC3C7")); c.setLineWidth(0.4)
            for il in range(0, int(tw), 8):
                c.line(tx+il, ty_bot, tx+il+6, ty_bot+6)
            # Dom (cima redondeada = cúpula de aislamiento)
            c.setFillColor(colors.HexColor("#CCD1D9")); c.setStrokeColor(colors.HexColor("#7F8C8D")); c.setLineWidth(1)
            c.roundRect(tx+tw*0.2, ty_top-4, tw*0.6, 10, 3, fill=1, stroke=1)
            # PRV + tuberías
            c.setStrokeColor(colors.HexColor("#7F8C8D")); c.setLineWidth(1)
            c.line(tx+tw/2, ty_top+6, tx+tw/2, ty_top+12)
            c.setFillColor(colors.HexColor("#C0392B")); c.setLineWidth(0)
            c.rect(tx+tw/2-3, ty_top+10, 6, 4, fill=1, stroke=0)

            # Etiquetas
            c.setFillColor(colors.HexColor("#2C3E50")); c.setFont("Helvetica-Bold", max(4.5, tw*0.095))
            short = tn.replace("TANQUE ","T").replace("TK ","T").replace(" BABOR","B").replace(" ESTRIBOR","E")
            c.drawCentredString(tx+tw/2, ty_bot + tank_inner_h*0.55, short)
            if pct > 0:
                txt_gnl = self.contrast_text(gnl_col) if pct > 0.01 else "#2C3E50"
                c.setFillColor(colors.HexColor(txt_gnl))
                c.setFont("Helvetica", max(4, tw*0.08))
                c.drawCentredString(tx+tw/2, ty_bot + tank_inner_h*0.35, f"{pct*100:.0f}%")
            if prod_name:
                c.setFillColor(colors.HexColor("#2C3E50")); c.setFont("Helvetica", max(3.5, tw*0.07))
                c.drawCentredString(tx+tw/2, hull_top-8, prod_name[:14])

        # Línea de flotación
        c.setStrokeColor(colors.HexColor("#2E86C1")); c.setLineWidth(1)
        c.setDash(5, 2); c.line(stern_x-8, mid_y, bow_x+10, mid_y); c.setDash()
        # Mastil
        c.setStrokeColor(colors.HexColor("#626567")); c.setLineWidth(1.2)
        c.line(bow_x-16, hull_top, bow_x-16, hull_top+26)
        c.line(bow_x-24, hull_top+18, bow_x-8, hull_top+18)
        c.setFillColor(colors.HexColor("#F4D03F")); c.setLineWidth(0)
        c.circle(bow_x-16, hull_top+26, 2, fill=1, stroke=0)

        c.restoreState()

    def dibujar_perfil_buque(self, c, x, y, width, height, title, tanks_data, ref_heights, water_levels, trim_sign):
        """PDF ship/tank profile drawing. Routes to specific renderers by tipo_medio."""
        tipo_nave = self.get_var("car_tipo_nave").get()
        etapa_key = 'inicial' if 'INICIAL' in title else 'final'
        tm = self.get_tipo_medio()

        # ── Non-maritime types: use ReportLab equivalent of TK drawings ──────
        if "TANQUE" in tm:
            self._pdf_draw_vertical_tank(c, x, y, width, height, etapa_key, title)
            return
        if tm == "ESFERA DE GAS":
            self._pdf_draw_spheres(c, x, y, width, height, etapa_key, title)
            return
        if "CAMION GAS" in tm:
            self._pdf_draw_pressure_truck(c, x, y, width, height, etapa_key, title)
            return
        if "CAMION" in tm:
            self._pdf_draw_liquid_truck(c, x, y, width, height, etapa_key, title)
            return
        if self.es_ducto():
            self._pdf_draw_pipeline(c, x, y, width, height, etapa_key, title)
            return
        if self.es_electrico():
            self._pdf_draw_electric(c, x, y, width, height, etapa_key, title)
            return
        _estilo_tq = "caja"
        if "GASERO" in tm or ("GLP" in tm and "CAMION" not in tm):
            _estilo_tq = "esfera"
        elif "METANERO" in tm or "GNL" in tm:
            _estilo_tq = "gnl"
        # ═══════════════════════════════════════════════════════════════════
        #  BUQUE / BARCAZA — perfil lateral estilo plano naval
        #  Casco esbelto y proporcionado, mar de fondo con flotación según
        #  calados reales (el asiento inclina la flotación), tanques con
        #  nivel de llenado, escalas de calado y vista de popa con escora.
        # ═══════════════════════════════════════════════════════════════════
        c.saveState()
        etapa = etapa_key
        es_barcaza = (tipo_nave == "BARCAZA")
        AZUL    = colors.HexColor("#1B3A5C")
        CASCO   = colors.HexColor("#22313F")
        CASCO_B = colors.HexColor("#101A22")
        ROJO    = colors.HexColor("#8E2F23")
        MAR     = colors.HexColor("#AED6F1")
        MAR2    = colors.HexColor("#85C1E9")
        MAR_LIN = colors.HexColor("#1A5276")
        GRIS    = colors.HexColor("#5D6D7E")

        # ── Datos de la medición ────────────────────────────────────────────
        c_proa = self.parse_float(self.get_var(f"{etapa}_Calados Proa").get() or "0")
        c_popa = self.parse_float(self.get_var(f"{etapa}_Calados Popa").get() or "0")
        if c_proa <= 0 and c_popa <= 0:
            c_proa = c_popa = 1.0
        puntal_m = max(1.0, max(c_proa, c_popa) * 1.45)   # profundidad estimada del casco

        # ── Layout: perfil (izq) + vista popa (der) ────────────────────────
        popa_w  = min(92, width * 0.15)
        px0, px1 = x, x + width - popa_w - 16
        keel_y  = y + 16
        hull_h  = max(34, height * 0.33)                  # casco esbelto (~1:12)
        deck_y  = keel_y + hull_h
        px_m    = hull_h / puntal_m
        stern_x = px0 + 46
        bow_x   = px1 - 52
        wl_st   = keel_y + min(c_popa, puntal_m * 0.92) * px_m
        wl_bw   = keel_y + min(c_proa, puntal_m * 0.92) * px_m

        # ── Título ─────────────────────────────────────────────────────────
        c.setFont("Helvetica-Bold", 8)
        c.setFillColor(AZUL)
        c.drawCentredString((px0 + px1) / 2, y + height - 8, title)

        # ── Mar de fondo (detrás del casco) ────────────────────────────────
        sea_top_st = wl_st + (wl_st - wl_bw) * 0.05
        sea_top_bw = wl_bw - (wl_st - wl_bw) * 0.05
        c.setFillColor(MAR)
        p_sea = c.beginPath()
        p_sea.moveTo(px0, sea_top_st); p_sea.lineTo(px1, sea_top_bw)
        p_sea.lineTo(px1, y + 8); p_sea.lineTo(px0, y + 8)
        p_sea.close()
        c.drawPath(p_sea, fill=1, stroke=0)
        c.setFillColor(MAR2)
        c.rect(px0, y + 8, px1 - px0, (min(sea_top_st, sea_top_bw) - y - 8) * 0.45, fill=1, stroke=0)
        c.saveState()
        c.setStrokeColor(colors.white); c.setFillAlpha(1); c.setStrokeAlpha(0.35); c.setLineWidth(0.7)
        for _vi in range(3):
            _vy = y + 10 + _vi * 4.5
            c.line(px0 + 20 + _vi * 40, _vy, px1 - 60 - _vi * 30, _vy)
        c.restoreState()

        # ── Bulbo de proa (detrás del casco, integrado a la roda) ─────────
        if not es_barcaza:
            _btip = bow_x + 27
            c.setFillColor(ROJO); c.setStrokeColor(colors.HexColor("#5B1A14")); c.setLineWidth(0.7)
            c.ellipse(_btip - 16, keel_y - 1.5, _btip + 7, keel_y + 5.5, fill=1, stroke=1)

        # ── Silueta del casco ──────────────────────────────────────────────
        p_hull = c.beginPath()
        if es_barcaza:
            rk = 20
            p_hull.moveTo(stern_x, deck_y)
            p_hull.lineTo(bow_x, deck_y)
            p_hull.lineTo(bow_x + rk, keel_y + hull_h * 0.42)
            p_hull.lineTo(bow_x + rk, keel_y + 2)
            p_hull.lineTo(bow_x - 8, keel_y)
            p_hull.lineTo(stern_x + 8, keel_y)
            p_hull.lineTo(stern_x - rk, keel_y + 2)
            p_hull.lineTo(stern_x - rk, keel_y + hull_h * 0.42)
            p_hull.close()
            bow_tip, stern_tip = bow_x + rk, stern_x - rk
        else:
            sheer = 4
            p_hull.moveTo(stern_x - 6, deck_y)                      # espejo de popa
            p_hull.lineTo(bow_x, deck_y + sheer)                    # cubierta con arrufo
            p_hull.curveTo(bow_x + 18, deck_y + sheer - 1,          # roda lanzada
                           bow_x + 27, wl_bw + 6,
                           bow_x + 25, wl_bw - 2)
            p_hull.curveTo(bow_x + 22, keel_y + 3,                  # entrada a quilla
                           bow_x + 12, keel_y,
                           bow_x - 10, keel_y)
            p_hull.lineTo(stern_x + 18, keel_y)                     # quilla
            p_hull.curveTo(stern_x + 6, keel_y + 1,                 # bovedilla
                           stern_x - 8, keel_y + hull_h * 0.22,
                           stern_x - 11, keel_y + hull_h * 0.42)
            p_hull.lineTo(stern_x - 13, deck_y)                     # espejo casi vertical
            p_hull.close()
            bow_tip, stern_tip = bow_x + 27, stern_x - 13
        c.setFillColor(CASCO); c.setStrokeColor(CASCO_B); c.setLineWidth(1)
        c.drawPath(p_hull, fill=1, stroke=1)

        # Obra viva (antifouling) recortada al casco, hasta la flotación
        c.saveState()
        c.clipPath(p_hull, stroke=0, fill=0)
        p_red = c.beginPath()
        p_red.moveTo(stern_tip - 6, keel_y - 8)
        p_red.lineTo(stern_tip - 6, wl_st + 2)
        p_red.lineTo(bow_tip + 6, wl_bw + 2)
        p_red.lineTo(bow_tip + 6, keel_y - 8)
        p_red.close()
        c.setFillColor(ROJO)
        c.drawPath(p_red, fill=1, stroke=0)
        c.setStrokeColor(colors.HexColor("#ECF0F1")); c.setLineWidth(1.3)
        c.line(stern_tip - 6, wl_st + 2.6, bow_tip + 6, wl_bw + 2.6)
        c.restoreState()

        # ── Bulbo, hélice y timón ──────────────────────────────────────────
        if not es_barcaza:
            prop_cy = keel_y + hull_h * 0.18
            c.setFillColor(colors.HexColor("#B7950B")); c.setStrokeColor(colors.HexColor("#7D6608"))
            c.setLineWidth(0.6)
            c.circle(stern_x - 8, prop_cy, 3.6, fill=1, stroke=1)
            c.setFillColor(GRIS); c.setStrokeColor(CASCO_B)
            p_tim = c.beginPath()
            p_tim.moveTo(stern_x - 13, prop_cy + 5); p_tim.lineTo(stern_x - 18, prop_cy + 3)
            p_tim.lineTo(stern_x - 18, prop_cy - 5); p_tim.lineTo(stern_x - 13, prop_cy - 3)
            p_tim.close()
            c.drawPath(p_tim, fill=1, stroke=1)

        # brillo sutil en la obra muerta (sensación de volumen)
        c.saveState()
        c.clipPath(p_hull, stroke=0, fill=0)
        c.setStrokeColor(colors.HexColor("#43596E")); c.setLineWidth(1.1)
        c.line(stern_tip, deck_y - 2.2, bow_tip, deck_y - 2.2 + (0 if es_barcaza else 3))
        c.restoreState()
        # ancla y escobén en la amura
        if not es_barcaza:
            _ay = (deck_y + max(wl_bw, wl_st)) / 2 + 6
            c.setFillColor(colors.HexColor("#0B1218"))
            c.circle(bow_x + 9, _ay, 1.9, fill=1, stroke=0)
            c.setStrokeColor(colors.HexColor("#0B1218")); c.setLineWidth(0.9)
            c.line(bow_x + 9, _ay - 1.5, bow_x + 7.5, _ay - 6)
            c.line(bow_x + 5.6, _ay - 4.6, bow_x + 9.4, _ay - 4.6)

        # ── Compartimentos (tanques) dentro del casco ─────────────────────
        target_side = "BABOR" if "BABOR" in title else "ESTRIBOR"
        tanks_to_draw = [t for t in self.lista_tanques
                         if target_side in t.upper()
                         or ("BABOR" not in t.upper() and "ESTRIBOR" not in t.upper())]
        carbs_to_draw = [cn for cn in self.lista_carbonera
                         if target_side in cn.upper()
                         or ("BABOR" not in cn.upper() and "ESTRIBOR" not in cn.upper())]

        acc_w  = 0 if es_barcaza else 58
        carb_w = 22 if carbs_to_draw else 0
        tz0    = stern_x + 2 + acc_w + carb_w + 3
        tz1    = bow_x - (10 if es_barcaza else 24)
        top_t  = deck_y - 2.5
        bot_t  = keel_y + 5

        def _dibujar_compart(cx0, cw, nombre, corto, es_carb=False):
            s_corr  = self.parse_float(self.get_var(f"{etapa}_{nombre}_s_corr").get())
            alt_ref = self.parse_float(self.get_var(f"{etapa}_{nombre}_alt_ref").get())
            agua_mm = self.parse_float(self.get_var(f"{etapa}_{nombre}_agua_s_real").get())
            vol_str = self.get_var(f"{etapa}_{nombre}_vol_nat_prod").get()
            prod    = self.get_var(f"{etapa}_{nombre}_prod_name").get()
            pct   = max(0.0, min(1.0, s_corr / alt_ref)) if alt_ref > 0 else 0.0
            pagua = max(0.0, min(pct, agua_mm / alt_ref)) if alt_ref > 0 else 0.0
            th = top_t - bot_t
            c.setFillColor(colors.HexColor("#FDFEFE")); c.setStrokeColor(colors.HexColor("#4D5656"))
            c.setLineWidth(0.7)
            c.rect(cx0, bot_t, cw, th, fill=1, stroke=1)
            if pct > 0.003:
                try:    col_hex, _ = self.get_prod_color(nombre, etapa)
                except Exception: col_hex = "#F1C40F"
                fh = max(1.2, th * pct)
                c.setFillColor(colors.HexColor(col_hex))
                c.rect(cx0 + 0.6, bot_t + 0.6, cw - 1.2, fh - 0.6, fill=1, stroke=0)
                c.setStrokeColor(colors.HexColor("#566573")); c.setLineWidth(0.4)
                c.line(cx0 + 0.6, bot_t + fh, cx0 + cw - 0.6, bot_t + fh)
            if pagua > 0.004:
                c.setFillColor(colors.HexColor("#1A5276"))
                c.rect(cx0 + 0.6, bot_t + 0.6, cw - 1.2, max(1, th * pagua - 0.6), fill=1, stroke=0)
            # etiqueta: chip blanco arriba del compartimento
            angosto = cw < 40
            chip_h = 7 if angosto else 12.5
            chip_y = top_t - chip_h - 1
            c.setFillAlpha(0.92)
            c.setFillColor(colors.white); c.setStrokeColor(colors.HexColor("#95A5A6")); c.setLineWidth(0.4)
            c.roundRect(cx0 + 1, chip_y, cw - 2, chip_h, 1.5, fill=1, stroke=1)
            c.setFillAlpha(1)
            c.setFillColor(AZUL)
            if angosto:
                c.setFont("Helvetica-Bold", 4)
                c.drawCentredString(cx0 + cw / 2, chip_y + 2, f"{corto[:8]} {pct*100:.0f}%")
            else:
                c.setFont("Helvetica-Bold", 5)
                c.drawCentredString(cx0 + cw / 2, chip_y + chip_h - 5, corto[:16])
                c.setFillColor(colors.HexColor("#273746"))
                c.setFont("Helvetica", 4.4)
                l2 = f"{pct*100:.0f}%"
                if vol_str: l2 += f" · {vol_str} L"
                if prod: l2 = f"{prod[:9]} · " + l2
                _maxc = max(6, int(cw / 2.4))   # truncar al ancho del tanque
                c.drawCentredString(cx0 + cw / 2, chip_y + 2.2, l2[:_maxc])

        def _dibujar_gas_tank(cx0, cw, nombre, corto):
            """Tanque de gasero (esfera) o metanero (domo GNL) sobre cubierta."""
            pct, _w = self._get_fill_pct(nombre, etapa)
            vol_liq = self.parse_float(self.get_var(f"{etapa}_{nombre}_vol_liq").get() or "0")
            _ilustrativo = False
            if pct <= 0 and vol_liq > 0:
                pct = 0.62; _ilustrativo = True
            cxm = cx0 + cw / 2
            AMBAR = colors.HexColor("#E67E22")
            if _estilo_tq == "esfera":
                r = min(cw / 2 - 2, hull_h * 0.62)
                cy = deck_y + r * 0.30
                c.setFillColor(colors.HexColor("#FDFEFE")); c.setStrokeColor(colors.HexColor("#4D5656"))
                c.setLineWidth(0.9)
                c.circle(cxm, cy, r, fill=1, stroke=1)
                if pct > 0.01:
                    c.saveState()
                    p_c = c.beginPath(); p_c.circle(cxm, cy, r - 0.6)
                    c.clipPath(p_c, stroke=0, fill=0)
                    c.setFillColor(AMBAR)
                    c.rect(cxm - r, cy - r, 2 * r, 2 * r * pct, fill=1, stroke=0)
                    c.setStrokeColor(colors.HexColor("#935116")); c.setLineWidth(0.4)
                    c.line(cxm - r, cy - r + 2 * r * pct, cxm + r, cy - r + 2 * r * pct)
                    c.restoreState()
                # ecuador y válvula superior
                c.setStrokeColor(colors.HexColor("#85929E")); c.setLineWidth(0.4)
                c.ellipse(cxm - r, cy - r * 0.22, cxm + r, cy + r * 0.22, fill=0, stroke=1)
                c.setFillColor(colors.HexColor("#5D6D7E"))
                c.rect(cxm - 1.6, cy + r, 3.2, 3, fill=1, stroke=0)
            else:
                # domo GNL: prisma con tapa redondeada que asoma sobre cubierta
                d_top = deck_y + hull_h * 0.36
                c.setFillColor(colors.HexColor("#FDFEFE")); c.setStrokeColor(colors.HexColor("#4D5656"))
                c.setLineWidth(0.9)
                c.roundRect(cx0 + 1, bot_t, cw - 2, d_top - bot_t, min(9, cw * 0.28), fill=1, stroke=1)
                if pct > 0.01:
                    c.saveState()
                    p_c = c.beginPath()
                    p_c.roundRect(cx0 + 1.6, bot_t + 0.6, cw - 3.2, d_top - bot_t - 1.2, min(8, cw * 0.26))
                    c.clipPath(p_c, stroke=0, fill=0)
                    c.setFillColor(AMBAR)
                    c.rect(cx0, bot_t, cw, (d_top - bot_t) * pct, fill=1, stroke=0)
                    c.restoreState()
            # chip de datos bajo cubierta
            chip_h = 11
            chip_y = deck_y - chip_h - 4
            c.setFillAlpha(0.92)
            c.setFillColor(colors.white); c.setStrokeColor(colors.HexColor("#95A5A6")); c.setLineWidth(0.4)
            c.roundRect(cx0 + 2, chip_y, cw - 4, chip_h, 1.5, fill=1, stroke=1)
            c.setFillAlpha(1)
            c.setFillColor(AZUL); c.setFont("Helvetica-Bold", 4.6)
            c.drawCentredString(cxm, chip_y + chip_h - 4.6, corto[:14])
            c.setFillColor(colors.HexColor("#273746")); c.setFont("Helvetica", 4.2)
            if vol_liq > 0:
                _l2g = f"{vol_liq:g} m3" + ("" if _ilustrativo else f" · {pct*100:.0f}%")
            else:
                _l2g = f"{pct*100:.0f}%"
            c.drawCentredString(cxm, chip_y + 2, _l2g[:max(6, int(cw / 2.4))])

        n_t = len(tanks_to_draw)
        if n_t and tz1 - tz0 > 30:
            gap = 2.5 if _estilo_tq == "caja" else 6
            tw = (tz1 - tz0 - gap * (n_t - 1)) / n_t
            for i, t_name in enumerate(tanks_to_draw):
                corto = t_name.replace("BABOR", "B").replace("ESTRIBOR", "E").strip()
                if _estilo_tq == "caja":
                    _dibujar_compart(tz0 + i * (tw + gap), tw, t_name, corto)
                else:
                    _dibujar_gas_tank(tz0 + i * (tw + gap), tw, t_name, corto)
            # baranda de cubierta sobre la zona de carga (solo cajas)
            if _estilo_tq == "caja" and not es_barcaza:
                c.setStrokeColor(colors.HexColor("#808B96")); c.setLineWidth(0.5)
                c.line(tz0, deck_y + 3.2, tz1, deck_y + 3.2 + sheer * 0.6)
                _np = int((tz1 - tz0) / 14)
                for _pi in range(_np + 1):
                    _pxp = tz0 + _pi * (tz1 - tz0) / max(1, _np)
                    _pyp = deck_y + (_pxp - tz0) / max(1, (tz1 - tz0)) * sheer * 0.6
                    c.line(_pxp, _pyp + 0.5, _pxp, _pyp + 3.2)
        if carbs_to_draw:
            for cn in carbs_to_draw[:1]:
                corto = cn.replace("CARBONERA", "CB").replace("BABOR", "B").replace("ESTRIBOR", "E").strip()
                _dibujar_compart(stern_x + 2 + acc_w + 1, carb_w, cn, corto, es_carb=True)

        # ── Superestructura (a popa) ───────────────────────────────────────
        if not es_barcaza:
            ax0 = stern_x + 2
            aw  = acc_w - 6
            nh  = 7.5
            for ni in range(3):
                yy = deck_y + ni * nh
                shr = ni * 2
                c.setFillColor(colors.HexColor("#F4F6F7")); c.setStrokeColor(colors.HexColor("#909BA5"))
                c.setLineWidth(0.5)
                c.rect(ax0 + shr, yy, aw - shr * 2, nh, fill=1, stroke=1)
                c.setFillColor(colors.HexColor("#5DADE2"))
                nw = max(2, int((aw - shr * 2 - 6) // 6))
                for wi in range(nw):
                    c.rect(ax0 + shr + 3.5 + wi * 6, yy + nh * 0.34, 3.4, nh * 0.34, fill=1, stroke=0)
            by = deck_y + 3 * nh
            c.setFillColor(colors.HexColor("#EAECEE")); c.setStrokeColor(colors.HexColor("#909BA5"))
            c.rect(ax0 + 5, by, aw - 10, 6, fill=1, stroke=1)
            c.setFillColor(colors.HexColor("#2E4053"))
            c.rect(ax0 + 6.2, by + 1.8, aw - 12.4, 2.8, fill=1, stroke=0)
            # chimenea
            fx = ax0 + aw - 10
            c.setFillColor(AZUL); c.setStrokeColor(CASCO_B); c.setLineWidth(0.5)
            p_fun = c.beginPath()
            p_fun.moveTo(fx, deck_y + nh * 1.6); p_fun.lineTo(fx + 8.5, deck_y + nh * 1.6)
            p_fun.lineTo(fx + 7.2, by + 10); p_fun.lineTo(fx + 1.3, by + 10)
            p_fun.close()
            c.drawPath(p_fun, fill=1, stroke=1)
            c.setFillColor(colors.white)
            c.rect(fx + 1.9, by + 5.4, 4.8, 2.2, fill=1, stroke=0)
            # mástil radar + luz
            mx = ax0 + 13
            c.setStrokeColor(colors.HexColor("#424949")); c.setLineWidth(0.7)
            c.line(mx, by + 6, mx, by + 13)
            c.line(mx - 3.5, by + 10.5, mx + 3.5, by + 10.5)
            c.setFillColor(colors.HexColor("#E74C3C")); c.circle(mx, by + 13.5, 0.9, fill=1, stroke=0)
            # castillo y mástil de proa
            c.setFillColor(colors.HexColor("#D5DBDB")); c.setStrokeColor(colors.HexColor("#909BA5"))
            c.setLineWidth(0.5)
            c.rect(bow_x - 18, deck_y + sheer, 15, 3.6, fill=1, stroke=1)
            c.setStrokeColor(colors.HexColor("#424949")); c.setLineWidth(0.7)
            c.line(bow_x - 4, deck_y + sheer + 3, bow_x - 4, deck_y + sheer + 13)
            c.line(bow_x - 4, deck_y + sheer + 10, bow_x + 5, deck_y + sheer + 6.5)
        else:
            ax0 = stern_x + 2
            c.setFillColor(colors.HexColor("#F4F6F7")); c.setStrokeColor(colors.HexColor("#909BA5"))
            c.setLineWidth(0.5)
            c.rect(ax0, deck_y, 24, 8, fill=1, stroke=1)
            c.rect(ax0 + 3, deck_y + 8, 18, 7, fill=1, stroke=1)
            c.setFillColor(colors.HexColor("#5DADE2"))
            for wi in range(3):
                c.rect(ax0 + 4.5 + wi * 5.5, deck_y + 10, 3.6, 3.2, fill=1, stroke=0)
            c.setStrokeColor(colors.HexColor("#424949")); c.setLineWidth(0.7)
            c.line(ax0 + 12, deck_y + 15, ax0 + 12, deck_y + 21)
            c.setFillColor(colors.HexColor("#E74C3C")); c.circle(ax0 + 12, deck_y + 21.5, 0.9, fill=1, stroke=0)

        # nombre en la amura
        _nm = (self.get_var("car_buque").get() or "").upper()[:22]
        if _nm and not es_barcaza:
            c.setFont("Helvetica-Bold", 4.4)
            c.setFillColor(colors.HexColor("#BDC3C7"))
            c.drawRightString(bow_x - 8, (deck_y + max(wl_bw, wl_st)) / 2 + 2.5, _nm)

        # ── Línea de flotación sobre el casco + olas ───────────────────────
        c.setStrokeColor(MAR_LIN); c.setLineWidth(1.1)
        c.line(px0, sea_top_st, px1, sea_top_bw)
        c.setLineWidth(0.55); c.setStrokeColor(colors.HexColor("#5499C7"))
        for wxi in range(7):
            wx = px0 + 14 + wxi * (px1 - px0 - 28) / 6.0
            if stern_tip - 14 < wx < bow_tip + 14: continue
            wy = sea_top_st + (sea_top_bw - sea_top_st) * ((wx - px0) / max(1, px1 - px0)) - 2.6
            c.arc(wx - 5, wy - 1.8, wx + 5, wy + 1.8, 200, 140)

        # ── Escalas de calado ──────────────────────────────────────────────
        def _escala(ex, calado, wl_y, lado):
            c.setStrokeColor(colors.HexColor("#34495E")); c.setLineWidth(0.7)
            c.line(ex, keel_y, ex, deck_y + 3)
            m = 0
            while m <= puntal_m + 0.01:
                yy = keel_y + m * px_m
                mayor = (m % 2 == 0)
                tick = 3 if mayor else 1.7
                c.setLineWidth(0.6 if mayor else 0.35)
                c.line(ex - (tick if lado == "izq" else 0), yy, ex + (tick if lado == "der" else 0), yy)
                if mayor and m > 0:
                    c.setFont("Helvetica", 3.8)
                    c.setFillColor(colors.HexColor("#34495E"))
                    if lado == "izq": c.drawRightString(ex - 4, yy - 1.3, f"{m}")
                    else: c.drawString(ex + 4, yy - 1.3, f"{m}")
                m += 1
            c.setFillColor(colors.HexColor("#C0392B"))
            p_fl = c.beginPath()
            dx = -1 if lado == "izq" else 1
            p_fl.moveTo(ex + dx * 2.5, wl_y)
            p_fl.lineTo(ex + dx * 8, wl_y + 2.6); p_fl.lineTo(ex + dx * 8, wl_y - 2.6)
            p_fl.close()
            c.drawPath(p_fl, fill=1, stroke=0)
            c.setFont("Helvetica-Bold", 5)
            c.setFillColor(colors.HexColor("#C0392B"))
            if lado == "izq": c.drawRightString(ex - 4, wl_y + 4, f"{calado:.2f} m")
            else: c.drawString(ex + 4, wl_y + 4, f"{calado:.2f} m")
        _escala(stern_tip - 13, c_popa, wl_st, "izq")
        _escala(bow_tip + 13, c_proa, wl_bw, "der")

        # ── Anotaciones ────────────────────────────────────────────────────
        c.setFont("Helvetica-Bold", 5.5); c.setFillColor(GRIS)
        c.drawString(bow_x + 4, y + 1.5, "PROA →")
        c.drawRightString(stern_x - 4, y + 1.5, "← POPA")
        _tr = trim_sign
        _tr_lbl = "apopado" if _tr > 0.005 else ("aproado" if _tr < -0.005 else "adrizado")
        c.setFont("Helvetica", 5.5); c.setFillColor(MAR_LIN)
        c.drawCentredString((px0 + px1) / 2, y + 1.5,
                            f"Asiento: {_tr:+.2f} m ({_tr_lbl})   |   Calado medio: {(c_proa+c_popa)/2:.2f} m")

        # ── Vista de popa (sección transversal) con escora ─────────────────
        vx0 = px1 + 16
        vw  = popa_w - 6
        vy0 = y + 16
        vh  = height - 42
        c.setFont("Helvetica-Bold", 6); c.setFillColor(AZUL)
        c.drawCentredString(vx0 + vw / 2, vy0 + vh + 6, "VISTA POPA")
        lista_v = self.parse_float(self.get_var(f"{etapa}_Lista").get() or "0")
        c_bab = self.parse_float(self.get_var(f"{etapa}_Calados Babor").get() or "0")
        c_est = self.parse_float(self.get_var(f"{etapa}_Calados Estribor").get() or "0")
        cal_med2 = (c_bab + c_est) / 2 if (c_bab or c_est) else (c_proa + c_popa) / 2
        bw2 = vw * 0.26                     # semimanga
        bh2 = vh * 0.44                     # semi-altura de la sección
        scx = vx0 + vw / 2
        scy = vy0 + vh * 0.52
        wl_sec = scy - bh2 + min(cal_med2, puntal_m) / puntal_m * (2 * bh2) * 0.92
        # mar de fondo
        c.setFillColor(MAR)
        c.rect(vx0 - 2, vy0 - 2, vw + 4, max(4, wl_sec - vy0 + 2), fill=1, stroke=0)
        # sección con escora
        ang = max(-8.0, min(8.0, lista_v * 5))
        c.saveState()
        c.translate(scx, scy); c.rotate(ang); c.translate(-scx, -scy)
        p_sec = c.beginPath()
        p_sec.moveTo(scx - bw2, scy + bh2)
        p_sec.lineTo(scx - bw2, scy - bh2 * 0.30)
        p_sec.curveTo(scx - bw2, scy - bh2 * 0.92, scx - bw2 * 0.5, scy - bh2, scx, scy - bh2)
        p_sec.curveTo(scx + bw2 * 0.5, scy - bh2, scx + bw2, scy - bh2 * 0.92, scx + bw2, scy - bh2 * 0.30)
        p_sec.lineTo(scx + bw2, scy + bh2)
        p_sec.close()
        c.setFillColor(CASCO); c.setStrokeColor(CASCO_B); c.setLineWidth(0.9)
        c.drawPath(p_sec, fill=1, stroke=1)
        c.saveState()
        c.clipPath(p_sec, stroke=0, fill=0)
        c.setFillColor(ROJO)
        c.rect(scx - bw2 - 3, scy - bh2 - 3, bw2 * 2 + 6, (wl_sec - (scy - bh2)) + 3, fill=1, stroke=0)
        c.setStrokeColor(colors.HexColor("#ECF0F1")); c.setLineWidth(1.1)
        c.line(scx - bw2 - 3, wl_sec + 1.4, scx + bw2 + 3, wl_sec + 1.4)
        c.restoreState()
        # caseta con camber en cubierta
        c.setFillColor(colors.HexColor("#F4F6F7")); c.setStrokeColor(colors.HexColor("#909BA5"))
        c.setLineWidth(0.5)
        c.rect(scx - bw2 * 0.45, scy + bh2, bw2 * 0.9, 6, fill=1, stroke=1)
        c.setFillColor(colors.HexColor("#5DADE2"))
        c.rect(scx - bw2 * 0.32, scy + bh2 + 1.8, bw2 * 0.64, 2.4, fill=1, stroke=0)
        # timón bajo el casco
        c.setStrokeColor(CASCO_B); c.setLineWidth(1)
        c.line(scx, scy - bh2, scx, scy - bh2 - 5)
        c.restoreState()
        # línea de flotación por encima (horizontal — la escora se ve contra el agua)
        c.setStrokeColor(MAR_LIN); c.setLineWidth(1)
        c.line(vx0 - 2, wl_sec, vx0 + vw + 2, wl_sec)
        c.setFont("Helvetica-Bold", 5); c.setFillColor(AZUL)
        c.drawString(vx0, vy0 + vh - 2, "BABOR")
        c.drawRightString(vx0 + vw, vy0 + vh - 2, "ESTRIBOR")
        c.setFont("Helvetica", 4.8); c.setFillColor(colors.HexColor("#34495E"))
        _esc_lbl = f"Escora: {lista_v:+.2f} m"
        if c_bab or c_est: _esc_lbl += f"  (B {c_bab:.2f} / E {c_est:.2f})"
        c.drawCentredString(vx0 + vw / 2, vy0 - 9, _esc_lbl)

        c.restoreState()

    def _celda_sin_marcador(self, var_key):
        """Valor de una variable para las tablas del PDF, ocultando los marcadores
        heredados tipo '[trim 2col]' o '[5pts]' que versiones previas dejaban en los
        campos de interpolación de 2 puntos (prod_s1, agua_s1, ...). El cálculo del
        volumen ya los ignora (ver calculos._pfm); acá evitamos que se filtren como
        texto a las columnas SOND/LTS de la planilla. Devuelve '' si es un marcador."""
        v = self.get_var(var_key).get()
        return "" if v.strip().startswith("[") else v

    def generar_reporte_tecnico_global(self, suffix, output_folder, shared_canvas=None):
        clean_name = self.clean_filename(self.get_var('car_buque').get())
        filename = f"Reporte_Tecnico_Global_{clean_name}_{datetime.now().strftime('%Y%m%d')}.pdf"
        full_path = os.path.join(output_folder, filename)
        
        if shared_canvas:
            c = shared_canvas
            w, h = landscape(A4)
        else:
            try: c = canvas.Canvas(full_path, pagesize=landscape(A4))
            except: return None
            w, h = landscape(A4)
        
        def draw_logo_header(title_suffix, etapa=None):
            try:
                raw_b64 = ICON_REPORT_B64.strip().replace("\n", "").replace("\r", "")
                icon_data = base64.b64decode(raw_b64)
                img = ImageReader(BytesIO(icon_data))
                c.drawImage(img, 30, h-70, width=50, height=50, preserveAspectRatio=True, mask=None)
            except: 
                c.saveState()
                c.rect(30, h-70, 50, 50)
                c.drawString(40, h-45, "ARCA")
                c.restoreState()

            c.setFont("Helvetica-Bold", 14)
            c.drawCentredString(w/2, h-40, "ARCA - DGA")
            
            # TITULO DINAMICO
            _tm_pl = self.get_tipo_medio()
            if "BARCAZA" in _tm_pl: base_title = "PLANILLA DE SONDAJES - BARCAZA"
            elif "CAMION GAS" in _tm_pl: base_title = "PLANILLA DE MEDICION - CAMION GAS/GLP"
            elif "CAMION" in _tm_pl: base_title = "PLANILLA DE MEDICION - CAMION CISTERNA"
            elif "TANQUE FIJO" in _tm_pl: base_title = "PLANILLA DE SONDAJES - TANQUE FIJO"
            elif "TANQUE FLOTANTE" in _tm_pl: base_title = "PLANILLA DE SONDAJES - TANQUE FLOTANTE"
            elif _tm_pl == "OLEODUCTO": base_title = "ACTA DE MEDICION - OLEODUCTO"
            elif _tm_pl == "POLIDUCTO": base_title = "ACTA DE MEDICION - POLIDUCTO"
            elif _tm_pl == "GASODUCTO": base_title = "ACTA DE MEDICION - GASODUCTO"
            elif _tm_pl == "MEDICION ELECTRICA": base_title = "ACTA DE MEDICION ELECTRICA"
            elif "GASERO" in _tm_pl or ("GLP" in _tm_pl and "CAMION" not in _tm_pl): base_title = "PLANILLA DE SONDAJES - BUQUE GASERO/GLP"
            elif "METANERO" in _tm_pl or "GNL" in _tm_pl: base_title = "PLANILLA DE SONDAJES - BUQUE METANERO/GNL"
            elif "QUIMIQUERO" in _tm_pl: base_title = "PLANILLA DE SONDAJES - BUQUE QUIMIQUERO"
            elif "ESFERA" in _tm_pl: base_title = "PLANILLA DE MEDICIÓN - ESFERA DE GAS A PRESIÓN"
            elif "DRAFT SURVEY" in _tm_pl: base_title = "PLANILLA DE SONDAJES - DRAFT SURVEY"
            else: base_title = "PLANILLA DE SONDAJES DE TANQUES DE BUQUES"
            
            c.setFont("Helvetica-Bold", 10)
            c.drawCentredString(w/2, h-55, f"{base_title} - {title_suffix}")
            
            if etapa:
                fecha = self.get_var(f"{etapa}_Fecha").get()
                hora  = self.get_var(f"{etapa}_Hora").get()
                c.setFont("Helvetica", 9)
                # ── Mostrar calados SOLO para tipos marítimos con calados reales ──
                _tmh = self.get_tipo_medio()
                _es_mar_h = _tmh in ("BUQUE","BARCAZA","BUQUE QUIMIQUERO","DRAFT SURVEY",
                                     "BUQUE GASERO/GLP","BUQUE METANERO/GNL")
                if _es_mar_h:
                    c_proa    = self.get_var(f"{etapa}_Calados Proa").get()
                    c_popa    = self.get_var(f"{etapa}_Calados Popa").get()
                    trim      = self.get_var(f"{etapa}_Trimación").get()
                    c_babor   = self.get_var(f"{etapa}_Calados Babor").get()
                    c_estribor= self.get_var(f"{etapa}_Calados Estribor").get()
                    asiento   = self.get_var(f"{etapa}_Lista").get()
                    header_info = (f"FECHA: {fecha}  HORA: {hora}  |  "
                                   f"CALADO PROA: {c_proa}  |  CALADO POPA: {c_popa}  |  "
                                   f"TRIM: {trim}  |  BABOR: {c_babor}  |  "
                                   f"ESTRIBOR: {c_estribor}  |  ESCORA: {asiento}")
                else:
                    header_info = f"FECHA: {fecha}  |  HORA: {hora}  |  {_tmh}"
                c.drawCentredString(w/2, h-75, header_info)
        
        def draw_signatures_2_lines():
            y_sig = 40
            c.setLineWidth(1)
            c.setFillColor(colors.black)
            c.line(100, y_sig, 300, y_sig)
            c.drawCentredString(200, y_sig-12, "Aduana")
            c.line(500, y_sig, 700, y_sig)
            c.drawCentredString(600, y_sig-12, "Interesado")

        all_tanks = self.lista_tanques + self.lista_carbonera
        
        # 1. TABLA INICIAL
        _tm_pdf = self.get_tipo_medio()
        _es_tie_pdf = self.es_tierra()
        _es_cam_pdf = self.es_camion()
        _es_gas_pdf = self.es_gasero()
        _es_duc_pdf = self.es_ducto()
        _es_elec_pdf = self.es_electrico()
        _es_cgb_pdf = self.es_camion_gas()
        _es_esf_pdf = self.es_esfera()
        if _es_duc_pdf:
            draw_logo_header("ACTA DE MEDICION - DUCTO", "inicial")
            headers = ["TRAMO/PUNTO", "PRODUCTO", "CONT.INI", "CONT.FIN", "VOL.LIN(m3)", "P(kPa)", "T(C)", "Z", "VOL.BASE(m3)", "CORIOLIS(kg)"]
            x_pos = [50, 120, 195, 255, 315, 370, 415, 455, 505, 595]
        elif _es_elec_pdf:
            draw_logo_header("ACTA DE MEDICION ELECTRICA", "inicial")
            headers = ["PUNTO", "INI.kWh Act", "FIN.kWh Act", "kWh Act", "INI.kWh Rea", "FIN.kWh Rea", "kWh Rea", "cos fi", "V", "A"]
            x_pos = [50, 115, 180, 245, 295, 355, 415, 465, 510, 550]
        elif _es_esf_pdf:
            draw_logo_header("DETALLE TÉCNICO - ESFERA DE GAS - INICIAL", "inicial")
            headers = ["ESFERA", "PRODUCTO", "P(kPa)", "T(°C)", "DENS", "VOL.LIQ", "FASE", "VOL.NAT", "Z", "MASA(kg)"]
            x_pos = [50, 130, 210, 270, 330, 390, 450, 510, 575, 640]
        elif _es_gas_pdf:
            draw_logo_header("DETALLE TÉCNICO - BUQUE GASERO - INICIAL", "inicial")
            headers = ["TANQUE", "PRODUCTO", "P(kPa)", "T(°C)", "DENS.LIQ", "VOL.LIQ", "FASE", "VOL.NAT", "Z", "MASA(kg)"]
            x_pos = [50, 130, 210, 270, 330, 390, 450, 510, 575, 640]
        elif _es_tie_pdf or _es_cam_pdf or _es_cgb_pdf:
            draw_logo_header("DETALLE TECNICO - INICIAL (TIERRA/CAMION)", "inicial")
            headers = ["TANQUE", "PRODUCTO", "N° UTI", "ALT REF", "SONDAJE", "VOL.BRUTO", "AGUA", "S.CORR", "TEMP", "LTS NAT"]
            x_pos = [50, 120, 210, 265, 310, 365, 420, 480, 545, 605]
        else:
            draw_logo_header("DETALLE TÉCNICO - INICIAL PRODUCTO", "inicial")
            headers = ["TANQUE", "PRODUCTO", "N° UTI", "ALT REF", "SOND 1", "LTS 1", "SOND 2", "LTS 2", "DESC", "CORREGIDO", "TEMP", "LTS NAT"]
            x_pos = [50, 130, 230, 280, 330, 380, 430, 480, 530, 580, 650, 715]
        y = h - 110
        c.setFont("Helvetica-Bold", 8)
        for i, txt in enumerate(headers): c.drawString(x_pos[i], y, txt)
        y -= 15
        c.setFont("Helvetica", 8)
        
        for tk_name in all_tanks:
            if _es_duc_pdf:
                vals = [tk_name,
                    self.get_var(f"inicial_{tk_name}_prod_name").get(),
                    self.get_var(f"inicial_{tk_name}_cont_ini").get(),
                    self.get_var(f"inicial_{tk_name}_cont_fin").get(),
                    self.get_var(f"inicial_{tk_name}_vol_linea").get(),
                    self.get_var(f"inicial_{tk_name}_P_lin").get() or self.get_var("car_presion_op").get(),
                    self.get_var(f"inicial_{tk_name}_T_lin").get() or self.get_var("car_temp_op").get(),
                    self.get_var(f"inicial_{tk_name}_Z").get(),
                    self.get_var(f"inicial_{tk_name}_vol_base").get(),
                    self.get_var(f"inicial_{tk_name}_masa_coriolis").get()]
            elif _es_elec_pdf:
                vals = [tk_name,
                    self.get_var(f"inicial_{tk_name}_el_ini_act").get(),
                    self.get_var(f"inicial_{tk_name}_el_fin_act").get(),
                    self.get_var(f"inicial_{tk_name}_el_kwh_act").get(),
                    self.get_var(f"inicial_{tk_name}_el_ini_rea").get(),
                    self.get_var(f"inicial_{tk_name}_el_fin_rea").get(),
                    self.get_var(f"inicial_{tk_name}_el_kwh_rea").get(),
                    self.get_var(f"inicial_{tk_name}_el_fp").get(),
                    self.get_var(f"inicial_{tk_name}_el_V").get(),
                    self.get_var(f"inicial_{tk_name}_el_A").get()]
            elif _es_esf_pdf or _es_gas_pdf:
                vals = [tk_name,
                    self.get_var(f"inicial_{tk_name}_prod_name").get(),
                    self.get_var(f"inicial_{tk_name}_P_lin").get() or self.get_var("car_presion_op").get(),
                    self.get_var(f"inicial_{tk_name}_temp").get(),
                    self.get_var(f"inicial_{tk_name}_dens_lab").get(),
                    self.get_var(f"inicial_{tk_name}_vol_liq").get() or self.get_var(f"inicial_{tk_name}_vol_bruto").get(),
                    self.get_var(f"inicial_{tk_name}_fase").get(),
                    self.get_var(f"inicial_{tk_name}_vol_nat_prod").get(),
                    self.get_var(f"inicial_{tk_name}_Z").get(),
                    self.get_var(f"inicial_{tk_name}_masa_kg").get()]
            elif _es_tie_pdf or _es_cam_pdf or _es_cgb_pdf:
                vals = [tk_name,
                    self.get_var(f"inicial_{tk_name}_prod_name").get(),
                    self.get_var(f"inicial_{tk_name}_num_uti").get(),
                    self.get_var(f"inicial_{tk_name}_alt_ref").get(),
                    self.get_var(f"inicial_{tk_name}_s_tierra").get(),
                    self.get_var(f"inicial_{tk_name}_vol_bruto").get(),
                    self.get_var(f"inicial_{tk_name}_vol_nat_agua").get(),
                    self.get_var(f"inicial_{tk_name}_s_corr").get(),
                    self.get_var(f"inicial_{tk_name}_temp").get(),
                    self.get_var(f"inicial_{tk_name}_vol_nat_prod").get()]
            else:
                vals = [tk_name, self.get_var(f"inicial_{tk_name}_prod_name").get(), self.get_var(f"inicial_{tk_name}_num_uti").get(), self.get_var(f"inicial_{tk_name}_alt_ref").get(), self._celda_sin_marcador(f"inicial_{tk_name}_prod_s1"), self._celda_sin_marcador(f"inicial_{tk_name}_prod_l1"), self._celda_sin_marcador(f"inicial_{tk_name}_prod_s2"), self._celda_sin_marcador(f"inicial_{tk_name}_prod_l2"), self.get_var(f"inicial_{tk_name}_desc_tubo").get(), self.get_var(f"inicial_{tk_name}_s_corr").get(), self.get_var(f"inicial_{tk_name}_temp").get(), self.get_var(f"inicial_{tk_name}_vol_nat_prod").get()]
            for i, v in enumerate(vals):
                if i < len(x_pos): c.drawString(x_pos[i], y, str(v))
            y -= 12
            if y < 80:
                draw_signatures_2_lines()
                c.showPage()
                if _es_duc_pdf: _cont_lbl = "ACTA DE MEDICION - DUCTO (CONT.)"
                elif _es_elec_pdf: _cont_lbl = "ACTA DE MEDICION ELECTRICA (CONT.)"
                elif _es_esf_pdf: _cont_lbl = "DETALLE TÉCNICO - ESFERA DE GAS (CONT.)"
                elif _es_gas_pdf: _cont_lbl = "DETALLE TÉCNICO - BUQUE GASERO (CONT.)"
                elif _es_tie_pdf or _es_cam_pdf or _es_cgb_pdf: _cont_lbl = "DETALLE TECNICO - INICIAL (CONT.)"
                else: _cont_lbl = "DETALLE TÉCNICO - INICIAL PRODUCTO (CONT.)"
                draw_logo_header(_cont_lbl, "inicial")
                y = h - 110
        
        draw_signatures_2_lines()
        c.showPage()
        
        # 2. TABLA FINAL
        if _es_duc_pdf: _lbl_final = "ACTA DE MEDICION - DUCTO (FINAL)"
        elif _es_elec_pdf: _lbl_final = "ACTA DE MEDICION ELECTRICA (FINAL)"
        elif _es_esf_pdf: _lbl_final = "DETALLE TÉCNICO - ESFERA DE GAS (FINAL)"
        elif _es_gas_pdf: _lbl_final = "DETALLE TÉCNICO - BUQUE GASERO (FINAL)"
        elif _es_tie_pdf or _es_cam_pdf or _es_cgb_pdf: _lbl_final = "DETALLE TECNICO - FINAL (TIERRA/CAMION)"
        else: _lbl_final = "DETALLE TÉCNICO - FINAL PRODUCTO"
        draw_logo_header(_lbl_final, "final")
        y = h - 110
        c.setFont("Helvetica-Bold", 8)
        for i, txt in enumerate(headers): c.drawString(x_pos[i], y, txt)
        y -= 15
        c.setFont("Helvetica", 8)
        for tk_name in all_tanks:
            if _es_duc_pdf:
                vals = [tk_name,
                    self.get_var(f"final_{tk_name}_prod_name").get(),
                    self.get_var(f"final_{tk_name}_cont_ini").get(),
                    self.get_var(f"final_{tk_name}_cont_fin").get(),
                    self.get_var(f"final_{tk_name}_vol_linea").get(),
                    self.get_var(f"final_{tk_name}_P_lin").get() or self.get_var("car_presion_op").get(),
                    self.get_var(f"final_{tk_name}_T_lin").get() or self.get_var("car_temp_op").get(),
                    self.get_var(f"final_{tk_name}_Z").get(),
                    self.get_var(f"final_{tk_name}_vol_base").get(),
                    self.get_var(f"final_{tk_name}_masa_coriolis").get()]
            elif _es_elec_pdf:
                vals = [tk_name,
                    self.get_var(f"final_{tk_name}_el_ini_act").get(),
                    self.get_var(f"final_{tk_name}_el_fin_act").get(),
                    self.get_var(f"final_{tk_name}_el_kwh_act").get(),
                    self.get_var(f"final_{tk_name}_el_ini_rea").get(),
                    self.get_var(f"final_{tk_name}_el_fin_rea").get(),
                    self.get_var(f"final_{tk_name}_el_kwh_rea").get(),
                    self.get_var(f"final_{tk_name}_el_fp").get(),
                    self.get_var(f"final_{tk_name}_el_V").get(),
                    self.get_var(f"final_{tk_name}_el_A").get()]
            elif _es_esf_pdf or _es_gas_pdf:
                vals = [tk_name,
                    self.get_var(f"final_{tk_name}_prod_name").get(),
                    self.get_var(f"final_{tk_name}_P_lin").get() or self.get_var("car_presion_op").get(),
                    self.get_var(f"final_{tk_name}_temp").get(),
                    self.get_var(f"final_{tk_name}_dens_lab").get(),
                    self.get_var(f"final_{tk_name}_vol_liq").get() or self.get_var(f"final_{tk_name}_vol_bruto").get(),
                    self.get_var(f"final_{tk_name}_fase").get(),
                    self.get_var(f"final_{tk_name}_vol_nat_prod").get(),
                    self.get_var(f"final_{tk_name}_Z").get(),
                    self.get_var(f"final_{tk_name}_masa_kg").get()]
            elif _es_tie_pdf or _es_cam_pdf or _es_cgb_pdf:
                vals = [tk_name,
                    self.get_var(f"final_{tk_name}_prod_name").get(),
                    self.get_var(f"final_{tk_name}_num_uti").get(),
                    self.get_var(f"final_{tk_name}_alt_ref").get(),
                    self.get_var(f"final_{tk_name}_s_tierra").get(),
                    self.get_var(f"final_{tk_name}_vol_bruto").get(),
                    self.get_var(f"final_{tk_name}_vol_nat_agua").get(),
                    self.get_var(f"final_{tk_name}_s_corr").get(),
                    self.get_var(f"final_{tk_name}_temp").get(),
                    self.get_var(f"final_{tk_name}_vol_nat_prod").get()]
            else:
                vals = [tk_name, self.get_var(f"final_{tk_name}_prod_name").get(), self.get_var(f"final_{tk_name}_num_uti").get(), self.get_var(f"final_{tk_name}_alt_ref").get(), self._celda_sin_marcador(f"final_{tk_name}_prod_s1"), self._celda_sin_marcador(f"final_{tk_name}_prod_l1"), self._celda_sin_marcador(f"final_{tk_name}_prod_s2"), self._celda_sin_marcador(f"final_{tk_name}_prod_l2"), self.get_var(f"final_{tk_name}_desc_tubo").get(), self.get_var(f"final_{tk_name}_s_corr").get(), self.get_var(f"final_{tk_name}_temp").get(), self.get_var(f"final_{tk_name}_vol_nat_prod").get()]
            for i, v in enumerate(vals):
                if i < len(x_pos): c.drawString(x_pos[i], y, str(v))
            y -= 12
            if y < 80:
                draw_signatures_2_lines()
                c.showPage()
                if _es_duc_pdf: _cont_lbl2 = "ACTA DUCTO - FINAL (CONT.)"
                elif _es_elec_pdf: _cont_lbl2 = "ACTA ELECTRICA - FINAL (CONT.)"
                elif _es_esf_pdf: _cont_lbl2 = "ESFERA DE GAS - FINAL (CONT.)"
                elif _es_gas_pdf: _cont_lbl2 = "BUQUE GASERO - FINAL (CONT.)"
                elif _es_tie_pdf or _es_cam_pdf or _es_cgb_pdf: _cont_lbl2 = "DETALLE TECNICO - FINAL (CONT.)"
                else: _cont_lbl2 = "DETALLE TÉCNICO - FINAL PRODUCTO (CONT.)"
                draw_logo_header(_cont_lbl2, "final")
                y = h - 110
                
        draw_signatures_2_lines()
        c.showPage()

        # 3. MEMORIA DE CALCULO — adaptada al tipo de medición
        _tm_rep = self.get_tipo_medio()
        _es_met_rep = "METANERO" in _tm_rep or "GNL" in _tm_rep
        _es_gas_rep = ("GASERO" in _tm_rep or "GLP" in _tm_rep) and not _es_met_rep
        _es_liq_mar = _tm_rep in ("BUQUE","BARCAZA","BUQUE QUIMIQUERO","DRAFT SURVEY")
        _es_tie_rep = self.es_tierra()
        _es_cam_rep = self.es_camion() and not self.es_camion_gas()
        _es_duc_rep = self.es_ducto()
        _es_el_rep  = self.es_electrico()
        _es_esf_rep = self.es_esfera()

        for etapa in ['inicial', 'final']:
            draw_logo_header(f"MEMORIA DE CÁLCULO ({etapa.upper()})", etapa)
            y = h - 100
            tanks_on_page = 0

            # Cabecera de sección según tipo
            c.setFont("Helvetica-Bold", 9)
            c.setFillColor(colors.HexColor("#1B3A5C"))
            tipo_label = {
                True: "BUQUE METANERO/GNL — Composición Molar + Fases",
                False: None,
            }
            if _es_met_rep:
                c.drawString(40, y, "TIPO: BUQUE METANERO/GNL — Composición Molar + Fases Líquida/Gaseosa")
            elif _es_gas_rep:
                c.drawString(40, y, "TIPO: BUQUE GASERO/GLP — Presión, Temperatura, Factor Z")
            elif _es_liq_mar:
                c.drawString(40, y, "TIPO: BUQUE/QUIMIQUERO — Sondaje UTI, Tablas de Calibrado, VCF")
            elif _es_esf_rep:
                c.drawString(40, y, "TIPO: ESFERA DE GAS — Presión/Temperatura/Densidad Líquida")
            elif _es_duc_rep:
                c.drawString(40, y, "TIPO: DUCTO — Contadores volumétricos, Factor Z, Volumen Base")
            elif _es_el_rep:
                c.drawString(40, y, "TIPO: MEDICIÓN ELÉCTRICA — Lectura kWh activa/reactiva")
            else:
                c.drawString(40, y, f"TIPO: {_tm_rep} — Sondaje / Varilla / Calibrado")
            c.setFont("Helvetica", 8)
            c.setFillColor(colors.black)
            y -= 16

            for tk_name in all_tanks:
                if not self.get_var(f"{etapa}_{tk_name}_prod_name").get(): continue

                if tanks_on_page >= 5 or y < 80:
                    draw_signatures_2_lines()
                    c.showPage()
                    draw_logo_header(f"MEMORIA DE CÁLCULO ({etapa.upper()} - CONT.)", etapa)
                    y = h - 100; tanks_on_page = 0

                prod_name = self.get_var(f"{etapa}_{tk_name}_prod_name").get()
                vol_nat = self.get_var(f"{etapa}_{tk_name}_vol_nat_prod").get() or "0"

                # Encabezado de tanque
                c.setFillColor(colors.HexColor("#ECF0F1"))
                c.setLineWidth(0)
                c.rect(38, y-3, w-76, 14, fill=1, stroke=0)
                c.setStrokeColor(colors.HexColor("#AEB6BF")); c.setLineWidth(0.5)
                c.rect(38, y-3, w-76, 14, fill=0, stroke=1)
                c.setFont("Helvetica-Bold", 8)
                c.setFillColor(colors.HexColor("#1B3A5C"))
                c.drawString(42, y+2, f"TANQUE: {tk_name}  —  PRODUCTO: {prod_name}")
                c.setFont("Helvetica", 7.5)
                c.setFillColor(colors.black)
                y -= 14

                # ── Tipo MARITIMO LIQUIDO (UTI) ─────────────────────────────
                if _es_liq_mar:
                    s_uti = self.get_var(f"{etapa}_{tk_name}_alt_uti").get() or "—"
                    desc  = self.get_var(f"{etapa}_{tk_name}_desc_tubo").get() or "0"
                    s_corr = self.get_var(f"{etapa}_{tk_name}_s_corr").get() or "—"
                    alt_ref = self.get_var(f"{etapa}_{tk_name}_alt_ref").get() or "—"
                    num_uti = self.get_var(f"{etapa}_{tk_name}_num_uti").get() or "—"
                    interp_str = self.get_interpolation_details(etapa, tk_name)
                    dens = self.parse_float(self.get_var(f"{etapa}_{tk_name}_dens_lab").get() or "0") or \
                           self.parse_float(self.get_var(f"{etapa}_{tk_name}_dens_doc").get() or "0")
                    temp = self.parse_float(self.get_var(f"{etapa}_{tk_name}_temp").get() or "0")
                    tbl  = self.get_var(f"{etapa}_{tk_name}_tabla_vcf").get() or "54B"
                    vcf_str = self.get_vcf_details(dens, temp, tbl)
                    agua_real = self.get_var(f"{etapa}_{tk_name}_agua_s_real").get() or "0"
                    agua_lts  = self.get_var(f"{etapa}_{tk_name}_vol_nat_agua").get() or "0"
                    _neto_v = self.parse_float(vol_nat) - self.parse_float(agua_lts)
                    try:
                        # Vol.15°C y peso sobre el NETO (bruto − agua), igual que la planilla
                        v15_val = _neto_v * self.calc_vcf(dens, temp, tbl)
                        _d_air = dens / 1000.0 if dens > 2.0 else dens
                        kg_air_val = v15_val * (_d_air - 0.0011) if _d_air > 0 else 0
                    except: v15_val = 0; kg_air_val = 0
                    lines_m = [
                        f"  UTI Nro: {num_uti}  |  Alt.Referencia: {alt_ref} mm",
                        f"  1. Sondaje UTI: {s_uti} mm  —  Desc.tubo: {desc} mm  →  Sondaje Corr.: {s_corr} mm",
                        f"  2. Interpolación tabla: {interp_str}  =  {vol_nat} Lts (bruto)",
                        f"  3. Agua de fondo: {agua_real} mm  →  {agua_lts} Lts  |  Vol.Neto: {_neto_v:,.0f} Lts",
                        f"  4. VCF ({tbl}): {vcf_str}  |  Vol.15°C: {_neto_v:,.0f}×VCF = {v15_val:,.0f} Lts",
                        f"  5. Dens.lab: {dens}  |  Temp: {temp}°C  |  Peso en aire: {v15_val:,.0f}×({dens}−0.0011) = {kg_air_val:,.0f} Kg",
                    ]
                    if self.get_var(f"{etapa}_{tk_name}_tabla_trim_agua_json").get():
                        lines_m.insert(4, f"     Interp. agua: {self.get_water_interp_details(etapa, tk_name)}")

                # ── Tipo METANERO (GNL) ───────────────────────────────────────
                elif _es_met_rep:
                    MW = {"CH4":16.04,"C2H6":30.07,"C3H8":44.10,"C4H10":58.12,
                          "iC4":58.12,"nC5":72.15,"N2":28.01,"CO2":44.01,"H2S":34.08}
                    comp_parts = []
                    for k in MW.keys():
                        v = self.get_var(f"{etapa}_{tk_name}_gc_{k}").get()
                        if v and float(v or "0") > 0:
                            comp_parts.append(f"{k}:{v}%")
                    gc_str = "  ".join(comp_parts) or "—"
                    gc_pm  = self.get_var(f"{etapa}_{tk_name}_gc_PM").get() or "—"
                    gc_sum = self.get_var(f"{etapa}_{tk_name}_gc_sum").get() or "—"
                    vl = self.get_var(f"{etapa}_{tk_name}_vol_liq").get() or "—"
                    vv = self.get_var(f"{etapa}_{tk_name}_vol_vap").get() or "—"
                    dl = self.get_var(f"{etapa}_{tk_name}_dens_liq").get() or "—"
                    dv = self.get_var(f"{etapa}_{tk_name}_dens_vap").get() or "—"
                    tl = self.get_var(f"{etapa}_{tk_name}_temp_liq").get() or "—"
                    tv = self.get_var(f"{etapa}_{tk_name}_temp_vap").get() or "—"
                    pres = self.get_var(f"{etapa}_{tk_name}_pres_gnl").get() or "—"
                    masa_l = self.get_var(f"{etapa}_{tk_name}_masa_liq").get() or "—"
                    masa_v = self.get_var(f"{etapa}_{tk_name}_masa_vap").get() or "—"
                    lines_m = [
                        f"  Composición molar: {gc_str}",
                        f"  Suma %mol: {gc_sum}  |  PM calculado: {gc_pm} g/mol",
                        f"  FASE LÍQUIDA: Vol={vl} m³  Dens={dl} kg/m³  Temp={tl}°C  Masa={masa_l} t",
                        f"  FASE GASEOSA: Vol={vv} m³  Dens={dv} kg/m³  Temp={tv}°C  Masa={masa_v} kg",
                        f"  Presión: {pres} kPa",
                    ]

                # ── Tipo GASERO (GLP/Propano/Butano) ──────────────────────────
                elif _es_gas_rep:
                    pres = self.get_var(f"{etapa}_{tk_name}_presion").get() or "—"
                    tl   = self.get_var(f"{etapa}_{tk_name}_temp_liq").get() or "—"
                    z    = self.get_var(f"{etapa}_{tk_name}_factor_z").get() or "—"
                    dv   = self.get_var(f"{etapa}_{tk_name}_dens_vapor").get() or "—"
                    fase = self.get_var(f"{etapa}_{tk_name}_fase").get() or "—"
                    # vol_nat en m³ o litros según disponible
                    lines_m = [
                        f"  Presión: {pres} kPa  |  Temperatura: {tl}°C  |  Factor Z: {z}",
                        f"  Densidad vapor: {dv} kg/m³  |  Fase: {fase}",
                        f"  Volumen liquido natural: {vol_nat}",
                    ]

                # ── Tipo ESFERA ───────────────────────────────────────────────
                elif _es_esf_rep:
                    pres  = self.get_var(f"{etapa}_{tk_name}_esf_pres").get() or "—"
                    temp  = self.get_var(f"{etapa}_{tk_name}_esf_temp").get() or "—"
                    dens  = self.get_var(f"{etapa}_{tk_name}_esf_dens").get() or "—"
                    vl    = self.get_var(f"{etapa}_{tk_name}_vol_liq").get() or "—"
                    vgas  = self.get_var(f"{etapa}_{tk_name}_esf_vol_gas").get() or "—"
                    masa  = self.get_var(f"{etapa}_{tk_name}_esf_masa").get() or "—"
                    fase  = self.get_var(f"{etapa}_{tk_name}_esf_fase").get() or "—"
                    lines_m = [
                        f"  Presión: {pres} kPa  |  Temperatura: {temp}°C",
                        f"  Densidad líq.: {dens} kg/m³  |  Vol.líquido: {vl} m³",
                        f"  Vol.gas base (15°C): {vgas} m³  |  Masa: {masa} t  |  Fase: {fase}",
                    ]

                # ── Tipo TIERRA o CAMION ──────────────────────────────────────
                elif _es_tie_rep or _es_cam_rep:
                    s_tierra = self.get_var(f"{etapa}_{tk_name}_s_tierra").get() or "—"
                    s_corr   = self.get_var(f"{etapa}_{tk_name}_s_corr").get() or "—"
                    vol_bruto = self.get_var(f"{etapa}_{tk_name}_vol_bruto").get() or "—"
                    interp_str = self.get_interpolation_details(etapa, tk_name)
                    dens = self.parse_float(self.get_var(f"{etapa}_{tk_name}_dens_lab").get() or "0")
                    temp = self.parse_float(self.get_var(f"{etapa}_{tk_name}_temp").get() or "0")
                    tbl  = self.get_var(f"{etapa}_{tk_name}_tabla_vcf").get() or "54B"
                    vcf_str = self.get_vcf_details(dens, temp, tbl)
                    _agua_t = self.parse_float(self.get_var(f"{etapa}_{tk_name}_vol_nat_agua").get() or "0")
                    _neto_t = self.parse_float(vol_nat) - _agua_t
                    try:
                        # parse_float (no float()): vol_nat de tierra viene con coma de miles
                        v15_val = _neto_t * self.calc_vcf(dens, temp, tbl)
                        _d_air = dens / 1000.0 if dens > 2.0 else dens
                        kg_air_val = v15_val * (_d_air - 0.0011) if _d_air > 0 else 0
                    except: v15_val = 0; kg_air_val = 0
                    lines_m = [
                        f"  1. Sondaje/Varilla: {s_tierra} mm  →  Corregido: {s_corr} mm",
                        f"  2. Interpolación: {interp_str}  =  {vol_nat} Lts",
                        f"  3. Agua: {_agua_t:,.0f} Lts  |  Vol.Neto: {_neto_t:,.0f} Lts",
                        f"  4. VCF ({tbl}): {vcf_str}  |  Vol.15°C: {v15_val:,.0f} Lts",
                        f"  5. Dens: {dens}  |  Temp: {temp}°C  |  Peso en aire: {kg_air_val:,.0f} Kg",
                    ]

                # ── Tipo DUCTO ────────────────────────────────────────────────
                elif _es_duc_rep:
                    c_ini = self.get_var(f"{etapa}_{tk_name}_cont_ini").get() or "—"
                    c_fin = self.get_var(f"{etapa}_{tk_name}_cont_fin").get() or "—"
                    vl    = self.get_var(f"{etapa}_{tk_name}_vol_linea").get() or "—"
                    P_lin = self.get_var(f"{etapa}_{tk_name}_P_lin").get() or "—"
                    T_lin = self.get_var(f"{etapa}_{tk_name}_T_lin").get() or "—"
                    Z     = self.get_var(f"{etapa}_{tk_name}_Z").get() or "—"
                    vb    = self.get_var(f"{etapa}_{tk_name}_vol_base").get() or "—"
                    lines_m = [
                        f"  Contador ini: {c_ini} m³  |  Contador fin: {c_fin} m³  |  Vol.línea: {vl} m³",
                        f"  P línea: {P_lin} kPa  |  T línea: {T_lin}°C  |  Factor Z: {Z}",
                        f"  Vol.base (ref 101.325 kPa / 15°C): {vb} m³",
                    ]

                # ── Tipo ELECTRICO ─────────────────────────────────────────────
                elif _es_el_rep:
                    ia = self.get_var(f"{etapa}_{tk_name}_el_ini_act").get() or "—"
                    fa = self.get_var(f"{etapa}_{tk_name}_el_fin_act").get() or "—"
                    ka = self.get_var(f"{etapa}_{tk_name}_el_kwh_act").get() or "—"
                    ir = self.get_var(f"{etapa}_{tk_name}_el_ini_rea").get() or "—"
                    fr = self.get_var(f"{etapa}_{tk_name}_el_fin_rea").get() or "—"
                    kr = self.get_var(f"{etapa}_{tk_name}_el_kwh_rea").get() or "—"
                    ct = self.get_var(f"{etapa}_{tk_name}_el_const").get() or "1"
                    fp = self.get_var(f"{etapa}_{tk_name}_el_fp").get() or "—"
                    lines_m = [
                        f"  kWh Activa:  Ini={ia}  Fin={fa}  Cte={ct}  →  {ka} kWh",
                        f"  kWh Reactiva: Ini={ir}  Fin={fr}  Cte={ct}  →  {kr} kWh",
                        f"  cos fi calculado: {fp}",
                    ]

                else:
                    lines_m = [f"  Vol.Natural: {vol_nat}"]

                # Imprimir líneas de la memoria
                for line_m in lines_m:
                    if y < 70:
                        draw_signatures_2_lines(); c.showPage()
                        draw_logo_header(f"MEMORIA DE CÁLCULO ({etapa.upper()} - CONT.)", etapa)
                        y = h - 100; tanks_on_page = 0
                    c.setFont("Helvetica", 7.5)
                    c.setFillColor(colors.black)
                    c.drawString(40, y, line_m)
                    y -= 11
                y -= 4
                tanks_on_page += 1

            draw_signatures_2_lines()
            c.showPage()
        
        # 4. GRAFICOS — tipos marítimos: vista lateral; otros: dibujo técnico específico
        _tm_gr = self.get_tipo_medio()
        _es_mar_gr = _tm_gr in ("BUQUE","BARCAZA","BUQUE QUIMIQUERO","DRAFT SURVEY",
                                "BUQUE GASERO/GLP","BUQUE METANERO/GNL")
        if _es_mar_gr:
            draw_logo_header("DETALLE TÉCNICO - GRÁFICO VISUAL - INICIAL", "inicial")
            trim_i = self.parse_float(self.get_var("inicial_Trimación").get())
            self.dibujar_perfil_buque(c, 85, 350, 630, 135, "VISTA LATERAL - TANQUES BABOR (INICIAL)", [], [], [], trim_i)
            self.dibujar_perfil_buque(c, 85, 100, 630, 135, "VISTA LATERAL - TANQUES ESTRIBOR (INICIAL)", [], [], [], trim_i)
            draw_signatures_2_lines()
            c.showPage()

            draw_logo_header("DETALLE TÉCNICO - GRÁFICO VISUAL - FINAL", "final")
            trim_f = self.parse_float(self.get_var("final_Trimación").get())
            self.dibujar_perfil_buque(c, 85, 350, 630, 135, "VISTA LATERAL - TANQUES BABOR (FINAL)", [], [], [], trim_f)
            self.dibujar_perfil_buque(c, 85, 100, 630, 135, "VISTA LATERAL - TANQUES ESTRIBOR (FINAL)", [], [], [], trim_f)
            draw_signatures_2_lines()
            c.showPage()
        else:
            # Página de dibujo para tipos terrestres/ductos/eléctricos
            draw_logo_header("DETALLE TÉCNICO - GRÁFICO VISUAL - INICIAL", "inicial")
            self.dibujar_perfil_buque(c, 70, 70, w-140, h-220, "VISTA TÉCNICA (INICIAL)", [], [], [], 0)
            draw_signatures_2_lines()
            c.showPage()

            draw_logo_header("DETALLE TÉCNICO - GRÁFICO VISUAL - FINAL", "final")
            self.dibujar_perfil_buque(c, 70, 70, w-140, h-220, "VISTA TÉCNICA (FINAL)", [], [], [], 0)
            draw_signatures_2_lines()
            c.showPage()
        
        if not shared_canvas:
            c.save()
            return full_path
        return None

    def generar_un_reporte(self, suffix, tank_list, is_partial=False, ddt_obj=None, output_folder="", density_mode_key="dens_lab", shared_canvas=None):
        clean_buque = self.clean_filename(self.get_var('car_buque').get())
        clean_suffix = self.clean_filename(suffix)
        filename = f"Planilla_{clean_buque}_{clean_suffix}_{datetime.now().strftime('%Y%m%d')}.pdf"
        full_path = os.path.join(output_folder, filename)
        if shared_canvas:
            c = shared_canvas
            w, h = landscape(A4)
        else:
            print(f"Intentando guardar en: {full_path}")
            try: 
                c = canvas.Canvas(full_path, pagesize=landscape(A4))
            except Exception as e:
                traceback.print_exc() 
                messagebox.showerror("Error de PDF", f"No se pudo crear el archivo:\n{full_path}\n\nError: {str(e)}")
                return None
            w, h = landscape(A4)
        sum_ini = {"neto":0, "15":0, "kv": 0, "ka": 0}
        sum_fin = {"neto":0, "15":0, "kv": 0, "ka": 0}
        
        # Para tipos sin VCF/densidad clásica, usar vol_nat_prod directamente
        _sum_tm = self.get_tipo_medio()
        _sum_es_liq = _sum_tm in ("BUQUE","BARCAZA","BUQUE QUIMIQUERO","DRAFT SURVEY",
                                   "TANQUE FIJO","TANQUE FLOTANTE","CAMION CISTERNA")
        _sum_es_elec = self.es_electrico()
        _sum_es_duc  = self.es_ducto()

        for tk_name in tank_list:
            if _sum_es_elec:
                # kWh activa como "neto"
                i_v = self.parse_float(self.get_var(f"inicial_{tk_name}_el_kwh_act").get() or "0")
                f_v = self.parse_float(self.get_var(f"final_{tk_name}_el_kwh_act").get() or "0")
                sum_ini["neto"] += i_v; sum_ini["15"] += i_v
                sum_fin["neto"] += f_v; sum_fin["15"] += f_v
                continue
            elif _sum_es_duc:
                # vol_base como "neto"
                i_v = self.parse_float(self.get_var(f"inicial_{tk_name}_vol_base").get() or "0")
                f_v = self.parse_float(self.get_var(f"final_{tk_name}_vol_base").get() or "0")
                sum_ini["neto"] += i_v; sum_ini["15"] += i_v
                sum_fin["neto"] += f_v; sum_fin["15"] += f_v
                continue
            elif not _sum_es_liq:
                # Gas/esfera/camion gas: vol_nat_prod como "neto"
                i_v = self.parse_float(self.get_var(f"inicial_{tk_name}_vol_nat_prod").get() or "0")
                f_v = self.parse_float(self.get_var(f"final_{tk_name}_vol_nat_prod").get() or "0")
                sum_ini["neto"] += i_v; sum_ini["15"] += i_v
                sum_fin["neto"] += f_v; sum_fin["15"] += f_v
                continue
            
            # Líquidos clásicos: cálculo completo con VCF y densidades
            d_i_raw = self.get_var(f"inicial_{tk_name}_{density_mode_key}").get()
            if not d_i_raw: d_i_raw = self.get_var(f"inicial_{tk_name}_dens_lab").get()
            d_i = self.parse_float(d_i_raw)
            table_type = self.get_var(f"inicial_{tk_name}_tabla_vcf").get()
            if not table_type: table_type = "54B (Combustibles)"
            i_temp = self.get_var(f"inicial_{tk_name}_temp").get()
            i_temp = self.parse_float(i_temp) 
            i_bruto = self.interpolar_prod("inicial", tk_name)
            i_agua = self.interpolar_agua("inicial", tk_name)
            i_neto = i_bruto - i_agua
            i_vcf = self.calc_vcf(d_i, i_temp, table_type) if d_i > 0 else 1.0
            i_15 = i_neto * i_vcf
            _di_g = d_i / 1000.0 if d_i > 2.0 else d_i
            i_kv = i_15 * _di_g if _di_g > 0 else 0
            i_ka = i_15 * (_di_g - 0.0011) if _di_g > 0 else 0
            sum_ini["neto"] += i_neto
            sum_ini["15"] += i_15
            sum_ini["kv"] += i_kv
            sum_ini["ka"] += i_ka
            d_f_raw = self.get_var(f"final_{tk_name}_{density_mode_key}").get()
            if not d_f_raw: d_f_raw = self.get_var(f"final_{tk_name}_dens_lab").get()
            d_f = self.parse_float(d_f_raw)
            table_type_f = self.get_var(f"final_{tk_name}_tabla_vcf").get()
            if not table_type_f: table_type_f = "54B (Combustibles)"
            f_temp = self.get_var(f"final_{tk_name}_temp").get()
            f_temp = self.parse_float(f_temp) 
            f_bruto = self.interpolar_prod("final", tk_name)
            f_agua = self.interpolar_agua("final", tk_name)
            f_neto = f_bruto - f_agua
            f_vcf = self.calc_vcf(d_f, f_temp, table_type_f) if d_f > 0 else 1.0
            f_15 = f_neto * f_vcf
            _df_g = d_f / 1000.0 if d_f > 2.0 else d_f
            f_kv = f_15 * _df_g if _df_g > 0 else 0
            f_ka = f_15 * (_df_g - 0.0011) if _df_g > 0 else 0
            sum_fin["neto"] += f_neto
            sum_fin["15"] += f_15
            sum_fin["kv"] += f_kv
            sum_fin["ka"] += f_ka
        
        avg_d_i = sum_ini["kv"] / sum_ini["15"] if sum_ini["15"] > 0 else 0
        avg_d_f = sum_fin["kv"] / sum_fin["15"] if sum_fin["15"] > 0 else 0
        kv_i, ka_i = sum_ini["kv"], sum_ini["ka"]
        kv_f, ka_f = sum_fin["kv"], sum_fin["ka"]
        dif_net = sum_ini['neto'] - sum_fin['neto']
        dif_15 = sum_ini['15'] - sum_fin['15']
        dif_ka = ka_i - ka_f
        dif_kv = kv_i - kv_f

        try:
            raw_b64 = ICON_REPORT_B64.strip().replace("\n", "").replace("\r", "")
            icon_data = base64.b64decode(raw_b64)
            img = ImageReader(BytesIO(icon_data))
            c.drawImage(img, 30, h-70, width=100, height=50, preserveAspectRatio=True, mask=None)
        except: pass
        
        c.setFont("Helvetica-Bold", 14)
        c.drawCentredString(w/2, h-40, "ARCA - DGA")
        num_print = self.get_var('car_num_planilla_gen').get()
        if is_partial and ddt_obj:
            val = ddt_obj['num_planilla'].get()
            num_print = val if val else num_print

        # TITULO DINAMICO (aplica a todos los reportes, parciales y generales)
        _tm_pl = self.get_tipo_medio()
        if "BARCAZA" in _tm_pl: base_title = "PLANILLA DE SONDAJES - BARCAZA"
        elif "CAMION GAS" in _tm_pl: base_title = "PLANILLA DE MEDICION - CAMION GAS/GLP"
        elif "CAMION" in _tm_pl: base_title = "PLANILLA DE MEDICION - CAMION CISTERNA"
        elif "TANQUE FIJO" in _tm_pl: base_title = "PLANILLA DE SONDAJES - TANQUE FIJO"
        elif "TANQUE FLOTANTE" in _tm_pl: base_title = "PLANILLA DE SONDAJES - TANQUE FLOTANTE"
        elif _tm_pl == "OLEODUCTO": base_title = "ACTA DE MEDICION - OLEODUCTO"
        elif _tm_pl == "POLIDUCTO": base_title = "ACTA DE MEDICION - POLIDUCTO"
        elif _tm_pl == "GASODUCTO": base_title = "ACTA DE MEDICION - GASODUCTO"
        elif _tm_pl == "MEDICION ELECTRICA": base_title = "ACTA DE MEDICION ELECTRICA"
        elif _tm_pl == "ESFERA DE GAS": base_title = "PLANILLA DE MEDICIÓN - ESFERA DE GAS"
        elif "GASERO" in _tm_pl or ("GLP" in _tm_pl and "CAMION" not in _tm_pl): base_title = "PLANILLA DE SONDAJES - BUQUE GASERO/GLP"
        elif "METANERO" in _tm_pl or "GNL" in _tm_pl: base_title = "PLANILLA DE SONDAJES - BUQUE METANERO/GNL"
        elif "QUIMIQUERO" in _tm_pl: base_title = "PLANILLA DE SONDAJES - BUQUE QUIMIQUERO"
        elif "DRAFT SURVEY" in _tm_pl: base_title = "PLANILLA DE SONDAJES - DRAFT SURVEY"
        else: base_title = "PLANILLA DE SONDAJES DE TANQUES DE BUQUES"
            

        c.drawRightString(w-40, h-55, f"NUMERO: {num_print}")
        
        doc_num_safe = ""
        if ddt_obj: doc_num_safe = ddt_obj['numero'].get()
        
        calc_title = suffix.replace(f"DOC_{self.clean_filename(doc_num_safe)}_", "").replace("_", " ") if is_partial else "GENERAL"
        c.setFont("Helvetica-Bold", 9)
        c.drawCentredString(w/2, h-55, base_title)
        c.setFont("Helvetica", 8)
        c.drawCentredString(w/2, h-68, f"AGENCIA DE RECAUDACIÓN ADUANERA - {calc_title}")
        
        all_ddts_assigned = set()
        all_prods_assigned = set()
        for tk_name in tank_list:
            d = self.get_var(f"inicial_{tk_name}_ddt_assign").get()
            p = self.get_var(f"inicial_{tk_name}_prod_name").get()
            if d: all_ddts_assigned.add(d)
            if p: all_prods_assigned.add(p)
        txt_ddt = ", ".join(sorted(list(all_ddts_assigned)))
        label_ddt_title = "Documentos" if len(all_ddts_assigned) > 1 else "Documento"
        txt_prod = ", ".join(sorted(list(all_prods_assigned)))
        y_header_start = h - 90
        col1 = 53; col2 = 335; col3 = 595 
        c.setFont("Helvetica", 8)
        # Actores: del documento si es reporte parcial; si es general, los de
        # todos los documentos (distintos, unidos con ' / '), fallback carátula
        _act = self._actores_pdf(ddt_obj if is_partial else None)
        c.drawString(col1, y_header_start,    f"Buque: {self.get_var('car_buque').get()} (IMO: {self.get_var('car_imo').get()})")
        c.drawString(col1, y_header_start-12, f"Despachante: {_act['despachante']} ({_act['cuit_desp']})")
        c.drawString(col1, y_header_start-24, f"Importador/Exportador: {_act['impexp']} ({_act['cuit_impexp']})")
        c.drawString(col1, y_header_start-36, f"MANI: {self.get_var('car_mani').get()}")
        aduana_cod  = self.aduana_codigo()
        aduana_nom  = self.aduana_nombre()
        lugar_op_val = (self.get_var("car_lop_codigo").get() + " " + self.get_var("car_lop_desc").get()).strip()
        aduana_str  = f"Aduana: {aduana_cod} - {aduana_nom}" if aduana_cod else f"Aduana: {aduana_nom}"
        c.drawString(col1, y_header_start-48, aduana_str)
        c.drawString(col1, y_header_start-60, f"{label_ddt_title}: {txt_ddt}")
        if lugar_op_val:
            c.drawString(col1, y_header_start-72, f"Lugar Op.: {lugar_op_val}")
        c.drawString(col2, y_header_start,    aduana_str)
        c.drawString(col2, y_header_start-12, f"ATA: {_act['ata']} ({_act['cuit_ata']})")
        c.drawString(col2, y_header_start-24, f"Viaje: {self.get_var('car_conocimientos').get()}")
        c.drawString(col2, y_header_start-36, f"Producto: {txt_prod}")
        current_y = y_header_start - 84  # shifted down for Lugar Op line
        if is_partial and ddt_obj:
            tot_sal_l = 0; tot_sal_k = 0
            for s in ddt_obj["salidas"]:
                try: tot_sal_l += self.parse_float(s['litros'].get()); tot_sal_k += self.parse_float(s['kilos'].get())
                except: pass
            doc_l = self.parse_float(ddt_obj['litros'].get())
            doc_k = self.parse_float(ddt_obj['kilos'].get())
            target_l = tot_sal_l if tot_sal_l > 0 else doc_l
            target_k = tot_sal_k if tot_sal_k > 0 else doc_k
            label_diff = "con Salidas" if tot_sal_l > 0 else "con Documento"
            diff_l = dif_15 - target_l
            diff_k = dif_kv - target_k 
            # Por mil: diferencia / valor declarado * 1000
            permil_l = (diff_l / target_l * 1000) if target_l != 0 else 0
            permil_k = (diff_k / target_k * 1000) if target_k != 0 else 0
            is_red_l = abs(permil_l) > 6.0
            is_red_k = abs(permil_k) > 6.0
            c.setFont("Helvetica", 8)
            dens_ddt = self.parse_float(ddt_obj['densidad'].get())
            tipo_doc_str = ddt_obj['tipo_doc'].get() if 'tipo_doc' in ddt_obj else "Detallada"
            c.drawString(col1, current_y, f"Documento {tipo_doc_str}: Litros {doc_l:,.0f}, Kilos {doc_k:,.0f}, Densidad {dens_ddt}")
            y_diff_top = y_header_start - 48 
            col_font_l = colors.red if is_red_l else colors.blue
            txt_l = f"Diferencias Litros (15°C) {label_diff}: {diff_l:,.0f} ({permil_l:.2f} ‰)"
            c.setFillColor(col_font_l)
            c.setFont("Helvetica", 8)
            c.drawString(col2, y_diff_top, txt_l)
            col_font_k = colors.red if is_red_k else colors.blue
            txt_k = f"Diferencias Kilos (Vacío) {label_diff}: {diff_k:,.0f} ({permil_k:.2f} ‰)"
            c.setFillColor(col_font_k)
            c.drawString(col2, y_diff_top - 12, txt_k)
            c.setFillColor(colors.black) 
            y_dens = y_header_start - 12
            c.setFont("Helvetica", 7)
            if lugar_op_val:
                c.drawString(col3, y_dens, f"Lugar Op.: {lugar_op_val}")
                y_dens -= 10
            c.setFont("Helvetica-Bold", 8)
            c.drawString(col3, y_dens, "COMPARATIVAS DENSIDAD:")
            y_dens -= 12
            c.setFont("Helvetica", 7)
            dens_salida_avg = 0
            if ddt_obj["salidas"]:
                tm=0; tv=0
                for s in ddt_obj["salidas"]:
                    dv=self.parse_float(s['densidad'].get()); lv=self.parse_float(s['litros'].get())
                    tm+=(dv*lv); tv+=lv
                if tv>0: dens_salida_avg = tm/tv
            def fmt_diff(v1, v2):
                d = v1 - v2
                pct = (d / v1) * 1000 if v1 != 0 else 0
                return f"{d:.5f} ({pct:.2f} ‰)"
            if dens_salida_avg > 0:
                # Solo comparar contra salidas si hay salidas cargadas
                c.drawString(col3, y_dens, f"Diferencia Doc vs Salida: {fmt_diff(dens_ddt, dens_salida_avg)}")
                y_dens -= 10
                c.drawString(col3, y_dens, f"Diferencia Salida vs Inicial: {fmt_diff(dens_salida_avg, avg_d_i)}")
                y_dens -= 10
                c.drawString(col3, y_dens, f"Diferencia Salida vs Final: {fmt_diff(dens_salida_avg, avg_d_f)}")
                y_dens -= 10
            c.drawString(col3, y_dens, f"Diferencia Doc vs Inicial: {fmt_diff(dens_ddt, avg_d_i)}")
            y_dens -= 10
            c.drawString(col3, y_dens, f"Diferencia Doc vs Final: {fmt_diff(dens_ddt, avg_d_f)}")
            y_dens -= 10
            c.drawString(col3, y_dens, f"Diferencia Ponderada Inicial vs Final: {fmt_diff(avg_d_i, avg_d_f)}")
            current_y -= 10
            c.setFont("Helvetica", 7)
            for s in ddt_obj["salidas"]:
                line_salida = f"Salida {s['numero'].get()}: Litros {s['litros'].get()}, Kilos {s['kilos'].get()}, Densidad {s['densidad'].get()}"
                c.drawString(col1, current_y, line_salida) 
                current_y -= 10
            current_y -= 5
        y_med = current_y - 10
        col_final_header = 600
        # Determinar si este reporte es de tipo marítimo para mostrar calados
        _tmr = self.get_tipo_medio()
        _es_mar_r = _tmr in ("BUQUE","BARCAZA","BUQUE QUIMIQUERO","DRAFT SURVEY",
                             "BUQUE GASERO/GLP","BUQUE METANERO/GNL")

        c.setFont("Helvetica-Bold", 8)
        c.drawString(col1, y_med, "MEDICION INICIAL")
        c.setFont("Helvetica", 8)
        
        f_ini = self.get_var('inicial_Fecha').get()
        h_ini = self.get_var('inicial_Hora').get()
        
        c.drawString(col1 + 140, y_med, f"Fecha: {f_ini}")
        c.drawString(col1 + 220, y_med, f"Hora: {h_ini}")
        if _es_mar_r:
            c_proa_i  = self.get_var('inicial_Calados Proa').get()
            c_popa_i  = self.get_var('inicial_Calados Popa').get()
            trim_i    = self.get_var('inicial_Trimación').get()
            bab_i     = self.get_var('inicial_Calados Babor').get()
            est_i     = self.get_var('inicial_Calados Estribor').get()
            asiento_i = self.get_var('inicial_Lista').get()
            c.drawString(col1, y_med - 10,
                         f"Calados: Proa {c_proa_i} | Popa {c_popa_i} | Trim {trim_i} | Babor {bab_i} | Estribor {est_i} | Escora {asiento_i}")

        c.setFont("Helvetica-Bold", 8)
        c.drawString(col_final_header - 180, y_med, "MEDICION FINAL")
        c.setFont("Helvetica", 8)
        
        f_fin = self.get_var('final_Fecha').get()
        h_fin = self.get_var('final_Hora').get()

        c.drawString(col_final_header + 90, y_med, f"Fecha: {f_fin}")
        c.drawString(col_final_header + 170, y_med, f"Hora: {h_fin}")
        if _es_mar_r:
            c_proa_f  = self.get_var('final_Calados Proa').get()
            c_popa_f  = self.get_var('final_Calados Popa').get()
            trim_f    = self.get_var('final_Trimación').get()
            bab_f     = self.get_var('final_Calados Babor').get()
            est_f     = self.get_var('final_Calados Estribor').get()
            asiento_f = self.get_var('final_Lista').get()
            c.drawString(col_final_header - 180, y_med - 10,
                         f"Calados: Proa {c_proa_f} | Popa {c_popa_f} | Trim {trim_f} | Babor {bab_f} | Estribor {est_f} | Escora {asiento_f}")

        
  
 
        
        y_table = y_med - 25
        c.setLineWidth(2)
        c.line(35, y_table, w-35, y_table)
        
        # ── Headers adaptativos según tipo de medición ──────────────────
        _tm_rep_t = self.get_tipo_medio()
        _es_liq_rep = _tm_rep_t in ("BUQUE","BARCAZA","BUQUE QUIMIQUERO","DRAFT SURVEY")
        _es_gas_rep_t = self.es_gasero()
        _es_duc_rep_t = self.es_ducto()
        _es_el_rep_t  = self.es_electrico()
        _es_tie_rep_t = self.es_tierra()
        _es_cam_rep_t = self.es_camion() and not self.es_camion_gas()
        _es_cgb_rep_t = self.es_camion_gas()
        _es_esf_rep_t = self.es_esfera()
        
        if _es_liq_rep:
            h_col = ["Tanque N° B/E", "Alt.Ref", "Sondeo\nUti", "Sondeo\nAgua", "Temp\nºC", "Sondeo\nCorr", "Litros\nc/agua", "Litros\nAgua", "Litros\nNetos", "F.C.V.", "Litros\n15ºC"]
        elif _es_el_rep_t:
            h_col = ["Punto Medición", "kWh\nActiva", "kWh\nReactiva", "cos fi", "Demanda\nkW", "Tensión\nV", "Corriente\nA", "V·A", "Fases", "—", "—"]
        elif _es_duc_rep_t:
            h_col = ["Tramo/Punto", "Cont.\nInicial", "Cont.\nFinal", "Vol.Línea\nm3", "P línea\nkPa", "T línea\nºC", "Factor Z", "Vol.Base\nm3", "Vol.Base\nKm3", "Caudal\nm3/h", "Masa\nCoriolis"]
        elif _es_gas_rep_t:
            h_col = ["Tanque", "Producto", "Presión\nkPa", "Temp\nºC", "Dens.Liq\nkg/m3", "Vol.Liq\nm3", "Fase", "Vol.Nat\nLts", "Factor Z", "—", "—"]
        elif _es_esf_rep_t:
            h_col = ["Esfera", "Presión\nkPa", "Temp\nºC", "Dens.Liq\nkg/m3", "Vol.Liq\nm3", "Vol.Gas\nBase m3", "Masa\nt", "Fase", "—", "—", "—"]
        elif _es_cgb_rep_t:
            h_col = ["Compartim.", "Presión\nkPa", "Temp\nºC", "Dens.Liq\nkg/m3", "Masa\nkg", "Vol.Líq\nL", "Vol.Gas\nm3", "Fase", "—", "—", "—"]
        elif _es_tie_rep_t or _es_cam_rep_t:
            h_col = ["Tanque/Comp.", "N°Util.", "Sondaje\nmm", "Sondaje\nCorr mm", "Temp\nºC", "Vol.Bruto\nLts", "Litros\nAgua", "Litros\nNetos", "F.C.V.", "Litros\n15ºC", "—"]
        else:
            h_col = ["Tanque N° B/E", "Altura Ref", "Sondeo\nUti", "Sondeo\nAgua", "Temp\nºC", "Sondeo\nCorregido", "Litros\nc/agua", "Litros\nAgua", "Litros\nNetos", "F.C.V.", "Litros\n15ºC"]
        
        h_left = h_col
        h_right = h_col
        x_start = 53
        col_w_name = 50 
        col_w_num = 31 
        c.setFont("Helvetica-Bold", 6)
        def draw_header_row(start_x, headers):
            curr_x = start_x
            for i, h in enumerate(headers):
                w_curr = col_w_name if i == 0 else col_w_num
                y_off = 0 if "\n" not in h else 6
                for l in h.split("\n"): 
                    c.drawString(curr_x, y_table - 8 - y_off, l)
                    y_off -= 6
                curr_x += w_curr
            return curr_x
        end_x_left = draw_header_row(x_start, h_left)
        x_mid = x_start + 360 + 15  # = 428 centrado
        draw_header_row(x_mid, h_right)
        c.line(35, y_table - 25, w-35, y_table - 25)
        y_row = y_table - 35
        c.setFont("Helvetica", 6)
        def val_or_zero(v):
            """Return '0' if value is empty/placeholder."""
            s = str(v).strip()
            if not s or s in ("DD/MM/AAAA", "00:00"): return "0"
            return s
        for tk_name in tank_list:
            i_ref = val_or_zero(self.get_var(f"inicial_{tk_name}_alt_ref").get())
            i_uti = val_or_zero(self.get_var(f"inicial_{tk_name}_alt_uti").get())
            i_temp = self.get_var(f"inicial_{tk_name}_temp").get()
            i_temp = self.parse_float(i_temp) 
            i_corr = val_or_zero(self.get_var(f"inicial_{tk_name}_s_corr").get())
            i_agua_real = val_or_zero(self.get_var(f"inicial_{tk_name}_agua_s_real").get())
            d_i_raw = self.get_var(f"inicial_{tk_name}_{density_mode_key}").get()
            if not d_i_raw: d_i_raw = self.get_var(f"inicial_{tk_name}_dens_lab").get()
            d_i = self.parse_float(d_i_raw)
            table_type = self.get_var(f"inicial_{tk_name}_tabla_vcf").get()
            if not table_type: table_type = "54B (Combustibles)"
            i_bruto = self.interpolar_prod("inicial", tk_name)
            i_agua = self.interpolar_agua("inicial", tk_name)
            i_neto = i_bruto - i_agua
            i_vcf = self.calc_vcf(d_i, i_temp, table_type) if d_i > 0 else 1.0
            i_15 = i_neto * i_vcf
            f_ref = val_or_zero(self.get_var(f"final_{tk_name}_alt_ref").get())
            f_uti = val_or_zero(self.get_var(f"final_{tk_name}_alt_uti").get())
            f_temp = self.get_var(f"final_{tk_name}_temp").get()
            f_temp = self.parse_float(f_temp) 
            f_corr = val_or_zero(self.get_var(f"final_{tk_name}_s_corr").get())
            f_agua_real = val_or_zero(self.get_var(f"final_{tk_name}_agua_s_real").get())
            d_f_raw = self.get_var(f"final_{tk_name}_{density_mode_key}").get()
            if not d_f_raw: d_f_raw = self.get_var(f"final_{tk_name}_dens_lab").get()
            d_f = self.parse_float(d_f_raw)
            table_type_f = self.get_var(f"final_{tk_name}_tabla_vcf").get()
            if not table_type_f: table_type_f = "54B (Combustibles)"
            f_bruto = self.interpolar_prod("final", tk_name)
            f_agua = self.interpolar_agua("final", tk_name)
            f_neto = f_bruto - f_agua
            f_vcf = self.calc_vcf(d_f, f_temp, table_type_f) if d_f > 0 else 1.0
            f_15 = f_neto * f_vcf
            
            # Construir vals_i y vals_f según tipo
            def draw_data_row(start_x, vals):
                curr_x = start_x
                for i, v in enumerate(vals):
                    w_curr = col_w_name if i == 0 else col_w_num
                    c.drawString(curr_x, y_row, str(v))
                    curr_x += w_curr
            
            if _es_liq_rep:
                vals_i = [tk_name, i_ref, i_uti, i_agua_real, f"{i_temp:.1f}" if i_temp else "0", i_corr, f"{i_bruto:.0f}", f"{i_agua:.0f}", f"{i_neto:.0f}", f"{i_vcf:.4f}", f"{i_15:.0f}"]
                vals_f = [tk_name, f_ref, f_uti, f_agua_real, f"{f_temp:.1f}" if f_temp else "0", f_corr, f"{f_bruto:.0f}", f"{f_agua:.0f}", f"{f_neto:.0f}", f"{f_vcf:.4f}", f"{f_15:.0f}"]
            elif _es_el_rep_t:
                def _eg(k): return val_or_zero(self.get_var(k).get())
                vals_i = [tk_name, _eg(f"inicial_{tk_name}_el_kwh_act"), _eg(f"inicial_{tk_name}_el_kwh_rea"),
                          _eg(f"inicial_{tk_name}_el_fp"), _eg(f"inicial_{tk_name}_el_dem"),
                          _eg(f"inicial_{tk_name}_el_V"), _eg(f"inicial_{tk_name}_el_A"),
                          _eg(f"inicial_{tk_name}_el_VA"), _eg(f"inicial_{tk_name}_el_fases"), "—", "—"]
                vals_f = [tk_name, _eg(f"final_{tk_name}_el_kwh_act"), _eg(f"final_{tk_name}_el_kwh_rea"),
                          _eg(f"final_{tk_name}_el_fp"), _eg(f"final_{tk_name}_el_dem"),
                          _eg(f"final_{tk_name}_el_V"), _eg(f"final_{tk_name}_el_A"),
                          _eg(f"final_{tk_name}_el_VA"), _eg(f"final_{tk_name}_el_fases"), "—", "—"]
            elif _es_duc_rep_t:
                def _dg(k): return val_or_zero(self.get_var(k).get())
                vals_i = [tk_name, _dg(f"inicial_{tk_name}_cont_ini"), _dg(f"inicial_{tk_name}_cont_fin"),
                          _dg(f"inicial_{tk_name}_vol_linea"), _dg(f"inicial_{tk_name}_P_lin"),
                          _dg(f"inicial_{tk_name}_T_lin"), _dg(f"inicial_{tk_name}_Z"),
                          _dg(f"inicial_{tk_name}_vol_base"), _dg(f"inicial_{tk_name}_vol_base_km3"),
                          _dg(f"inicial_{tk_name}_caudal_mh"), _dg(f"inicial_{tk_name}_masa_coriolis")]
                vals_f = [tk_name, _dg(f"final_{tk_name}_cont_ini"), _dg(f"final_{tk_name}_cont_fin"),
                          _dg(f"final_{tk_name}_vol_linea"), _dg(f"final_{tk_name}_P_lin"),
                          _dg(f"final_{tk_name}_T_lin"), _dg(f"final_{tk_name}_Z"),
                          _dg(f"final_{tk_name}_vol_base"), _dg(f"final_{tk_name}_vol_base_km3"),
                          _dg(f"final_{tk_name}_caudal_mh"), _dg(f"final_{tk_name}_masa_coriolis")]
            elif _es_gas_rep_t:
                def _gg(k): return val_or_zero(self.get_var(k).get())
                vals_i = [tk_name, _gg(f"inicial_{tk_name}_prod_name"), _gg(f"inicial_{tk_name}_presion"),
                          _gg(f"inicial_{tk_name}_temp_liq"), _gg(f"inicial_{tk_name}_dens_liq"),
                          _gg(f"inicial_{tk_name}_vol_liq"), _gg(f"inicial_{tk_name}_fase"),
                          _gg(f"inicial_{tk_name}_vol_nat_prod"), _gg(f"inicial_{tk_name}_factor_z"), "—", "—"]
                vals_f = [tk_name, _gg(f"final_{tk_name}_prod_name"), _gg(f"final_{tk_name}_presion"),
                          _gg(f"final_{tk_name}_temp_liq"), _gg(f"final_{tk_name}_dens_liq"),
                          _gg(f"final_{tk_name}_vol_liq"), _gg(f"final_{tk_name}_fase"),
                          _gg(f"final_{tk_name}_vol_nat_prod"), _gg(f"final_{tk_name}_factor_z"), "—", "—"]
            elif _es_esf_rep_t:
                def _sfg(k): return val_or_zero(self.get_var(k).get())
                vals_i = [tk_name, _sfg(f"inicial_{tk_name}_esf_pres"), _sfg(f"inicial_{tk_name}_esf_temp"),
                          _sfg(f"inicial_{tk_name}_esf_dens"), _sfg(f"inicial_{tk_name}_vol_liq"),
                          _sfg(f"inicial_{tk_name}_esf_vol_gas"), _sfg(f"inicial_{tk_name}_esf_masa"),
                          _sfg(f"inicial_{tk_name}_esf_fase"), "—", "—", "—"]
                vals_f = [tk_name, _sfg(f"final_{tk_name}_esf_pres"), _sfg(f"final_{tk_name}_esf_temp"),
                          _sfg(f"final_{tk_name}_esf_dens"), _sfg(f"final_{tk_name}_vol_liq"),
                          _sfg(f"final_{tk_name}_esf_vol_gas"), _sfg(f"final_{tk_name}_esf_masa"),
                          _sfg(f"final_{tk_name}_esf_fase"), "—", "—", "—"]
            elif _es_cgb_rep_t:
                def _cgg(k): return val_or_zero(self.get_var(k).get())
                vals_i = [tk_name, _cgg(f"inicial_{tk_name}_cg_pres"), _cgg(f"inicial_{tk_name}_cg_temp"),
                          _cgg(f"inicial_{tk_name}_cg_dens"), _cgg(f"inicial_{tk_name}_cg_masa"),
                          _cgg(f"inicial_{tk_name}_cg_vol"), _cgg(f"inicial_{tk_name}_cg_vol_gas"),
                          _cgg(f"inicial_{tk_name}_fase"), "—", "—", "—"]
                vals_f = [tk_name, _cgg(f"final_{tk_name}_cg_pres"), _cgg(f"final_{tk_name}_cg_temp"),
                          _cgg(f"final_{tk_name}_cg_dens"), _cgg(f"final_{tk_name}_cg_masa"),
                          _cgg(f"final_{tk_name}_cg_vol"), _cgg(f"final_{tk_name}_cg_vol_gas"),
                          _cgg(f"final_{tk_name}_fase"), "—", "—", "—"]
            else:
                # Tierra y camión cisterna
                def _tg(k): return val_or_zero(self.get_var(k).get())
                vals_i = [tk_name, _tg(f"inicial_{tk_name}_num_uti"), _tg(f"inicial_{tk_name}_s_tierra"),
                          _tg(f"inicial_{tk_name}_s_corr"), f"{i_temp:.1f}" if i_temp else "0",
                          _tg(f"inicial_{tk_name}_vol_bruto"), f"{i_agua:.0f}",
                          f"{i_neto:.0f}", f"{i_vcf:.4f}", f"{i_15:.0f}", "—"]
                vals_f = [tk_name, _tg(f"final_{tk_name}_num_uti"), _tg(f"final_{tk_name}_s_tierra"),
                          _tg(f"final_{tk_name}_s_corr"), f"{f_temp:.1f}" if f_temp else "0",
                          _tg(f"final_{tk_name}_vol_bruto"), f"{f_agua:.0f}",
                          f"{f_neto:.0f}", f"{f_vcf:.4f}", f"{f_15:.0f}", "—"]
            draw_data_row(x_start, vals_i)
            draw_data_row(x_mid, vals_f)
            y_row -= 10
            if y_row < 50: c.showPage(); y_row = h - 50
        c.line(35, y_row+5, w-35, y_row+5); y_row -= 5 
        c.setFont("Helvetica-Bold", 8)
        c.setFillColor(colors.blue)
        texto_inicial = f"El total de litros naturales es {sum_ini['neto']:,.0f} y de litros a 15 es {sum_ini['15']:,.0f}"
        c.drawString(x_start, y_row, texto_inicial)
        texto_final = f"El total de litros naturales es {sum_fin['neto']:,.0f} y de litros a 15 es {sum_fin['15']:,.0f}"
        c.drawString(x_mid, y_row, texto_final)
        y_row -= 10
        c.setFillColor(colors.black)
        y_row -= 15

        if is_partial:
            x_transf = x_mid + 245 
            def draw_stat_line(lbl, val_i, val_f, transf_label=None, transf_val=None, color_transf=colors.black):
                c.setFillColor(colors.black)
                c.drawString(x_start, y_row, f"{lbl}: {val_i}")
                c.drawString(x_mid, y_row, f"{lbl}: {val_f}")
                if transf_label:
                    c.setFillColor(colors.black)
                    c.setFont("Helvetica-Bold", 8)
                    c.drawString(x_transf, y_row, f"{transf_label}: ")
                    if transf_val is not None:
                        c.setFillColor(color_transf)
                        c.setFont("Helvetica", 8)
                        width_lbl = c.stringWidth(f"{transf_label}: ", "Helvetica-Bold", 8)
                        c.drawString(x_transf + width_lbl, y_row, str(transf_val))
                c.setFillColor(colors.black) 
            
            c.setFont("Helvetica", 8)
            draw_stat_line("Total Litros Naturales Netos", f"{sum_ini['neto']:,.0f}", f"{sum_fin['neto']:,.0f}", "Diferencia Litros Naturales", f"{dif_net:,.0f}")
            y_row -= 12
            draw_stat_line("Total Litros a 15º C", f"{sum_ini['15']:,.0f}", f"{sum_fin['15']:,.0f}", "Diferencia Litros a 15 C", f"{dif_15:,.0f}")
            y_row -= 12
            draw_stat_line("Densidad del producto", f"{avg_d_i:.4f}", f"{avg_d_f:.4f}", "Diferencia Kilos Aire", f"{dif_ka:,.0f}")
            y_row -= 12
            draw_stat_line("Total Kilos Aire", f"{ka_i:,.0f}", f"{ka_f:,.0f}", "Diferencia Kilos Vacío", f"{dif_kv:,.0f}")
            y_row -= 12
            c.setFont("Helvetica-Bold", 8)
            c.drawString(x_start, y_row, f"Total Kilogramos al Vacío: {kv_i:,.0f}")
            c.drawString(x_mid, y_row, f"Total Kilogramos al Vacío: {kv_f:,.0f}")
            dens_transf = avg_d_f if avg_d_f > 0 else avg_d_i
            c.drawString(x_transf, y_row, "Densidad Doc: ")
            c.setFont("Helvetica", 8)
            c.drawString(x_transf + c.stringWidth("Densidad Doc: ", "Helvetica-Bold", 8), y_row, f"{dens_transf:.4f}")
            y_row -= 12
            y_row -= 25
        else:
            c.setFont("Helvetica-Bold", 10)
            c.drawString(53, y_row, "Producto por Tanque:")
            y_row -= 15
            mapa_ddt = {}
            for tk_name in tank_list:
                d_assign = self.get_var(f"inicial_{tk_name}_ddt_assign").get()
                if d_assign:
                    if d_assign not in mapa_ddt: mapa_ddt[d_assign] = []
                    mapa_ddt[d_assign].append(tk_name)
            c.setFont("Helvetica", 8)
            for d_num, tks in mapa_ddt.items():
                found = next((d for d in self.ddt_data if d["numero"].get() == d_num), None)
                if found:
                    prod = found["producto"].get()
                    pos = found["pos_arancel"].get()
                    tipo = found["tipo_doc"].get() if "tipo_doc" in found else "Detallada"
                    chunks = [tks[i:i + 4] for i in range(0, len(tks), 4)]
                    first_chunk = ", ".join(chunks[0])
                    linea = f"Documento {tipo}: {d_num} - {prod} - Pos. Arancelaria: {pos} - Tanques: {first_chunk}"
                    c.drawString(53, y_row, linea)
                    y_row -= 12
                    for chunk in chunks[1:]:
                        linea_cont = f"       (Cont. Tanques): {', '.join(chunk)}"
                        c.drawString(53, y_row, linea_cont)
                        y_row -= 12
        y_sig_line = 40
        y_sig_text = 30
        c.setLineWidth(1)
        c.setFillColor(colors.black)
        c.line(40, y_sig_line, 190, y_sig_line)
        c.drawCentredString(115, y_sig_text, "Aduana Inicial")
        c.line(240, y_sig_line, 390, y_sig_line)
        c.drawCentredString(315, y_sig_text, "Interesado Inicial")
        c.line(440, y_sig_line, 590, y_sig_line)
        c.drawCentredString(515, y_sig_text, "Aduana Final")
        c.line(640, y_sig_line, 790, y_sig_line)
        c.drawCentredString(715, y_sig_text, "Interesado Final")
        c.showPage()
        if not shared_canvas:
            c.save()
            return full_path
        return None

