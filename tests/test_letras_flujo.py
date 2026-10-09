"""Voz -> texto con el motor real y audios libres de tests/datos (ver LICENCIAS.txt allí)."""
import threading
import unittest
from pathlib import Path

from partitura_libre import exportar, letras, tareas

DATOS = Path(__file__).parent / "datos"
MODELO = next((m for m in ("small", "base", "tiny") if letras.instalado(m)), None)


@unittest.skipUnless(MODELO, "no hay ningún modelo de voz descargado (descarga uno desde la app)")
class Voz(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.eventos, cls.cond = [], threading.Condition()

        def recibir(ev):
            with cls.cond:
                cls.eventos.append(ev)
                cls.cond.notify_all()
        cls.motor = tareas.Tarea("partitura_libre.workers.voz", [str(letras.carpeta_modelo(MODELO))], "app", recibir)

    @classmethod
    def tearDownClass(cls):
        cls.motor.cancelar()

    def transcribir(self, i, **orden):
        self.motor.enviar(id=i, **orden)
        with self.cond:
            ok = self.cond.wait_for(lambda: any(e["t"] in ("fin", "error") and e.get("id") == i for e in self.eventos), 300)
        self.assertTrue(ok, "el motor de voz no respondió")
        return [e for e in self.eventos if e.get("id") == i]

    def test_español_detectado_con_tiempos_y_exportable(self):
        ev = self.transcribir(1, audio=str(DATOS / "voz-es.flac"), idioma="")
        idioma = next(e for e in ev if e["t"] == "idioma")
        self.assertEqual(idioma["idioma"], "es")
        segs = [{k: e[k] for k in ("inicio", "fin", "texto", "dudoso")} for e in ev if e["t"] == "segmento"]
        texto = " ".join(s["texto"] for s in segs).lower()
        self.assertIn("desambiguación", texto)
        self.assertIn("wikipedia", texto)
        for a, b in zip(segs, segs[1:]):   # marcas de tiempo crecientes y dentro del audio
            self.assertLessEqual(a["inicio"], b["inicio"])
        self.assertTrue(all(0 <= s["inicio"] < s["fin"] <= 26 for s in segs), segs)
        vuelta = exportar.leer(exportar.srt(segs))  # exportación y reimportación
        self.assertEqual([s["texto"] for s in vuelta], [s["texto"] for s in segs])
        self.assertEqual(len(exportar.leer(exportar.lrc(segs))), len(segs))

    def test_idioma_elegido_a_mano_y_desfase_de_segmento_en_vivo(self):
        ev = self.transcribir(2, audio=str(DATOS / "jfk.flac"), idioma="en", desfase=100.0)
        segs = [e for e in ev if e["t"] == "segmento"]
        self.assertIn("ask not what your country can do for you", " ".join(s["texto"] for s in segs))
        self.assertTrue(all(s["inicio"] >= 100.0 for s in segs))

    def test_archivo_ilegible_da_error_y_el_motor_sigue_vivo(self):
        ev = self.transcribir(3, audio=str(DATOS / "LICENCIAS.txt"), idioma="es")
        self.assertEqual(ev[-1]["t"], "error")
        self.assertTrue(self.motor.viva())
        self.assertEqual(self.transcribir(4, audio=str(DATOS / "jfk.flac"), idioma="en")[-1]["t"], "fin")

    def test_modo_voz_cantada_no_inventa_texto_en_musica_sin_voz(self):
        """Una melodía sintética sin voz: lo que salga debe venir vacío o marcado como dudoso."""
        import tempfile
        from partitura_libre import rutas
        from tests.comun import ESCALA, escribir_wav
        rutas.TEMP.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=rutas.TEMP) as d:
            wav = escribir_wav(Path(d) / "melodía.wav", [(m, 0.5) for m in ESCALA] * 2)
            ev = self.transcribir(5, audio=str(wav), idioma="es", cantada=True)
        self.assertEqual(ev[-1]["t"], "fin")
        self.assertTrue(all(e["dudoso"] for e in ev if e["t"] == "segmento"), ev)


@unittest.skipUnless(MODELO, "no hay ningún modelo de voz descargado")
class SeparacionDeVoz(unittest.TestCase):
    """Voz real mezclada con una melodía fuerte, como una canción: el separador debe quitar la música."""

    @classmethod
    def setUpClass(cls):
        from partitura_libre import separacion
        if not separacion.instalado():
            raise unittest.SkipTest("el separador de voz no está descargado (se descarga desde la app)")
        import numpy as np
        from faster_whisper.audio import decode_audio
        from tests.comun import ESCALA, tono
        cls.voz = decode_audio(str(DATOS / "voz-es.flac"), sampling_rate=separacion.SR)[:separacion.SR * 12]
        musica = np.concatenate([tono(m, 0.5, separacion.SR) + tono(m - 12, 0.5, separacion.SR) for m in ESCALA * 3])[:len(cls.voz)]
        cls.musica = (musica * 0.25).astype("float32")
        cls.mezcla = cls.voz + cls.musica

    def test_la_voz_separada_tiene_mucha_menos_musica(self):
        import numpy as np
        from partitura_libre import separacion
        pasos = []
        estereo = np.stack([self.mezcla, self.mezcla], axis=1)
        voz = separacion.separar(estereo, pasos.append).mean(axis=1)
        self.assertEqual(len(voz), len(self.mezcla))
        self.assertEqual(pasos[-1], 1.0)
        self.assertEqual(pasos, sorted(pasos))
        db = lambda senal, ruido: 10 * np.log10(float((senal ** 2).sum()) / float((ruido ** 2).sum()))
        antes, despues = db(self.voz, self.musica), db(self.voz, voz - self.voz)
        self.assertGreater(despues, antes + 6, f"la separación apenas mejora: de {antes:.1f} a {despues:.1f} dB")

    def test_el_motor_transcribe_la_voz_separada_y_avisa_del_progreso(self):
        import tempfile
        import soundfile as sf
        from partitura_libre import rutas, separacion, tareas
        eventos, fin = [], threading.Event()
        rutas.TEMP.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=rutas.TEMP) as d:
            wav = Path(d) / "canción.wav"
            sf.write(wav, self.mezcla, separacion.SR, subtype="PCM_16")
            motor = tareas.Tarea("partitura_libre.workers.voz", [str(letras.carpeta_modelo(MODELO))], "app",
                                 lambda ev: (eventos.append(ev), fin.set() if ev["t"] in ("fin", "error") else None))
            motor.enviar(id=1, audio=str(wav), idioma="es", cantada=True, separar=True)
            self.assertTrue(fin.wait(300))
            motor.cancelar()
            self.assertEqual(list(rutas.TEMP.glob("voz-separada-*.wav")), [])      # el temporal se borra
        self.assertEqual(eventos[-1]["t"], "fin", eventos[-1])
        self.assertTrue(any(e["t"] == "progreso" and "Separando" in e["msg"] for e in eventos))
        self.assertIn("wikipedia", " ".join(e["texto"] for e in eventos if e["t"] == "segmento").lower())


class Modelos(unittest.TestCase):
    def test_catalogo_explica_tamaño_y_memoria(self):
        for nombre, (repo, mb, ram, descripcion) in letras.MODELOS.items():
            self.assertTrue(repo.startswith("Systran/faster-whisper-"))
            self.assertTrue(mb > 0 and ram > 0 and descripcion)
        self.assertLess(letras.MODELOS["base"][1], letras.MODELOS["small"][1])

    def test_los_modelos_viven_dentro_de_la_carpeta_portable(self):
        from partitura_libre import rutas
        self.assertTrue(rutas.dentro_de(letras.carpeta_modelo("small"), rutas.MODELOS))


if __name__ == "__main__":
    unittest.main()
