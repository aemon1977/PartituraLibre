"""Actualización automática, probada sobre una instalación de pega: nunca toca la real."""
import hashlib
import io
import tarfile
import unittest
import zipfile
from pathlib import Path

from partitura_libre import __version__, actualizar, descargas, rutas
from tests.comun import Aislada


class Actualizacion(Aislada):
    def setUp(self):
        super().setUp()
        self._rutas = (rutas.RAIZ, rutas.APP, rutas.RUNTIME, rutas.TEMP)
        raiz = self.dir / "Partitura Libre instalada"
        rutas.RAIZ, rutas.APP, rutas.RUNTIME, rutas.TEMP = raiz, raiz / "app", raiz / "runtime", raiz / "temp"
        (rutas.APP / "partitura_libre").mkdir(parents=True)
        (rutas.APP / "partitura_libre" / "__init__.py").write_text(f'__version__ = "{__version__}"\n')
        (rutas.APP / "viejo.py").write_text("código anterior")
        (raiz / "data").mkdir()
        (raiz / "data" / "mi grabación.wav").write_text("audio del usuario")
        (raiz / "README.md").write_text("léeme viejo")
        self.addCleanup(lambda: setattr(rutas, "RAIZ", self._rutas[0]) or setattr(rutas, "APP", self._rutas[1])
                        or setattr(rutas, "RUNTIME", self._rutas[2]) or setattr(rutas, "TEMP", self._rutas[3]))

    def paquete(self, version, extra=None):
        """Crea un paquete como los publicados y devuelve los datos que daría GitHub sobre él."""
        archivos = {"PartituraLibre/app/partitura_libre/__init__.py": f'__version__ = "{version}"\n',
                    "PartituraLibre/app/nuevo.py": "código nuevo", "PartituraLibre/README.md": "léeme nuevo",
                    "PartituraLibre/docs/guia.md": "guía", "PartituraLibre/iniciar-linux.sh": "#!/bin/sh\n", **(extra or {})}
        ruta = self.dir / ("paquete" + actualizar.SUFIJO)
        if ruta.suffix == ".zip":
            with zipfile.ZipFile(ruta, "w") as z:
                for nombre, texto in archivos.items():
                    z.writestr(nombre, texto)
        else:
            with tarfile.open(ruta, "w:gz") as t:
                for nombre, texto in archivos.items():
                    info = tarfile.TarInfo(nombre)
                    info.size = len(texto.encode())
                    t.addfile(info, io.BytesIO(texto.encode()))
        return {"version": version, "url": ruta.as_uri(), "sha256": hashlib.sha256(ruta.read_bytes()).hexdigest(), "mb": 0.1}

    def test_orden_de_versiones(self):
        self.assertGreater(actualizar.numero("v1.10.0"), actualizar.numero("1.9.9"))
        self.assertEqual(actualizar.numero("v2.0.1"), (2, 0, 1))
        self.assertFalse(actualizar.numero(__version__) > actualizar.numero("v" + __version__))

    def test_consultar_detecta_solo_versiones_mas_nuevas_y_elige_el_paquete_de_este_sistema(self):
        def respuesta(tag):
            return {"tag_name": tag, "body": "Novedades", "html_url": "https://ejemplo/r", "assets": [
                {"name": "PartituraLibre-9-windows11-x64.zip", "browser_download_url": "https://ejemplo/w.zip", "size": 2**20, "digest": "sha256:aa"},
                {"name": "PartituraLibre-9-linux-x64.tar.gz", "browser_download_url": "https://ejemplo/l.tgz", "size": 2**21, "digest": "sha256:bb"}]}
        original = descargas.leer_json
        self.addCleanup(setattr, descargas, "leer_json", original)
        descargas.leer_json = lambda url: respuesta("v99.0.0")
        info = actualizar.consultar()
        self.assertTrue(info["nueva"])
        self.assertTrue(info["url"].endswith("w.zip" if rutas.WINDOWS else "l.tgz"))
        self.assertEqual((info["version"], info["sha256"], info["notas"]), ("99.0.0", "aa" if rutas.WINDOWS else "bb", "Novedades"))
        descargas.leer_json = lambda url: respuesta("v" + __version__)
        self.assertFalse(actualizar.consultar()["nueva"])
        descargas.leer_json = lambda url: respuesta("v0.0.1")
        self.assertFalse(actualizar.consultar()["nueva"])                    # nunca se «actualiza» hacia atrás
        descargas.leer_json = lambda url: {"tag_name": "v99.0.0", "assets": []}
        self.assertFalse(actualizar.consultar()["nueva"])                    # sin paquete para este sistema no se ofrece

    def test_descargar_aplicar_y_volver_atras_sin_tocar_los_datos(self):
        actualizar.preparar(self.paquete("99.1.0"))
        self.assertEqual(actualizar.pendiente(), "99.1.0")
        self.assertTrue((rutas.APP / "viejo.py").exists())                   # hasta el próximo arranque no cambia nada
        self.assertEqual(list(rutas.TEMP.glob("actualizacion*")), [])        # ni quedan descargas a medias

        self.assertEqual(actualizar.aplicar(), "99.1.0")                     # lo que hace el lanzador al arrancar
        self.assertTrue((rutas.APP / "nuevo.py").exists())
        self.assertFalse((rutas.APP / "viejo.py").exists())
        self.assertEqual((rutas.RAIZ / "README.md").read_text(), "léeme nuevo")
        self.assertTrue((rutas.RAIZ / "docs" / "guia.md").exists())
        self.assertEqual((rutas.RAIZ / "data" / "mi grabación.wav").read_text(), "audio del usuario")
        self.assertEqual(actualizar.aplicar(), "")                           # ya no queda nada pendiente
        self.assertEqual(actualizar.pendiente(), "")

        self.assertEqual(actualizar.deshacer(), __version__)                 # y se puede volver a la anterior
        self.assertTrue((rutas.APP / "viejo.py").exists())
        self.assertFalse((rutas.APP / "nuevo.py").exists())
        self.assertEqual(actualizar.deshacer(), "")

    def test_un_paquete_dañado_o_falso_no_cambia_nada(self):
        info = self.paquete("99.2.0")
        with self.assertRaises(OSError):                                     # suma de verificación incorrecta
            actualizar.preparar({**info, "sha256": "0" * 64})
        with self.assertRaises(OSError):                                     # dice ser una versión y contiene otra
            actualizar.preparar({**info, "version": "99.9.9"})
        self.assertEqual(actualizar.pendiente(), "")
        self.assertEqual(actualizar.aplicar(), "")
        self.assertTrue((rutas.APP / "viejo.py").exists())
        self.assertEqual(list(rutas.TEMP.glob("actualizacion*")), [])

    def test_un_paquete_no_puede_escribir_fuera_de_la_carpeta(self):
        fuera = self.dir / "fuera.txt"
        info = self.paquete("99.3.0", {"PartituraLibre/../../fuera.txt": "intruso"})
        with self.assertRaises((OSError, tarfile.TarError)):
            actualizar.preparar(info)
        self.assertFalse(fuera.exists())
        self.assertFalse((self.dir.parent / "fuera.txt").exists())
        self.assertEqual(actualizar.pendiente(), "")

    def test_el_creador_y_el_repositorio_figuran_en_la_aplicacion(self):
        self.assertEqual(actualizar.CREADOR, "aemon1977")
        self.assertEqual(actualizar.WEB, "https://github.com/aemon1977/PartituraLibre")
        self.assertIn("aemon1977", (self._rutas[0] / "LICENSE").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
