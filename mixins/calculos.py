"""Motor de cálculo: VCF, interpolaciones, volúmenes, gas, eléctrico, draft survey.

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


class CalculosMixin:
    def _vcf_k0k1_1980_54B(self, rho):
        """
        Coeficientes K0/K1 de la tabla 54B según ASTM D1250-1980 (tablas impresas).
        Cuatro zonas de densidad — reproduce exactamente las tablas físicas.

        Zona 1  rho ≤ 770          K0=346.42278  K1=0.43884
        Zona 2  770 < rho < 778    Transición: alpha = A + B/rho²
        Zona 3  778 ≤ rho < 839    K0=594.5418   K1=0
        Zona 4  rho ≥ 839          K0=186.9696   K1=0.48618
        """
        if rho <= 770.0:
            return 346.42278, 0.43884, None        # (k0, k1, alpha_override)
        elif rho < 778.0:
            # Zona de transición — alpha calculado directamente, no por k0/k1
            A, B = -0.0033612, 2680.32
            alpha_override = A + B / (rho ** 2)
            return None, None, alpha_override
        elif rho < 839.0:
            return 594.5418, 0.0, None
        else:
            return 186.9696, 0.48618, None

    def _calc_vcf_exponencial(self, rho, t, k0, k1, alpha_override=None):
        """Fórmula exponencial ASTM: VCF = exp(-α·ΔT·(1 + 0.8·α·ΔT))"""
        if alpha_override is not None:
            alpha = alpha_override
        else:
            alpha = (k0 / (rho ** 2)) + (k1 / rho)
        dt  = t - 15.0
        vcf = math.exp(-alpha * dt * (1.0 + 0.8 * alpha * dt))
        return round(vcf, 5)

    def calc_volumen_geometrico_tierra(self, sondaje_mm, radio_interno_m, modo="INNAGE"):
        """V en litros. radio en metros, sondaje en mm.
        Techo fijo/flotante: cilindro vertical π*r²*h."""
        try:
            h = float(sondaje_mm) / 1000.0   # mm → m
            r = float(radio_interno_m)
            vol_m3 = math.pi * r**2 * h
            return vol_m3 * 1000.0            # m³ → litros
        except: return 0.0

    def calc_volumen_cilindro_horizontal(self, varilla_mm, radio_interno_m, largo_m):
        """V en litros para cisterna horizontal (camión).
        varilla = nivel desde el fondo, en mm."""
        try:
            h = float(varilla_mm) / 1000.0
            r = float(radio_interno_m)
            L = float(largo_m)
            if h < 0: h = 0
            if h > 2*r: h = 2*r
            ratio = (r - h) / r
            ratio = max(-1.0, min(1.0, ratio))
            alpha = math.acos(ratio)
            vol_m3 = L * r**2 * (alpha - math.sin(alpha)*math.cos(alpha))
            return vol_m3 * 1000.0
        except: return 0.0

    # ══════════════════════════════════════════════════════════════════════
    #  Interpolación bilineal por sondaje × asiento (trim) — buques/barcazas
    # ══════════════════════════════════════════════════════════════════════
    def _interp_1d(self, pts, x):
        """Interpola linealmente en una lista [(x0,y0),(x1,y1),...] (clamp en los extremos).
        Devuelve None si no hay puntos usables."""
        pts = [(float(a), float(b)) for a, b in pts if a is not None and b is not None]
        if not pts: return None
        pts.sort(key=lambda p: p[0])
        if len(pts) == 1: return pts[0][1]
        if x <= pts[0][0]:  return pts[0][1]
        if x >= pts[-1][0]: return pts[-1][1]
        for k in range(len(pts) - 1):
            x0, y0 = pts[k]; x1, y1 = pts[k+1]
            if x0 <= x <= x1:
                if x1 == x0: return y0
                return y0 + (x - x0) / (x1 - x0) * (y1 - y0)
        return pts[-1][1]

    def _interp_trim_table(self, obj, s, trim):
        """Interpolación bilineal en una tabla multi-asiento.
        obj = {"trims":[t0,t1,...], "rows":[[sondaje, v_t0, v_t1, ...], ...]}
        1) Para cada columna de asiento interpola volumen vs sondaje en 's'.
        2) Interpola esos volúmenes entre columnas según el 'trim' real (popa-proa).
        Devuelve (volumen, detalle_str) o (None, motivo)."""
        try:
            trims = [float(t) for t in obj.get("trims", [])]
            rows = [r for r in obj.get("rows", []) if r and r[0] is not None]
            if not trims or len(rows) < 1:
                return None, "tabla trim vacía"
            col_vols = []
            for c in range(len(trims)):
                pts = [(r[0], r[c+1]) for r in rows if len(r) > c+1 and r[c+1] is not None]
                v = self._interp_1d(pts, s)
                if v is not None:
                    col_vols.append((trims[c], v))
            if not col_vols:
                return None, "sin volúmenes por columna"
            vol = self._interp_1d(col_vols, trim)
            det = (f"Sondaje {s:.0f}mm, asiento {trim:+.2f}m → "
                   + " | ".join(f"t{tc:g}:{vc:.0f}" for tc, vc in col_vols)
                   + f" ⇒ {vol:.0f}")
            return vol, det
        except Exception as ex:
            return None, f"error: {ex}"

    def calc_trim(self, etapa):
        if self.is_loading_data: return
        try:
            p1 = self.parse_float(self.get_var(f"{etapa}_Calados Popa").get())
            p2 = self.parse_float(self.get_var(f"{etapa}_Calados Proa").get())
            self.get_var(f"{etapa}_Trimación").set(f"{p1-p2:.2f}")
            b = self.parse_float(self.get_var(f"{etapa}_Calados Babor").get())
            e = self.parse_float(self.get_var(f"{etapa}_Calados Estribor").get())
            self.get_var(f"{etapa}_Lista").set(f"{b-e:.2f}")
        except: pass

    def calc_sondaje_prod(self, etapa, tanque):
        if self.is_loading_data: return
        try:
            uti = self.parse_float(self.get_var(f"{etapa}_{tanque}_alt_uti").get())
            desc = self.parse_float(self.get_var(f"{etapa}_{tanque}_desc_tubo").get())
            res = uti - desc
            self.get_var(f"{etapa}_{tanque}_s_corr").set(f"{res:.0f}")
            self.calc_volumen_prod_ui(etapa, tanque)
        except: pass

    def calc_sondaje_agua(self, etapa, tanque):
        if self.is_loading_data: return
        try:
            lec = self.parse_float(self.get_var(f"{etapa}_{tanque}_agua_lectura").get())
            desc = self.parse_float(self.get_var(f"{etapa}_{tanque}_agua_desc").get())
            res = lec - desc
            self.get_var(f"{etapa}_{tanque}_agua_s_real").set(f"{res:.0f}")
            self.calc_volumen_agua_ui(etapa, tanque)
        except: pass

    def calc_volumen_prod_ui(self, etapa, tanque):
        if self.is_loading_data: return
        import json
        try:
            s = self.parse_float(self.get_var(f"{etapa}_{tanque}_s_corr").get())
            # ── Tabla de calibrado × asiento (buque/barcaza) — prioridad ────
            trim_json = self.get_var(f"{etapa}_{tanque}_tabla_trim_json").get()
            handled_trim = False
            if trim_json:
                obj = json.loads(trim_json)
                trim_m = self.parse_float(self.get_var(f"{etapa}_Trimación").get() or "0")
                vol_t, det_t = self._interp_trim_table(obj, s, trim_m)
                if vol_t is not None:
                    self.get_var(f"{etapa}_{tanque}_vol_nat_prod").set(f"{vol_t:.0f}")
                    val = vol_t
                    handled_trim = True
            # ── Tabla de calibrado multi-punto (si existe) ──────────────────
            tabla_json = "" if handled_trim else self.get_var(f"{etapa}_{tanque}_tabla_cal_json").get()
            if tabla_json:
                pts = json.loads(tabla_json)
                if len(pts) >= 2:
                    pts.sort(key=lambda x: x[0])
                    sonds = [p[0] for p in pts]; lits = [p[1] for p in pts]
                    trims = [p[2] if len(p) > 2 else 0.0 for p in pts]
                    if s <= sonds[0]: val = lits[0]; trim_corr = trims[0]
                    elif s >= sonds[-1]: val = lits[-1]; trim_corr = trims[-1]
                    else:
                        val = lits[0]; trim_corr = 0.0
                        for k in range(len(pts)-1):
                            if sonds[k] <= s <= sonds[k+1]:
                                ds = sonds[k+1] - sonds[k]
                                if ds != 0:
                                    frac = (s - sonds[k]) / ds
                                    val = lits[k] + frac * (lits[k+1] - lits[k])
                                    trim_corr = trims[k] + frac * (trims[k+1] - trims[k])
                                else:
                                    val = lits[k]; trim_corr = trims[k]
                                break
                    # Aplicar corrección de trim si hay datos de trimación
                    try:
                        trim_m = self.parse_float(self.get_var(f"{etapa}_Trimación").get() or "0")
                        if trim_corr != 0.0 and trim_m != 0.0:
                            val += trim_corr * trim_m
                    except: pass
                    self.get_var(f"{etapa}_{tanque}_vol_nat_prod").set(f"{val:.0f}")
            elif not handled_trim:
                # ── Interpolación 2 puntos (modo original) ──────────────────
                # Ignorar marcadores tipo "[5pts]" que versiones previas
                # escribían en prod_s1 (parse_float los convertía en número).
                def _pfm(k):
                    v = self.get_var(k).get()
                    return 0.0 if "[" in v else self.parse_float(v)
                s1 = _pfm(f"{etapa}_{tanque}_prod_s1")
                l1 = _pfm(f"{etapa}_{tanque}_prod_l1")
                s2 = _pfm(f"{etapa}_{tanque}_prod_s2")
                l2 = _pfm(f"{etapa}_{tanque}_prod_l2")
                if s1 == 0 and s2 == 0 and l1 == 0 and l2 == 0:
                    # Sin datos de interpolación: conservar el volumen ya
                    # cargado (p.ej. geométrico de tierra/camión o manual)
                    # en vez de pisarlo con 0 al recalcular para el PDF.
                    val = self.parse_float(self.get_var(f"{etapa}_{tanque}_vol_nat_prod").get())
                else:
                    if s2 == s1: val = l1
                    else: val = l1 + ((s - s1) / (s2 - s1)) * (l2 - l1)
                    self.get_var(f"{etapa}_{tanque}_vol_nat_prod").set(f"{val:.0f}")
            temp_str = self.get_var(f"{etapa}_{tanque}_temp").get()
            if not temp_str: return
            temp = self.parse_float(temp_str)
            table_type = self.get_var(f"{etapa}_{tanque}_tabla_vcf").get()
            if not table_type: table_type = "54B (Combustibles)"
            # Litros a 15° y kilos sobre el volumen NETO (bruto − agua de fondo),
            # igual que la planilla PDF (generar_un_reporte) y el cálculo de cargos.
            agua_lts = self.parse_float(self.get_var(f"{etapa}_{tanque}_vol_nat_agua").get() or "0")
            val_neto = val - agua_lts
            def calc_set(dens_key_suffix, out_v15, out_kv, out_ka):
                d_str = self.get_var(f"{etapa}_{tanque}_{dens_key_suffix}").get()
                if d_str:
                    dens = self.parse_float(d_str)
                    vcf = self.calc_vcf(dens, temp, table_type)
                    vol_15 = val_neto * vcf
                    d_calc = dens
                    if d_calc > 2.0: d_calc = d_calc / 1000.0
                    kg_vacio = vol_15 * d_calc
                    kg_aire = vol_15 * (d_calc - 0.0011)
                    self.get_var(f"{etapa}_{tanque}_{out_v15}").set(f"{vol_15:.0f}")
                    self.get_var(f"{etapa}_{tanque}_{out_kv}").set(f"{kg_vacio:.0f}")
                    self.get_var(f"{etapa}_{tanque}_{out_ka}").set(f"{kg_aire:.0f}")
                else:
                    self.get_var(f"{etapa}_{tanque}_{out_v15}").set("---")
                    self.get_var(f"{etapa}_{tanque}_{out_kv}").set("---")
                    self.get_var(f"{etapa}_{tanque}_{out_ka}").set("---")
            calc_set("dens_lab", "v15_lab", "kv_lab", "ka_lab")
            calc_set("dens_doc", "v15_doc", "kv_doc", "ka_doc")
            calc_set("dens_salida", "v15_sal", "kv_sal", "ka_sal")
        except: pass 

    def calc_volumen_agua_ui(self, etapa, tanque):
        if self.is_loading_data: return
        import json
        try:
            s = self.parse_float(self.get_var(f"{etapa}_{tanque}_agua_s_real").get())
            # ── Tabla × asiento para agua (buque/barcaza) — prioridad ──────
            trim_json = self.get_var(f"{etapa}_{tanque}_tabla_trim_agua_json").get()
            handled = False
            if trim_json:
                obj = json.loads(trim_json)
                trim_m = self.parse_float(self.get_var(f"{etapa}_Trimación").get() or "0")
                vol_t, _det = self._interp_trim_table(obj, s, trim_m)
                if vol_t is not None:
                    self.get_var(f"{etapa}_{tanque}_vol_nat_agua").set(f"{vol_t:.0f}")
                    handled = True
            if not handled:
                s1 = self.parse_float(self.get_var(f"{etapa}_{tanque}_agua_s1").get())
                l1 = self.parse_float(self.get_var(f"{etapa}_{tanque}_agua_l1").get())
                s2 = self.parse_float(self.get_var(f"{etapa}_{tanque}_agua_s2").get())
                l2 = self.parse_float(self.get_var(f"{etapa}_{tanque}_agua_l2").get())
                if s2 == s1: val = l1
                else: val = l1 + ((s - s1) / (s2 - s1)) * (l2 - l1)
                self.get_var(f"{etapa}_{tanque}_vol_nat_agua").set(f"{val:.0f}")
        except: self.get_var(f"{etapa}_{tanque}_vol_nat_agua").set("0")
        # El agua afecta v15/kv/ka del producto → refrescar
        self.calc_volumen_prod_ui(etapa, tanque)

    def interpolar_prod(self, etapa, tanque):
        self.calc_volumen_prod_ui(etapa, tanque)
        try: return self.parse_float(self.get_var(f"{etapa}_{tanque}_vol_nat_prod").get())
        except: return 0.0

    def interpolar_agua(self, etapa, tanque):
        self.calc_volumen_agua_ui(etapa, tanque)
        try: return self.parse_float(self.get_var(f"{etapa}_{tanque}_vol_nat_agua").get())
        except: return 0.0

    def get_interpolation_details(self, etapa, tanque):
        import json
        try:
            s = self.get_var(f"{etapa}_{tanque}_s_corr").get()
            # Tabla × asiento (trim): detalle real de la interpolación 2D
            tj = self.get_var(f"{etapa}_{tanque}_tabla_trim_json").get()
            if tj:
                trim_m = self.parse_float(self.get_var(f"{etapa}_Trimación").get() or "0")
                vol, det = self._interp_trim_table(json.loads(tj), self.parse_float(s), trim_m)
                if vol is not None: return det
            # Tabla de calibrado multi-punto
            cj = self.get_var(f"{etapa}_{tanque}_tabla_cal_json").get()
            if cj:
                pts = json.loads(cj)
                return f"Tabla de calibrado ({len(pts)} pts, {pts[0][0]:.0f}→{pts[-1][0]:.0f} mm), sondaje {s} mm"
            s1 = self.get_var(f"{etapa}_{tanque}_prod_s1").get()
            l1 = self.get_var(f"{etapa}_{tanque}_prod_l1").get()
            s2 = self.get_var(f"{etapa}_{tanque}_prod_s2").get()
            l2 = self.get_var(f"{etapa}_{tanque}_prod_l2").get()
            return f"{l1} + (({s} - {s1}) / ({s2} - {s1})) * ({l2} - {l1})"
        except: return "Error en datos"

    def get_water_interp_details(self, etapa, tanque):
        import json
        try:
            s = self.get_var(f"{etapa}_{tanque}_agua_s_real").get()
            tj = self.get_var(f"{etapa}_{tanque}_tabla_trim_agua_json").get()
            if tj:
                trim_m = self.parse_float(self.get_var(f"{etapa}_Trimación").get() or "0")
                vol, det = self._interp_trim_table(json.loads(tj), self.parse_float(s), trim_m)
                if vol is not None: return det
            s1 = self.get_var(f"{etapa}_{tanque}_agua_s1").get()
            l1 = self.get_var(f"{etapa}_{tanque}_agua_l1").get()
            s2 = self.get_var(f"{etapa}_{tanque}_agua_s2").get()
            l2 = self.get_var(f"{etapa}_{tanque}_agua_l2").get()
            return f"{l1} + (({s} - {s1}) / ({s2} - {s1})) * ({l2} - {l1})"
        except: return ""

    def get_vcf_details(self, dens, temp, table):
        """Detalle de cálculo VCF para incluir en reportes PDF."""
        try:
            rho = float(dens)
            t   = float(temp)
            if rho < 2.0: rho = rho * 1000.0
            if rho <= 0: return "S/D"

            norma = getattr(self, "norma_astm", None)
            usar_1980 = (norma is None) or (norma.get() == "1980")
            norma_str = "ASTM D1250-80" if usar_1980 else "API MPMS 11.1-2004"

            if "54A" in table:
                k0, k1, alpha_ov = 613.9723, 0.0, None
            elif "54D" in table:
                k0, k1, alpha_ov = 1489.0672, 0.0, None
            elif "54B" in table or True:
                if usar_1980:
                    k0, k1, alpha_ov = self._vcf_k0k1_1980_54B(rho)
                    if alpha_ov is not None:
                        # Zona transición
                        alpha = alpha_ov
                        zona = "Zona transición (770<ρ<778)"
                        coef_str = f"α directo={alpha:.7f}"
                    else:
                        alpha = (k0/rho**2) + (k1/rho)
                        if rho <= 770:   zona = "Zona 1 (ρ≤770)"
                        elif rho < 839:  zona = "Zona 3 (778≤ρ<839)"
                        else:            zona = "Zona 4 (ρ≥839)"
                        coef_str = f"K0={k0}, K1={k1}"
                else:
                    k0, k1, alpha_ov = 346.4228, 0.4033, None
                    alpha = (k0/rho**2) + (k1/rho)
                    zona = "—"
                    coef_str = f"K0={k0}, K1={k1}"

            if alpha_ov is None:
                alpha = (k0/rho**2) + (k1/rho) if "54B" not in table or not usar_1980 else alpha
                coef_str = coef_str if "coef_str" in dir() else f"K0={k0}, K1={k1}"
                zona = zona if "zona" in dir() else "—"

            dt  = t - 15.0
            vcf = round(math.exp(-alpha * dt * (1.0 + 0.8 * alpha * dt)), 5)
            return f"{norma_str} | {coef_str} | Alpha={alpha:.7f}, ΔT={dt:.1f}°C, VCF={vcf:.5f}"
        except:
            return "S/D"

    def calc_gas_propiedades(self, composicion_pct):
        """MW, Tc(K), Pc(kPa) de mezcla por Kay's rule."""
        try:
            total = sum(composicion_pct.values())
            if total == 0: return {"MW":16.0,"Tc":190.56,"Pc":4599.0}
            MW=Tc=Pc=0.0
            for nombre, mw, tc, pc in self.COMPONENTES_GAS:
                yi = composicion_pct.get(nombre,0.0)/total
                MW+=yi*mw; Tc+=yi*tc; Pc+=yi*pc
            return {"MW":MW,"Tc":Tc,"Pc":Pc}
        except: return {"MW":16.0,"Tc":190.56,"Pc":4599.0}

    def calc_factor_z(self, P_kPa, T_C, Tc_K=190.56, Pc_kPa=4599.0, composicion_pct=None):
        """Factor Z por ecuacion de Papay (AGA simplificado, prec. +-0.3%)."""
        try:
            if composicion_pct:
                props = self.calc_gas_propiedades(composicion_pct)
                Tc_K=props["Tc"]; Pc_kPa=props["Pc"]
            Tr = (T_C+273.15)/Tc_K
            Pr = P_kPa/Pc_kPa
            Z = 1-(3.52*Pr)/(10**(0.9813*Tr))+(0.274*Pr**2)/(10**(0.8157*Tr))
            return max(0.50,min(1.05,Z))
        except: return 1.0

    def calc_volumen_base_gas(self, vol_m3, P_kPa, T_C, Z, P_base=101.325, T_base_C=15.0):
        """V condiciones de línea → V condiciones base (IRAM/AGA)."""
        try:
            return vol_m3*(P_kPa/P_base)*((T_base_C+273.15)/(T_C+273.15))*(1.0/Z)
        except: return 0.0

    def calc_pig_volumen_m3(self, diametro_pulg, longitud_m):
        """Volumen nominal del tramo (calibración pig)."""
        try:
            D=float(diametro_pulg)*0.0254; L=float(longitud_m)
            return math.pi/4*D**2*L
        except: return 0.0

    def calc_energia_electrica(self, lect_ini, lect_fin, constante=1.0):
        """kWh = (fin - ini) * constante de transformacion."""
        try: return (float(lect_fin)-float(lect_ini))*float(constante)
        except: return 0.0

    def calc_fp_kwh(self, kwh_act, kwh_react):
        """cos φ desde kWh activa/reactiva."""
        try:
            a,r=float(kwh_act),float(kwh_react)
            return a/math.sqrt(a**2+r**2) if (a**2+r**2)>0 else 1.0
        except: return 1.0

    def calc_volumen_camion_gas(self, masa_kg, dens_kgm3):
        """Vol líquido GLP/GNC en cisterna a presión (L)."""
        try: return (float(masa_kg)/float(dens_kgm3))*1000.0
        except: return 0.0

    def calc_masa_gas_cil_horizontal(self, varilla_mm, radio_m, largo_m, densidad_kgm3):
        """Masa de líquido GLP en cisterna horizontal (por varilla)."""
        try:
            vol_l = self.calc_volumen_cilindro_horizontal(varilla_mm, radio_m, largo_m)
            return (vol_l / 1000.0) * float(densidad_kgm3)
        except: return 0.0

    def calc_gas_fase(self, presion_kpa, temp_c, producto="GLP"):
        """Determina fase (líquido/gas/bifásico) según P/T.
        GLP propano: P_sat a 20°C ≈ 836 kPa, a -42°C ≈ 101 kPa.
        GLP butano:  P_sat a 20°C ≈ 210 kPa, a -0.5°C ≈ 101 kPa.
        GNC: siempre gas (alta presión)."""
        try:
            if "GNC" in producto.upper() or "GNV" in producto.upper():
                return "GAS COMPRIMIDO"
            # Approximación lineal de P_sat para propano/butano mixtura
            # P_sat(T) ≈ 101.325 * exp(a + b/T_K) — usamos tabla simplificada
            t_k = temp_c + 273.15
            # Propano: log(P_sat/kPa) = 6.803 - 803.8/T_K
            psat_prop = 10 ** (6.803 - 803.8/t_k)
            if presion_kpa > psat_prop * 1.05: return "LÍQUIDO"
            elif presion_kpa < psat_prop * 0.95: return "GAS"
            else: return "BIFÁSICO"
        except: return "DESCONOCIDO"

    def _get_cromatografia(self, prefix):
        """Devuelve dict {nombre: %mol} desde variables de cromatografia."""
        comp_names = ["CH4","C2H6","C3H8","iC4","nC4","iC5","nC5","C6+","N2","CO2","H2S"]
        result = {}
        for cn in comp_names:
            val = self.parse_float(self.get_var(f"{prefix}_gc_{cn}").get() or "0")
            if val > 0: result[cn] = val
        return result if result else None

    def calc_potencia_aparente(self, V, I):
        try: return float(V)*float(I)
        except: return 0.0

    def calc_draft_trim(self, proa_b, proa_e, popa_b, popa_e, medio_b, medio_e):
        """Calados medios en proa, medio y popa."""
        proa  = (proa_b  + proa_e)  / 2
        popa  = (popa_b  + popa_e)  / 2
        medio = (medio_b + medio_e) / 2
        trim  = popa - proa  # positivo = trimado a popa (stern trim)
        return proa, popa, medio, trim

    def calc_draft_corr_trim(self, proa, popa, medio, lbp):
        """Corrección de calado medio por trimado (método estándar Lloyd's/RINA).
        Dc = (Dproa + 6*Dmedio + Dpopa) / 8  → calado hidrostático (mean of means)
        Corrección por diferencia de centro de carena: δ = trim * (LCF - LBP/2) / LBP
        """
        try:
            d_medio_corr = (proa + 6*medio + popa) / 8
            return d_medio_corr
        except: return (proa + 6*medio + popa) / 8

    def calc_draft_hog_sag(self, proa, popa, medio):
        """Hog (camello) o Sag (pandeo).
        Positivo = Hog (buque arqueado hacia arriba, medio más alto que extremos).
        Negativo = Sag (buque pandeado, medio más bajo)."""
        teorico_medio = (proa + popa) / 2
        diff = medio - teorico_medio
        if diff > 0.002:   return ("HOG", round(diff*1000, 1))
        elif diff < -0.002: return ("SAG", round(abs(diff)*1000, 1))
        else:               return ("RECTO", 0.0)

    def calc_desplazamiento_interpolado(self, calado_m, tabla_hidro):
        """Interpola desplazamiento desde tabla hidrostática.
        tabla_hidro: lista de (calado_m, desplaz_t, tpc, lcf_m) ordenada por calado."""
        if not tabla_hidro: return 0.0, 0.0, 0.0
        tabla = sorted(tabla_hidro, key=lambda x: x[0])
        if calado_m <= tabla[0][0]:  return tabla[0][1], tabla[0][2], tabla[0][3]
        if calado_m >= tabla[-1][0]: return tabla[-1][1], tabla[-1][2], tabla[-1][3]
        for i in range(len(tabla)-1):
            c0,d0,t0,l0 = tabla[i]
            c1,d1,t1,l1 = tabla[i+1]
            if c0 <= calado_m <= c1:
                f = (calado_m - c0) / (c1 - c0)
                return d0+f*(d1-d0), t0+f*(t1-t0), l0+f*(l1-l0)
        return 0.0, 0.0, 0.0

    def calc_draft_desp_trimado(self, desp_medio, trim_m, tpc, lcf, lbp):
        """Corrección del desplazamiento por trimado (1ª corrección de trim).
        δD = TPC * trim * (LCF - LBP/2) * 100 / LBP
        """
        try:
            if lbp <= 0: return desp_medio
            corr = tpc * trim_m * (lcf - lbp/2) * 100.0 / lbp
            return desp_medio + corr
        except: return desp_medio

    def calc_draft_peso_carga(self, desp_llegada, desp_salida, constante_buque,
                              peso_combustible_ini, peso_combustible_fin,
                              peso_agua_ini, peso_agua_fin,
                              otros_ini=0.0, otros_fin=0.0):
        """Peso de la carga por diferencia de desplazamiento.
        Carga = (Desp_fin - Desp_ini)
                - [(Constante_fin - Constante_ini)]
                - [(Comb_fin - Comb_ini) + (Agua_fin - Agua_ini) + (Otros_fin - Otros_ini)]
        """
        delta_desp    = desp_llegada - desp_salida
        delta_const   = constante_buque
        delta_deducts = (peso_combustible_fin - peso_combustible_ini) + \
                        (peso_agua_fin - peso_agua_ini) + \
                        (otros_fin - otros_ini)
        peso_carga = delta_desp - delta_const - delta_deducts
        return peso_carga, delta_desp, delta_deducts

    def calc_vcf(self, dens_input, temp_input, table_type):
        """
        Calcula VCF (Volume Correction Factor) según la norma seleccionada.

        NORMA 1980 — ASTM D1250-80 (tablas impresas, uso habitual aduana AR):
          54B: 4 zonas de densidad con coeficientes distintos
               ρ ≤ 770        K0=346.42278  K1=0.43884
               770 < ρ < 778  transición:   α = -0.0033612 + 2680.32/ρ²
               778 ≤ ρ < 839  K0=594.5418   K1=0
               ρ ≥ 839        K0=186.9696   K1=0.48618
          54A: K0=613.9723  K1=0  (igual en ambas normas)
          54D: K0=1489.0672 K1=0  (igual en ambas normas)

        NORMA 2004 — API MPMS 11.1 / ASTM D1250-04 (norma digital):
          54B: K0=346.4228  K1=0.4033  (fórmula única para todo el rango)
          54A: K0=613.9723  K1=0
          54D: K0=1489.0672 K1=0

        Resultado siempre redondeado a 5 decimales (ASTM D1250).
        """
        try:
            if not dens_input or not temp_input: return 1.0
            rho = float(dens_input)
            t   = float(temp_input)
            if rho <= 0: return 1.0
            if rho < 2.0: rho = rho * 1000.0     # g/cm³ → kg/m³

            # ── Tablas con fórmula lineal ─────────────────────────────────────
            if "Químico" in table_type:
                return round(max(0.50, min(1.50, 1.0 - 0.0011 * (t - 15.0))), 5)

            elif "GLP" in table_type or "Propano" in table_type:
                # API MPMS 11.2.4 / GPA 8217 tabla 54E — alpha depende de rho
                alpha_glp = 757.0 / (rho ** 2)
                return round(max(0.80, min(1.20, 1.0 - alpha_glp * (t - 15.0))), 5)

            elif "GNL" in table_type or "Criog" in table_type:
                # Metano líquido, base -162°C, alpha=0.00468/°C (NIST)
                return round(max(0.50, min(1.50, 1.0 - 0.00468 * (t - (-162.0)))), 5)

            elif "Amoniaco" in table_type or "Refrigerante" in table_type:
                # NH3, alpha=0.00226/°C (Measurement Canada / Haar & Gallagher)
                return round(max(0.70, min(1.30, 1.0 - 0.00226 * (t - 15.0))), 5)

            elif "Sin corrección" in table_type or "VCF=1" in table_type:
                return 1.00000

            # ── Tablas ASTM 54 con fórmula exponencial ────────────────────────
            norma = getattr(self, "norma_astm", None)
            usar_1980 = (norma is None) or (norma.get() == "1980")

            if "54A" in table_type:
                # Igual en 1980 y 2004
                return self._calc_vcf_exponencial(rho, t, 613.9723, 0.0)

            elif "54D" in table_type:
                # Igual en 1980 y 2004
                return self._calc_vcf_exponencial(rho, t, 1489.0672, 0.0)

            elif "54B" in table_type or True:   # fallback = 54B
                if usar_1980:
                    k0, k1, alpha_ov = self._vcf_k0k1_1980_54B(rho)
                    return self._calc_vcf_exponencial(rho, t, k0, k1, alpha_ov)
                else:
                    # 2004: fórmula única
                    return self._calc_vcf_exponencial(rho, t, 346.4228, 0.4033)

        except:
            return 1.0

