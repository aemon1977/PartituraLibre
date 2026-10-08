"""Utilidades de las pruebas: carpeta de datos aislada y audio sintético de notas conocidas."""
import shutil
import tempfile
import unittest
from pathlib import Path

import numpy as np

from partitura_libre import config, rutas

ESCALA = [60, 62, 64, 65, 67, 69, 71, 72]  # Do mayor, Do4..Do5


def tono(midi, segundos, sr=44100):
    f = 440 * 2 ** ((midi - 69) / 12)
    t = np.arange(int(sr * segundos)) / sr
    env = np.minimum(1, t / 0.01) * np.minimum(1, (segundos - t) / 0.02)
    return 0.5 * env * (np.sin(2 * np.pi * f * t) + 0.4 * np.sin(4 * np.pi * f * t) + 0.2 * np.sin(6 * np.pi * f * t))


def escribir_wav(ruta, notas, sr=44100):
    """notas: [(midi, segundos)]. Devuelve la ruta."""
    import soundfile as sf
    sf.write(ruta, np.concatenate([tono(m, s, sr) for m, s in notas]).astype("float32"), sr, subtype="PCM_16")
    return ruta


class Aislada(unittest.TestCase):
    """Cada prueba trabaja en una carpeta temporal con espacios y tildes, dentro de temp/ del programa."""

    def setUp(self):
        rutas.TEMP.mkdir(exist_ok=True)
        self.dir = Path(tempfile.mkdtemp(prefix="prueba ñandú ", dir=rutas.TEMP))
        self._orig = (rutas.PROYECTOS, config.ARCHIVO)
        rutas.PROYECTOS, config.ARCHIVO = self.dir / "proyectos", self.dir / "ajustes.json"
        rutas.PROYECTOS.mkdir()

    def tearDown(self):
        rutas.PROYECTOS, config.ARCHIVO = self._orig
        shutil.rmtree(self.dir, ignore_errors=True)
