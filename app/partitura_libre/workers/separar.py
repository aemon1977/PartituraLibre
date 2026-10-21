"""Aísla la voz de una canción en su propio proceso: al terminar, el sistema recupera toda la memoria del
separador (~1,6 GB) antes de que se cargue el reconocedor de voz. Lo lanza workers/voz.py.

Uso: python -m partitura_libre.workers.separar <audio> <destino.wav> <pid del proceso que lo lanza>
Termina solo si ese proceso pide parar (o se cancela) o deja de existir: así nunca queda trabajando huérfano.
"""
import os
import sys

from .. import separacion
from . import emitir, parada_pedida, vivo


def main():
    padre = int(sys.argv[3])

    def progreso(f):
        if parada_pedida(padre) or not vivo(padre):
            os._exit(1)
        emitir("progreso", v=round(f, 3))
    try:
        separacion.voz_a_wav(sys.argv[1], sys.argv[2], progreso)
        emitir("fin")
        return 0
    except Exception as e:
        import traceback
        traceback.print_exc()
        emitir("error", msg=f"{type(e).__name__}: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
