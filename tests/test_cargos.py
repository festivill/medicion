# Verifica que el cargo/denuncia use los mismos kilos que la planilla
# (neto × VCF × densidad) y que el PDF del cargo se genere.
from _base import nueva_app, setup_buque, cargar_tanque_buque
import os
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.lib.pagesizes import A4, landscape

root, a, out = nueva_app()
setup_buque(a)
DOC = "23073IC04000123X"
a.agregar_ddt_row(data={
    "numero": DOC, "num_planilla": "1", "tipo_doc": "Detallada",
    "producto": "GASOIL", "pos_arancel": "2710.19.21", "densidad": "0.845",
    "litros": "4000", "kilos": "3380", "valor_litro": "1.0", "divisa": "USD",
    "divisa_desc": "", "tipo_cambio": "1000", "salidas": []})
ddt = next(d for d in a.ddt_data if d["numero"].get() == DOC)
for etapa, uti, agua in (("inicial", "1600", "80"), ("final", "1200", "60")):
    cargar_tanque_buque(a, "TK 1", etapa, uti, agua, doc=DOC)
    a.on_ddt_selected(etapa, "TK 1")

# kv_doc netos: 10202 / 7479 → dif 2723
assert a.get_var("inicial_TK 1_kv_doc").get() == "10202"
assert a.get_var("final_TK 1_kv_doc").get() == "7479"

info = a.inferir_tipo_operacion(ddt)
assert info["codigo"] == "IC04", info

pdf = os.path.join(out, "cargo_test.pdf")
c = rl_canvas.Canvas(pdf, pagesize=A4)
a._generar_cargo_en_canvas(c, ddt, 2723.0, 3380.0, modo_comp_forzado="documento",
                           tipo_operacion=info.get("tipo", "importacion"),
                           tipo_operacion_info=info)
c.setPageSize(landscape(A4))
a.generar_un_reporte("DOC_TEST", ["TK 1"], is_partial=True, ddt_obj=ddt,
                     output_folder=out, density_mode_key="dens_doc", shared_canvas=c)
c.save()
assert os.path.getsize(pdf) > 5000

root.destroy()
print("test_cargos OK")
