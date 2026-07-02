# ─── REGISTRO DE ERRORES A ARCHIVO ───────────────────────────────────────────
# El código tiene muchos `except` silenciosos; este módulo da un lugar donde
# los errores no capturados (Python y callbacks de Tk) quedan registrados para
# poder diagnosticar problemas sin correr desde consola.
import logging
import pathlib
import sys
import traceback


def app_dir():
    """Directorio de la aplicación (o del .exe si está congelado con PyInstaller)."""
    if getattr(sys, 'frozen', False):
        return pathlib.Path(sys.executable).parent
    return pathlib.Path(__file__).resolve().parent


LOG_PATH = app_dir() / "medicion.log"
logger = logging.getLogger("medicion")
if not logger.handlers:
    logger.setLevel(logging.INFO)
    try:
        _h = logging.FileHandler(LOG_PATH, encoding="utf-8")
        _h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logger.addHandler(_h)
    except Exception:
        pass  # sin permisos de escritura: seguir sin log


def log_exception(msg=""):
    """Registrar la excepción activa con contexto."""
    try:
        logger.error("%s\n%s", msg, traceback.format_exc())
    except Exception:
        pass


def instalar_hooks(root=None):
    """Loguea excepciones no capturadas (consola y callbacks de tkinter)."""
    def _hook(exc_type, exc, tb):
        try:
            logger.error("Excepción no capturada:\n%s",
                         "".join(traceback.format_exception(exc_type, exc, tb)))
        except Exception:
            pass
        sys.__excepthook__(exc_type, exc, tb)
    sys.excepthook = _hook
    if root is not None:
        def _tk_err(exc_type, exc, tb):
            try:
                logger.error("Error en callback Tk:\n%s",
                             "".join(traceback.format_exception(exc_type, exc, tb)))
            except Exception:
                pass
            traceback.print_exception(exc_type, exc, tb)
        root.report_callback_exception = _tk_err
