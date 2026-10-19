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

    def test_modo_cancion_el_motor_da_una_linea_con_una_palabra_por_nota(self):
        """Por el motor real: con «melodia» la letra sale una palabra por nota y sin notas simultáneas."""
        wav = escribir_wav(self.dir / "voz.wav", [(67, 1.5), (69, 0.5), (71, 0.5)])
        palabras = [[0.0, 0.3, "no"], [0.5, 0.8, "be"], [1.0, 1.3, "re"], [1.55, 1.8, "sí"], [2.05, 2.3, "ya"]]
        eventos, codigo = ejecutar({"cmd": "transcribir", "audio": str(wav), "carpeta": str(self.dir), "nombre": "canción",
                                    "palabras": palabras, "melodia": True})
        self.assertEqual(codigo, 0, eventos)
        _, notas = partituras.leer_notas(self.dir / eventos[-1]["notas"])
        letra = partituras.leer_letra(self.dir / eventos[-1]["notas"])
        self.assertEqual([t for t in letra if t], ["no be re", "sí", "ya"])   # la partitura manda: el Sol largo no se divide
        self.assertEqual(sum(1 for a, b in zip(notas, notas[1:]) if b[0] < a[1] - 1e-3), 0)   # una sola línea
        self.assertEqual([n[2] for n, t in zip(notas, letra) if t], [67, 69, 71])

    def test_la_clave_elegida_y_los_nombres_de_nota_llegan_al_musicxml(self):
        wav = escribir_wav(self.dir / "escala.wav", [(m, 0.5) for m in ESCALA])
        eventos, codigo = ejecutar({"cmd": "transcribir", "audio": str(wav), "carpeta": str(self.dir), "nombre": "en fa",
                                    "clave": "fa", "nombres": True})
        self.assertEqual(codigo, 0, eventos)
        raiz = ET.parse(self.dir / eventos[-1]["musicxml"]).getroot()
        self.assertEqual([(c.findtext("sign"), c.findtext("line")) for c in raiz.iter("clef")], [("F", "4")])
        self.assertEqual([l.findtext("text") for l in raiz.iter("lyric")], ["Do", "Re", "Mi", "Fa", "Sol", "La", "Si", "Do"])
        self.assertEqual({l.get("color") for l in raiz.iter("lyric")}, {"#1D5FA8"})     # nombres en azul, distinto de la letra
        self.assertEqual(tonos_musicxml(self.dir / eventos[-1]["musicxml"]), ESCALA)   # la clave no cambia las notas
        sin, _ = ejecutar({"cmd": "regenerar", "notas": str(self.dir / eventos[-1]["notas"]), "carpeta": str(self.dir), "nombre": "sin nombres"})
        self.assertEqual(list(ET.parse(self.dir / sin[-1]["musicxml"]).getroot().iter("lyric")), [])

    def test_los_acordes_de_la_cancion_se_reconocen_y_llegan_al_musicxml(self):
        import numpy as np
        import soundfile as sf
        sr, progresion = 22050, [(48, 52, 55), (45, 48, 52), (41, 45, 48), (43, 47, 50)]   # Do, Lam, Fa, Sol
        t = np.arange(2 * sr) / sr
        sonar = lambda tonos: sum(np.sin(2 * np.pi * 440 * 2 ** ((m + o - 69) / 12) * t) for m in tonos for o in (0, 12)) * 0.08
        wav = self.dir / "acordes.wav"
        sf.write(wav, np.concatenate([sonar(a) for a in progresion]).astype("float32"), sr)
        eventos, codigo = ejecutar({"cmd": "transcribir", "audio": str(wav), "acordes_de": str(wav), "carpeta": str(self.dir),
                                    "nombre": "acordes", "bpm": 120, "armadura": 0})
        self.assertEqual(codigo, 0, eventos)
        acordes = partituras.leer_acordes(self.dir / eventos[-1]["notas"])
        self.assertEqual([partituras.nombre_acorde(r, tipo) for _t, r, tipo in acordes], ["Do", "Lam", "Fa", "Sol"])
        self.assertEqual([round(a[0]) for a in acordes], [0, 2, 4, 6])
        raiz = ET.parse(self.dir / eventos[-1]["musicxml"]).getroot()
        self.assertEqual([(h.findtext("root/root-step"), h.findtext("kind")) for h in raiz.iter("harmony")],
                         [("C", "major"), ("A", "minor"), ("F", "major"), ("G", "major")])
        otra, _ = ejecutar({"cmd": "regenerar", "notas": str(self.dir / eventos[-1]["notas"]), "carpeta": str(self.dir), "nombre": "editada"})
        self.assertEqual(partituras.leer_acordes(self.dir / otra[-1]["notas"]), acordes)   # editar no los pierde

    def test_al_parar_se_conserva_lo_analizado(self):
        """«Parar» a mitad: se termina el trozo en curso y se escribe la partitura con lo hecho hasta ahí."""
        wav = escribir_wav(self.dir / "larga.wav", [(m, 0.5) for m in ESCALA] * 20)   # 80 s
        eventos, fin = [], threading.Event()
        t = tareas.Tarea("partitura_libre.workers.notas", [json.dumps({"cmd": "transcribir", "audio": str(wav), "carpeta": str(self.dir),
                                                                      "nombre": "parada", "trozo_s": 10, "acordes_de": str(wav)})],
                         "partituras", lambda ev: (eventos.append(ev), t.parar() if ev["t"] == "progreso" and ev["v"] > 0 else None),
                         lambda c, cancelada: fin.set())
        self.assertTrue(fin.wait(300))
        r = eventos[-1]
        self.assertEqual(r["t"], "fin", r)
        self.assertTrue(r["parada"])
        self.assertLess(r["hasta"], 40)                               # no siguió hasta el final
        bpm, notas = partituras.leer_notas(self.dir / r["notas"])
        self.assertTrue(notas)                                        # lo analizado se conserva
        self.assertLess(max(n[0] for n in notas), r["hasta"])
        self.assertTrue(all(a[0] < r["hasta"] for a in partituras.leer_acordes(self.dir / r["notas"])))

    def test_con_hasta_la_partitura_acaba_donde_se_paro_la_letra(self):
        wav = escribir_wav(self.dir / "escala.wav", [(m, 0.5) for m in ESCALA] * 3)   # 12 s
        eventos, codigo = ejecutar({"cmd": "transcribir", "audio": str(wav), "carpeta": str(self.dir), "nombre": "hasta",
                                    "trozo_s": 4, "hasta": 5.0})
        self.assertEqual(codigo, 0, eventos)
        self.assertEqual((eventos[-1]["parada"], eventos[-1]["hasta"]), (True, 5.0))
        _bpm, notas = partituras.leer_notas(self.dir / eventos[-1]["notas"])
        self.assertTrue(notas and max(n[0] for n in notas) < 5.0)

    def test_los_cambios_de_tempo_llegan_al_musicxml_en_su_compas(self):
        # 8 negras a 120 (4 s) y después 8 negras a 60 (8 s): en la partitura, dos compases de negras cada uno
        notas = [[i * 0.5, i * 0.5 + 0.45, 60 + i, 0.7] for i in range(8)] + [[4 + i, 4 + i + 0.9, 70 + i, 0.7] for i in range(8)]
        partituras.guardar_notas(self.dir / "tempos.json", 120, notas, tempos=[[0.0, 120, ""], [4.0, 60, "Adagio"]])
        eventos, codigo = ejecutar({"cmd": "regenerar", "notas": str(self.dir / "tempos.json"), "carpeta": str(self.dir), "nombre": "tempos"})
        self.assertEqual(codigo, 0, eventos)
        raiz = ET.parse(self.dir / eventos[-1]["musicxml"]).getroot()
        marcas = [(m.get("number"), " ".join(w.text for w in m.iter("words")), m.findtext(".//metronome/per-minute"))
                  for m in raiz.iter("measure") if m.find(".//metronome") is not None]
        self.assertEqual(marcas, [("1", "Allegro", "120"), ("3", "Adagio", "60")])
        duraciones = [n.findtext("type") for n in raiz.iter("note") if n.find("rest") is None]
        self.assertEqual(duraciones, ["quarter"] * 16)                        # las lentas siguen siendo negras, no blancas
        self.assertEqual(partituras.leer_tempos(self.dir / eventos[-1]["notas"]), [[0.0, 120, ""], [4.0, 60, "Adagio"]])

    def test_ritmos_irregulares_no_generan_tresillos(self):
        """Regresión: los tresillos que deducía la conversión hacían que MuseScore se cerrase al abrir el archivo."""
        notas = [[i / 3 * 0.5, (i + 1) / 3 * 0.5, 60 + i % 5, 0.7] for i in range(24)] + [[4.1, 4.37, 72, 0.7], [4.43, 5.0, 74, 0.7]]
        partituras.guardar_notas(self.dir / "irregular.json", 120, notas)
        eventos, codigo = ejecutar({"cmd": "regenerar", "notas": str(self.dir / "irregular.json"), "carpeta": str(self.dir), "nombre": "irregular"})
        self.assertEqual(codigo, 0, eventos)
        xml = (self.dir / eventos[-1]["musicxml"]).read_text(encoding="utf-8")
        self.assertNotIn("<tuplet", xml)
        self.assertNotIn("<time-modification", xml)
        self.assertGreater(xml.count("<note"), 10)

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


class Silabas(unittest.TestCase):
    def test_silabas_del_espanol(self):
        from partitura_libre.silabas import silabas
        casos = {"beberé": "be-be-ré", "¿Cuántas": "¿Cuán-tas", "todavía": "to-da-ví-a", "agua": "a-gua", "construir": "cons-truir",
                 "perro": "pe-rro", "calle": "ca-lle", "noche": "no-che", "caer": "ca-er", "país": "pa-ís", "hoy": "hoy", "y": "y",
                 "querer?": "que-rer?", "Miguel": "Mi-guel", "pingüino": "pin-güi-no", "instrumento": "ins-tru-men-to",
                 "aeropuerto": "a-e-ro-puer-to", "ahora": "a-ho-ra", "transporte": "trans-por-te", "izquierda": "iz-quier-da"}
        for palabra, esperado in casos.items():
            self.assertEqual("-".join(silabas(palabra)), esperado, palabra)

    def test_la_letra_silabeada_va_al_musicxml_enlazada_y_vuelve_igual(self):
        import tempfile
        from pathlib import Path
        from partitura_libre import rutas
        rutas.TEMP.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=rutas.TEMP) as d:
            notas = [[i * 0.5, i * 0.5 + 0.5, 60 + 2 * i, 0.7] for i in range(4)]
            partituras.guardar_notas(Path(d) / "n.json", 120, notas, ["be-", "be-", "ré", "sí"])
            ev, codigo = ejecutar({"cmd": "regenerar", "notas": str(Path(d) / "n.json"), "carpeta": d, "nombre": "s"})
            self.assertEqual(codigo, 0, ev)
            raiz = ET.parse(Path(d) / ev[-1]["musicxml"]).getroot()
            self.assertEqual([(l.findtext("syllabic"), l.findtext("text")) for l in raiz.iter("lyric")],
                             [("begin", "be"), ("middle", "be"), ("end", "ré"), ("single", "sí")])
            ev2, _ = ejecutar({"cmd": "importar", "partitura": str(Path(d) / ev[-1]["musicxml"]), "carpeta": d, "nombre": "r"})
            self.assertEqual(partituras.leer_letra(Path(d) / ev2[-1]["notas"]), ["be-", "be-", "ré", "sí"])


class Tonalidad(unittest.TestCase):
    def test_detecta_la_tonalidad_de_escalas_conocidas(self):
        escala = lambda tonica, pasos: [[i * 0.5, i * 0.5 + 0.5, tonica + p, .7] for i, p in enumerate(pasos)] + [[4.0, 6.0, tonica, .7]]
        mayor, menor = [0, 2, 4, 5, 7, 9, 11, 12], [0, 2, 3, 5, 7, 8, 10, 12]
        self.assertEqual(partituras.tonalidad(escala(60, mayor)), (0, "Do mayor"))
        self.assertEqual(partituras.tonalidad(escala(62, mayor)), (2, "Re mayor"))
        self.assertEqual(partituras.tonalidad(escala(65, mayor)), (-1, "Fa mayor"))
        self.assertEqual(partituras.tonalidad(escala(70, mayor)), (-2, "Si♭ mayor"))
        self.assertEqual(partituras.tonalidad(escala(57, menor)), (0, "La menor"))
        self.assertEqual(partituras.tonalidad(escala(62, menor)), (-1, "Re menor"))
        self.assertEqual(partituras.tonalidad([]), (0, "Do mayor"))

    def test_deletreo_segun_la_armadura(self):
        self.assertEqual(partituras.solfeo(70, 0), "La♯")        # sin armadura, sostenidos (como hasta ahora)
        self.assertEqual(partituras.solfeo(70, -1), "Si♭")       # en Fa mayor, Si bemol
        self.assertEqual(partituras.solfeo(66, 2), "Fa♯")
        self.assertEqual(partituras.solfeo(68, -3), "La♭")       # en Mi♭ mayor
        self.assertEqual(partituras.solfeo(61, -2), "Re♭")       # nota ajena en tonalidad de bemoles: bemol
        self.assertEqual(partituras.nombre_nota(71, -6), "Do♭5")  # Do bemol: la octava es la de Do
        self.assertEqual(partituras.alteraciones(3), {3: 1, 0: 1, 4: 1})
        self.assertEqual(partituras.alteraciones(-2), {6: -1, 2: -1})
        self.assertEqual(partituras.posicion(70, "sol", -1), (4, False))   # Si♭4 en la línea central, sin sostenido
        self.assertEqual(partituras.posicion(70, "sol", 0), (3, True))     # La♯4 en el segundo espacio


class ArmaduraEnLaHoja(unittest.TestCase):
    def test_posiciones_estandar_de_la_armadura_en_cada_clave(self):
        from partitura_libre.ui.pentagrama import ARMADURA_SOL, DESPLAZA_CLAVE

        def posiciones(clave, signo):
            desplaza, maximo = DESPLAZA_CLAVE[clave]
            salida = []
            for letra, octava in ARMADURA_SOL[signo]:
                pos = octava * 7 + letra - 30 + desplaza
                salida.append(pos - 7 if pos > maximo else pos + 7 if pos < -1 else pos)
            return salida
        # 0 = línea inferior, 8 = superior. Posiciones de los manuales de solfeo:
        self.assertEqual(posiciones("sol", 1), [8, 5, 9, 6, 3, 7, 4])
        self.assertEqual(posiciones("sol", -1), [4, 7, 3, 6, 2, 5, 1])
        self.assertEqual(posiciones("fa", 1), [6, 3, 7, 4, 1, 5, 2])
        self.assertEqual(posiciones("fa", -1), [2, 5, 1, 4, 0, 3, -1])
        self.assertEqual(posiciones("do3", 1), [7, 4, 8, 5, 2, 6, 3])
        self.assertEqual(posiciones("do4", 1), [2, 6, 3, 7, 4, 8, 5])


class Notacion(unittest.TestCase):
    def test_posicion_de_las_notas_en_cada_clave(self):
        # Hechos de solfeo: la clave da nombre a su línea (0 = línea inferior, 2 = segunda, 8 = superior).
        self.assertEqual(partituras.posicion(67, "sol"), (2, False))    # Sol4 en la 2.ª línea
        self.assertEqual(partituras.posicion(60, "sol"), (-2, False))   # Do4 en la primera línea adicional inferior
        self.assertEqual(partituras.posicion(77, "sol"), (8, False))    # Fa5 en la 5.ª línea
        self.assertEqual(partituras.posicion(53, "fa"), (6, False))     # Fa3 en la 4.ª línea
        self.assertEqual(partituras.posicion(60, "fa"), (10, False))    # Do4 en la primera adicional superior
        self.assertEqual(partituras.posicion(60, "do3"), (4, False))    # Do4 en la 3.ª línea
        self.assertEqual(partituras.posicion(60, "do4"), (6, False))    # Do4 en la 4.ª línea
        self.assertEqual(partituras.posicion(66, "sol"), (1, True))     # Fa♯4: primer espacio, con sostenido
        self.assertEqual(partituras.posicion(59, "sol")[0], partituras.posicion(60, "sol")[0] - 1)  # Si-Do: un solo paso

    def test_compases_y_duracion_de_las_figuras(self):
        self.assertEqual([partituras.compas(t, 120) for t in (0.0, 1.8, 2.0, 3.8, 4.0)], [0, 0, 1, 1, 2])   # 4/4 a 120: un compás = 2 s
        self.assertEqual(partituras.compas(1.99, 120), 1)        # un inicio casi en la barra pertenece al compás siguiente
        self.assertEqual(partituras.compas(4.0, 60), 1)
        for fig in partituras.NEGRAS:                            # ida y vuelta figura <-> segundos
            self.assertEqual(partituras.figura(partituras.segundos_de(fig, 96), 96), fig)

    def test_posicion_y_nota_son_inversas_y_los_silencios_llenan_el_hueco(self):
        for clave in partituras.CLAVES:
            for midi in (36, 48, 60, 62, 64, 65, 67, 69, 71, 72, 84):      # notas naturales
                self.assertEqual(partituras.midi_de(partituras.posicion(midi, clave)[0], clave), midi)
        self.assertEqual(partituras.midi_de(2, "sol"), 67)                 # clic en la 2.ª línea en clave de Sol = Sol4
        self.assertEqual(partituras.silencios(1.5), ["negra", "corchea"])
        self.assertEqual(partituras.silencios(4), ["redonda"])
        self.assertEqual(partituras.silencios(0.1), [])                    # un respiro no es un silencio
        self.assertEqual(sum(partituras.NEGRAS[f] for f in partituras.silencios(2.75)), 2.75)

    def test_descripcion_de_una_nota(self):
        self.assertEqual(partituras.descripcion([1.2, 1.7, 67, 0.7], 120), "Sol4 · negra · empieza en 1,20 s · dura 0,50 s")
        self.assertEqual(partituras.descripcion([0.0, 0.75, 66, 0.7], 120, "sol"), "Fa♯4 · negra con puntillo · empieza en 0,00 s · dura 0,75 s · «sol»")

    def test_puntillo_y_teclas_de_nota(self):
        self.assertEqual(partituras.figura_y_puntillo(0.75, 120), ("negra", True))      # negra con puntillo a 120 = 0,75 s
        self.assertEqual(partituras.figura_y_puntillo(0.5, 120), ("negra", False))
        self.assertEqual(partituras.figura_y_puntillo(0.37, 120), ("negra", False))     # imprecisión de un audio: sin puntillo
        for fig in ("blanca", "negra", "corchea", "semicorchea"):
            self.assertEqual(partituras.figura_y_puntillo(partituras.segundos_de(fig, 90, True), 90), (fig, True))
        # escribir «Do Re Mi Fa Sol La Si Do» con el teclado sube por grados: cada nota, la más cercana a la anterior
        tono, escala = 60, []
        for letra in "DEFGABC":
            tono = partituras.tono_cercano(letra, tono)
            escala.append(tono)
        self.assertEqual(escala, [62, 64, 65, 67, 69, 71, 72])
        self.assertEqual(partituras.tono_cercano("G", 60), 55)     # Sol más cercano al Do4: el de abajo (una cuarta), no el de arriba (una quinta)
        self.assertEqual(partituras.tono_cercano("c", 61), 60)

    def test_clave_automatica_entre_sol_fa_y_do(self):
        clave = lambda tonos: partituras.clave_adecuada([[i, i + 0.5, t, .7] for i, t in enumerate(tonos)])
        self.assertEqual(clave([67, 72, 76, 79, 84]), "sol")             # violín, flauta, voz de soprano
        self.assertEqual(clave([40, 43, 45, 48, 50]), "fa")              # contrabajo, voz de bajo
        self.assertEqual(clave([50, 52, 55, 57, 60, 62]), "fa")         # Re3–Re4: Fa, con solo una línea adicional
        self.assertEqual(clave([52, 55, 57, 60, 64, 67, 69]), "do3")    # Mi3–La4 (viola): ni Sol ni Fa caben; Do en 3.ª
        self.assertEqual(clave([]), "sol")

    def test_cambios_de_tempo(self):
        T = partituras.tempos_de(120, [[8.0, 60, ""]])                       # 120 los primeros 8 s (16 negras), luego 60
        self.assertEqual(partituras.negras_en(10, T), 18.0)
        self.assertEqual(partituras.segundos_en(18, T), 10.0)
        self.assertEqual(partituras.a_compas(13, T), 12.0)                   # el compás 6 empieza en el segundo 12
        self.assertEqual(partituras.poner_tempo(T, 13, 90, "Andante")[-1], [12.0, 90, "Andante"])
        self.assertEqual(partituras.poner_tempo(T, 9, 0), [[0.0, 120, ""]])   # quitar el cambio de ese compás
        self.assertEqual(partituras.poner_tempo(T, 1, 100), [[0.0, 100, ""], [8.0, 60, ""]])
        # detección: un cambio claro que se mantiene; las oscilaciones y un doble suelto no cuentan
        self.assertEqual(partituras.cambios_de_tempo([100, 101, 99, 100, 130, 131, 129, 130], 100), [[0.0, 100, ""], [60.0, 130, ""]])
        self.assertEqual(partituras.cambios_de_tempo([100, 102, 98, 200, 101, 99], 100), [[0.0, 100, ""]])
        self.assertEqual([partituras.indicacion(b) for b in (50, 70, 99, 110, 130, 190)],
                         ["Largo", "Adagio", "Andante", "Moderato", "Allegro", "Presto"])
        self.assertEqual(partituras.marca_tempo(130, "Con brío"), "Con brío ♩ = 130")

    def test_acorde_de_un_cromagrama(self):
        croma = lambda *pcs: [1.0 if i in pcs else 0.05 for i in range(12)]
        self.assertEqual(partituras.acorde(croma(0, 4, 7)), (0, ""))                # Do mayor
        self.assertEqual(partituras.acorde(croma(9, 0, 4)), (9, "m"))               # La menor
        self.assertIsNone(partituras.acorde([1.0] * 12))                            # ruido: ningún acorde
        self.assertEqual(partituras.nombre_acorde(10, "", -2), "Si♭")
        self.assertEqual(partituras.nombre_acorde(6, "m", 2), "Fa♯m")
        # un trozo suelto distinto entre dos iguales es ruido; el silencio no lleva acorde
        trozos = [croma(0, 4, 7), croma(0, 4, 7), croma(2, 5, 9), croma(0, 4, 7), [0.0] * 12, croma(7, 11, 2)]
        self.assertEqual(partituras.acordes(trozos, 1.0), [[0.0, 0, ""], [5.0, 7, ""]])
        voz = lambda tonos: partituras.clave_adecuada([[i, i + 0.5, t, .7] for i, t in enumerate(tonos)], voz=True)
        self.assertEqual(voz([45, 48, 50, 51, 53, 55]), "sol8")           # voz grave cantando: Sol 8ª baja, nunca Fa
        self.assertEqual(voz([62, 64, 67, 69, 72]), "sol")                # voz aguda: Sol

    def test_nombres_figuras_acordes_y_clave_automatica(self):
        self.assertEqual([partituras.solfeo(m) for m in (60, 62, 64, 65, 67, 69, 71, 73)], ["Do", "Re", "Mi", "Fa", "Sol", "La", "Si", "Do♯"])
        self.assertEqual([partituras.figura(s, 120) for s in (2.0, 1.0, 0.5, 0.25, 0.12)], ["redonda", "blanca", "negra", "corchea", "semicorchea"])
        self.assertEqual(partituras.figura(1.0, 60), "negra")           # a 60 pulsos/min un segundo es una negra
        self.assertEqual(partituras.figura(0.37, 120), "negra")         # una negra detectada algo corta sigue siendo negra
        notas = [[0.5, 1.0, 64, .7], [0.0, 0.5, 60, .7], [0.52, 1.0, 67, .7], [0.5, 1.0, 60, .7]]
        self.assertEqual(partituras.columnas(notas), [[1], [3, 0, 2]])  # un acorde Do-Mi-Sol tras un Do suelto
        self.assertEqual(partituras.clave_adecuada([[0, 1, m, .7] for m in (60, 64, 67)]), "sol")
        self.assertEqual(partituras.clave_adecuada([[0, 1, m, .7] for m in (40, 43, 48)]), "fa")


class MelodiaCantada(unittest.TestCase):
    def test_una_sola_linea_gana_la_nota_mas_fuerte_y_se_quitan_los_restos(self):
        notas = [[0.0, 1.0, 60, 0.8], [0.0, 1.0, 72, 0.3],      # octava fantasma, más débil: fuera
                 [0.95, 1.5, 62, 0.9],                          # pisa el final del Do: el Do se acorta hasta 0,95
                 [1.5, 1.53, 64, 0.9],                          # resto de 30 ms: fuera
                 [1.6, 2.0, 65, 0.7], [2.03, 2.5, 65, 0.7]]     # misma nota partida por un respiro: se une
        self.assertEqual(partituras.melodia(notas), [[0.0, 0.95, 60, 0.8], [0.95, 1.6, 62, 0.9], [1.6, 2.5, 65, 0.7]])
        self.assertEqual(partituras.melodia([[0.0, 0.5, 60, 0.7], [1.0, 1.5, 62, 0.7]]),          # un silencio de verdad se respeta
                         [[0.0, 0.5, 60, 0.7], [1.0, 1.5, 62, 0.7]])

    def test_la_partitura_manda_las_notas_no_cambian(self):
        notas = [[0.0, 1.5, 67, 0.7], [1.5, 2.0, 69, 0.7], [2.0, 2.4, 71, 0.7], [5.0, 5.5, 72, 0.7]]
        # «beré» se canta mientras sigue el Sol de «no»: lo comparten. Igual «la» y «to» en el La.
        # «hola» no suena con ninguna nota: se añade a la sílaba anterior para no perderla.
        palabras = [[0.0, 0.3, "no"], [1.0, 1.3, "beré"], [1.55, 1.7, "la"], [1.7, 1.9, "to"], [2.05, 2.3, "mas"], [8.0, 8.3, "hola"]]
        notas2, letra = partituras.letra_cantada(notas, palabras)
        self.assertEqual(notas2, notas)                                  # ni divididas, ni creadas, ni quitadas
        self.assertEqual(letra, ["no beré", "la to", "mas hola", ""])
        self.assertEqual(partituras.letra_cantada(notas, []), (notas, ["", "", "", ""]))
        self.assertEqual(partituras.letra_cantada([], palabras), ([], []))

    def test_las_silabas_ocupan_las_notas_que_suenan_y_las_libres_que_siguen(self):
        notas = [[0, 0.4, 60, .7], [0.4, 0.6, 62, .7], [0.6, 0.8, 64, .7], [0.8, 1.0, 65, .7], [3, 3.2, 67, .7]]
        self.assertEqual(partituras.letra_cantada(notas, [[0, 0.3, "todavía"], [3, 3.1, "me"]])[1], ["to-", "da-", "ví-", "a", "me"])
        corta = [[0, 0.3, 60, .7], [0.3, 0.5, 62, .7]]           # sin sitio para todas las sílabas: van juntas
        self.assertEqual(partituras.letra_cantada(corta, [[0, 0.2, "tomaste"], [0.3, 0.4, "sin"]])[1], ["tomaste", "sin"])

    def test_notas_de_sobra_en_una_palabra_quedan_sin_texto_melisma(self):
        notas = [[0.0, 0.3, 60, .7], [0.3, 0.6, 62, .7], [0.6, 0.9, 64, .7]]
        self.assertEqual(partituras.letra_cantada(notas, [[0.0, 0.9, "sol"]])[1], ["sol", "", ""])

    def test_la_letra_nunca_retrocede_ni_se_pierde(self):
        notas = [[0.0, 0.4, 60, .7], [0.5, 0.9, 62, .7], [1.0, 1.4, 64, .7], [1.5, 1.9, 65, .7]]
        _, letra = partituras.letra_cantada(notas, [[0.0, 0.4, "se"], [0.5, 0.9, "perdió"], [0.6, 0.8, "juventud"]])
        self.assertEqual(letra, ["se", "perdió juventud", "", ""])

    def test_caso_real_no_bebere(self):
        notas = [[3.86, 4.22, 54, 0.6], [4.23, 4.45, 55, 0.4], [4.59, 5.0, 54, 0.6]]
        notas2, letra = partituras.letra_cantada(notas, [[3.86, 4.0, "no"], [4.0, 4.3, "beberé"], [4.6, 4.8, "y"]])
        self.assertEqual((notas2, letra), (notas, ["no", "beberé", "y"]))


class LetraEscritaAMano(unittest.TestCase):
    def test_se_reparte_en_silabas_una_por_nota(self):
        self.assertEqual(partituras.unidades("¿Cuántas veces dijiste?"), ["¿Cuán-", "tas", "ve-", "ces", "di-", "jis-", "te?"])
        self.assertEqual(partituras.unidades("no be-be-ré"), ["no", "be-", "be-", "ré"])      # la división escrita manda
        self.assertEqual(partituras.repartir_texto("can-ta-re sol", 6), (["can-", "ta-", "re", "sol"], 0))
        self.assertEqual(partituras.repartir_texto("a la mar", 5, desde=3), (["a", "la mar"], 1))   # sobran: juntas en la última
        self.assertEqual(partituras.repartir_texto("hola", 3, desde=3), ([], 2))
        self.assertEqual(partituras.juntar(["be-", "be-", "ré", "sí"]), "beberé sí")


class LetraBajoLasNotas(unittest.TestCase):
    NOTAS = [[0.0, 0.5, 60, .7], [0.5, 1.0, 62, .7], [1.0, 2.0, 64, .7], [1.0, 2.0, 52, .7], [3.0, 3.5, 65, .7]]

    def test_cada_palabra_va_a_la_nota_que_suena(self):
        palabras = [[0.05, 0.4, "Ho"], [0.55, 0.9, "la"], [1.1, 1.4, "mun"], [1.6, 1.9, "do"], [2.9, 3.3, "sí"]]
        self.assertEqual(partituras.asignar_letra(self.NOTAS, palabras), ["Ho", "la", "mun do", "", "sí"])
        # con dos notas a la vez la palabra va a la aguda (melodía), no al bajo; dos palabras en una nota larga se juntan

    def test_palabra_lejos_de_toda_nota_no_se_fuerza(self):
        self.assertEqual(partituras.asignar_letra(self.NOTAS, [[2.4, 2.6, "cerca"], [8.0, 8.5, "hablado"]]), ["", "", "cerca", "", ""])
        self.assertEqual(partituras.asignar_letra([], [[0, 1, "nada"]]), [])

    def test_guardar_y_leer_conserva_la_letra_junto_a_su_nota_aunque_se_reordene(self):
        import tempfile
        from pathlib import Path
        from partitura_libre import rutas
        rutas.TEMP.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=rutas.TEMP) as d:
            ruta = Path(d) / "n.json"
            partituras.guardar_notas(ruta, 100, [[2.0, 2.5, 64, .7], [0.0, 0.5, 60, .7], [1.0, 1.5, 62, .7]], ["tres", "uno"])
            self.assertEqual([n[2] for n in partituras.leer_notas(ruta)[1]], [60, 62, 64])
            self.assertEqual(partituras.leer_letra(ruta), ["uno", "", "tres"])
            partituras.guardar_notas(ruta, 100, [[0.0, 0.5, 60, .7]])
            self.assertEqual(partituras.leer_letra(ruta), [])


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
