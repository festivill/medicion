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
set "PY_VER=3.11.9"
set "PY_TAG=python311"
set "PY_ZIP=python-%PY_VER%-embed-amd64.zip"
set "PY_URL=https://www.python.org/ftp/python/%PY_VER%/%PY_ZIP%"
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

REM ----- 2) Descarga Python embebido -----
if exist "%PYEXE%" (
    echo [2/5] Python embebido ya presente, se omite descarga.
) else (
    echo [2/5] Descargando Python %PY_VER% (aprox. 11 MB)...
    powershell -NoProfile -Command "Invoke-WebRequest -UseBasicParsing -Uri '%PY_URL%' -OutFile '%~dp0%PY_ZIP%'"
    if errorlevel 1 (
        echo  ERROR: Fallo la descarga de Python.
        pause
        exit /b 1
    )
    echo       Descomprimiendo...
    if not exist "%PY_DIR%" mkdir "%PY_DIR%"
    powershell -NoProfile -Command "Expand-Archive -Force -Path '%~dp0%PY_ZIP%' -DestinationPath '%PY_DIR%'"
    if errorlevel 1 (
        echo  ERROR: No se pudo descomprimir Python.
        pause
        exit /b 1
    )
    del "%~dp0%PY_ZIP%" >nul 2>&1
    echo       OK
)

REM ----- 3) Configurar _pth para habilitar site-packages -----
echo [3/5] Configurando entorno Python...
set "PTH_FILE=%PY_DIR%\%PY_TAG%._pth"
> "%PTH_FILE%" echo %PY_TAG%.zip
>> "%PTH_FILE%" echo .
>> "%PTH_FILE%" echo Lib\site-packages
>> "%PTH_FILE%" echo.
>> "%PTH_FILE%" echo import site

if not exist "%PY_DIR%\Scripts\pip.exe" (
    echo       Instalando pip...
    powershell -NoProfile -Command "Invoke-WebRequest -UseBasicParsing -Uri '%PIP_URL%' -OutFile '%PY_DIR%\get-pip.py'"
    if errorlevel 1 (
        echo  ERROR: Fallo la descarga de pip.
        pause
        exit /b 1
    )
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
