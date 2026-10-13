"""Cómo es el equipo: núcleos y memoria. Sirve para elegir modelos y repartir el procesador sin que la
ventana se trabe en ordenadores modestos (un mini PC con Ryzen 3, por ejemplo). Solo stdlib."""
import os

from . import rutas


def nucleos():
    """Hilos de procesador que puede usar el programa (los que el sistema le deja, no los del equipo entero)."""
    try:
        return len(os.sched_getaffinity(0))
    except AttributeError:   # Windows
        return os.cpu_count() or 2


def memoria_gb():
    """Memoria total en GB (0 si no se puede saber)."""
    try:
        if rutas.WINDOWS:
            import ctypes

            class Estado(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong), ("ullTotalPhys", ctypes.c_ulonglong),
                            ("ullAvailPhys", ctypes.c_ulonglong), ("ullTotalPageFile", ctypes.c_ulonglong),
                            ("ullAvailPageFile", ctypes.c_ulonglong), ("ullTotalVirtual", ctypes.c_ulonglong),
                            ("ullAvailVirtual", ctypes.c_ulonglong), ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
            e = Estado()
            e.dwLength = ctypes.sizeof(Estado)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(e))
            return e.ullTotalPhys / 2**30
        with open("/proc/meminfo") as f:
            return int(next(l for l in f if l.startswith("MemTotal")).split()[1]) / 2**20
    except Exception:
        return 0


def modesto(n=None, gb=None):
    """Equipo de pocos recursos: 4 hilos o menos, o menos de 12 GB de memoria."""
    n = nucleos() if n is None else n
    gb = memoria_gb() if gb is None else gb
    return n <= 4 or 0 < gb < 12


def hilos_de_calculo():
    """Hilos para los análisis: todos menos uno, que queda libre para que la ventana responda."""
    return max(1, nucleos() - 1)
