import unittest

from partitura_libre import exportar, letras

SEGS = [
    {"inicio": 0.0, "fin": 2.5, "texto": "Hola, ¿qué tal estás?", "dudoso": False},
    {"inicio": 3.25, "fin": 61.004, "texto": "Canción de la mañana", "dudoso": True},
    {"inicio": 3723.5, "fin": 3725.0, "texto": "Fin", "dudoso": False},
]


class Formatos(unittest.TestCase):
    def test_srt_exacto(self):
        self.assertEqual(exportar.srt(SEGS[:2]),
                         "1\n00:00:00,000 --> 00:00:02,500\nHola, ¿qué tal estás?\n\n"
                         "2\n00:00:03,250 --> 00:01:01,004\n⚠ Canción de la mañana\n")

    def test_vtt_y_lrc_exactos(self):
        self.assertTrue(exportar.vtt(SEGS).startswith("WEBVTT\n\n00:00:00.000 --> 00:00:02.500\nHola"))
        self.assertIn("01:02:03.500 --> 01:02:05.000\nFin", exportar.vtt(SEGS))
        self.assertEqual(exportar.lrc(SEGS).splitlines(),
                         ["[00:00.00]Hola, ¿qué tal estás?", "[00:03.25]⚠ Canción de la mañana", "[62:03.50]Fin"])

    def test_ida_y_vuelta_srt_y_vtt(self):
        for fmt in (exportar.srt, exportar.vtt):
            vuelta = exportar.leer(fmt(SEGS))
            self.assertEqual([s["texto"] for s in vuelta], [s["texto"] for s in SEGS])
            self.assertEqual([s["dudoso"] for s in vuelta], [s["dudoso"] for s in SEGS])
            for a, b in zip(vuelta, SEGS):
                self.assertAlmostEqual(a["inicio"], b["inicio"], places=3)
                self.assertAlmostEqual(a["fin"], b["fin"], places=3)

    def test_ida_y_vuelta_lrc_rellena_el_fin(self):
        vuelta = exportar.leer(exportar.lrc(SEGS))
        self.assertEqual([round(s["inicio"], 2) for s in vuelta], [0.0, 3.25, 3723.5])
        self.assertEqual(vuelta[0]["fin"], 3.25)   # hasta donde empieza la siguiente
        self.assertGreater(vuelta[2]["fin"], vuelta[2]["inicio"])

    def test_txt_sin_tiempos_y_srt_con_varias_lineas(self):
        vuelta = exportar.leer(exportar.txt(SEGS))
        self.assertEqual([s["texto"] for s in vuelta], [s["texto"] for s in SEGS])
        self.assertTrue(all(s["inicio"] is None for s in vuelta))
        self.assertEqual(exportar.con_tiempos(vuelta), [])
        multilinea = exportar.leer("1\n00:00:01,000 --> 00:00:02,000\nprimera\nsegunda\n\n2\n00:00:03,000 --> 00:00:04,000\n1999\n")
        self.assertEqual([s["texto"] for s in multilinea], ["primera segunda", "1999"])


class TextoEditable(unittest.TestCase):
    def test_correcciones_conservan_los_tiempos(self):
        texto = letras.a_texto(SEGS, marcas=False)
        editado = texto.replace("Hola", "Buenas").replace("⚠ ", "")  # corrige y da por revisado
        segs = letras.de_texto(editado, SEGS)
        self.assertEqual(segs[0]["texto"], "Buenas, ¿qué tal estás?")
        self.assertEqual([(s["inicio"], s["fin"]) for s in segs], [(s["inicio"], s["fin"]) for s in SEGS])
        self.assertFalse(segs[1]["dudoso"])

    def test_con_marcas_ida_y_vuelta_y_cambio_manual_de_tiempo(self):
        texto = letras.a_texto(SEGS, marcas=True)
        self.assertEqual(texto.splitlines()[1], "[00:03.25] ⚠ Canción de la mañana")
        self.assertEqual(letras.de_texto(texto, SEGS), [{**s, "fin": s["fin"]} for s in SEGS])
        movido = letras.de_texto(texto.replace("[00:03.25]", "[00:10.00]"), SEGS)
        self.assertEqual(movido[1]["inicio"], 10.0)

    def test_linea_nueva_sin_marca_no_inventa_tiempo(self):
        segs = letras.de_texto(letras.a_texto(SEGS, True) + "\nverso añadido a mano", SEGS)
        self.assertEqual(len(segs), 4)
        self.assertIsNone(segs[3]["inicio"])
        self.assertEqual(len(exportar.con_tiempos(segs)), 3)

    def test_criterio_de_duda(self):
        self.assertFalse(letras.es_dudoso(-0.2, 0.05, 1.4))
        self.assertTrue(letras.es_dudoso(-1.3, 0.05, 1.4))   # el modelo no está seguro
        self.assertTrue(letras.es_dudoso(-0.2, 0.9, 1.4))    # probablemente no hay voz
        self.assertTrue(letras.es_dudoso(-0.2, 0.05, 3.0))   # texto repetitivo (alucinación típica)


if __name__ == "__main__":
    unittest.main()
