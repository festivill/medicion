# Sistema de Medición de Hidrocarburos ARCA

Aplicación de escritorio para la confección de planillas oficiales de medición
de hidrocarburos líquidos y gaseosos según las normas vigentes:

- **ASTM D1250-1980** (tablas impresas — 4 zonas de densidad en Tabla 54B)
- **API MPMS 11.1-2004** (cálculo digital — K0=346.4228, K1=0.4033 en 54B)
- **VCF para gases**: GLP (K0/rho²), GNL (α=0.00468) y NH₃ (α=0.00226)

## Instalación

1. Bajar este repositorio: **Code → Download ZIP** (o `git clone`).
2. Descomprimir en una carpeta.
3. Ejecutar el instalador de su sistema:
   - **Windows**: doble clic en **`instalar.bat`**.
   - **Linux**: `bash instalar.sh`.

Ambos instaladores dejan todo listo sin permisos de administrador (en Linux
solo piden `sudo` si falta Tkinter/venv del sistema): Python con Tkinter,
las dependencias (`reportlab`) y un acceso directo con el ícono ARCA en el
escritorio / menú de aplicaciones.

Para abrir el programa: el acceso directo **"Sistema de Medición"**, o
`Medicion.bat` (Windows) / `./run.sh` (Linux) dentro de la carpeta.

El detalle de qué descarga y configura cada instalador está en
[`INSTALL.md`](INSTALL.md).

## Actualización automática

Al abrirse, el programa consulta en segundo plano si hay una versión nueva
publicada en este repositorio. Si la hay, descarga el paquete y le pregunta
al usuario si desea instalarla. Si no hay conexión a Internet, no hace nada
(silencioso). Los datos locales (`.db`, `.meg`, `autosave.json`) se preservan
en todas las actualizaciones.

## Estructura

- `main.py` — punto de entrada.
- `app.py` — aplicación principal (UI Tkinter, lógica de cálculo).
- `updater.py` — módulo de auto-actualización.
- `db/` — acceso a SQLite (funcionarios, aduanas, lugares operativos).
- `calculations/`, `models/`, `ui/`, `utils/`, `visualization/`, `reports/` —
  módulos auxiliares.
- `assets/` — íconos embebidos.
- `instalar.bat`, `Medicion.bat`, `arca-icon.ico` — instalador y launcher
  para Windows.
- `instalar.sh`, `run.sh`, `arca-icon.png` — instalador y launcher para Linux.
- `requirements.txt`, `INSTALL.md` — dependencias y checklist de instalación.
- `VERSION` — versión actual publicada.
