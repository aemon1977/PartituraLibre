"""Revisión del contenido de la carpeta portable y desinstalación (borrado de la carpeta)."""
import os
import shutil
import subprocess

from . import rutas

DESCRIPCION = {"app": "código del programa", "runtime": "Python, paquetes y editor portables",
               "models": "modelos de voz", "data": "grabaciones, partituras y letras",
               "config": "preferencias", "logs": "diagnósticos", "temp": "temporales"}


def tamano(carpeta):
    total = 0
    for base, _, archivos in os.walk(carpeta):
        for a in archivos:
            try:
                total += os.lstat(os.path.join(base, a)).st_size
            except OSError:
                pass
    return total


def contenido():
    """[(nombre, descripción, bytes)] de lo que hay en la carpeta del programa."""
    return [(p.name, DESCRIPCION.get(p.name, ""), tamano(p) if p.is_dir() else p.stat().st_size)
            for p in sorted(rutas.RAIZ.iterdir()) if p.name != ".git"]


def vaciar_temporales():
    shutil.rmtree(rutas.TEMP, ignore_errors=True)
    rutas.TEMP.mkdir(exist_ok=True)


def es_carpeta_del_programa(carpeta):
    """Salvaguarda: solo se borra una carpeta que sea inequívocamente la de Partitura Libre."""
    c = rutas.Path(carpeta).resolve()
    return ((c / "app" / "partitura_libre" / "__init__.py").is_file() and len(c.parts) >= 3
            and c != rutas.Path.home().resolve() and any((c / f).is_file() for f in ("iniciar-linux.sh", "iniciar-windows.bat")))


def desinstalar():
    """Lanza un proceso independiente que borra la carpeta cuando la app se cierre.
    No toca nada fuera de ella. La app debe salir justo después de llamar aquí."""
    raiz = rutas.RAIZ
    if not es_carpeta_del_programa(raiz):
        raise RuntimeError(f"Por seguridad no se borra {raiz}: no parece la carpeta de Partitura Libre.")
    if rutas.WINDOWS:
        orden = f'ping -n 4 127.0.0.1 >nul & rmdir /s /q "{raiz}"'
        subprocess.Popen(["cmd", "/c", orden], cwd=str(raiz.parent), creationflags=0x00000008 | 0x08000000)  # DETACHED | NO_WINDOW
    else:
        subprocess.Popen(["/bin/sh", "-c", 'sleep 2; rm -rf -- "$1"', "sh", str(raiz)], cwd=str(raiz.parent),
                         start_new_session=True, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
