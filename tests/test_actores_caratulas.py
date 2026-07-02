# Verifica actores por documento (prefill, fallback, PDF) y carátulas guardadas.
from _base import nueva_app, setup_buque
import json, os

root, a, out = nueva_app()
setup_buque(a)
for d in a.ddt_data[:]:
    d["main_frame"].destroy()
a.ddt_data = []
a.agregar_ddt_row(data={
    "numero": "DOC-1", "num_planilla": "1", "tipo_doc": "Detallada",
    "producto": "GASOIL", "pos_arancel": "", "densidad": "0.845",
    "litros": "10000", "kilos": "8450", "salidas": [],
    "despachante": "PEREZ JUAN", "cuit_desp": "20-11111111-1",
    "impexp": "YPF S.A.", "cuit_impexp": "30-22222222-2",
    "ata": "AGENCIA SUR", "cuit_ata": "30-33333333-3"})
a.agregar_ddt_row()   # prefill automático desde DOC-1
d2 = a.ddt_data[-1]
assert d2["impexp"].get() == "YPF S.A.", d2["impexp"].get()
assert d2["cuit_ata"].get() == "30-33333333-3"

d2["impexp"].set("SHELL S.A.")
assert a._ddt_actor(d2, "impexp") == "SHELL S.A."
assert "YPF S.A." in a._actores_pdf()["impexp"] and "SHELL S.A." in a._actores_pdf()["impexp"]
# fallback a carátula
d2b = dict(d2); d2b.pop("impexp")
a.get_var("car_impexp").set("GLOBAL SA")
assert a._ddt_actor({}, "impexp") == "GLOBAL SA"

# ── Carátulas guardadas ──
import tkinter.simpledialog as sd
sd.askstring = lambda *ar, **k: "_test_caratula"
a.get_var("car_mani").set("MANI-NO-VA")
a.guardar_caratula()
p = a._caratulas_dir() / "_test_caratula.json"
assert p.exists()
dj = json.load(open(p, encoding="utf-8"))
assert dj.get("car_buque") == "TEST SHIP"
assert "car_mani" not in dj, "MANI no debe guardarse en la plantilla"
assert dj.get("_tipo_medio") == "BUQUE"
p.unlink()

root.destroy()
print("test_actores_caratulas OK")
