# ─── BASE DE DATOS SQLITE: FUNCIONES ─────────────────────────────────────────
import sqlite3
from .aduanas import _get_aduana_db_path

def _init_funciones_db():
    db = _get_aduana_db_path()
    con = sqlite3.connect(db)
    con.execute("""CREATE TABLE IF NOT EXISTS funciones (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nombre TEXT UNIQUE NOT NULL
    )""")
    SEED_FUNCIONES = [
        "CUSTODIA", "GUARDA", "GUARDA VERIFICADOR", "MEDIDOR",
        "VERIFICADOR", "JEFE DE TURNO / SECTOR", "SUPERVISOR"
    ]
    for nombre in SEED_FUNCIONES:
        try:
            con.execute("INSERT OR IGNORE INTO funciones(nombre) VALUES(?)", (nombre,))
        except: pass
    con.commit()
    return con

def db_get_funciones():
    """Devuelve lista de strings con los nombres de funciones."""
    try:
        con = _init_funciones_db()
        rows = con.execute("SELECT nombre FROM funciones ORDER BY nombre").fetchall()
        con.close()
        return [r[0] for r in rows]
    except: return []

def db_guardar_funcion(nombre):
    try:
        con = _init_funciones_db()
        con.execute("INSERT OR IGNORE INTO funciones(nombre) VALUES(?)", (nombre.strip().upper(),))
        con.commit(); con.close(); return True
    except: return False

def db_eliminar_funcion(nombre):
    try:
        con = _init_funciones_db()
        con.execute("DELETE FROM funciones WHERE nombre=?", (nombre,))
        con.commit(); con.close()
    except: pass

_init_funciones_db()  # create on import
