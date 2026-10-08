@echo off
rem Partitura Libre - lanzador portable para Windows 11 (x64).
rem No instala nada en el sistema: todo se descarga dentro de esta carpeta.
rem   iniciar-windows.bat                abre la aplicacion (la primera vez prepara el runtime)
rem   iniciar-windows.bat --reparar      reinstala los paquetes del runtime portable
rem   iniciar-windows.bat --diagnostico  imprime el diagnostico sin abrir la ventana
setlocal EnableExtensions
chcp 65001 >nul
set "DIR=%~dp0"
set "RT=%DIR%runtime"
set "UV_VERSION=0.12.23"
set "UV_SHA256=75d05de6762778c31ee183398de7dd15093fad0ed90b1f236d8205ea5ec00c90"
set "UV_CACHE_DIR=%RT%\uv-cache"
set "UV_PYTHON_INSTALL_DIR=%RT%\python"
set "UV_PYTHON_PREFERENCE=only-managed"
set "UV_NO_CONFIG=1"
set "UV_LINK_MODE=copy"
set "PYTHONHOME="
set "PYTHONSTARTUP="
set "VIRTUAL_ENV="
set "PYTHONUSERBASE="
set "PYTHONNOUSERSITE=1"
set "PYTHONUTF8=1"
set "PYTHONPATH=%DIR%app"

set "ARQ=%PROCESSOR_ARCHITECTURE%"
if defined PROCESSOR_ARCHITEW6432 set "ARQ=%PROCESSOR_ARCHITEW6432%"
if /i not "%ARQ%"=="AMD64" (
    echo ERROR: este paquete es para Windows de 64 bits ^(x64^).
    goto :fallo
)
if not exist "%RT%" mkdir "%RT%"
if not exist "%RT%" (
    echo ERROR: no se puede escribir en "%DIR%". Copia el programa a una carpeta tuya, por ejemplo Documentos.
    goto :fallo
)

call :buscar_python
if exist "%RT%\uv.exe" if defined PY goto :lanzar

echo Primera preparacion: se descargara dentro de esta carpeta (nada en el sistema):
echo   - gestor uv %UV_VERSION% ........ unos 50 MB en disco
echo   - Python 3.11 portable ....... unos 90 MB en disco
if /i not "%~1"=="--si" (
    set /p "R=Continuar? [S/n] "
)
if /i "%R%"=="n" exit /b 1

if not exist "%RT%\uv.exe" (
    curl.exe -fL --retry 3 -o "%RT%\uv.zip" "https://github.com/astral-sh/uv/releases/download/%UV_VERSION%/uv-x86_64-pc-windows-msvc.zip"
    if errorlevel 1 (
        echo ERROR: no se pudo descargar uv. Revisa la conexion a Internet y vuelve a ejecutar este lanzador.
        goto :fallo
    )
    certutil -hashfile "%RT%\uv.zip" SHA256 | findstr /i /x "%UV_SHA256%" >nul
    if errorlevel 1 (
        del "%RT%\uv.zip"
        echo ERROR: la descarga de uv esta danada ^(suma incorrecta^). Vuelve a ejecutar este lanzador.
        goto :fallo
    )
    tar.exe -xf "%RT%\uv.zip" -C "%RT%" uv.exe
    del "%RT%\uv.zip"
)
"%RT%\uv.exe" python install 3.11 --no-bin --no-registry
if errorlevel 1 (
    echo ERROR: no se pudo descargar Python 3.11 portable. Revisa la conexion y reintenta.
    goto :fallo
)
call :buscar_python
if not defined PY (
    echo ERROR: no aparece Python 3.11 en "%RT%\python". Borra la carpeta runtime y reintenta.
    goto :fallo
)

:lanzar
"%PY%" -s -m partitura_libre.lanzar %*
if errorlevel 1 goto :fallo
exit /b 0

:buscar_python
set "PY="
if not exist "%RT%\python" exit /b 0
pushd "%RT%\python"
for /d %%D in (cpython-3.11*) do if exist "%%~fD\python.exe" set "PY=%%~fD\python.exe"
popd
exit /b 0

:fallo
echo.
pause
exit /b 1
