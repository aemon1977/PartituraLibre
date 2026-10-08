"""WAV sintético de notas conocidas -> MIDI -> MusicXML, con el motor real en su proceso aparte."""
import json
import threading
import time
import unittest
import xml.etree.ElementTree as ET

from partitura_libre import partituras, tareas
from tests.comun import ESCALA, Aislada, escribir_wav

PASO = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}


def ejecutar(orden, espera=300):
    """Lanza el motor de partituras y devuelve (eventos, código de salida)."""
    eventos, fin = [], threading.Event()
    codigo = []
    tareas.Tarea("partitura_libre.workers.notas", [json.dumps(orden)], "partituras", eventos.append,
                 lambda c, cancelada: (codigo.append(c), fin.set()))
    assert fin.wait(espera), "el motor no terminó a tiempo"
    return eventos, codigo[0]


def tonos_musicxml(ruta):
    raiz = ET.parse(ruta).getroot()
    tonos = []
    for nota in raiz.iter("note"):
        p = nota.find("pitch")
        if p is not None and nota.find("tie[@type='stop']") is None:
            tonos.append(PASO[p.findtext("step")] + int(float(p.findtext("alter") or 0)) + 12 * (int(p.findtext("octave")) + 1))
    return tonos


class Flujo(Aislada):
    def test_escala_conocida_llega_a_midi_y_musicxml_y_se_puede_corregir(self):
        wav = escribir_wav(self.dir / "escala de prueba.wav", [(m, 0.5) for m in ESCALA])
        eventos, codigo = ejecutar({"cmd": "transcribir", "audio": str(wav), "carpeta": str(self.dir), "nombre": "escala ñ"})
        self.assertEqual(codigo, 0, eventos)
        fin = eventos[-1]
        self.assertEqual(fin["t"], "fin")
        self.assertTrue(any(e["t"] == "progreso" for e in eventos))

        bpm, notas = partituras.leer_notas(self.dir / fin["notas"])
        self.assertEqual([n[2] for n in notas], ESCALA)
        for i, (inicio, final, _, _) in enumerate(notas):  # cada nota donde se tocó (±60 ms)
            self.assertAlmostEqual(inicio, i * 0.5, delta=0.06)
            self.assertAlmostEqual(final, i * 0.5 + 0.5, delta=0.08)
        self.assertEqual((self.dir / fin["midi"]).read_bytes()[:4], b"MThd")
        self.assertEqual(tonos_musicxml(self.dir / fin["musicxml"]), ESCALA)
        self.assertEqual(list(self.dir.glob("*.parcial")), [])
        self.assertTrue(wav.exists())

        # Corrección manual: el Mi pasa a Mi bemol y se crea una versión nueva sin pisar la primera.
        antes = {f: (self.dir / fin[f]).read_bytes() for f in ("midi", "musicxml", "notas")}
        notas[2][2] = 63
        edicion = self.dir / "edición.json"
        partituras.guardar_notas(edicion, bpm, notas)
        eventos2, codigo2 = ejecutar({"cmd": "regenerar", "notas": str(edicion), "carpeta": str(self.dir), "nombre": "escala ñ"})
        self.assertEqual(codigo2, 0, eventos2)
        fin2 = eventos2[-1]
        self.assertEqual(fin2["midi"], "escala ñ-2.mid")
        self.assertEqual(tonos_musicxml(self.dir / fin2["musicxml"]), ESCALA[:2] + [63] + ESCALA[3:])
        for f, contenido in antes.items():
            self.assertEqual((self.dir / fin[f]).read_bytes(), contenido, f"se modificó la primera versión de {f}")

    def test_audio_troceado_conserva_la_continuidad_temporal(self):
        """Con trozos de 2 s, una nota de 3 s cruza un corte: debe salir una sola nota y los tiempos reales."""
        wav = escribir_wav(self.dir / "larga.wav", [(60, 1.0), (67, 3.0), (72, 1.5)])
        eventos, codigo = ejecutar({"cmd": "transcribir", "audio": str(wav), "carpeta": str(self.dir), "nombre": "larga", "trozo_s": 2})
        self.assertEqual(codigo, 0, eventos)
        _, notas = partituras.leer_notas(self.dir / eventos[-1]["notas"])
        self.assertEqual([n[2] for n in notas], [60, 67, 72])
        for (inicio, final, _, _), (ei, ef) in zip(notas, [(0, 1), (1, 4), (4, 5.5)]):
            self.assertAlmostEqual(inicio, ei, delta=0.08)
            self.assertAlmostEqual(final, ef, delta=0.12)

    def test_silencio_no_inventa_notas_y_conserva_el_audio(self):
        import numpy as np
        import soundfile as sf
        wav = self.dir / "silencio.wav"
        sf.write(wav, np.zeros(44100 * 2, dtype="float32"), 44100, subtype="PCM_16")
        eventos, codigo = ejecutar({"cmd": "transcribir", "audio": str(wav), "carpeta": str(self.dir), "nombre": "silencio"})
        self.assertEqual(codigo, 1)
        self.assertEqual(eventos[-1]["t"], "error")
        self.assertIn("ninguna nota", eventos[-1]["msg"])
        self.assertEqual(sorted(p.name for p in self.dir.iterdir()), ["proyectos", "silencio.wav"])

    def test_archivo_ilegible_da_error_explicado_y_ningun_resultado(self):
        falso = self.dir / "no es audio.wav"
        falso.write_text("esto no es un WAV")
        eventos, codigo = ejecutar({"cmd": "transcribir", "audio": str(falso), "carpeta": str(self.dir), "nombre": "x"})
        self.assertEqual(codigo, 1)
        self.assertEqual(eventos[-1]["t"], "error")
        self.assertEqual(list(self.dir.glob("x*")), [])

    def test_cancelar_detiene_el_motor_y_no_deja_resultados_a_medias(self):
        wav = escribir_wav(self.dir / "larga.wav", [(m, 0.5) for m in ESCALA] * 4)
        fin, datos = threading.Event(), {}
        t = tareas.Tarea("partitura_libre.workers.notas",
                         [json.dumps({"cmd": "transcribir", "audio": str(wav), "carpeta": str(self.dir), "nombre": "cancelada"})],
                         "partituras", None, lambda c, cancelada: (datos.update(c=c, cancelada=cancelada), fin.set()))
        time.sleep(1.0)
        inicio = time.monotonic()
        t.cancelar()
        self.assertTrue(fin.wait(10))
        self.assertLess(time.monotonic() - inicio, 5)
        self.assertTrue(datos["cancelada"])
        self.assertFalse(t.viva())
        tareas.limpiar_parciales(self.dir)
        self.assertEqual(list(self.dir.glob("cancelada*")), [])
        self.assertTrue(wav.exists())


class Integracion(unittest.TestCase):
    def test_nota_que_cruza_trozos_se_alarga_y_no_se_duplica(self):
        hechas, ultima = [], {}
        # trozo 1: núcleo [0, 2), audio [0, 3)
        partituras.integrar(hechas, ultima, [[0.0, 1.0, 60, 0.7], [1.0, 2.6, 67, 0.8], [2.65, 3.0, 67, 0.5]], 0, 0, 2)
        self.assertEqual(hechas, [[0.0, 1.0, 60, 0.7], [1.0, 2.6, 67, 0.8]])   # el reataque del margen no cuenta
        # trozo 2: núcleo [2, 4), audio [1, 5): el Sol ya sonaba; un Do empieza en 3.99
        partituras.integrar(hechas, ultima, [[1.02, 4.0, 67, 0.8], [3.99, 5.0, 72, 0.6]], 1, 2, 4)
        # trozo 3: núcleo [4, fin), audio [3, 5.5): el mismo Do, visto ahora desde 4.01
        partituras.integrar(hechas, ultima, [[3.0, 4.0, 67, 0.8], [4.01, 5.5, 72, 0.9]], 3, 4, float("inf"))
        self.assertEqual(hechas, [[0.0, 1.0, 60, 0.7], [1.0, 4.0, 67, 0.8], [3.99, 5.5, 72, 0.9]])

    def test_en_vivo_sin_contexto_no_pierde_la_nota_que_empieza_en_el_corte(self):
        hechas, ultima = [], {}
        partituras.integrar(hechas, ultima, [[2.5, 2.98, 69, 0.7], [1.0, 3.0, 55, 0.7]], 0, 0, float("inf"))
        # segmento siguiente (empieza en 3.02): un Si nuevo y el Sol grave que seguía sonando
        partituras.integrar(hechas, ultima, [[3.03, 3.5, 71, 0.7], [3.03, 4.0, 55, 0.7]], 3.02, 3.02, float("inf"))
        self.assertEqual(sorted(hechas), [[1.0, 4.0, 55, 0.7], [2.5, 2.98, 69, 0.7], [3.03, 3.5, 71, 0.7]])

    def test_notas_repetidas_del_mismo_tono_siguen_separadas(self):
        hechas, ultima = [], {}
        partituras.integrar(hechas, ultima, [[0.0, 0.5, 60, 0.7], [0.5, 1.0, 60, 0.7], [1.0, 1.5, 60, 0.7]], 0, 0, 10)
        self.assertEqual(len(hechas), 3)

    def test_solo_se_quita_el_armonico_debil_y_simultaneo(self):
        fundamental, fantasma = [2.5, 3.0, 69, 0.76], [2.5, 2.7, 88, 0.30]   # 88 = tercer armónico de La4
        fuerte, despues, otra = [2.5, 3.0, 81, 0.70], [3.2, 3.4, 88, 0.30], [2.5, 2.7, 70, 0.30]
        notas = [fundamental, fantasma, fuerte, despues, otra]
        self.assertEqual(partituras.quitar_armonicos(notas), [fundamental, fuerte, despues, otra])


if __name__ == "__main__":
    unittest.main()
