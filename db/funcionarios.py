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
        UNIQUE(cuil, legajo, funcion)
    )""")
    # Migración: agregar columna si no existe (bases de datos antiguas)
    try:
        con.execute("ALTER TABLE funcionarios ADD COLUMN lugar_operativo TEXT DEFAULT ''")
    except Exception:
        pass  # ya existe
    # Migración: el esquema viejo (UNIQUE(cuil, legajo)) pisaba la función
    # anterior del agente; ahora se guarda una fila por (cuil, legajo, funcion)
    # para que un mismo agente pueda tener todas sus funciones registradas.
    try:
        sql = con.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='funcionarios'"
        ).fetchone()[0]
        if "funcion" not in sql.split("UNIQUE", 1)[1]:
            con.execute("ALTER TABLE funcionarios RENAME TO funcionarios_old")
            con.execute("""CREATE TABLE funcionarios (
                id      INTEGER PRIMARY KEY AUTOINCREMENT,
                cuil    TEXT,
                legajo  TEXT,
                apellido TEXT,
                nombre  TEXT,
                funcion TEXT,
                aduana  TEXT,
                lugar_operativo TEXT DEFAULT '',
                UNIQUE(cuil, legajo, funcion)
            )""")
            con.execute(
                "INSERT OR IGNORE INTO funcionarios(cuil,legajo,apellido,nombre,funcion,aduana,lugar_operativo) "
                "SELECT cuil,legajo,apellido,nombre,funcion,aduana,COALESCE(lugar_operativo,'') FROM funcionarios_old")
            con.execute("DROP TABLE funcionarios_old")
    except Exception:
        pass
    con.commit()
    return con

def db_buscar_funcionarios(query, campo="apellido", limit=50):
    """Devuelve lista de dicts que coinciden (una fila por función del agente)."""
    try:
        con = _init_db()
        rows = con.execute(
            f"SELECT cuil,legajo,apellido,nombre,funcion,aduana,lugar_operativo FROM funcionarios "
            f"WHERE {campo} LIKE ? ORDER BY apellido LIMIT ?",
            (f"%{query}%", int(limit))
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

def db_eliminar_funcionario(cuil, legajo, funcion=None):
    """Elimina un registro. Con funcion: solo esa función del agente;
    sin funcion: todas las funciones de ese cuil+legajo."""
    try:
        con = _init_db()
        if funcion is None:
            con.execute("DELETE FROM funcionarios WHERE cuil=? AND legajo=?", (cuil, legajo))
        else:
            con.execute("DELETE FROM funcionarios WHERE cuil=? AND legajo=? AND funcion=?", (cuil, legajo, funcion))
        con.commit(); con.close()
    except: pass

_init_db()   # create on import
