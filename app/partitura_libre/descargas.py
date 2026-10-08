"""Descargas con progreso, cancelación y verificación. Solo se usan tras una acción del usuario."""
import hashlib
import json
import os
import urllib.request
from pathlib import Path

AGENTE = {"User-Agent": "PartituraLibre/1.0"}


class Cancelada(Exception):
    pass


def leer_json(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=AGENTE), timeout=30) as r:
        return json.load(r)


def descargar(url, destino, progreso=None, cancelar=None, sha256=None):
    """Baja `url` a `destino` pasando por destino.parcial. `progreso(bytes_hechos, bytes_total)`.
    `cancelar` es un threading.Event."""
    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    parcial = destino.with_name(destino.name + ".parcial")
    h = hashlib.sha256()
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=AGENTE), timeout=60) as r, open(parcial, "wb") as f:
            total, hecho = int(r.headers.get("Content-Length") or 0), 0
            while True:
                if cancelar is not None and cancelar.is_set():
                    raise Cancelada()
                b = r.read(1 << 18)
                if not b:
                    break
                f.write(b)
                h.update(b)
                hecho += len(b)
                if progreso:
                    progreso(hecho, total)
        if sha256 and h.hexdigest() != sha256:
            raise OSError(f"La descarga de {destino.name} llegó dañada (suma de verificación incorrecta). Reinténtalo.")
        os.replace(parcial, destino)
    finally:
        parcial.unlink(missing_ok=True)
    return destino
