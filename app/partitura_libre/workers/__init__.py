"""Procesos de análisis. Hablan con la interfaz por líneas JSON en la salida estándar."""
import json
import os
import sys

from .. import rutas

_salida = sys.stdout
sys.stdout = sys.stderr  # lo que impriman las bibliotecas va al log, no al protocolo


def emitir(t, **datos):
    _salida.write(json.dumps({"t": t, **datos}, ensure_ascii=False) + "\n")
    _salida.flush()


def aviso_de_parar(pid=None):
    """Archivo con el que la interfaz pide a un motor que pare (lo crea tareas.Tarea.parar). Es un archivo y no
    una orden por la entrada estándar: en Windows, un hilo esperando en la entrada bloqueaba el análisis."""
    return rutas.TEMP / f"parar-{pid or os.getpid()}"


def parada_pedida(pid=None):
    return aviso_de_parar(pid).exists()


def vivo(pid):
    """¿Sigue en marcha ese proceso? (para que un proceso hijo no siga trabajando si su padre ya no está)."""
    if rutas.WINDOWS:
        import ctypes
        h = ctypes.windll.kernel32.OpenProcess(0x00100000, False, pid)   # SYNCHRONIZE
        if not h:
            return False
        try:
            return ctypes.windll.kernel32.WaitForSingleObject(h, 0) == 0x102   # WAIT_TIMEOUT: aún no ha terminado
        finally:
            ctypes.windll.kernel32.CloseHandle(h)
    return os.getppid() == pid


def reemplazar(parcial, final):
    """Publica un resultado terminado; hasta entonces solo existe el .parcial."""
    os.replace(parcial, final)
