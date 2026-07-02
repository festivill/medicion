# Base común de los tests headless. Requiere DISPLAY (la app es tkinter);
# los tests no abren ventanas (root.withdraw) ni diálogos (se stubbean).
import os, sys, json, tempfile

# La app auto-restaura autosave.json al iniciar; en tests trabajamos sobre el
# APP_DIR real, así que lo desactivamos para partir siempre de una app en blanco.
os.environ.setdefault("MEDICION_SKIP_AUTOLOAD", "1")

APP_DIR = os.environ.get("MEDICION_DIR") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(APP_DIR)
sys.path.insert(0, APP_DIR)

import tkinter as tk           # noqa: E402
import app as appmod           # noqa: E402


def nueva_app(out_dir=None):
    """App instanciada sin ventana, con diálogos stubbeados. Devuelve (root, app, out)."""
    out = out_dir or tempfile.mkdtemp(prefix="medicion_test_")
    appmod.filedialog.askdirectory = lambda **kw: out
    appmod.messagebox.showinfo = lambda *a, **k: None
    appmod.messagebox.showerror = lambda *a, **k: print('[ERROR-BOX]', a)
    appmod.messagebox.showwarning = lambda *a, **k: print('[WARN-BOX]', a)
    appmod.subprocess.call = lambda *a, **k: 0
    root = tk.Tk()
    root.withdraw()
    a = appmod.PlanillaFinalApp(root)
    return root, a, out


TRIM_PROD = {"trims": [0.0, 0.5], "rows": [[1000, 8000, 8200], [2000, 16000, 16400]]}
TRIM_AGUA = {"trims": [0.0, 0.5], "rows": [[50, 100, 110], [150, 300, 330]]}


def cargar_tanque_buque(a, tk_name, etapa, uti, agua_lec, doc=""):
    """Carga un tanque de buque con tabla trim de producto y agua."""
    p = f"{etapa}_{tk_name}"
    a.get_var(f"{p}_prod_name").set("GASOIL")
    if doc: a.get_var(f"{p}_ddt_assign").set(doc)
    a.get_var(f"{p}_num_uti").set("UTI-77")
    a.get_var(f"{p}_alt_ref").set("9000")
    a.get_var(f"{p}_alt_uti").set(uti)
    a.get_var(f"{p}_desc_tubo").set("100")
    a.calc_sondaje_prod(etapa, tk_name)
    a.get_var(f"{p}_tabla_trim_json").set(json.dumps(TRIM_PROD))
    a.get_var(f"{p}_tabla_trim_agua_json").set(json.dumps(TRIM_AGUA))
    a.get_var(f"{p}_agua_lectura").set(agua_lec)
    a.get_var(f"{p}_agua_desc").set("0")
    a.calc_sondaje_agua(etapa, tk_name)
    a.get_var(f"{p}_temp").set("20")
    a.get_var(f"{p}_dens_lab").set("0.845")
    a.get_var(f"{p}_tabla_vcf").set("54B (Combustibles)")
    a.calc_volumen_prod_ui(etapa, tk_name)
    a.calc_volumen_agua_ui(etapa, tk_name)


def setup_buque(a, tanques=("TK 1",)):
    a.get_var("car_tipo_medio").set("BUQUE")
    a.get_var("car_tipo_nave").set("BUQUE")
    a.get_var("car_buque").set("TEST SHIP")
    a.lista_tanques = list(tanques)
    a.lista_carbonera = []
    for etapa in ("inicial", "final"):
        a.get_var(f"{etapa}_Calados Popa").set("5.50")
        a.get_var(f"{etapa}_Calados Proa").set("5.00")
        a.calc_trim(etapa)
