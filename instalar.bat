@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul
title Instalador - Sistema de Medicion de Hidrocarburos ARCA

cd /d "%~dp0"

echo.
echo ============================================================
echo   Sistema de Medicion de Hidrocarburos ARCA - Instalador
echo ============================================================
echo.

REM ----- Configuracion -----
REM Se usa el instalador COMPLETO de Python (no el "embeddable"): el paquete
REM embebido no incluye Tkinter (la interfaz grafica) y la aplicacion no abre.
REM La instalacion es silenciosa, por-usuario (sin administrador) y queda
REM contenida en la subcarpeta "python" de esta aplicacion.
set "PY_VER=3.11.9"
set "PY_EXE_INST=python-%PY_VER%-amd64.exe"
set "PY_URL=https://www.python.org/ftp/python/%PY_VER%/%PY_EXE_INST%"
set "PIP_URL=https://bootstrap.pypa.io/get-pip.py"
set "PY_DIR=%~dp0python"
set "PYEXE=%PY_DIR%\python.exe"
set "PYWEXE=%PY_DIR%\pythonw.exe"

REM ----- 1) Conectividad -----
echo [1/5] Verificando conexion a Internet...
powershell -NoProfile -Command "try { $r = Invoke-WebRequest -UseBasicParsing -Uri 'https://www.python.org' -TimeoutSec 8; if ($r.StatusCode -ge 200 -and $r.StatusCode -lt 400) { exit 0 } else { exit 1 } } catch { exit 1 }"
if errorlevel 1 (
    echo.
    echo  ERROR: No se detecta conexion a Internet.
    echo  Conectese a Internet y vuelva a ejecutar este instalador.
    echo.
    pause
    exit /b 1
)
echo       OK

REM ----- 2) Python (completo, con Tkinter) -----
set "NEED_PY=1"
if exist "%PYEXE%" (
    "%PYEXE%" -c "import tkinter" >nul 2>&1
    if not errorlevel 1 (
        set "NEED_PY=0"
        echo [2/5] Python con Tkinter ya presente, se omite descarga.
    ) else (
        echo [2/5] Se detecto un Python previo SIN Tkinter ^(instalacion vieja^).
        echo       Se reemplaza por el Python completo...
        rmdir /s /q "%PY_DIR%" >nul 2>&1
    )
)
if "!NEED_PY!"=="1" (
    echo [2/5] Descargando Python %PY_VER% completo ^(aprox. 25 MB^)...
    powershell -NoProfile -Command "Invoke-WebRequest -UseBasicParsing -Uri '%PY_URL%' -OutFile '%~dp0%PY_EXE_INST%'"
    if errorlevel 1 (
        echo  ERROR: Fallo la descarga de Python.
        pause
        exit /b 1
    )
    echo       Instalando ^(silencioso, por usuario, sin administrador^)...
    start /wait "" "%~dp0%PY_EXE_INST%" /quiet InstallAllUsers=0 TargetDir="%PY_DIR%" ^
        Include_tcltk=1 Include_pip=1 Include_test=0 Include_doc=0 Include_dev=0 ^
        Include_launcher=0 Shortcuts=0 AssociateFiles=0 PrependPath=0
    if not exist "%PYEXE%" (
        echo  ERROR: No se pudo instalar Python.
        pause
        exit /b 1
    )
    del "%~dp0%PY_EXE_INST%" >nul 2>&1
    echo       OK
)

REM ----- 3) Verificar Tkinter y pip -----
echo [3/5] Verificando entorno Python...
"%PYEXE%" -c "import tkinter" >nul 2>&1
if errorlevel 1 (
    echo  ERROR: Python quedo sin Tkinter. Reintente el instalador.
    pause
    exit /b 1
)
"%PYEXE%" -m pip --version >nul 2>&1
if errorlevel 1 (
    echo       Instalando pip...
    powershell -NoProfile -Command "Invoke-WebRequest -UseBasicParsing -Uri '%PIP_URL%' -OutFile '%PY_DIR%\get-pip.py'"
    "%PYEXE%" "%PY_DIR%\get-pip.py" --no-warn-script-location
    if errorlevel 1 (
        echo  ERROR: Fallo la instalacion de pip.
        pause
        exit /b 1
    )
    del "%PY_DIR%\get-pip.py" >nul 2>&1
)
echo       OK

REM ----- 4) Instalar dependencias -----
echo [4/5] Instalando librerias necesarias...
"%PYEXE%" -m pip install --upgrade --no-warn-script-location -r "%~dp0requirements.txt"
if errorlevel 1 (
    echo  ERROR: Fallo la instalacion de librerias.
    pause
    exit /b 1
)
echo       OK

REM ----- 5) Acceso directo en el escritorio -----
echo [5/5] Creando acceso directo en el escritorio...
set "ICON=%~dp0arca-icon.ico"
set "TARGET=%PYWEXE%"
set "ARGS=%~dp0main.py"
set "WORKDIR=%~dp0"

powershell -NoProfile -Command "$ws = New-Object -ComObject WScript.Shell; $desktop = [Environment]::GetFolderPath('Desktop'); $sc = $ws.CreateShortcut((Join-Path $desktop 'Sistema de Medicion.lnk')); $sc.TargetPath = '%TARGET%'; $sc.Arguments = '\"%ARGS%\"'; $sc.WorkingDirectory = '%WORKDIR%'; $sc.IconLocation = '%ICON%'; $sc.WindowStyle = 1; $sc.Description = 'Sistema de Medicion de Hidrocarburos ARCA'; $sc.Save()"
if errorlevel 1 (
    echo       AVISO: no se pudo crear el acceso directo, pero la instalacion esta lista.
) else (
    echo       OK
)

REM ----- Verificacion final -----
"%PYEXE%" -c "import tkinter, reportlab" >nul 2>&1
if errorlevel 1 (
    echo  AVISO: la verificacion final fallo. Revise los mensajes anteriores.
) else (
    echo       Verificacion final: Tkinter y reportlab OK.
)

echo.
echo ============================================================
echo   Instalacion completa.
echo.
echo   - Se creo un acceso directo "Sistema de Medicion" en su
echo     escritorio. Hacer doble clic para abrir el programa.
echo.
echo   - Tambien puede iniciarlo desde esta carpeta haciendo
echo     doble clic en "Medicion.bat".
echo ============================================================
echo.
pause
endlocal
