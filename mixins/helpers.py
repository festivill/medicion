"""Utilidades generales: vars, parseo, validaciones, tipos de medio, actores DDT.

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


class HelpersMixin:
    def get_var(self, key, default=""):
        if key not in self.vars: self.vars[key] = tk.StringVar(value=default)
        return self.vars[key]

    def _ddt_actor(self, ddt_obj, key):
        """Actor (despachante/imex/ATA o CUIT) del documento; si el documento
        no lo tiene cargado, cae a la carátula global."""
        v = ""
        try:
            sv = ddt_obj.get(key) if ddt_obj else None
            v = sv.get().strip() if isinstance(sv, tk.StringVar) else str(sv or "").strip()
        except: pass
        return v or self.get_var(self.DDT_ACTOR_GLOBAL[key]).get()

    def _actores_pdf(self, ddt_obj=None):
        """Actores a imprimir en un PDF. Con ddt_obj: los de ese documento
        (fallback carátula). Sin ddt_obj (reporte general): los valores
        distintos entre todos los documentos, unidos con ' / '."""
        res = {}
        for k in self.DDT_ACTOR_KEYS:
            if ddt_obj is not None:
                res[k] = self._ddt_actor(ddt_obj, k)
            else:
                vistos = []
                for d in self.ddt_data:
                    sv = d.get(k)
                    val = sv.get().strip() if isinstance(sv, tk.StringVar) else ""
                    if val and val not in vistos: vistos.append(val)
                res[k] = " / ".join(vistos) if vistos else self.get_var(self.DDT_ACTOR_GLOBAL[k]).get()
        return res

    def parse_float(self, value):
        if not value: return 0.0
        if isinstance(value, (int, float)): return float(value)
        val_str = str(value).strip()
        if not val_str: return 0.0
        if ',' in val_str and '.' in val_str:
            if val_str.rfind(',') > val_str.rfind('.'): val_str = val_str.replace('.', '').replace(',', '.')
            else: val_str = val_str.replace(',', '')
        elif ',' in val_str: val_str = val_str.replace(',', '.')
        val_str = re.sub(r'[^\d.-]', '', val_str)
        try: return float(val_str)
        except: return 0.0

    def aduana_nombre(self):
        """Devuelve solo el nombre de la aduana (consulta DB + dict estático)."""
        raw = self.get_var("car_lugar").get().strip()
        if " - " in raw:
            return raw.split(" - ", 1)[1].strip()
        cod = self.aduana_codigo()
        if cod:
            # Primero intenta en la DB dinámica
            try:
                aduanas_db = db_get_aduanas()
                for a in aduanas_db:
                    if a["codigo"] == cod:
                        return a["nombre"]
            except: pass
            # Fallback al lookup estático
            if cod in self._ADUANA_LOOKUP:
                return self._ADUANA_LOOKUP[cod]
        if raw and not raw[:3].isdigit():
            return raw
        return raw or "USHUAIA"

    def aduana_completa(self):
        """Devuelve la cadena completa '067 - USHUAIA'."""
        raw = self.get_var("car_lugar").get().strip()
        if " - " in raw:
            return raw
        cod = self.aduana_codigo()
        nom = self.aduana_nombre()
        if cod and nom:
            return f"{cod} - {nom}"
        return raw or "USHUAIA"

    def aduana_codigo(self):
        """Devuelve el código numérico de la aduana con ceros a la izquierda (3 dígitos).
        Ej: '67 - USHUAIA' → '067', '1 - BS.AS.' → '001'.
        Fallback: extrae el código del MANI (posición 2-5 del número).
        """
        raw = self.get_var("car_lugar").get().strip()
        if " - " in raw:
            cod = raw.split(" - ", 1)[0].strip()
            return cod.zfill(3) if cod.isdigit() else cod
        # Fallback: extraer del MANI (formato "26067MANI000618G" → "067")
        mani = self.get_var("car_mani").get().strip()
        if len(mani) >= 5 and mani[:2].isdigit() and mani[2:5].isdigit():
            return mani[2:5]
        return ""

    def inferir_tipo_operacion(self, ddt_obj):
        """Infiere tipo de operación a partir del subrégimen del documento.
        Para REMO: determina automáticamente carga/descarga comparando
        la aduana del documento con la aduana actual (car_lugar).
          - aduana_doc == aduana_actual → CARGA (Art. 959)
          - aduana_doc != aduana_actual → DESCARGA (Art. 954)
        Solo pide confirmación si no se puede determinar del número.
        """
        import re as _re
        num = ddt_obj["numero"].get().upper().strip()
        
        # Extraer subrégimen del número
        subr = ""
        for sr in ["ER01","ER02","ER03","ER05","ER06","ER07","ER08",
                   "EC01","EC03","EC06","IC04","IC05","IC06","IC07","IC65",
                   "IR01","IR02","IS01","IS04","IT01","IT04","IT14",
                   "RE01","REMO","TRAN","ZF01","ZF06"]:
            if sr in num:
                subr = sr
                break
        if not subr:
            td = ddt_obj.get("tipo_doc", None)
            if td:
                tdv = td.get() if hasattr(td, "get") else str(td)
                if "Rancho" in tdv: subr = "ER01"
                elif "Expediente" in tdv: subr = "RE01"

        # IC/IR/IS/IT → Importación (Art. 954)
        if subr.startswith("IC") or subr.startswith("IR") or subr.startswith("IS") or subr.startswith("IT"):
            return {"tipo":"importacion","art_principal":"Art. 954 del Código Aduanero",
                    "art_inc":"Art. 954 inc. c) C.A.","descripcion":f"IMPORTACIÓN ({subr})",
                    "codigo":subr,"necesita_pregunta":False}
        
        # EC* → Exportación (Art. 959)
        if subr.startswith("EC"):
            return {"tipo":"exportacion","art_principal":"Art. 959 del Código Aduanero",
                    "art_inc":"Art. 959 inc. c) C.A.","descripcion":f"EXPORTACIÓN ({subr})",
                    "codigo":subr,"necesita_pregunta":False}
        
        # Rancho bandera extranjera
        if subr in ("ER01","ER05"):
            return {"tipo":"rancho_ext","art_principal":"Art. 959 del Código Aduanero",
                    "art_inc":"Art. 959 inc. c) C.A.",
                    "descripcion":f"RANCHO DE COMBUSTIBLE - BANDERA EXTRANJERA ({subr})",
                    "codigo":subr,"necesita_pregunta":False}
        
        # Rancho bandera argentina
        if subr in ("ER02","ER06"):
            return {"tipo":"rancho_arg","art_principal":"Art. 954 del Código Aduanero",
                    "art_inc":"Art. 954 inc. c) C.A.",
                    "descripcion":f"RANCHO DE COMBUSTIBLE - BANDERA ARGENTINA ({subr})",
                    "codigo":subr,"necesita_pregunta":False}
        
        # REMO → determinar por comparación de aduanas (NUNCA preguntar para Detallada)
        if subr == "REMO":
            tipo_doc_val = ""
            td = ddt_obj.get("tipo_doc", None)
            if td: tipo_doc_val = td.get() if hasattr(td, "get") else str(td)
            es_detallada = "detallada" in tipo_doc_val.lower() or tipo_doc_val == ""
            aduana_actual = self.aduana_codigo()  # ej: "067"
            # El número de REMO tiene el código de aduana origen embebido
            # Formato típico: "AANNNNREMONNNNN" donde NNNN = cod aduana (4 dígitos o 3)
            # Intentar extraer los dígitos antes de "REMO"
            # Formato: YY(2) + ADUANA(3) + "REMO" + ...
            # Extrae los 3 dígitos en posición [2:5] del número
            remo_pos = num.find("REMO")
            if remo_pos >= 5:
                aduana_doc = num[remo_pos-3:remo_pos]          # mantener ceros: "033"
            else:
                m = _re.search(r"(\d{2})(\d{3})REMO", num)
                aduana_doc = m.group(2) if m else ""            # ya son 3 dígitos
            aduana_doc_padded = aduana_doc.zfill(3)            # asegurar 3 dígitos
            aduana_act_stripped = aduana_actual.lstrip("0")
            
            if aduana_doc and aduana_actual:
                if aduana_doc.lstrip("0") == aduana_act_stripped:
                    # Misma aduana → CARGA
                    return {"tipo":"remo_carga","art_principal":"Art. 959 del Código Aduanero",
                            "art_inc":"Art. 959 inc. c) C.A.",
                            "descripcion":"TRANSFERENCIA DE COMBUSTIBLE A LA CARGA (REMO) - MISMA ADUANA",
                            "codigo":"REMO","necesita_pregunta":False}
                else:
                    # Distinta aduana → DESCARGA
                    return {"tipo":"remo_descarga","art_principal":"Art. 954 del Código Aduanero",
                            "art_inc":"Art. 954 inc. c) C.A.",
                            "descripcion":f"REMO - DESCARGA - ADUANA ORIGEN {aduana_doc_padded} - {self._ADUANA_LOOKUP.get(aduana_doc_padded, aduana_doc_padded)}",
                            "codigo":"REMO","necesita_pregunta":False}
            # No se pudo determinar del número
            if es_detallada:
                # Detallada: nunca preguntar → asumir descarga (viene de otra aduana)
                return {"tipo":"remo_descarga","art_principal":"Art. 954 del Código Aduanero",
                        "art_inc":"Art. 954 inc. c) C.A.",
                        "descripcion":"TRANSFERENCIA DE COMBUSTIBLE A LA DESCARGA (REMO)",
                        "codigo":"REMO","necesita_pregunta":False}
            # No es Detallada → pedir confirmación
            return {"tipo":"remo","art_principal":"Art. 954 del Código Aduanero",
                    "art_inc":"Art. 954 inc. c) C.A.",
                    "descripcion":"TRANSFERENCIA DE COMBUSTIBLE (REMO)",
                    "codigo":"REMO","necesita_pregunta":True}
        
        # Default (RE01, TRAN, ZF*, etc)
        return {"tipo":"otro","art_principal":"Art. 954 del Código Aduanero",
                "art_inc":"Art. 954 inc. c) C.A.",
                "descripcion":f"OPERACIÓN ADUANERA ({subr or 'DETALLADA'})",
                "codigo":subr or "","necesita_pregunta":False}

    def clean_filename(self, text):
        return re.sub(r'[\\/*?:"<>|]', "", str(text)).strip()

    def validar_fecha(self, new_value):
        """Valida formato DD/MM/AAAA permitiendo escritura progresiva"""
        if new_value == "" or new_value == "DD/MM/AAAA":
            return True
        # Permitir solo digitos y /
        cleaned = new_value.replace("/", "")
        if not cleaned.isdigit():
            return False
        if len(new_value) > 10:
            return False
        # Auto-insertar / despues de DD y MM
        # Validar parcialmente segun lo que se lleva escrito
        parts = new_value.split("/")
        if len(parts) > 3:
            return False
        # Validar dia
        if parts[0]:
            if len(parts[0]) > 2: return False
            if len(parts[0]) == 2:
                d = int(parts[0])
                if d < 1 or d > 31: return False
        # Validar mes
        if len(parts) > 1 and parts[1]:
            if len(parts[1]) > 2: return False
            if len(parts[1]) == 2:
                m = int(parts[1])
                if m < 1 or m > 12: return False
        # Validar año
        if len(parts) > 2 and parts[2]:
            if len(parts[2]) > 4: return False
        return True

    def validar_hora(self, new_value):
        """Valida formato HH:MM permitiendo escritura progresiva"""
        if new_value == "" or new_value == "HH:MM":
            return True
        cleaned = new_value.replace(":", "")
        if not cleaned.isdigit():
            return False
        if len(new_value) > 5:
            return False
        parts = new_value.split(":")
        if len(parts) > 2:
            return False
        if parts[0]:
            if len(parts[0]) > 2: return False
            if len(parts[0]) == 2:
                h = int(parts[0])
                if h > 23: return False
        if len(parts) > 1 and parts[1]:
            if len(parts[1]) > 2: return False
            if len(parts[1]) == 2:
                m = int(parts[1])
                if m > 59: return False
        return True

    def on_fecha_focus_in(self, event, var):
        if var.get() == "DD/MM/AAAA":
            var.set("")

    def on_fecha_focus_out(self, event, var):
        if var.get() == "":
            var.set("DD/MM/AAAA")

    def on_hora_focus_in(self, event, var):
        if var.get() == "00:00" or var.get() == "HH:MM":
            var.set("")

    def on_hora_focus_out(self, event, var):
        if var.get() == "":
            var.set("00:00")

    def validar_cuit(self, cuit_str):
        """Valida CUIT/CUIL argentino. Retorna True/False y mensaje."""
        if not cuit_str or cuit_str.strip() == "":
            return True, ""
        clean = cuit_str.replace("-", "").replace(" ", "")
        if not clean.isdigit():
            return False, "Solo números y guiones"
        if len(clean) != 11:
            return False, f"Debe tener 11 dígitos (tiene {len(clean)})"
        # Verificar dígito verificador
        mult = [5, 4, 3, 2, 7, 6, 5, 4, 3, 2]
        total = sum(int(clean[i]) * mult[i] for i in range(10))
        resto = 11 - (total % 11)
        if resto == 11: dv = 0
        elif resto == 10: dv = 9
        else: dv = resto
        if int(clean[10]) != dv:
            return False, "Dígito verificador inválido"
        return True, "OK"

    def on_cuit_validate(self, widget, var):
        """Valida CUIT al salir del campo - solo feedback visual, sin popup."""
        val = var.get().strip()
        if not val:
            widget.configure(background="white")
            return
        clean = val.replace("-", "").replace(" ", "")
        if len(clean) < 11:
            # Aún incompleto, no marcar error
            widget.configure(background="#fff9c4")  # amarillo suave = en progreso
            return
        ok, msg = self.validar_cuit(val)
        if ok:
            widget.configure(background="#e8f5e9")  # verde claro
        else:
            widget.configure(background="#ffcdd2")  # rojo claro

    def auto_calc_densidad(self, sv_lits, sv_kgs, sv_dens):
        try:
            l = self.parse_float(sv_lits.get())
            k = self.parse_float(sv_kgs.get())
            if l > 0: sv_dens.set(f"{k/l:.5f}")
        except: pass

    @staticmethod
    def contrast_text(hex_color):
        """Devuelve '#FFFFFF' o '#000000' según la luminancia del color de fondo.
        Garantiza contraste legible sobre cualquier producto."""
        try:
            r = int(hex_color[1:3], 16)
            g = int(hex_color[3:5], 16)
            b = int(hex_color[5:7], 16)
            # Luminancia relativa WCAG
            lum = 0.2126 * r + 0.7152 * g + 0.0722 * b
            return "#FFFFFF" if lum < 140 else "#000000"
        except:
            return "#FFFFFF"

    def get_prod_color(self, tk_name, etapa_key=None):
        """Devuelve (fill, outline) para el producto del tanque.
        NUNCA retorna azul (#3498DB) que está reservado para AGUA."""
        prod = ""
        if etapa_key and tk_name:
            prod = self.get_var(f"{etapa_key}_{tk_name}_prod_name").get().lower()
        prod_low = prod.lower()
        if any(x in prod_low for x in ["gasoil","diesel","go "]): return self.PROD_COLORS["gasoil"]
        if any(x in prod_low for x in ["fuel","fo ","furnace"]): return self.PROD_COLORS["fuel"]
        if any(x in prod_low for x in ["crudo","crude","pf"]): return self.PROD_COLORS["crudo"]
        if any(x in prod_low for x in ["nafta","gasolin","naphtha"]): return self.PROD_COLORS["nafta"]
        if any(x in prod_low for x in ["glp","propano","butano","gas licuado"]): return self.PROD_COLORS["glp"]
        if any(x in prod_low for x in ["gnl","lng","metano","natural"]): return self.PROD_COLORS["gnl"]
        if any(x in prod_low for x in ["quim","acid","solvente","benceno","tolueno"]): return self.PROD_COLORS["quimico"]
        if any(x in prod_low for x in ["lubri","aceite"]): return self.PROD_COLORS["lubricante"]
        if any(x in prod_low for x in ["metanol","methanol","alcohol"]): return self.PROD_COLORS["metanol"]
        if any(x in prod_low for x in ["slop","residuo"]): return self.PROD_COLORS["slop"]
        return self.PROD_COLORS["default"]

    def get_tipo_medio(self):
        v = self.get_var("car_tipo_medio", "BUQUE").get().strip()
        if not v: v = self.get_var("car_tipo_nave", "BUQUE").get().strip()
        return v or "BUQUE"

    def es_maritimo(self):
        return self.get_tipo_medio() in ("BUQUE","BARCAZA",
            "BUQUE GASERO/GLP","BUQUE QUIMIQUERO","BUQUE METANERO/GNL","DRAFT SURVEY")

    def es_tierra(self):
        return self.get_tipo_medio() in ("TANQUE FIJO","TANQUE FLOTANTE")

    def es_camion(self):
        tm = self.get_tipo_medio()
        return "CAMION" in tm

    def es_camion_gas(self):
        tm = self.get_tipo_medio()
        return "CAMION GAS" in tm

    def es_ducto(self):
        tm = self.get_tipo_medio()
        return tm in ("OLEODUCTO","POLIDUCTO","GASODUCTO")

    def es_gasoducto(self):
        return self.get_tipo_medio() == "GASODUCTO"

    def es_electrico(self):
        return self.get_tipo_medio() == "MEDICION ELECTRICA"

    def es_esfera(self):
        return self.get_tipo_medio() == "ESFERA DE GAS"

    def es_no_tradicional(self):
        """Ductos + electricidad: no tienen tanques en el sentido habitual."""
        return self.es_ducto() or self.es_electrico() or self.es_esfera()

    def es_gasero(self):
        """Buques que transportan gas a presión/criogénico (NO incluye quimiquero que es líquido)."""
        tm = self.get_tipo_medio()
        # QUIMIQUERO es tanquero LÍQUIDO, no gasero — se excluye explícitamente
        return ("GASERO" in tm or "METANERO" in tm or "GNL" in tm or
                ("GLP" in tm and "CAMION" not in tm and "QUIMIQUERO" not in tm))

    def label_unidad(self):
        """Nombre genérico de la unidad operativa para labels y PDF."""
        tm = self.get_tipo_medio()
        if "BARCAZA" in tm:         return "BARCAZA"
        if "GASERO" in tm:          return "BUQUE GASERO"
        if "QUIMIQUERO" in tm:      return "BUQUE QUIMIQUERO"
        if "METANERO" in tm or "GNL" in tm: return "BUQUE METANERO/GNL"
        if "TANQUE FIJO" in tm:     return "PLANTA - TANQUE FIJO"
        if "TANQUE FLOTANTE" in tm: return "PLANTA - TANQUE FLOTANTE"
        if "CAMION GAS" in tm:      return "CAMION GAS/GLP"
        if "CAMION" in tm:          return "CAMION CISTERNA"
        if tm == "OLEODUCTO":       return "OLEODUCTO"
        if tm == "POLIDUCTO":       return "POLIDUCTO"
        if tm == "GASODUCTO":       return "GASODUCTO"
        if tm == "MEDICION ELECTRICA": return "INSTALACION ELECTRICA"
        if tm == "ESFERA DE GAS":       return "ESFERA DE GAS"
        return "BUQUE"

    def label_contenedor(self):
        """Nombre del identificador principal."""
        tm = self.get_tipo_medio()
        if self.es_tierra():          return "ID Tanque / N° Planta:"
        if "CAMION" in tm:            return "Dominio / Patente:"
        if self.es_ducto():           return "Nombre del Ducto:"
        if self.es_electrico():       return "Instalación / Punto de Medición:"
        return "Nombre Buque/Barcaza:"

    def label_doc_principal(self):
        """Etiqueta para MANI / documento de transporte."""
        if self.es_ducto():           return "N° Acta / Expediente:"
        if self.es_electrico():       return "N° Expediente / Contrato:"
        if self.es_ducto():                       return "N° Acta / Expediente:"
        if self.es_electrico():                   return "N° Expediente / Contrato:"
        if self.es_tierra() or self.es_camion():  return "N° Expediente:"
        return "N° MANI:"

    def calcular_letra_dest(self, num_str):
        """Intenta calcular la letra verificadora por módulo 23 (TRWAGMYFPDXBNJZSQVHLCKE).
        Nota: el algoritmo exacto del SIM/MALVINA no es público, esta es una aproximación."""
        tabla = "TRWAGMYFPDXBNJZSQVHLCKE"
        try:
            # Extraer solo dígitos
            digits = "".join(c for c in num_str if c.isdigit())
            if not digits: return "?"
            n = int(digits)
            return tabla[n % 23]
        except:
            return "?"

    def _apply_tipo_lock(self):
        """Bloquea el combobox de tipo_medio a la categoría de la medición actual.
        Ej: BUQUE solo puede cambiar entre tipos marítimos; TANQUE solo entre tierra, etc."""
        if not getattr(self, "_archivo_bloqueado", False): return
        tm_locked = getattr(self, "_archivo_tipo_medio", "")
        allowed = self.CATEGORIA_TIPOS.get(tm_locked, [tm_locked])
        try:
            for w in self.tab_caratula.winfo_children():
                for w2 in self._find_all_comboboxes(w):
                    try:
                        curr_var = str(self.get_var("car_tipo_medio"))
                        if hasattr(w2, "cget") and w2.cget("textvariable") == curr_var:
                            w2.config(values=allowed)
                            if len(allowed) <= 1:
                                w2.config(state="disabled")
                            else:
                                w2.config(state="readonly")
                    except: pass
        except: pass

    def _find_all_comboboxes(self, widget):
        result = []
        if isinstance(widget, ttk.Combobox): result.append(widget)
        try:
            for child in widget.winfo_children():
                result.extend(self._find_all_comboboxes(child))
        except: pass
        return result

