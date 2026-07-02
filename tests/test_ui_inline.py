# Verifica la sección de interp × asiento embebida en la ficha del tanque
# (producto y agua) y la apertura de la ficha completa.
from _base import nueva_app, setup_buque
import tkinter as tk

root, a, out = nueva_app()
setup_buque(a)
p = "inicial_TK 1"
a.get_var(f"{p}_prod_name").set("GASOIL")
a.get_var(f"{p}_alt_uti").set("1600"); a.get_var(f"{p}_desc_tubo").set("100")
a.calc_sondaje_prod("inicial", "TK 1")
a.get_var(f"{p}_temp").set("20"); a.get_var(f"{p}_dens_lab").set("0.845")
a.get_var(f"{p}_agua_lectura").set("80"); a.get_var(f"{p}_agua_desc").set("0")
a.calc_sondaje_agua("inicial", "TK 1")

top = tk.Toplevel(root); top.withdraw()
fr = tk.Frame(top); fr.pack()
a.crear_interp_trim_inline("inicial", "TK 1", fr, 0, agua=False)
entries = [w for w in fr.winfo_children() if isinstance(w, tk.Entry)]
vals = [None, None, "1000", "8000", "8200", "2000", "16000", "16400"]
for e, v in zip(entries, vals):
    if v is None: continue
    e.delete(0, "end"); e.insert(0, v)
root.update()
assert a.get_var(f"{p}_vol_nat_prod").get() == "12300"
assert a.get_var(f"{p}_tabla_trim_json").get() != ""

fr2 = tk.Frame(top); fr2.pack()
a.crear_interp_trim_inline("inicial", "TK 1", fr2, 0, agua=True)
entries2 = [w for w in fr2.winfo_children() if isinstance(w, tk.Entry)]
vals2 = [None, None, "50", "100", "110", "150", "300", "330"]
for e, v in zip(entries2, vals2):
    if v is None: continue
    e.delete(0, "end"); e.insert(0, v)
root.update()
assert a.get_var(f"{p}_vol_nat_agua").get() == "176"
assert a.get_var(f"{p}_v15_lab").get() == "12073"   # refrescó el producto

for e in entries2[2:8]:
    e.delete(0, "end")
root.update()
assert a.get_var(f"{p}_tabla_trim_agua_json").get() == ""

a.abrir_popup_detalle("inicial", "TK 1")
root.update()
root.destroy()
print("test_ui_inline OK")
