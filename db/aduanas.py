# ─── BASE DE DATOS SQLITE: ADUANAS Y LUGARES OPERATIVOS ──────────────────────
import sqlite3, pathlib

def _get_aduana_db_path():
    import sys
    if getattr(sys, 'frozen', False):
        base = pathlib.Path(sys.executable).parent
    else:
        base = pathlib.Path(__file__).resolve().parent.parent
    return base / "aduanas.db"

def _init_aduana_db():
    db = _get_aduana_db_path()
    con = sqlite3.connect(db)
    con.execute("""CREATE TABLE IF NOT EXISTS aduanas (
        codigo TEXT PRIMARY KEY,
        nombre TEXT NOT NULL
    )""")
    con.execute("""CREATE TABLE IF NOT EXISTS lugares_operativos (
        id     INTEGER PRIMARY KEY AUTOINCREMENT,
        codigo TEXT NOT NULL,
        descripcion TEXT NOT NULL,
        aduana_codigo TEXT NOT NULL,
        UNIQUE(codigo, aduana_codigo)
    )""")
    # Seed initial aduanas from master list
    SEED = [
        ("001","BS.AS. (CAPITAL)"),("003","BAHIA BLANCA"),("004","BARILOCHE"),
        ("008","CAMPANA"),("010","BARRANQUERAS"),("012","CLORINDA"),
        ("013","COLON"),("014","COMODORO RIVADAVIA"),("015","CONCEPCION DEL URUGUAY"),
        ("016","CONCORDIA"),("017","CORDOBA"),("018","CORRIENTES"),
        ("019","PUERTO DESEADO"),("020","DIAMANTE"),("023","ESQUEL"),
        ("024","FORMOSA"),("025","GOYA"),("026","GUALEGUAYCHU"),
        ("029","IGUAZU"),("031","JUJUY"),("033","LA PLATA"),
        ("034","LA QUIACA"),("037","MAR DEL PLATA"),("038","MENDOZA"),
        ("040","NECOCHEA"),("041","PARANA"),("042","PASO DE LOS LIBRES"),
        ("045","POCITOS"),("046","POSADAS"),("047","PUERTO MADRYN"),
        ("048","RIO GALLEGOS"),("049","RIO GRANDE"),("052","ROSARIO"),
        ("053","SALTA"),("054","SAN JAVIER"),("055","SAN JUAN"),
        ("057","SAN LORENZO"),("058","S. MARTIN DE LOS ANDES"),("059","SAN NICOLAS"),
        ("060","SAN PEDRO"),("061","SANTA CRUZ"),("062","SANTA FE"),
        ("066","TINOGASTA"),("067","USHUAIA"),("069","VILLA CONSTITUCION"),
        ("073","EZEIZA"),("074","TUCUMAN"),("075","NEUQUEN"),
        ("076","ORAN"),("078","SAN RAFAEL"),("079","LA RIOJA"),
        ("080","SAN ANTONIO OESTE"),("082","BERNARDO DE YRIGOYEN"),("083","SAN LUIS"),
        ("084","SANTO TOME"),("085","VILLA REGINA"),("086","OBERA"),
        ("087","CALETA OLIVIA"),("088","GENERAL DEHEZA"),("089","SANTIAGO DEL ESTERO"),
        ("090","GENERAL PICO"),("091","BS.AS. NORTE"),("092","BS.AS. SUR"),
        ("093","RAFAELA"),("099","MULTIADUANA"),
        ("258","Z.F GENERAL PICO"),("266","Z.F CORONEL ROSALES"),
        ("267","Z.F CONCEP.DEL.URUG."),("268","Z.F. V. CONSTITUCION"),
        ("269","Z.F. PUERTO GALVAN"),
    ]
    for cod, nom in SEED:
        try:
            con.execute("INSERT OR IGNORE INTO aduanas(codigo,nombre) VALUES(?,?)", (cod, nom))
        except: pass
    con.commit()
    return con

def db_get_aduanas():
    try:
        con = _init_aduana_db()
        rows = con.execute("SELECT codigo, nombre FROM aduanas ORDER BY codigo").fetchall()
        con.close()
        return [{"codigo": r[0], "nombre": r[1]} for r in rows]
    except: return []

def db_guardar_aduana(codigo, nombre):
    try:
        con = _init_aduana_db()
        con.execute("INSERT OR REPLACE INTO aduanas(codigo,nombre) VALUES(?,?)", (codigo.strip().zfill(3), nombre.strip()))
        con.commit(); con.close(); return True
    except: return False

def db_eliminar_aduana(codigo):
    try:
        con = _init_aduana_db()
        con.execute("DELETE FROM aduanas WHERE codigo=?", (codigo,))
        con.execute("DELETE FROM lugares_operativos WHERE aduana_codigo=?", (codigo,))
        con.commit(); con.close()
    except: pass

def db_get_lugares_operativos(aduana_codigo=None):
    try:
        con = _init_aduana_db()
        if aduana_codigo:
            rows = con.execute(
                "SELECT codigo,descripcion,aduana_codigo FROM lugares_operativos WHERE aduana_codigo=? ORDER BY codigo",
                (aduana_codigo,)).fetchall()
        else:
            rows = con.execute(
                "SELECT codigo,descripcion,aduana_codigo FROM lugares_operativos ORDER BY aduana_codigo, codigo").fetchall()
        con.close()
        return [{"codigo": r[0], "descripcion": r[1], "aduana_codigo": r[2]} for r in rows]
    except: return []

def db_guardar_lugar_operativo(codigo, descripcion, aduana_codigo):
    try:
        con = _init_aduana_db()
        con.execute("INSERT OR REPLACE INTO lugares_operativos(codigo,descripcion,aduana_codigo) VALUES(?,?,?)",
                    (codigo.strip(), descripcion.strip(), aduana_codigo.strip()))
        con.commit(); con.close(); return True
    except: return False

def db_eliminar_lugar_operativo(codigo, aduana_codigo):
    try:
        con = _init_aduana_db()
        con.execute("DELETE FROM lugares_operativos WHERE codigo=? AND aduana_codigo=?", (codigo, aduana_codigo))
        con.commit(); con.close()
    except: pass

_init_aduana_db()  # create on import
