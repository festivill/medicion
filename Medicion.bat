@echo off
REM Launcher del Sistema de Medicion de Hidrocarburos ARCA.
REM Usa el Python embebido instalado por instalar.bat.
cd /d "%~dp0"
if not exist "%~dp0python\pythonw.exe" (
    echo.
    echo  No se encuentra Python instalado en esta carpeta.
    echo  Ejecute primero "instalar.bat".
    echo.
    pause
    exit /b 1
)
start "" "%~dp0python\pythonw.exe" "%~dp0main.py"
