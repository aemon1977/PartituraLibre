import time
import unittest
from pathlib import Path

from partitura_libre import limpieza, rutas
from tests.comun import Aislada


class Desinstalacion(Aislada):
    def copia_falsa(self):
        raiz = self.dir / "Partitura Libre de pega"
        (raiz / "app" / "partitura_libre").mkdir(parents=True)
        (raiz / "app" / "partitura_libre" / "__init__.py").write_text("")
        (raiz / "iniciar-linux.sh").write_text("#!/bin/sh\n")
        (raiz / "data").mkdir()
        (raiz / "data" / "toma.wav").write_bytes(b"RIFF")
        return raiz

    def test_solo_reconoce_la_carpeta_del_programa(self):
        self.assertTrue(limpieza.es_carpeta_del_programa(rutas.RAIZ))
        self.assertTrue(limpieza.es_carpeta_del_programa(self.copia_falsa()))
        for ajena in (Path.home(), Path("/"), self.dir, rutas.RAIZ.parent, rutas.RAIZ / "app"):
            self.assertFalse(limpieza.es_carpeta_del_programa(ajena), ajena)

    def test_desinstalar_borra_la_carpeta_y_nada_mas(self):
        raiz = self.copia_falsa()
        vecino = self.dir / "copia exportada fuera.txt"
        vecino.write_text("debe sobrevivir")
        original, rutas.RAIZ = rutas.RAIZ, raiz
        try:
            limpieza.desinstalar()
        finally:
            rutas.RAIZ = original
        limite = time.monotonic() + 15
        while raiz.exists() and time.monotonic() < limite:
            time.sleep(0.2)
        self.assertFalse(raiz.exists())
        self.assertEqual(vecino.read_text(), "debe sobrevivir")
        self.assertTrue(rutas.RAIZ.exists())

    def test_se_niega_si_la_carpeta_no_es_la_del_programa(self):
        original, rutas.RAIZ = rutas.RAIZ, self.dir
        try:
            with self.assertRaises(RuntimeError):
                limpieza.desinstalar()
        finally:
            rutas.RAIZ = original
        self.assertTrue(self.dir.exists())

    def test_contenido_describe_las_carpetas(self):
        nombres = {n for n, _, _ in limpieza.contenido()}
        self.assertTrue({"app", "runtime"} <= nombres)


if __name__ == "__main__":
    unittest.main()
