#!/bin/bash
# Instalador Linux del Sistema de Medición de Hidrocarburos ARCA.
#
# Uso:  bash instalar.sh
#
# Qué hace:
#   1. Verifica python3, Tkinter y venv (si faltan, los instala con el gestor
#      de paquetes de la distro — pide sudo solo en ese caso).
#   2. Crea el entorno virtual .venv y instala las dependencias (reportlab).
#   3. Deja run.sh ejecutable.
#   4. Crea el lanzador de escritorio (menú de aplicaciones + Escritorio) con
#      el ícono de ARCA y StartupWMClass para que el dock lo asocie bien.
set -e
cd "$(dirname "$0")"
APP_DIR="$(pwd)"

say()  { printf '\n\033[1;34m%s\033[0m\n' "$*"; }
ok()   { printf '\033[1;32m      OK\033[0m %s\n' "$*"; }
fail() { printf '\033[1;31mERROR:\033[0m %s\n' "$*" >&2; exit 1; }

echo "============================================================"
echo "  Sistema de Medición de Hidrocarburos ARCA — Instalador"
echo "============================================================"

# ----- 1) Python 3 + Tkinter + venv --------------------------------------
say "[1/4] Verificando Python 3, Tkinter y venv..."

PKGS=()
command -v python3 >/dev/null 2>&1 || PKGS+=("PYTHON")
if command -v python3 >/dev/null 2>&1; then
    python3 -c "import tkinter" >/dev/null 2>&1 || PKGS+=("TK")
    python3 -m venv --help    >/dev/null 2>&1 || PKGS+=("VENV")
fi

if [ ${#PKGS[@]} -gt 0 ]; then
    # Mapear a nombres de paquete según la distro
    if   command -v apt-get >/dev/null 2>&1; then
        MAP_PYTHON="python3"; MAP_TK="python3-tk"; MAP_VENV="python3-venv"
        INSTALL="sudo apt-get update -qq && sudo apt-get install -y"
    elif command -v dnf >/dev/null 2>&1; then
        MAP_PYTHON="python3"; MAP_TK="python3-tkinter"; MAP_VENV="python3-libs"
        INSTALL="sudo dnf install -y"
    elif command -v pacman >/dev/null 2>&1; then
        MAP_PYTHON="python"; MAP_TK="tk"; MAP_VENV=""
        INSTALL="sudo pacman -S --noconfirm"
    elif command -v zypper >/dev/null 2>&1; then
        MAP_PYTHON="python3"; MAP_TK="python3-tk"; MAP_VENV=""
        INSTALL="sudo zypper install -y"
    else
        fail "No se reconoce el gestor de paquetes. Instale a mano: python3, tkinter (python3-tk) y venv, y vuelva a correr este instalador."
    fi
    TO_INSTALL=""
    for p in "${PKGS[@]}"; do
        v="MAP_$p"; [ -n "${!v}" ] && TO_INSTALL="$TO_INSTALL ${!v}"
    done
    echo "      Faltan componentes:$TO_INSTALL"
    echo "      Se instalarán con:  $INSTALL$TO_INSTALL"
    eval "$INSTALL$TO_INSTALL" || fail "No se pudieron instalar los paquetes del sistema."
fi

python3 -c "import tkinter" >/dev/null 2>&1 || fail "Tkinter sigue faltando (instale python3-tk y reintente)."
python3 -m venv --help >/dev/null 2>&1 || fail "El módulo venv sigue faltando (instale python3-venv y reintente)."
ok "python3 $(python3 -c 'import sys;print(".".join(map(str,sys.version_info[:3])))') con Tkinter $(python3 -c 'import tkinter;print(tkinter.TkVersion)')"

# ----- 2) Entorno virtual + dependencias ---------------------------------
say "[2/4] Creando entorno virtual e instalando dependencias..."
if [ ! -x .venv/bin/python ]; then
    python3 -m venv .venv || fail "No se pudo crear el entorno virtual."
fi
.venv/bin/python -m pip install --quiet --upgrade pip
.venv/bin/python -m pip install --quiet --upgrade -r requirements.txt \
    || fail "No se pudieron instalar las dependencias (requirements.txt)."
ok "reportlab $(.venv/bin/python -c 'import reportlab;print(reportlab.Version)')"

# ----- 3) Launcher ejecutable ---------------------------------------------
say "[3/4] Configurando el lanzador..."
chmod +x run.sh
ok "run.sh ejecutable"

# ----- 4) Accesos directos (.desktop) -------------------------------------
say "[4/4] Creando accesos directos..."
DESKTOP_FILE_CONTENT="[Desktop Entry]
Type=Application
Name=Sistema de Medición ARCA
Comment=Medición de Hidrocarburos ARCA
Exec=$APP_DIR/run.sh
Icon=$APP_DIR/arca-icon.png
Terminal=false
Categories=Office;Utility;
StartupWMClass=Medicion"

APPS_DIR="$HOME/.local/share/applications"
mkdir -p "$APPS_DIR"
printf '%s\n' "$DESKTOP_FILE_CONTENT" > "$APPS_DIR/medicion-arca.desktop"
chmod +x "$APPS_DIR/medicion-arca.desktop"
ok "menú de aplicaciones: $APPS_DIR/medicion-arca.desktop"

if [ -d "$HOME/Desktop" ] || [ -d "$HOME/Escritorio" ]; then
    DESK="$HOME/Desktop"; [ -d "$HOME/Escritorio" ] && DESK="$HOME/Escritorio"
    printf '%s\n' "$DESKTOP_FILE_CONTENT" > "$DESK/medicion-arca.desktop"
    chmod +x "$DESK/medicion-arca.desktop"
    # GNOME requiere marcarlo como confiable para que se vea como ícono
    command -v gio >/dev/null 2>&1 && gio set "$DESK/medicion-arca.desktop" metadata::trusted true 2>/dev/null || true
    ok "escritorio: $DESK/medicion-arca.desktop"
fi
command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database "$APPS_DIR" 2>/dev/null || true

# ----- Verificación final --------------------------------------------------
.venv/bin/python -c "import tkinter, reportlab" \
    || fail "La verificación final falló (tkinter/reportlab)."

echo
echo "============================================================"
echo "  Instalación completa."
echo
echo "  - Abra «Sistema de Medición ARCA» desde el menú de"
echo "    aplicaciones o el ícono del escritorio."
echo "  - También puede iniciarlo con:  $APP_DIR/run.sh"
echo "============================================================"
