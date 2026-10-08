"""Procesos de análisis. Hablan con la interfaz por líneas JSON en la salida estándar."""
import json
import os
import sys

_salida = sys.stdout
sys.stdout = sys.stderr  # lo que impriman las bibliotecas va al log, no al protocolo


def emitir(t, **datos):
    _salida.write(json.dumps({"t": t, **datos}, ensure_ascii=False) + "\n")
    _salida.flush()


def reemplazar(parcial, final):
    """Publica un resultado terminado; hasta entonces solo existe el .parcial."""
    os.replace(parcial, final)
