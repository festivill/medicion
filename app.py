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

from mixins import (
    HelpersMixin,
    CalculosMixin,
    CaratulaUIMixin,
    TanquesUIMixin,
    DibujoTkMixin,
    PdfReportsMixin,
    CargosMixin,
    PersistenciaMixin,
)

class PlanillaFinalApp(HelpersMixin, CalculosMixin, CaratulaUIMixin, TanquesUIMixin, DibujoTkMixin, PdfReportsMixin, CargosMixin, PersistenciaMixin):
    def __init__(self, root):
        self.root = root
        _instalar_hooks(root)   # errores no capturados → medicion.log
        self.root.title("Sistema de Medición - V120 (VCF gases: GLP K0/rho2 | GNL alpha=0.00468 | NH3 alpha=0.00226)")
        self.root.geometry("1600x900")
        
        self.setup_icon()
        
        self.ui_font_size = 9 
        self.tabs_built = {1: False, 2: False, 3: False}
        self.is_loading_data = False

        self.vars = {}
        self.norma_astm = tk.StringVar(value="1980")   # "1980" | "2004"
        self.ddt_data = [] 
        self.ddt_counter = 0
        self.combos_ddt = [] 
        self.funcionarios_data = []
        self.func_counter = 0

        self.lista_tanques = []
        for i in range(1, 9): 
            self.lista_tanques.append(f"TK {i} BABOR")
            self.lista_tanques.append(f"TK {i} ESTRIBOR")
        self.lista_tanques.append("SLOP BABOR")
        self.lista_tanques.append("SLOP ESTRIBOR")
        self.lista_carbonera = ["CARBONERA 1"]

        # --- MENU ---
        menubar = tk.Menu(root)
        filemenu = tk.Menu(menubar, tearoff=0)
        filemenu.add_command(label="Nueva Medición", command=self.nueva_medicion)
        filemenu.add_separator()
        filemenu.add_command(label="Cargar Datos (.meg)", command=self.cargar_datos)
        filemenu.add_command(label="Guardar Datos (.meg)...", command=self.guardar_datos_manual)
        filemenu.add_separator()
        filemenu.add_command(label="Cargar Carátula...", command=self.cargar_caratula)
        filemenu.add_command(label="Guardar Carátula...", command=self.guardar_caratula)
        filemenu.add_separator()
        filemenu.add_command(label="Generar Reportes PDF...", command=self.generar_con_seleccion)
        filemenu.add_separator()
        filemenu.add_command(label="Salir", command=root.quit)
        menubar.add_cascade(label="Archivo", menu=filemenu)
        root.config(menu=menubar)

        # --- NOTEBOOK ---
        self.notebook = ttk.Notebook(root)
        self.tab_caratula = ttk.Frame(self.notebook)
        self.tab_ini_prod = ttk.Frame(self.notebook)
        self.tab_fin_prod = ttk.Frame(self.notebook)
        self.tab_preview = ttk.Frame(self.notebook)
        
        self.notebook.add(self.tab_caratula, text=' 1. CARÁTULA (Documentos) ')
        self.notebook.add(self.tab_ini_prod, text=' 2. INICIAL (Completo) ')
        self.notebook.add(self.tab_fin_prod, text=' 3. FINAL (Completo) ')
        self.notebook.add(self.tab_preview, text=' 4. VISTA PREVIA / REPORTES ')
        
        self.notebook.pack(expand=True, fill="both")
        self.notebook.bind("<<NotebookTabChanged>>", self.on_tab_changed)

        self.construir_caratula()
        if not self.ddt_data: self.agregar_ddt_row(def_prod="GASOIL")
        self.lista_carbonera = ["CARBONERA 1"]

        self.status_bar = tk.Label(root, text="V120: Norma VCF seleccionable — 1980 (tablas impresas) | 2004 (API MPMS 11.1)", bd=1, relief=tk.SUNKEN, anchor=tk.W)
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X)
        self._update_norma_status()
        self._recuperar_autosave()   # ofrecer recuperar sesión previa (si hay)
        self.auto_save_loop()
        
        # --- RESPONSIVE FONTS ---
        self._last_responsive_w = 0
        self._setup_responsive_fonts()
        root.bind("<Configure>", self._on_root_configure)

    def _update_norma_status(self):
        """Actualiza la barra de estado con la norma activa."""
        n = self.norma_astm.get()
        if n == "1980":
            info = "Norma activa: ASTM D1250-1980 (tablas impresas — 4 zonas densidad en 54B)"
        else:
            info = "Norma activa: API MPMS 11.1-2004 (digital — K0=346.4228 K1=0.4033 en 54B)"
        self.status_bar.config(text=info)

    def _on_norma_changed(self):
        """Llamado al cambiar la norma — recalcula todas las celdas visibles."""
        self._update_norma_status()
        # Forzar recálculo de todos los tanques (pestaña activa)
        try:
            for etapa in ("inicial", "final"):
                for tk_name in self.lista_tanques + self.lista_carbonera:
                    self.calc_volumen_prod_ui(etapa, tk_name)
        except Exception:
            pass

    def _setup_responsive_fonts(self):
        """Calcula el tamaño de fuente base según el ancho de la ventana y aplica estilos ttk."""
        w = self.root.winfo_width() or 1600
        h = self.root.winfo_height() or 900
        # Escala: 1600px ancho = tamaño 9. Cap en 11 para evitar X11 BadLength con RENDER
        base = max(7, min(10, int(w / 178)))
        small = max(6, base - 1)
        big   = base + 2
        title = base + 4
        self.ui_font_size = base

        style = ttk.Style()
        style.configure(".", font=("Arial", base))
        style.configure("TLabel",    font=("Arial", base))
        style.configure("TEntry",    font=("Arial", base))
        style.configure("TButton",   font=("Arial", base))
        style.configure("TCombobox", font=("Arial", base))
        style.configure("TNotebook.Tab", font=("Arial", min(8, base), "bold"), padding=[8, 4])
        style.configure("TLabelframe.Label", font=("Arial", min(8, base), "bold"))
        style.configure("Treeview",  font=("Arial", small), rowheight=max(18, base + 8))
        style.configure("Treeview.Heading", font=("Arial", min(8, small), "bold"))
        # Tk native widgets need to be updated too - we store the fonts for reuse
        self._font_base  = ("Arial", base)
        self._font_small = ("Arial", small)
        self._font_big   = ("Arial", min(8, big), "bold")
        self._font_title = ("Arial", min(8, title), "bold")

    def _on_root_configure(self, event):
        """Actualiza fuentes cuando cambia el tamaño de la ventana principal."""
        if event.widget != self.root: return
        w = event.width
        # Solo actualizar si el ancho cambió más de 30px (evitar loops)
        if abs(w - self._last_responsive_w) < 30: return
        self._last_responsive_w = w
        self._setup_responsive_fonts()

    def setup_icon(self):
        # Ícono de la ventana (multiplataforma). Debe ir ANTES del AppUserModelID
        # de Windows: en Linux ctypes.windll no existe y cortaba setup_icon antes
        # del iconphoto, dejando el ícono genérico (engranaje) del gestor de ventanas.
        try:
            _icon_ok = False
            # 1) PNG del disco. Tk 8.6 soporta PNG; el b64 embebido es JPEG y Tk
            #    (PhotoImage) NO lee JPEG, así que hay que evitar ese camino.
            _png = os.path.join(os.path.dirname(os.path.abspath(__file__)), "arca-icon.png")
            if os.path.exists(_png):
                try:
                    icon_image = tk.PhotoImage(file=_png)
                    self.root.iconphoto(True, icon_image)
                    self._icon_image_ref = icon_image  # evitar garbage collection
                    _icon_ok = True
                except Exception:
                    pass
            # 2) Fallback: decodificar el ícono embebido con PIL (sí lee JPEG)
            if not _icon_ok:
                from PIL import Image, ImageTk
                import io
                raw = ICON_WINDOW_B64.strip()
                if "," in raw: raw = raw.split(",")[1]
                _img = Image.open(io.BytesIO(base64.b64decode(raw))).resize((64, 64), Image.LANCZOS)
                _photo = ImageTk.PhotoImage(_img)
                self.root.iconphoto(True, _photo)
                self._icon_image_ref = _photo
        except Exception:
            pass
        # AppUserModelID: solo Windows (agrupa la app bajo su ícono en la barra
        # de tareas). Protegido para no afectar a Linux/Mac.
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('arca.medicion')
        except Exception:
            pass

    # Actores propios de cada declaración detallada (con su CUIT)
    DDT_ACTOR_KEYS = ("despachante", "cuit_desp", "impexp", "cuit_impexp", "ata", "cuit_ata")
    # Mapeo actor del DDT → campo global de la carátula (fallback)
    DDT_ACTOR_GLOBAL = {
        "despachante": "car_despachante", "cuit_desp": "car_cuit_desp",
        "impexp": "car_impexp", "cuit_impexp": "car_cuit_impexp",
        "ata": "car_ata", "cuit_ata": "car_cuit_ata",
    }

    # Lookup de códigos de aduana → nombre
    _ADUANA_LOOKUP = {
        "001":"BUENOS AIRES","004":"IGUAZU REMOTO","006":"BAHIA BLANCA",
        "008":"BARRANQUERAS","009":"BELEN","010":"BUENOS AIRES NORTE",
        "011":"CLORINDA","012":"COLON (ER)","013":"COLON (BA)",
        "014":"COMODORO RIVADAVIA","015":"CONCEPCION DEL URUGUAY","016":"CONCORDIA",
        "017":"CORDOBA","018":"CORRIENTES","019":"PUERTO DESEADO",
        "020":"DIAMANTE","023":"ESQUEL","024":"FORMOSA","025":"GOYA",
        "026":"GUALEGUAYCHU","029":"IGUAZU","031":"JUJUY","033":"LA PLATA",
        "034":"LA QUIACA","037":"MAR DEL PLATA","038":"MENDOZA","040":"NECOCHEA",
        "041":"PARANA","042":"PASO DE LOS LIBRES","045":"POCITOS","046":"POSADAS",
        "047":"PUERTO MADRYN","048":"RIO GALLEGOS","049":"RIO GRANDE","052":"ROSARIO",
        "053":"SALTA","054":"SAN JAVIER","055":"SAN JUAN","057":"SAN LORENZO",
        "058":"SAN MARTIN DE LOS ANDES","059":"SAN NICOLAS","060":"SAN PEDRO",
        "061":"SANTA CRUZ","062":"SANTA FE","066":"TINOGASTA","067":"USHUAIA",
        "069":"VILLA CONSTITUCION","073":"EZEIZA","074":"TUCUMAN","075":"NEUQUEN",
        "076":"ORAN","078":"SAN RAFAEL","079":"LA RIOJA","080":"SAN ANTONIO OESTE",
        "082":"BERNARDO DE YRIGOYEN","083":"SAN LUIS","084":"SANTO TOME",
        "085":"VILLA REGINA","086":"OBERA","087":"CALETA OLIVIA",
        "088":"GENERAL DEHEZA","089":"SANTIAGO DEL ESTERO","090":"GENERAL PICO",
        "091":"BS.AS. NORTE","092":"BS.AS. SUR","093":"RAFAELA","099":"MULTIADUANA",
    }

    # --- SUBREGÍMENES DE DECLARACIÓN DETALLADA ---

    # ── Tipos de medio disponibles ───────────────────────────────
    TIPO_MEDIOS = [
        "BUQUE", "BARCAZA",
        "BUQUE GASERO/GLP", "BUQUE QUIMIQUERO", "BUQUE METANERO/GNL",
        "TANQUE FIJO", "TANQUE FLOTANTE",
        "ESFERA DE GAS",
        "CAMION CISTERNA", "CAMION GAS/GLP",
        "OLEODUCTO", "POLIDUCTO", "GASODUCTO",
        "MEDICION ELECTRICA",
        "DRAFT SURVEY",
    ]
    # Tipos permitidos en el mismo proyecto por categoría operativa
    CATEGORIA_TIPOS = {
        "BUQUE":              ["BUQUE","BARCAZA","BUQUE GASERO/GLP","BUQUE QUIMIQUERO","BUQUE METANERO/GNL","DRAFT SURVEY"],
        "BARCAZA":            ["BUQUE","BARCAZA","BUQUE GASERO/GLP","BUQUE QUIMIQUERO","BUQUE METANERO/GNL","DRAFT SURVEY"],
        "BUQUE GASERO/GLP":   ["BUQUE","BARCAZA","BUQUE GASERO/GLP","BUQUE QUIMIQUERO","BUQUE METANERO/GNL","DRAFT SURVEY"],
        "BUQUE QUIMIQUERO":   ["BUQUE","BARCAZA","BUQUE GASERO/GLP","BUQUE QUIMIQUERO","BUQUE METANERO/GNL","DRAFT SURVEY"],
        "BUQUE METANERO/GNL": ["BUQUE","BARCAZA","BUQUE GASERO/GLP","BUQUE QUIMIQUERO","BUQUE METANERO/GNL","DRAFT SURVEY"],
        "DRAFT SURVEY":       ["BUQUE","BARCAZA","BUQUE GASERO/GLP","BUQUE QUIMIQUERO","BUQUE METANERO/GNL","DRAFT SURVEY"],
        "TANQUE FIJO":        ["TANQUE FIJO","TANQUE FLOTANTE","ESFERA DE GAS"],
        "TANQUE FLOTANTE":    ["TANQUE FIJO","TANQUE FLOTANTE","ESFERA DE GAS"],
        "ESFERA DE GAS":      ["TANQUE FIJO","TANQUE FLOTANTE","ESFERA DE GAS"],
        "CAMION CISTERNA":    ["CAMION CISTERNA","CAMION GAS/GLP"],
        "CAMION GAS/GLP":     ["CAMION CISTERNA","CAMION GAS/GLP"],
        "OLEODUCTO":          ["OLEODUCTO","POLIDUCTO","GASODUCTO"],
        "POLIDUCTO":          ["OLEODUCTO","POLIDUCTO","GASODUCTO"],
        "GASODUCTO":          ["OLEODUCTO","POLIDUCTO","GASODUCTO"],
        "MEDICION ELECTRICA": ["MEDICION ELECTRICA"],
    }

    # ── Color palette por tipo de producto ──────────────────────────────────
    # AGUA siempre es #3498DB. Producto NUNCA azul.
    PROD_COLORS = {
        "default":     ("#F0B429", "#D4880A"),   # amber (gasoil genérico)
        "gasoil":      ("#F0B429", "#D4880A"),   # amber/dorado
        "fuel":        ("#3D1C0A", "#5C3317"),   # marrón oscuro (fuel oil)
        "crudo":       ("#1C0A00", "#3D1A00"),   # negro petróleo
        "nafta":       ("#FFD700", "#C9A800"),   # dorado brillante
        "glp":         ("#FF6B35", "#CC4A1A"),   # naranja GLP/propano
        "gnl":         ("#E8E8F0", "#A0A0C0"),   # blanco-plata (GNL criogénico, NUNCA azul)
        "quimico":     ("#8B6914", "#6B4F10"),   # bronce/marrón químico
        "lubricante":  ("#556B2F", "#3D4F22"),   # verde oscuro lubricante
        "agua_carga":  ("#85C1E9", "#5B9FC0"),   # azul claro (agua de carga)
        "slop":        ("#8D6E63", "#6D4C41"),   # marrón sucio slop
        "gas_comp":    ("#FF8C00", "#CC6600"),   # naranja gas comprimido
        "metanol":     ("#9B59B6", "#7D3C98"),   # violeta
        "acido":       ("#E74C3C", "#C0392B"),   # rojo ácido
    }

    SUBREGIMENES = [
        "REMO", "ER01", "ER02", "ER03", "ER05", "ER06",
        "EC01", "EC03", "ES01", "ES02", "ES06",
        "IC04", "IC05", "IC06", "IC07", "IC65",
        "IR01", "IR02", "IS01", "IS04",
        "IT01", "IT04", "IT14",
        "RE01", "TRAN", "ZF01", "ZF06"
    ]

    # ═══════════════════════════════════════════════════════════════════════════
    # SHARED DRAWING HELPERS
    # ═══════════════════════════════════════════════════════════════════════════

    # ═══════════════════════════════════════════════════════════════════════════
    # TANQUE FIJO / FLOTANTE
    # ═══════════════════════════════════════════════════════════════════════════

    # ─────────────────────────────────────────────────────────────────────────
    # CÁLCULOS ESPECÍFICOS: GAS, DUCTOS, ELECTRICIDAD
    # ─────────────────────────────────────────────────────────────────────────

    COMPONENTES_GAS = [
        ("CH4",  16.043, 190.56, 4599.0),
        ("C2H6", 30.069, 305.32, 4872.0),
        ("C3H8", 44.096, 369.83, 4248.0),
        ("iC4",  58.122, 407.82, 3640.0),
        ("nC4",  58.122, 425.12, 3796.0),
        ("iC5",  72.149, 460.35, 3381.0),
        ("nC5",  72.149, 469.70, 3370.0),
        ("C6+",  86.175, 507.60, 3025.0),
        ("N2",   28.014, 126.19, 3396.0),
        ("CO2",  44.010, 304.13, 7375.0),
        ("H2S",  34.082, 373.10, 8937.0),
    ]

    # ═══════════════════════════════════════════════════════════════════════════
    # TRIBUTOS DINÁMICOS
    # ═══════════════════════════════════════════════════════════════════════════

    # Tributos disponibles: (nombre, alicuota_default, activo_default, es_configurable)
    TRIBUTOS_CATALOGO = [
        ("Derechos de Importación",        8.0,  True,  True),
        ("Derechos de Exportación",        8.0,  True,  True),
        ("IVA",                           21.0,  False, True),
        ("IVA reducido",                  10.5,  False, True),
        ("Estadística",                    0.5,  True,  True),
        ("Anticipo Ganancias",             0.5,  True,  True),
        ("Tasa Comprobación Destino (TCD)",0.5,  False, True),
        ("Antidumping / Compensatorio",    0.0,  False, True),
        ("Ingresos Brutos (prov.)",        3.0,  False, True),
        ("Tasa Aduanera de Servicios",     0.5,  False, True),
    ]

    # ═══════════════════════════════════════════════════════════════════════════
    # DRAFT SURVEY — ESTIMACIÓN DE PESO POR CALADOS
    # Métodos de cálculo + ventana completa
    # ═══════════════════════════════════════════════════════════════════════════

    # ═══════════════════════════════════════════════════════════════════════════
    # PDF DRAWING METHODS (ReportLab) — mirror of TK drawings
    # ═══════════════════════════════════════════════════════════════════════════

    # ═══════════════════════════════════════════════════════════════════════
    # CARÁTULAS GUARDADAS — plantillas de carátula sin datos de medición
    # ═══════════════════════════════════════════════════════════════════════
    # Datos operativos de cada medición: NO se guardan en la plantilla
    CARATULA_EXCLUIR = ("car_fecha", "car_num_planilla_gen", "car_mani",
                        "car_conocimientos", "car_tipo_cambio")

