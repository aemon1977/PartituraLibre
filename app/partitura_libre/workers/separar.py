"""Aísla la voz de una canción en su propio proceso: al terminar, el sistema recupera toda la memoria del
separador (~1,6 GB) antes de que se cargue el reconocedor de voz. Lo lanza workers/voz.py.

Uso: python -m partitura_libre.workers.separar <audio> <destino.wav>
Si el proceso que lo lanzó muere (por ejemplo, al cancelar), su entrada estándar se cierra y este termina también.
"""
import os
import sys
import threading

from .. import separacion
from . import emitir


def main():
    threading.Thread(target=lambda: (sys.stdin.read(), os._exit(1)), daemon=True).start()   # huérfano: fuera
    try:
        separacion.voz_a_wav(sys.argv[1], sys.argv[2], lambda f: emitir("progreso", v=round(f, 3)))
        emitir("fin")
        return 0
    except Exception as e:
        import traceback
        traceback.print_exc()
        emitir("error", msg=f"{type(e).__name__}: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
