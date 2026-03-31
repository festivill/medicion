# ─── BASE DE DATOS SQLITE DE FUNCIONARIOS ────────────────────────────────────
import sqlite3, pathlib

def _get_db_path():
    """DB junto al .py (o .exe en caso de PyInstaller)."""
    import sys
    if getattr(sys, 'frozen', False):
        base = pathlib.Path(sys.executable).parent
    else:
        base = pathlib.Path(__file__).resolve().parent.parent
    return base / "funcionarios.db"

def _init_db():
    db = _get_db_path()
    con = sqlite3.connect(db)
    con.execute("""CREATE TABLE IF NOT EXISTS funcionarios (
        id      INTEGER PRIMARY KEY AUTOINCREMENT,
        cuil    TEXT,
        legajo  TEXT,
        apellido TEXT,
        nombre  TEXT,
        funcion TEXT,
        aduana  TEXT,
        lugar_operativo TEXT DEFAULT '',
        UNIQUE(cuil, legajo)
    )""")
    # Migración: agregar columna si no existe (bases de datos antiguas)
    try:
        con.execute("ALTER TABLE funcionarios ADD COLUMN lugar_operativo TEXT DEFAULT ''")
    except Exception:
        pass  # ya existe
    con.commit()
    return con

def db_buscar_funcionarios(query, campo="apellido"):
    """Devuelve lista de dicts que coinciden."""
    try:
        con = _init_db()
        rows = con.execute(
            f"SELECT cuil,legajo,apellido,nombre,funcion,aduana,lugar_operativo FROM funcionarios "
            f"WHERE {campo} LIKE ? ORDER BY apellido LIMIT 20",
            (f"%{query}%",)
        ).fetchall()
        con.close()
        return [{"cuil":r[0],"legajo":r[1],"apellido":r[2],"nombre":r[3],"funcion":r[4],"aduana":r[5],"lugar_operativo":r[6] or ""} for r in rows]
    except Exception as e:
        return []

def db_guardar_funcionario(cuil, legajo, apellido, nombre, funcion, aduana, lugar_operativo=""):
    """INSERT OR REPLACE por cuil+legajo."""
    try:
        con = _init_db()
        con.execute(
            "INSERT OR REPLACE INTO funcionarios(cuil,legajo,apellido,nombre,funcion,aduana,lugar_operativo) VALUES(?,?,?,?,?,?,?)",
            (cuil, legajo, apellido, nombre, funcion, aduana, lugar_operativo or "")
        )
        con.commit(); con.close()
        return True
    except Exception as e:
        return False

def db_todos_funcionarios():
    try:
        con = _init_db()
        rows = con.execute("SELECT cuil,legajo,apellido,nombre,funcion,aduana,lugar_operativo FROM funcionarios ORDER BY apellido").fetchall()
        con.close()
        return [{"cuil":r[0],"legajo":r[1],"apellido":r[2],"nombre":r[3],"funcion":r[4],"aduana":r[5],"lugar_operativo":r[6] or ""} for r in rows]
    except: return []

def db_eliminar_funcionario(cuil, legajo):
    try:
        con = _init_db()
        con.execute("DELETE FROM funcionarios WHERE cuil=? AND legajo=?", (cuil, legajo))
        con.commit(); con.close()
    except: pass

_init_db()   # create on import
