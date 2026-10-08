"""MuseScore Studio como editor y exportador de PDF. Nunca se instala en el sistema:
se usa una copia portable dentro de runtime/musescore o una instalación que ya exista."""
import os
import shutil
import stat
import subprocess
from pathlib import Path

from . import config, descargas, rutas

VERSION = "4.7.5"
_BASE = f"https://github.com/musescore/MuseScore/releases/download/v{VERSION}/MuseScore-Studio-4.7.5.260831071-x86_64"
PORTABLE = ({"url": _BASE + ".paf.exe", "mb": 139, "sha256": "1f482f572edac911bf61a8fd2e7844b1a010c05b1a1bf611955c57c2c40eb4fa"}
            if rutas.WINDOWS else
            {"url": _BASE + ".AppImage", "mb": 195, "sha256": "a31b2da2dbcc2191bcc98beb7be5c15f2f517bedb3444def96fe3088b74d3a1e"})
CARPETA = rutas.RUNTIME / "musescore"
LICENCIA = "MuseScore Studio es software libre (GPL v3) de MuseScore Ltd.; se descarga de su página oficial de GitHub."


def _portable():
    if rutas.WINDOWS:
        return next(iter(CARPETA.glob("**/MuseScore*Portable.exe")), None) or next(iter(CARPETA.glob("**/MuseScore4.exe")), None)
    r = CARPETA / "squashfs-root" / "AppRun"
    return r if r.is_file() else None


def buscar():
    """(ruta, origen) con origen 'portable', 'elegido' o 'sistema'; (None, '') si no hay."""
    p = _portable()
    if p:
        return p, "portable"
    elegido = config.cargar().get("musescore")
    if elegido and Path(elegido).is_file():
        return Path(elegido), "elegido"
    for n in ("mscore4portable", "musescore4", "mscore4", "MuseScore4", "musescore", "mscore", "musescore3", "mscore3"):
        r = shutil.which(n)
        if r:
            return Path(r), "sistema"
    if rutas.WINDOWS:
        for base in (os.environ.get("ProgramFiles"), os.environ.get("ProgramFiles(x86)")):
            for r in (Path(base).glob("MuseScore*/bin/MuseScore*.exe") if base else ()):
                return r, "sistema"
    return None, ""


def _entorno(origen):
    if origen != "portable":
        return None  # una instalación existente se usa tal cual, sin tocar su configuración
    e = dict(os.environ)
    casa = rutas.DATOS / "musescore"
    casa.mkdir(parents=True, exist_ok=True)
    if not rutas.WINDOWS:
        # MuseScore crea ~/Documents/MuseScore4 y su configuración: con HOME y XDG dentro de la
        # carpeta del programa, todo eso queda aquí. Su AppImage solo trae bien el modo X11 (xcb).
        e.setdefault("XAUTHORITY", str(Path.home() / ".Xauthority"))
        e.update(HOME=str(casa), XDG_CONFIG_HOME=str(rutas.CONFIG / "musescore"), XDG_DATA_HOME=str(casa / "datos"),
                 XDG_CACHE_HOME=str(rutas.TEMP / "cache"), QT_QPA_PLATFORM="xcb")
    e.pop("PYTHONPATH", None)
    return e


def abrir(archivo=None):
    """Abre MuseScore (con una partitura o vacío). Devuelve False si no hay editor."""
    exe, origen = buscar()
    if not exe:
        return False
    subprocess.Popen([str(exe), *([str(archivo)] if archivo else [])], env=_entorno(origen),
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return True


def exportar_pdf(partitura, pdf, espera=180):
    """Convierte MusicXML/MIDI/MSCZ a PDF con MuseScore. Devuelve '' o el motivo del fallo."""
    exe, origen = buscar()
    if not exe:
        return "No hay MuseScore disponible."
    parcial = Path(pdf).with_name("parcial-" + Path(pdf).name)  # MuseScore decide el formato por la extensión
    try:
        r = subprocess.run([str(exe), "-o", str(parcial), str(partitura)], env=_entorno(origen), capture_output=True,
                           text=True, errors="replace", timeout=espera, stdin=subprocess.DEVNULL)
        if r.returncode != 0 or not parcial.is_file() or parcial.stat().st_size == 0:
            return f"MuseScore no pudo crear el PDF (código {r.returncode}). {r.stderr.strip()[-300:]}"
        os.replace(parcial, pdf)
        return ""
    except subprocess.TimeoutExpired:
        return "MuseScore tardó demasiado en responder al exportar el PDF."
    except OSError as e:
        return f"No se pudo ejecutar MuseScore: {e}"
    finally:
        parcial.unlink(missing_ok=True)


def instalar_portable(progreso=None, cancelar=None):
    """Descarga MuseScore dentro de runtime/musescore (acción explícita del usuario)."""
    CARPETA.mkdir(parents=True, exist_ok=True)
    archivo = CARPETA / PORTABLE["url"].rsplit("/", 1)[1]
    descargas.descargar(PORTABLE["url"], archivo, progreso, cancelar, PORTABLE["sha256"])
    if rutas.WINDOWS:
        # Instalador de PortableApps: solo descomprime en la carpeta indicada, sin registro ni permisos.
        r = subprocess.run([str(archivo), f"/DESTINATION={CARPETA}\\", "/SILENT=true", "/AUTOCLOSE=true"], timeout=900)
    else:
        archivo.chmod(archivo.stat().st_mode | stat.S_IXUSR)
        shutil.rmtree(CARPETA / "squashfs-root", ignore_errors=True)
        # Se extrae en vez de montarse: así no depende de FUSE del sistema.
        r = subprocess.run([str(archivo), "--appimage-extract"], cwd=str(CARPETA), stdout=subprocess.DEVNULL,
                           stderr=subprocess.PIPE, timeout=900)
    archivo.unlink(missing_ok=True)
    if r.returncode != 0 or not _portable():
        raise OSError("No se pudo descomprimir MuseScore dentro de la carpeta del programa.")


def quitar_portable():
    shutil.rmtree(CARPETA, ignore_errors=True)
