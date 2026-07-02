"""Autosave, archivos .meg y carátulas guardadas.

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


class PersistenciaMixin:
    def auto_save_loop(self):
        clean_ddts = []
        for d in self.ddt_data:
            c_d = {
                "numero": d["numero"].get(),
                "num_planilla": d["num_planilla"].get(),
                "tipo_doc": d["tipo_doc"].get(),
                "producto": d["producto"].get(),
                "pos_arancel": d["pos_arancel"].get(),
                "densidad": d["densidad"].get(),
                "litros": d["litros"].get(),
                "kilos": d["kilos"].get(),
                "valor_litro": d["valor_litro"].get() if "valor_litro" in d else "",
                "divisa": d["divisa"].get() if "divisa" in d else "ARS",
                "divisa_desc": d["divisa_desc"].get() if "divisa_desc" in d else "",
                "tipo_cambio": d["tipo_cambio"].get() if "tipo_cambio" in d else "",
                "salidas": []
            }
            for _ak in self.DDT_ACTOR_KEYS:
                c_d[_ak] = d[_ak].get() if _ak in d else ""
            for s in d["salidas"]:
                c_d["salidas"].append({
                    "numero": s["numero"].get(),
                    "litros": s["litros"].get(),
                    "kilos": s["kilos"].get(),
                    "densidad": s["densidad"].get()
                })
            clean_ddts.append(c_d)
        data = {k: v.get() for k, v in self.vars.items() if "tkinter" not in k and "<module" not in k}
        data["_ddt_struct"] = clean_ddts
        data["_tank_list"] = self.lista_tanques
        data["_carb_list"] = self.lista_carbonera
        data["_funcionarios"] = [{"cuil": f["cuil"].get(), "legajo": f["legajo"].get(), "apellido": f["apellido"].get(), "nombre": f["nombre"].get(), "funcion": f["funcion"].get()} for f in self.funcionarios_data]
        # Anclado al directorio de la app (no al CWD desde donde se lanzó)
        with open(_app_dir() / "autosave.json", 'w') as f: json.dump(data, f)
        self.root.after(30000, self.auto_save_loop)

    def _caratulas_dir(self):
        import sys
        base = pathlib.Path(sys.executable).parent if getattr(sys, 'frozen', False) \
            else pathlib.Path(__file__).resolve().parent
        d = base / "caratulas"
        d.mkdir(exist_ok=True)
        return d

    def guardar_caratula(self):
        """Guarda la carátula actual (buque, actores, aduana, tipo, etc.)
        como plantilla reutilizable, sin datos de medición."""
        from tkinter import simpledialog
        sugerido = self.get_var("car_buque").get().strip() or self.get_var("car_patente").get().strip() or "caratula"
        nombre = simpledialog.askstring("Guardar Carátula",
                                        "Nombre de la carátula:",
                                        initialvalue=sugerido, parent=self.root)
        if not nombre: return
        data = {k: v.get() for k, v in self.vars.items()
                if k.startswith("car_") and k not in self.CARATULA_EXCLUIR}
        data["_tipo_medio"] = self.get_tipo_medio()
        path = self._caratulas_dir() / f"{self.clean_filename(nombre)}.json"
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=1)
            messagebox.showinfo("Carátula guardada",
                                f"Guardada como «{path.stem}».\n"
                                "Solo datos de carátula (sin medición, MANI, viaje ni fecha).")
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo guardar la carátula:\n{e}")

    def cargar_caratula(self):
        """Selector de carátulas guardadas: cargar (doble click) o eliminar."""
        d = self._caratulas_dir()
        archivos = sorted(d.glob("*.json"))
        if not archivos:
            messagebox.showinfo("Sin carátulas",
                                "No hay carátulas guardadas todavía.\n"
                                "Use Archivo → Guardar Carátula… para crear una.")
            return
        top = tk.Toplevel(self.root)
        top.title("Cargar Carátula")
        top.geometry("520x420")
        top.grab_set()
        fh = tk.Frame(top, bg="#1B3A5C"); fh.pack(fill="x")
        tk.Label(fh, text="CARÁTULAS GUARDADAS", bg="#1B3A5C", fg="white",
                 font=("Arial", 10, "bold")).pack(side="left", padx=14, pady=8)
        tk.Label(fh, text="Doble click = cargar", bg="#1B3A5C", fg="#AED6F1",
                 font=("Arial", 8)).pack(side="right", padx=10)
        f_l = tk.Frame(top); f_l.pack(fill="both", expand=True, padx=12, pady=8)
        sb = ttk.Scrollbar(f_l, orient="vertical")
        lb = tk.Listbox(f_l, font=("Arial", 10), yscrollcommand=sb.set, activestyle="dotbox")
        sb.config(command=lb.yview)
        sb.pack(side="right", fill="y"); lb.pack(side="left", fill="both", expand=True)
        for p in archivos:
            desc = p.stem
            try:
                with open(p, encoding="utf-8") as f: dj = json.load(f)
                extra = dj.get("_tipo_medio", "")
                if extra: desc += f"   [{extra}]"
            except: pass
            lb.insert("end", desc)
        def _sel_path():
            sel = lb.curselection()
            return archivos[sel[0]] if sel else None
        def _cargar():
            p = _sel_path()
            if not p: return
            try:
                with open(p, encoding="utf-8") as f: dj = json.load(f)
            except Exception as e:
                messagebox.showerror("Error", f"No se pudo leer la carátula:\n{e}", parent=top)
                return
            # Tipo primero (dispara reinicio de tanques/tabs por trace)
            tm = dj.get("_tipo_medio") or dj.get("car_tipo_medio")
            if tm:
                self.get_var("car_tipo_medio").set(tm)
                self.get_var("car_tipo_nave").set(tm)
            for k, v in dj.items():
                if not k.startswith("car_") or k in self.CARATULA_EXCLUIR: continue
                if k in ("car_tipo_medio", "car_tipo_nave"): continue
                self.get_var(k).set(v)
            top.destroy()
            messagebox.showinfo("Carátula cargada",
                                f"Carátula «{p.stem}» aplicada.\n"
                                "Complete MANI, viaje, fecha y documentos de la operación.")
        def _eliminar():
            p = _sel_path()
            if not p: return
            if not messagebox.askyesno("Eliminar", f"¿Eliminar la carátula «{p.stem}»?", parent=top):
                return
            try: p.unlink()
            except Exception: pass
            top.destroy(); self.cargar_caratula()
        lb.bind("<Double-1>", lambda e: _cargar())
        fb = tk.Frame(top, bg="#2C3E50"); fb.pack(fill="x", side="bottom")
        tk.Button(fb, text="  Cargar  ", bg="#27AE60", fg="white", font=("Arial", 9, "bold"),
                  command=_cargar).pack(side="left", padx=12, pady=8, ipadx=8, ipady=3)
        tk.Button(fb, text="Eliminar", bg="#C0392B", fg="white", font=("Arial", 8),
                  command=_eliminar).pack(side="left", padx=4, pady=8, ipadx=6, ipady=2)
        tk.Button(fb, text="Cancelar", bg="#7F8C8D", fg="white", font=("Arial", 8),
                  command=top.destroy).pack(side="right", padx=12, pady=8, ipadx=6, ipady=2)

    def guardar_datos_manual(self):
        _buque_meg = self.clean_filename(self.get_var('car_buque').get()) or 'medicion'
        _fecha_meg = datetime.now().strftime('%Y%m%d')
        f = filedialog.asksaveasfilename(defaultextension=".meg", initialfile=f"{_buque_meg}_{_fecha_meg}", filetypes=[("Archivos MEG", "*.meg"), ("Todos", "*.*")])
        if f: 
            clean_ddts = []
            for d in self.ddt_data:
                c_d = {
                    "numero": d["numero"].get(),
                    "num_planilla": d["num_planilla"].get(),
                    "tipo_doc": d["tipo_doc"].get(),
                    "producto": d["producto"].get(),
                    "pos_arancel": d["pos_arancel"].get(),
                    "densidad": d["densidad"].get(),
                    "litros": d["litros"].get(),
                    "kilos": d["kilos"].get(),
                    "valor_litro": d["valor_litro"].get() if "valor_litro" in d else "",
                    "divisa": d["divisa"].get() if "divisa" in d else "ARS",
                    "divisa_desc": d["divisa_desc"].get() if "divisa_desc" in d else "",
                    "tipo_cambio": d["tipo_cambio"].get() if "tipo_cambio" in d else "",
                    "salidas": []
                }
                for _ak in self.DDT_ACTOR_KEYS:
                    c_d[_ak] = d[_ak].get() if _ak in d else ""
                for s in d["salidas"]:
                    c_d["salidas"].append({
                        "numero": s["numero"].get(),
                        "litros": s["litros"].get(),
                        "kilos": s["kilos"].get(),
                        "densidad": s["densidad"].get()
                    })
                clean_ddts.append(c_d)
            data = {k: v.get() for k, v in self.vars.items() if "tkinter" not in k and "<module" not in k}
            data["_ddt_struct"] = clean_ddts
            data["_tipo_medio"] = self.get_tipo_medio()
            data["_tank_list"] = self.lista_tanques
            data["_carb_list"] = self.lista_carbonera
            data["_funcionarios"] = [{"cuil": f["cuil"].get(), "legajo": f["legajo"].get(), "apellido": f["apellido"].get(), "nombre": f["nombre"].get(), "funcion": f["funcion"].get()} for f in self.funcionarios_data]
            with open(f, 'w') as file: json.dump(data, file)

    def cargar_datos(self):
        f = filedialog.askopenfilename(filetypes=[("Archivos MEG", "*.meg"), ("Todos", "*.*")])
        if not f: return
        try:
            with open(f, 'r') as file:
                data = json.load(file)
            # Limpiar vars antiguas
            for key in list(self.vars.keys()): self.vars[key].set("")
            self.vars.clear()
            for k,v in data.items():
                if k.startswith("_"): continue
                if "tkinter" in k or "<module" in k: continue
                self.get_var(k).set(v)
            if "_tipo_medio" in data:
                tm = data["_tipo_medio"]
                self.get_var("car_tipo_medio").set(tm)
                self.get_var("car_tipo_nave").set(tm)
                # LOCK: guardar tipo original para impedir cambio de categoría
                self._archivo_tipo_medio = tm
                self._archivo_bloqueado  = True
            # Tank lists
            if "_tank_list" in data:  self.lista_tanques  = data["_tank_list"]
            if "_carb_list"  in data: self.lista_carbonera = data["_carb_list"]
            # Rebuild UI PRIMERO - construir_caratula crea func_stack y ddt_stack frescos
            # Rebuild UI
            for w in self.tab_caratula.winfo_children(): w.destroy()
            self.combos_ddt = []
            self.construir_caratula()
            self.rebuild_all_tabs()
            self._apply_tipo_lock()  # apply lock after rebuild
            # Funcionarios - DESPUES de construir_caratula (func_stack ya existe)
            # Funcionarios
            if "_funcionarios" in data:
                self.funcionarios_data = []
                self.func_counter = 0
                for fc in data["_funcionarios"]:
                    self.agregar_funcionario_row(data=fc)
            # DDT - DESPUES de construir_caratula (ddt_stack ya existe)
            # DDT data
            for d in self.ddt_data[:]: d["main_frame"].destroy()
            self.ddt_data = []
            self.ddt_counter = 0
            if "_ddt_struct" in data:
                for ddt_d in data["_ddt_struct"]:
                    self.agregar_ddt_row(data=ddt_d)
            elif "_ddt_list" in data:  # compatibilidad con archivos viejos
                for ddt_d in data["_ddt_list"]:
                    self.agregar_ddt_row(data=ddt_d)
            elif not self.ddt_data:
                self.agregar_ddt_row(def_prod="GASOIL")
        except Exception as e:
            traceback.print_exc()
            messagebox.showerror("Error", f"No se pudo cargar el archivo:\n{e}")

