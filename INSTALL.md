# Instalación — Sistema de Medición de Hidrocarburos ARCA

La aplicación es Python puro (no se compila): **el mismo código corre en
Windows y Linux**, y el auto-updater distribuye las actualizaciones a ambas
plataformas por igual desde este repositorio.

## Descarga (ambas plataformas)

1. `Code → Download ZIP` en GitHub (o `git clone`).
2. Descomprimir en una carpeta con permisos de escritura (la app guarda ahí
   sus datos y se auto-actualiza en el lugar).

---

## Windows — `instalar.bat` (doble clic)

### Checklist de lo que baja y configura

| # | Paso | Detalle |
|---|------|---------|
| 1 | Conexión a Internet | necesaria solo para instalar |
| 2 | **Python 3.11.9 completo** (~25 MB, python.org) | instalación **silenciosa, por-usuario, sin administrador**, contenida en la subcarpeta `python/` de la app. ⚠️ Se usa el instalador completo porque el Python *embeddable* **no incluye Tkinter** (la interfaz) y la app no abre |
| 3 | **Tkinter** | verificado con `import tkinter`; si había un `python/` viejo sin Tkinter (instalador anterior), se reemplaza solo |
| 4 | **pip** | incluido con Python; fallback a `get-pip.py` si faltara |
| 5 | **Dependencias** (`requirements.txt`) | `reportlab` (PDFs) |
| 6 | **Acceso directo** "Sistema de Medición" en el Escritorio | apunta a `pythonw.exe main.py` con el ícono ARCA (`arca-icon.ico`) |
| 7 | Verificación final | `import tkinter, reportlab` |

- Para abrir: acceso directo del Escritorio o `Medicion.bat`.
- Nota: la instalación por-usuario de Python queda registrada en
  *Configuración → Aplicaciones* como "Python 3.11.9"; se puede desinstalar
  desde ahí si algún día se elimina la app.

## Linux — `instalar.sh` (`bash instalar.sh`)

### Checklist de lo que verifica/instala y configura

| # | Paso | Detalle |
|---|------|---------|
| 1 | **python3** | del sistema; si falta lo instala (apt/dnf/pacman/zypper, pide `sudo` solo en ese caso) |
| 2 | **Tkinter** | `python3-tk` (Debian/Ubuntu), `python3-tkinter` (Fedora), `tk` (Arch) |
| 3 | **venv** | `python3-venv` en Debian/Ubuntu |
| 4 | **Entorno virtual** `.venv/` | dentro de la carpeta de la app |
| 5 | **Dependencias** (`requirements.txt`) | `reportlab` (PDFs) |
| 6 | `run.sh` ejecutable | lanzador: `.venv/bin/python main.py` |
| 7 | **Lanzadores `.desktop`** | menú de aplicaciones (`~/.local/share/applications/`) y Escritorio, con ícono ARCA (`arca-icon.png`) y `StartupWMClass=Medicion` (para que el dock muestre el ícono correcto) |
| 8 | Verificación final | `import tkinter, reportlab` |

- Para abrir: "Sistema de Medición ARCA" en el menú de aplicaciones, o `./run.sh`.

---

## Requisitos que la app espera en tiempo de ejecución

| Componente | Windows | Linux | Para qué |
|---|---|---|---|
| Python | 3.11 (embebido en `python/`) | 3.x del sistema (venv en `.venv/`) | intérprete |
| Tkinter (Tcl/Tk 8.6) | incluido en el Python completo | paquete del sistema | toda la interfaz |
| reportlab ≥ 4 | pip | pip | generación de PDFs |
| Pillow | opcional | opcional | solo fallback del ícono |
| Internet | opcional | opcional | auto-update silencioso al abrir |

## Datos locales (sobreviven a las actualizaciones)

`autosave.json` (sesión en curso), `*.db` (funcionarios, aduanas), `*.meg`
(mediciones guardadas), `caratulas/` — el auto-updater los preserva siempre.
