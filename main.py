import sys
import os

# Ensure the package directory is in the path
_pkg_dir = os.path.dirname(os.path.abspath(__file__))
if _pkg_dir not in sys.path:
    sys.path.insert(0, _pkg_dir)

import tkinter as tk
from app import PlanillaFinalApp

if __name__ == "__main__":
    # className fija el WM_CLASS de la ventana para que el gestor de ventanas /
    # dock la asocie al lanzador .desktop (StartupWMClass=Medicion) y muestre el
    # ícono de ARCA en vez del genérico.
    root = tk.Tk(className="Medicion")
    app = PlanillaFinalApp(root)
    try:
        from updater import check_for_updates_async
        check_for_updates_async(root)
    except Exception:
        pass
    root.mainloop()
