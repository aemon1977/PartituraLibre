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
    """Hilos para los análisis: todos menos uno, que queda libre para que la ventana responda. En equipos
    modestos, la mitad: un mini PC con todos los núcleos al máximo durante minutos se calienta tanto que
    puede llegar a apagarse."""
    n = nucleos()
    return max(1, n // 2) if modesto(n) else max(1, n - 1)


def onnxruntime():
    """ONNX Runtime del paquete. En Windows 11, System32 trae su propio onnxruntime.dll (de Windows ML), de otra
    versión: si el sistema lo carga en vez del nuestro, «import onnxruntime» falla (y Basic Pitch lo ocultaba con un
    «_default_model_type is not defined»). Por eso se carga antes el nuestro, por su ruta completa. Si aun así
    falla, el error real llega a quien lo use."""
    if rutas.WINDOWS:
        import ctypes
        import importlib.util
        from pathlib import Path
        capi = Path(importlib.util.find_spec("onnxruntime").origin).parent / "capi"
        # onnxruntime.dll necesita la biblioteca de C++ de Microsoft (msvcp140.dll), que un Windows recién instalado
        # no trae. El paquete ya la lleva junto a la ventana (shiboken6): se carga de ahí, sin instalar nada.
        for carpeta in (rutas.RUNTIME / "site-app" / "shiboken6", rutas.RUNTIME / "site-app" / "PySide6"):
            if (carpeta / "msvcp140.dll").is_file():
                os.add_dll_directory(str(carpeta))
                for nombre in ("msvcp140.dll", "msvcp140_1.dll", "msvcp140_2.dll"):   # vcruntime ya lo carga Python
                    if (carpeta / nombre).is_file():
                        ctypes.WinDLL(str(carpeta / nombre))
                break
        os.add_dll_directory(str(capi))
        ctypes.WinDLL(str(capi / "onnxruntime.dll"))
    import onnxruntime as ort
    return ort


def sesion_onnx(ruta):
    """Sesión de ONNX Runtime con los hilos de `hilos_de_calculo` y sin reserva anticipada de memoria
    (con ella, el separador ocupaba 2,9 GB; así, 1,4 GB, igual de rápido)."""
    ort = onnxruntime()
    opciones = ort.SessionOptions()
    opciones.intra_op_num_threads = hilos_de_calculo()
    opciones.inter_op_num_threads = 1
    opciones.enable_cpu_mem_arena = False
    opciones.enable_mem_pattern = False
    opciones.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_BASIC   # medido: −170 MB, igual de rápido
    return ort.InferenceSession(str(ruta), opciones, providers=["CPUExecutionProvider"])
