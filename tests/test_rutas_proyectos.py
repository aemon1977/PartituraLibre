import unittest
from pathlib import Path

from partitura_libre import proyectos, rutas
from tests.comun import Aislada, escribir_wav


class Nombres(Aislada):
    def test_nombre_seguro_conserva_tildes_y_quita_lo_prohibido(self):
        self.assertEqual(rutas.nombre_seguro('Canción: "niño" <1>?'), "Canción_ _niño_ _1__")
        self.assertEqual(rutas.nombre_seguro("  ..  "), "sin-titulo")
        self.assertNotIn(rutas.nombre_seguro("CON").upper(), {"CON"})
        self.assertNotIn(rutas.nombre_seguro("nul.txt").upper().split(".")[0], {"NUL"})
        self.assertFalse(rutas.nombre_seguro("a/b\\c").count("/") + rutas.nombre_seguro("a/b\\c").count("\\"))
        self.assertLessEqual(len(rutas.nombre_seguro("x" * 500)), 80)

    def test_ruta_unica_no_pisa_ninguna_extension(self):
        (self.dir / "toma.mid").write_text("x")
        (self.dir / "toma-2.musicxml").write_text("x")
        self.assertEqual(rutas.ruta_unica(self.dir, "toma", ".mid", (".musicxml",)).name, "toma-3.mid")
        self.assertEqual(rutas.ruta_unica(self.dir, "otra", ".mid").name, "otra.mid")

    def test_dentro_de(self):
        self.assertTrue(rutas.dentro_de(rutas.DATOS / "x"))
        self.assertFalse(rutas.dentro_de(Path.home()))
        self.assertFalse(rutas.dentro_de(rutas.RAIZ.parent / (rutas.RAIZ.name + "-otra")))

    def test_entorno_no_apunta_fuera_de_la_carpeta(self):
        for conjunto in ("app", "partituras"):
            e = rutas.entorno(conjunto)
            for clave in ("HF_HOME", "NUMBA_CACHE_DIR", "MPLCONFIGDIR", "XDG_CACHE_HOME", "XDG_CONFIG_HOME", "XDG_DATA_HOME", "TMPDIR", "TEMP"):
                self.assertTrue(rutas.dentro_de(e[clave]), clave)
            for ruta in e["PYTHONPATH"].split(rutas.os.pathsep):
                self.assertTrue(rutas.dentro_de(ruta), ruta)
            self.assertEqual(e["PYTHONNOUSERSITE"], "1")
        for clave, valor in rutas.uv_entorno().items():
            if clave.startswith("UV_") and rutas.os.sep in valor:
                self.assertTrue(rutas.dentro_de(valor), clave)


class Proyectos(Aislada):
    def test_mismo_nombre_crea_carpetas_distintas(self):
        a, b = proyectos.crear("Mi toma", "partitura"), proyectos.crear("Mi toma", "partitura")
        self.assertNotEqual(a, b)
        self.assertEqual({a.name, b.name}, {"Mi toma", "Mi toma-2"})

    def test_importar_conserva_el_original_y_lo_asocia(self):
        origen = escribir_wav(self.dir / "melodía original.wav", [(60, 0.2)])
        d = proyectos.crear("importada", "partitura")
        copia = proyectos.importar_audio(d, origen)
        self.assertEqual(copia.read_bytes(), origen.read_bytes())
        self.assertTrue(origen.exists())
        self.assertEqual(proyectos.leer(d)["audio"], copia.name)
        segunda = proyectos.importar_audio(d, origen)  # reimportar no pisa
        self.assertNotEqual(segunda, copia)

    def test_resultado_queda_asociado_a_la_toma(self):
        d = proyectos.crear("toma", "partitura")
        proyectos.actualizar(d, audio="toma.wav")
        proyectos.anotar_resultado(d, "partitura", midi="toma.mid", musicxml="toma.musicxml", notas="toma.notas.json")
        proyectos.anotar_resultado(d, "partitura", midi="toma-2.mid", musicxml="toma-2.musicxml", notas="toma-2.notas.json")
        ficha = dict(proyectos.listar())[d]
        self.assertEqual(ficha["audio"], "toma.wav")
        self.assertEqual([r["midi"] for r in ficha["resultados"]], ["toma.mid", "toma-2.mid"])

    def test_grabacion_interrumpida_se_marca_y_no_se_borra(self):
        d = proyectos.crear("a medias", "letra")
        (d / "a medias.wav").write_bytes(b"RIFF")
        proyectos.actualizar(d, audio="a medias.wav", estado="grabando")
        self.assertEqual(proyectos.marcar_interrumpidos(), 1)
        ficha = proyectos.leer(d)
        self.assertEqual(ficha["estado"], "interrumpida")
        self.assertTrue(ficha["incompleta"])
        self.assertTrue((d / "a medias.wav").exists())

    def test_eliminar_solo_borra_proyectos(self):
        ajena = self.dir / "carpeta ajena"
        ajena.mkdir()
        (ajena / "importante.txt").write_text("no tocar")
        with self.assertRaises(ValueError):
            proyectos.eliminar(ajena)
        self.assertTrue((ajena / "importante.txt").exists())
        d = proyectos.crear("borrable", "letra")
        proyectos.eliminar(d)
        self.assertFalse(d.exists())

    def test_proyecto_en_carpeta_externa_aparece_en_el_historial(self):
        fuera = self.dir / "otra carpeta"
        d = proyectos.crear("externo", "partitura", fuera)
        self.assertIn(d, dict(proyectos.listar()))
        copia = proyectos.exportar(d, self.dir / "copias")
        self.assertTrue((copia / proyectos.FICHA).is_file())
        self.assertTrue(d.exists())


if __name__ == "__main__":
    unittest.main()
