"""Diagnóstico del paquete portable. Sin grabaciones ni datos personales en el informe."""
import platform
import shutil
import sys
from datetime import datetime
from pathlib import Path

from . import __version__, audio, editor, lanzar, letras, rutas

OK, AVISO, ERROR = "OK", "AVISO", "ERROR"


def _anonimo(texto):
    return str(texto).replace(str(rutas.RAIZ), "<carpeta del programa>").replace(str(Path.home()), "~")


def comprobar(probar_micro=True):
    """Lista de (comprobación, estado, detalle)."""
    r = []
    lanzador = "iniciar-windows.bat" if rutas.WINDOWS else "./iniciar-linux.sh"
    r.append(("Sistema", OK, f"{platform.system()} {platform.release()} · Partitura Libre {__version__}"))

    portable = rutas.es_runtime_portable()
    r.append(("Runtime portable", OK if portable else ERROR,
              f"Python {platform.python_version()} en {sys.executable}"
              + ("" if portable else f" — NO es el del paquete. Abre el programa con {lanzador}")))
    r.append(("Entorno activo", OK if sys.version_info[:2] == (3, 11) else ERROR,
              f"conjunto «{rutas.os.environ.get('PARTITURA_LIBRE_CONJUNTO', '?')}», Python {sys.version_info.major}.{sys.version_info.minor}"))

    for c, (modulos, _, _) in lanzar.CONJUNTOS.items():
        fallo = lanzar.comprobar(c) if lanzar.instalado(c) else "paquetes sin instalar"
        r.append((f"Paquetes «{c}»", ERROR if fallo else OK,
                  f"{fallo}. Solución: {lanzador} --reparar" if fallo else "se importan: " + ", ".join(modulos)))

    try:
        s = audio.sd()
        r.append(("Sistema de audio", OK, s.get_portaudio_version()[1]))
        micros = audio.microfonos()
        r.append(("Micrófonos", OK if micros else AVISO,
                  "; ".join(m["nombre"] + (" (predeterminado)" if m["predeterminado"] else "") for m in micros)
                  or "No hay ninguna entrada de audio. Conecta un micrófono y pulsa «Actualizar»."))
        if micros and probar_micro:
            try:
                g = audio.Grabadora(dispositivo=micros[0]["indice"], fuente=micros[0]["fuente"])
                g.iniciar()
                g.detener()
                r.append(("Acceso al micrófono", OK, f"se abre «{micros[0]['nombre']}» a {g.sr} Hz"))
            except audio.ErrorAudio as e:
                r.append(("Acceso al micrófono", ERROR, str(e)))
    except audio.ErrorAudio as e:
        r.append(("Sistema de audio", ERROR, str(e)))

    r.append(("Motor de partituras", OK if lanzar.instalado("partituras") else ERROR,
              "Basic Pitch 0.4.0 (ONNX) + music21, en proceso aparte con Python 3.11 portable"))
    puestos = [m for m in letras.MODELOS if letras.instalado(m)]
    r.append(("Modelos de voz", OK if puestos else AVISO,
              ", ".join(puestos) or "Ninguno descargado. Descarga uno en Letras o en Ajustes."))
    exe, origen = editor.buscar()
    r.append(("Editor de partituras", OK if exe else AVISO,
              f"MuseScore ({origen}): {exe}" if exe else
              "MuseScore no está disponible: la edición externa y el PDF quedan desactivados. "
              "Puedes descargar la versión portable desde Ajustes."))

    libre = shutil.disk_usage(rutas.RAIZ).free / 2**30
    r.append(("Espacio libre", OK if libre > 2 else AVISO, f"{libre:.1f} GB en la unidad del programa"))
    for carpeta in (rutas.DATOS, rutas.CONFIG, rutas.LOGS, rutas.TEMP, rutas.MODELOS):
        try:
            carpeta.mkdir(parents=True, exist_ok=True)
            (carpeta / ".prueba").write_text("")
            (carpeta / ".prueba").unlink()
        except OSError as e:
            r.append((f"Escritura en {carpeta.name}/", ERROR, f"{e}. Copia el programa a una carpeta donde puedas escribir."))
    return [(n, e, _anonimo(d)) for n, e, d in r]


def informe(resultados):
    return "\n".join(f"[{e:5}] {n}: {d}" for n, e, d in resultados) + "\n"


def guardar(resultados):
    rutas.LOGS.mkdir(parents=True, exist_ok=True)
    ruta = rutas.LOGS / f"diagnostico-{datetime.now():%Y%m%d-%H%M%S}.txt"
    ruta.write_text(informe(resultados), encoding="utf-8")
    return ruta
