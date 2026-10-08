"""Entrada de la aplicación. Debe ejecutarse con el Python del paquete (lo hacen los lanzadores)."""
import sys

from . import rutas


def main():
    lanzador = "iniciar-windows.bat" if rutas.WINDOWS else "./iniciar-linux.sh"
    if "--diagnostico" in sys.argv:
        from . import diagnostico
        r = diagnostico.comprobar()
        print(diagnostico.informe(r) + f"Informe guardado en {diagnostico.guardar(r)}")
        return 1 if any(e == diagnostico.ERROR for _, e, _ in r) else 0
    if not rutas.es_runtime_portable():
        print(f"Partitura Libre debe abrirse con {lanzador} (usa su propio Python, no el del sistema).\n"
              f"Python actual: {sys.executable}")
        return 2
    try:
        from .ui import ventana
    except ImportError as e:  # el caso del prototipo anterior: se detecta ANTES de abrir la ventana
        print(f"Falta una dependencia en el runtime portable: {e}\nSolución: {lanzador} --reparar")
        return 3
    return ventana.ejecutar()


if __name__ == "__main__":
    sys.exit(main())
