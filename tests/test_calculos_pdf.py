# Verifica el pipeline completo: interp × asiento, neto = bruto − agua,
# VCF, kilos, y que la generación de PDFs no falle.
from _base import nueva_app, setup_buque, cargar_tanque_buque
import os

root, a, out = nueva_app()
setup_buque(a)
cargar_tanque_buque(a, "TK 1", "inicial", "1600", "80")
cargar_tanque_buque(a, "TK 1", "final", "1200", "60")

# Interp bilineal esperada: s=1500, trim=0.5 → 12300 bruto; agua 176
assert a.get_var("inicial_TK 1_vol_nat_prod").get() == "12300", a.get_var("inicial_TK 1_vol_nat_prod").get()
assert a.get_var("inicial_TK 1_vol_nat_agua").get() == "176"
assert a.get_var("final_TK 1_vol_nat_prod").get() == "9020"
assert a.get_var("final_TK 1_vol_nat_agua").get() == "132"
# v15/kv sobre el NETO (12300−176)×0.99581 = 12073 ; ×0.845 = 10202
assert a.get_var("inicial_TK 1_v15_lab").get() == "12073", a.get_var("inicial_TK 1_v15_lab").get()
assert a.get_var("inicial_TK 1_kv_lab").get() == "10202"
assert a.get_var("final_TK 1_v15_lab").get() == "8851"
assert a.get_var("final_TK 1_kv_lab").get() == "7479"

# El volumen manual/geométrico no se pisa con 0 si no hay datos de interp
a.get_var("inicial_TK 1_tabla_trim_json").set("")
a.get_var("inicial_TK 1_vol_nat_prod").set("5555")
a.calc_volumen_prod_ui("inicial", "TK 1")
assert a.get_var("inicial_TK 1_vol_nat_prod").get() == "5555", "el recálculo pisó un volumen sin datos de interp"
a.get_var("inicial_TK 1_tabla_trim_json").set(__import__("json").dumps(
    {"trims": [0.0, 0.5], "rows": [[1000, 8000, 8200], [2000, 16000, 16400]]}))
a.calc_volumen_prod_ui("inicial", "TK 1")

# PDFs completos sin errores
a.generar_todos_reportes()
pdfs = [f for f in os.listdir(out) if f.endswith(".pdf")]
assert pdfs, "no se generó el PDF"
assert os.path.getsize(os.path.join(out, pdfs[0])) > 10000

root.destroy()
print("test_calculos_pdf OK")
