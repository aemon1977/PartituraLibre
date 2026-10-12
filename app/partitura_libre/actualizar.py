"""Actualizaciones desde GitHub. Solo stdlib, porque también lo usa el lanzador.

La app consulta la última versión publicada y, si el usuario acepta, descarga el paquete de su
sistema, lo comprueba y lo deja preparado en runtime/actualizacion. El cambio se aplica en el
siguiente arranque, antes de abrir nada: se sustituye app/ (la anterior queda en app.anterior)
y no se tocan runtime/, models/, data/, config/ ni logs/.
"""
import os
import re
import shutil
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path

from . import __version__, descargas, rutas

CREADOR = "aemon1977"
REPO = "aemon1977/PartituraLibre"
WEB = f"https://github.com/{REPO}"
API = f"https://api.github.com/repos/{REPO}/releases/latest"
SUFIJO = "-windows11-x64.zip" if rutas.WINDOWS else "-linux-x64.tar.gz"
RAIZ_PAQUETE = "PartituraLibre"
# Lo que se renueva además de app/. El .bat no se toca en Windows: se está ejecutando mientras se actualiza.
# Lo que se renueva además de app/, cada sistema con su lanzador: el ejecutable en Windows (ya se ha
# cerrado al arrancar Python: solo abre el programa y termina) y el guion en Linux.
OTROS = ("README.md", "LICENSE", "docs") + (("PartituraLibre.exe",) if rutas.WINDOWS else ("iniciar-linux.sh",))


def numero(version):
    """'v1.10.2' -> (1, 10, 2), para comparar versiones."""
    return tuple(int(x) for x in re.findall(r"\d+", version)[:3])


def _pendiente():
    return rutas.RUNTIME / "actualizacion"


def _version_de(carpeta_app):
    try:
        texto = (Path(carpeta_app) / "partitura_libre" / "__init__.py").read_text(encoding="utf-8")
        return re.search(r'__version__ = "(.+?)"', texto).group(1)
    except (OSError, AttributeError):
        return ""


def consultar():
    """Datos de la última versión publicada: {'version', 'nueva', 'notas', 'url', 'sha256', 'mb', 'pagina'}.
    Lanza OSError si no hay conexión o aún no hay ninguna versión publicada."""
    d = descargas.leer_json(API)
    version = d.get("tag_name", "").lstrip("v")
    # El paquete pequeño (solo el programa), no el completo de descarga, que lleva Python y modelos
    paquete = next((a for a in d.get("assets", []) if a["name"] == f"PartituraLibre-{version}{SUFIJO}"), None)
    return {"version": version, "nueva": bool(paquete) and numero(version) > numero(__version__),
            "notas": (d.get("body") or "").strip(), "pagina": d.get("html_url", WEB),
            "url": paquete["browser_download_url"] if paquete else "",
            "sha256": (paquete.get("digest") or "").removeprefix("sha256:") if paquete else "",
            "mb": round(paquete["size"] / 2**20, 1) if paquete else 0}


def preparar(info, progreso=None, cancelar=None):
    """Descarga y comprueba la versión nueva y la deja lista para el próximo arranque."""
    rutas.TEMP.mkdir(parents=True, exist_ok=True)
    archivo = rutas.TEMP / ("actualizacion" + SUFIJO)
    extraido = rutas.TEMP / "actualizacion-extraida"
    try:
        descargas.descargar(info["url"], archivo, progreso, cancelar, info.get("sha256") or None)
        shutil.rmtree(extraido, ignore_errors=True)
        if str(archivo).endswith(".zip"):
            with zipfile.ZipFile(archivo) as z:
                if any(Path(n).is_absolute() or ".." in Path(n).parts for n in z.namelist()):
                    raise OSError("El paquete de actualización contiene rutas no válidas.")
                z.extractall(extraido)
        else:
            with tarfile.open(archivo) as t:
                t.extractall(extraido, filter="data")   # rechaza rutas fuera de la carpeta, enlaces y permisos raros
        nueva = extraido / RAIZ_PAQUETE
        if _version_de(nueva / "app") != info["version"]:
            raise OSError("El paquete descargado no corresponde a la versión anunciada. No se ha cambiado nada.")
        shutil.rmtree(_pendiente(), ignore_errors=True)
        _pendiente().mkdir(parents=True)
        shutil.move(str(nueva), str(_pendiente() / RAIZ_PAQUETE))
    finally:
        archivo.unlink(missing_ok=True)
        shutil.rmtree(extraido, ignore_errors=True)


def pendiente():
    """Versión ya descargada que espera al próximo arranque, o ''."""
    v = _version_de(_pendiente() / RAIZ_PAQUETE / "app")
    return v if v and numero(v) > numero(__version__) else ""


def aplicar():
    """Lo llama el lanzador al arrancar. Sustituye app/ por la versión preparada y devuelve su número
    ('' si no había nada que aplicar). La app anterior queda en app.anterior por si hay que volver."""
    nueva = _pendiente() / RAIZ_PAQUETE
    version = _version_de(nueva / "app")
    if not version:
        shutil.rmtree(_pendiente(), ignore_errors=True)
        return ""
    anterior = rutas.RAIZ / "app.anterior"
    shutil.rmtree(anterior, ignore_errors=True)
    os.replace(rutas.APP, anterior)
    try:
        shutil.move(str(nueva / "app"), str(rutas.APP))
    except OSError:
        os.replace(anterior, rutas.APP)   # no se pudo colocar la nueva: se deja todo como estaba
        raise
    for nombre in OTROS:
        origen, destino = nueva / nombre, rutas.RAIZ / nombre
        if origen.is_dir():
            shutil.rmtree(destino, ignore_errors=True)
            shutil.copytree(origen, destino)
        elif origen.is_file():
            _sustituir(origen, destino)
    shutil.rmtree(_pendiente(), ignore_errors=True)
    return version


def _sustituir(origen, destino, intentos=20):
    """Copia un archivo encima de otro de forma atómica. Si está en uso (el .exe que acaba de abrir el
    programa tarda un instante en cerrarse), lo reintenta; si no se puede, se queda el anterior, que sigue
    sirviendo: no es motivo para dejar la actualización a medias."""
    import time
    temporal = destino.with_name(destino.name + ".nuevo")
    shutil.copy2(origen, temporal)
    for _ in range(intentos):
        try:
            os.replace(temporal, destino)
            return True
        except PermissionError:
            time.sleep(0.25)
    temporal.unlink(missing_ok=True)
    print(f"AVISO: {destino.name} estaba en uso y se mantiene el anterior; se renovará en la próxima actualización.")
    return False


def deshacer():
    """Vuelve a la versión anterior a la última actualización. Devuelve su número, o '' si no hay copia."""
    anterior = rutas.RAIZ / "app.anterior"
    version = _version_de(anterior)
    if version:
        descartada = rutas.RAIZ / "app.descartada"
        shutil.rmtree(descartada, ignore_errors=True)
        os.replace(rutas.APP, descartada)
        os.replace(anterior, rutas.APP)
        shutil.rmtree(descartada, ignore_errors=True)
    return version


def reiniciar():
    """Abre de nuevo el programa con su lanzador (que aplicará la actualización). La app debe cerrarse después."""
    if rutas.WINDOWS:
        exe = rutas.RAIZ / "PartituraLibre.exe"
        orden = [str(exe)] if exe.is_file() else ["cmd", "/c", "start", "", str(rutas.RAIZ / "iniciar-windows.bat")]
        subprocess.Popen(orden, cwd=str(rutas.RAIZ), creationflags=0x00000008)
    else:
        subprocess.Popen(["/bin/sh", str(rutas.RAIZ / "iniciar-linux.sh")], cwd=str(rutas.RAIZ), start_new_session=True,
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
