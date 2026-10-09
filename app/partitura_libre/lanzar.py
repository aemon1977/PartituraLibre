"""Prepara los paquetes dentro de runtime/ y abre la aplicación. Solo stdlib.

Lo ejecutan los lanzadores con el Python portable. La interfaz y los motores se
abren SIEMPRE con este mismo intérprete, así que no puede haber discrepancia
entre el Python que abre la ventana y el que contiene las dependencias.
"""
import hashlib
import shutil
import subprocess
import sys

from . import rutas

# conjunto: (módulos que deben poder importarse, tamaño aproximado en disco, imprescindible)
CONJUNTOS = {
    "app": (["PySide6.QtWidgets", "numpy", "sounddevice", "soundfile", "faster_whisper", "av"], "≈ 650 MB", True),
    "partituras": (["basic_pitch.inference", "onnxruntime", "pretty_midi", "music21", "soundfile"], "≈ 710 MB", False),
}


def _uv():
    return rutas.RUNTIME / ("uv.exe" if rutas.WINDOWS else "uv")


def _bloqueo(conjunto):
    return rutas.APP / "requisitos" / f"{conjunto}.txt"


def _huella(conjunto):
    return hashlib.sha256(_bloqueo(conjunto).read_bytes()).hexdigest()


def instalado(conjunto):
    sello = rutas.sitio(conjunto) / ".sello"
    return sello.is_file() and sello.read_text().strip() == _huella(conjunto)


def instalar(conjunto):
    destino = rutas.sitio(conjunto)
    sello = destino / ".sello"
    sello.unlink(missing_ok=True)
    orden = [str(_uv()), "pip", "install", "--python", sys.executable, "--target", str(destino),
             "--require-hashes", "--no-deps", "--no-config", "-r", str(_bloqueo(conjunto))]
    if subprocess.call(orden, env=rutas.uv_entorno()) != 0:
        return False
    sello.write_text(_huella(conjunto))
    return True


def comprobar(conjunto):
    """Importa de verdad los módulos con el intérprete y rutas que usará la app.
    Devuelve '' si todo va bien o el texto del error."""
    modulos = CONJUNTOS[conjunto][0]
    codigo = "import importlib,sys\nfor m in sys.argv[1:]:\n    importlib.import_module(m)\n"
    r = subprocess.run([sys.executable, "-s", "-c", codigo, *modulos], env=rutas.entorno(conjunto),
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    return "" if r.returncode == 0 else (r.stderr.strip().splitlines() or ["error desconocido"])[-1]


def main(args=None):
    args = list(sys.argv[1:] if args is None else args)
    reparar = "--reparar" in args
    si = "--si" in args or not sys.stdin or not sys.stdin.isatty()
    args = [a for a in args if a not in ("--reparar", "--si")]
    lanzador = "iniciar-windows.bat" if rutas.WINDOWS else "./iniciar-linux.sh"

    if not rutas.es_runtime_portable():
        print(f"ERROR: este programa debe abrirse con {lanzador}\n"
              f"  Python usado: {sys.executable}\n  Se esperaba uno dentro de: {rutas.RUNTIME}")
        return 2
    rutas.crear_carpetas()

    from . import actualizar   # una actualización descargada se aplica aquí, antes de abrir nada
    if "--deshacer-actualizacion" in args:
        v = actualizar.deshacer()
        print(f"Se ha vuelto a la versión {v}." if v else "No hay una versión anterior guardada.")
        args.remove("--deshacer-actualizacion")
        if not v:
            return 1
        return subprocess.call([sys.executable, "-s", "-m", "partitura_libre.lanzar", *args])
    try:
        nueva = actualizar.aplicar()
    except OSError as e:
        print(f"AVISO: no se pudo aplicar la actualización descargada ({e}). Se sigue con la versión actual.")
        nueva = ""
    if nueva:   # se vuelve a empezar con el código nuevo (su lanzador puede pedir paquetes distintos)
        print(f"Partitura Libre se ha actualizado a la versión {nueva}.")
        codigo = subprocess.call([sys.executable, "-s", "-c", "import partitura_libre.lanzar"])
        if codigo != 0:
            actualizar.deshacer()
            print("AVISO: la versión nueva no arranca; se ha restaurado la anterior.")
        return subprocess.call([sys.executable, "-s", "-m", "partitura_libre.lanzar", *args])

    pendientes = [c for c in CONJUNTOS if reparar or not instalado(c)]
    if pendientes:
        print("\nSe van a descargar componentes DENTRO de esta carpeta (nada en el sistema):")
        for c in pendientes:
            print(f"  - paquetes «{c}»: {CONJUNTOS[c][1]} en {rutas.sitio(c)}")
        if not si and input("¿Continuar? [S/n] ").strip().lower() in ("n", "no"):
            return 1
        for c in pendientes:
            print(f"\n== Instalando paquetes «{c}» ==", flush=True)
            if not instalar(c):
                print(f"\nERROR: no se pudieron descargar los paquetes «{c}».\n"
                      f"  Revisa la conexión a Internet y el espacio libre, y ejecuta: {lanzador} --reparar")
                if CONJUNTOS[c][2]:
                    return 1
        if all(instalado(c) for c in CONJUNTOS):  # la caché de descarga ya no hace falta
            shutil.rmtree(rutas.RUNTIME / "uv-cache", ignore_errors=True)

    for c, (_, _, imprescindible) in CONJUNTOS.items():
        fallo = comprobar(c) if instalado(c) else "paquetes sin instalar"
        if fallo:
            print(f"\n{'ERROR' if imprescindible else 'AVISO'}: el conjunto «{c}» no funciona: {fallo}\n"
                  f"  Solución (no instala nada en el sistema): {lanzador} --reparar")
            if imprescindible:
                return 1

    py = sys.executable
    if rutas.WINDOWS and "--diagnostico" not in args:  # sin consola negra detrás de la ventana
        pyw = rutas.Path(py).with_name("pythonw.exe")
        if pyw.is_file():
            subprocess.Popen([str(pyw), "-s", "-m", "partitura_libre", *args], env=rutas.entorno("app", False))
            return 0
    return subprocess.call([py, "-s", "-m", "partitura_libre", *args], env=rutas.entorno("app", False))


if __name__ == "__main__":
    sys.exit(main())
