# Sistema de Medición de Hidrocarburos ARCA

Aplicación de escritorio para la confección de planillas oficiales de medición
de hidrocarburos líquidos y gaseosos según las normas vigentes:

- **ASTM D1250-1980** (tablas impresas — 4 zonas de densidad en Tabla 54B)
- **API MPMS 11.1-2004** (cálculo digital — K0=346.4228, K1=0.4033 en 54B)
- **VCF para gases**: GLP (K0/rho²), GNL (α=0.00468) y NH₃ (α=0.00226)

## Instalación en Windows

1. Bajar este repositorio: **Code → Download ZIP** (o `git clone`).
2. Descomprimir en una carpeta.
3. Doble clic en **`instalar.bat`**.

El instalador es portable, no requiere permisos de administrador. Descarga
Python 3.11.9 embebido (~11 MB) dentro de la propia carpeta, instala las
dependencias necesarias y crea un acceso directo en el escritorio.

Para abrir el programa: doble clic en el acceso directo **"Sistema de Medición"**
del escritorio, o en `Medicion.bat` dentro de la carpeta.

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
- `instalar.bat`, `Medicion.bat`, `requirements.txt`, `arca-icon.ico` —
  instalador y launcher para Windows.
- `VERSION` — versión actual publicada.
