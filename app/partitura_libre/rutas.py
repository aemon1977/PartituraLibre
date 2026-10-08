"""Rutas del paquete portable. Todo cuelga de la carpeta del programa. Solo stdlib."""
import os
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
APP = RAIZ / "app"
RUNTIME = RAIZ / "runtime"
MODELOS = RAIZ / "models"
DATOS = RAIZ / "data"
PROYECTOS = DATOS / "proyectos"
CONFIG = RAIZ / "config"
LOGS = RAIZ / "logs"
TEMP = RAIZ / "temp"
WINDOWS = os.name == "nt"

_RESERVADOS = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}


def crear_carpetas():
    for c in (RUNTIME, MODELOS, PROYECTOS, CONFIG, LOGS, TEMP):
        c.mkdir(parents=True, exist_ok=True)


def dentro_de(ruta, base=RAIZ):
    """True si `ruta` está dentro de `base` (por defecto, la carpeta portable)."""
    try:
        Path(ruta).resolve().relative_to(Path(base).resolve())
        return True
    except ValueError:
        return False


def nombre_seguro(nombre, defecto="sin-titulo"):
    """Nombre de archivo válido en Windows y Linux; conserva tildes, eñes y espacios."""
    n = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", str(nombre)).strip(" .")[:80].strip(" .")
    if not n or n.upper().split(".")[0] in _RESERVADOS:
        n = f"{defecto}-{n}".strip("-") if n else defecto
    return n


def ruta_unica(carpeta, nombre, ext="", tambien=()):
    """Ruta que aún no existe: nombre.ext, nombre-2.ext… `tambien` son otras
    extensiones que deben quedar libres con el mismo nombre base."""
    carpeta, base = Path(carpeta), nombre_seguro(nombre)
    n = 1
    while True:
        b = f"{base}{'' if n == 1 else f'-{n}'}"
        if not any((carpeta / f"{b}{e}").exists() for e in (ext, *tambien)):
            return carpeta / f"{b}{ext}"
        n += 1


def carpeta_unica(carpeta, nombre):
    """Crea y devuelve una carpeta nueva; nunca reutiliza una existente."""
    while True:
        r = ruta_unica(carpeta, nombre)
        try:
            r.mkdir(parents=True)
            return r
        except FileExistsError:
            continue


def python_portable():
    """Intérprete Python 3.11 del paquete, o None si aún no se ha preparado."""
    patron = "cpython-3.11*/python.exe" if WINDOWS else "cpython-3.11*/bin/python3.11"
    return next(iter(sorted((RUNTIME / "python").glob(patron))), None)


def sitio(conjunto):
    return RUNTIME / f"site-{conjunto}"


def entorno(conjunto="app", aislar_perfil=True):
    """Variables para un proceso hijo: usa solo paquetes del paquete portable y
    redirige cachés/temporales a la carpeta del programa."""
    e = dict(os.environ)
    for k in ("PYTHONHOME", "PYTHONSTARTUP", "VIRTUAL_ENV", "PYTHONUSERBASE"):
        e.pop(k, None)
    e.update(
        PYTHONPATH=os.pathsep.join([str(APP), str(sitio(conjunto))]),
        PYTHONNOUSERSITE="1",
        PYTHONUTF8="1",
        PYTHONUNBUFFERED="1",
        PARTITURA_LIBRE_CONJUNTO=conjunto,
        HF_HOME=str(MODELOS / "hf"),
        HF_HUB_DISABLE_TELEMETRY="1",
        HF_HUB_OFFLINE="1",  # los modelos los descarga la app, nunca una biblioteca por su cuenta
        NUMBA_CACHE_DIR=str(TEMP / "numba"),
        MPLCONFIGDIR=str(TEMP / "mpl"),
        XDG_CACHE_HOME=str(TEMP / "cache"),
        TMPDIR=str(TEMP), TEMP=str(TEMP), TMP=str(TEMP),
    )
    cookie = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "pulse" / "cookie"
    if not WINDOWS and not cookie.exists():  # que la biblioteca de audio del sistema no la cree en el perfil
        e["PULSE_COOKIE"] = str(CONFIG / "pulse-cookie")
    if aislar_perfil:  # procesos sin audio: tampoco pueden escribir configuración en el perfil
        e.update(XDG_CONFIG_HOME=str(CONFIG / "xdg"), XDG_DATA_HOME=str(DATOS / "xdg"))
    return e


def uv_entorno():
    e = dict(os.environ)
    e.update(
        UV_CACHE_DIR=str(RUNTIME / "uv-cache"),
        UV_PYTHON_INSTALL_DIR=str(RUNTIME / "python"),
        UV_PYTHON_PREFERENCE="only-managed",
        UV_NO_CONFIG="1",
        UV_LINK_MODE="copy",
    )
    return e


def es_runtime_portable():
    return dentro_de(sys.executable, RUNTIME)
