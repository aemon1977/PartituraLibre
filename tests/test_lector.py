"""Lector de partituras: instrumento y letra en el MusicXML (siempre) y, si MuseScore y Audiveris están
descargados, de una partitura real en PDF a sonido, con las mismas notas que el original."""
import os
import unittest
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

from partitura_libre import editor, lector, rutas
from tests.comun import Aislada

DATOS = Path(__file__).parent / "datos"
PASOS = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}

DOS_PARTES = """<?xml version="1.0" encoding="UTF-8"?>
<score-partwise version="3.1">
  <part-list>
    <score-part id="P1"><part-name>Voz</part-name>
      <score-instrument id="P1-I1"><instrument-name>Voice</instrument-name><instrument-sound>voice.vocals</instrument-sound></score-instrument>
      <midi-instrument id="P1-I1"><midi-channel>1</midi-channel><midi-program>53</midi-program></midi-instrument>
    </score-part>
    <score-part id="P2"><part-name>Bajo</part-name></score-part>
  </part-list>
  <part id="P1"><measure number="1">
    <attributes><divisions>1</divisions><time><beats>2</beats><beat-type>4</beat-type></time><clef><sign>G</sign><line>2</line></clef></attributes>
    <note><pitch><step>C</step><octave>5</octave></pitch><duration>1</duration><type>quarter</type><lyric><syllabic>single</syllabic><text>la</text></lyric></note>
    <note><pitch><step>F</step><alter>1</alter><octave>4</octave></pitch><duration>1</duration><type>quarter</type><lyric><text>ra</text></lyric></note>
  </measure></part>
  <part id="P2"><measure number="1">
    <attributes><divisions>1</divisions><time><beats>2</beats><beat-type>4</beat-type></time><clef><sign>F</sign><line>4</line></clef></attributes>
    <note><pitch><step>C</step><octave>3</octave></pitch><duration>2</duration><type>half</type></note>
  </measure></part>
</score-partwise>
"""


def alturas(musicxml):
    """Número MIDI de cada nota sonora de un MusicXML."""
    return [(int(p.findtext("octave")) + 1) * 12 + PASOS[p.findtext("step")] + int(float(p.findtext("alter") or 0))
            for p in ET.parse(musicxml).iter("pitch")]


def suenan(midi):
    """Número MIDI de cada nota que suena en un archivo MIDI (sin la percusión): la altura real, también
    en los instrumentos transpositores, cuya partitura se escribe en otra altura."""
    d, i, notas = Path(midi).read_bytes(), 14, []

    def numero(j):   # cantidad de longitud variable
        n = 0
        while True:
            n, j = (n << 7) | (d[j] & 0x7F), j + 1
            if not d[j - 1] & 0x80:
                return n, j
    while i < len(d):
        fin, j, estado = i + 8 + int.from_bytes(d[i + 4:i + 8], "big"), i + 8, 0
        while j < fin:
            j = numero(j)[1]
            if d[j] == 0xFF:
                largo, j = numero(j + 2)
                j += largo
                continue
            if d[j] in (0xF0, 0xF7):
                largo, j = numero(j + 1)
                j += largo
                continue
            if d[j] & 0x80:
                estado, j = d[j], j + 1
            if estado >> 4 in (0xC, 0xD):
                j += 1
                continue
            if estado >> 4 == 9 and d[j + 1] and estado & 0xF != 9:
                notas.append(d[j])
            j += 2
        i = fin
    return notas


class Instrumento(Aislada):
    def test_todas_las_partes_con_el_instrumento_elegido_y_sin_letra(self):
        (self.dir / "dos.musicxml").write_text(DOS_PARTES, encoding="utf-8")
        salida = lector.con_instrumento(self.dir / "dos.musicxml", "Trompeta", self.dir / "t.musicxml")
        arbol = ET.parse(salida)
        self.assertEqual(list(arbol.iter("lyric")), [])
        self.assertEqual(list(arbol.iter("midi-instrument")), [])   # su programa 53 haría elegir otro instrumento
        partes = list(arbol.iter("score-part"))
        self.assertEqual([p.findtext("part-name") for p in partes], ["Trumpet in B♭"] * 2)
        self.assertEqual([p.findtext("score-instrument/instrument-sound") for p in partes], ["brass.trumpet"] * 2)
        self.assertEqual(alturas(salida), [72, 66, 48])   # las notas no se tocan

    def test_cada_instrumento_tiene_sonido_y_nombre(self):
        self.assertEqual(len(lector.INSTRUMENTOS), 35)
        for nombre, (sonido, en_musescore) in lector.INSTRUMENTOS.items():
            self.assertRegex(sonido, r"^[a-z-]+(\.[a-z-]+)+$", nombre)
            self.assertTrue(en_musescore, nombre)

    def test_paquete_deb_sin_dpkg(self):
        """Sin dpkg-deb, el .deb (un archivo «ar») se abre en Python: se busca su miembro data.tar.*"""
        deb = self.dir / "prueba.deb"
        cabecera = lambda n, t: f"{n:<16}{0:<12}{0:<6}{0:<6}{100644:<8}{t:<10}`\n".encode()
        deb.write_bytes(b"!<arch>\n" + cabecera("debian-binary", 4) + b"2.0\n" + cabecera("control.tar.zst", 3) + b"abc\n"
                        + cabecera("data.tar.zst", 5) + b"datos\n")
        origen, rutas.TEMP = rutas.TEMP, self.dir
        try:
            extraido = lector._miembro_ar(deb, "data.tar")
        finally:
            rutas.TEMP = origen
        self.assertEqual(extraido.read_bytes(), b"datos")

    def test_sin_componentes_lo_dice(self):
        origen = editor.buscar
        editor.buscar = lambda: (None, "")
        try:
            with self.assertRaisesRegex(FileNotFoundError, "MuseScore"):
                lector.musescore(self.dir / "x.musicxml", self.dir / "x.wav")
        finally:
            editor.buscar = origen
        if not lector.audiveris():
            with self.assertRaisesRegex(FileNotFoundError, "Audiveris"):
                lector.a_musicxml(DATOS / "minueto-bach.pdf", self.dir)


def _perfil():
    """Carpetas que MuseScore o Audiveris crearían en el perfil del usuario si no se les encerrase."""
    casa = Path.home()
    sitios = [casa / ".config/MuseScore", casa / ".local/share/MuseScore", casa / "Documents/MuseScore4",
              casa / ".config/AudiverisLtd", casa / ".cache/AudiverisLtd", casa / ".local/share/AudiverisLtd"]
    if rutas.WINDOWS:
        sitios.append(lector._documentos() / "MuseScore4")
    for var in ("APPDATA", "LOCALAPPDATA"):
        if os.environ.get(var):
            sitios += [Path(os.environ[var]) / "MuseScore", Path(os.environ[var]) / "AudiverisLtd"]
    return {s for s in sitios if s.exists()}


@unittest.skipUnless(editor.buscar()[0], "MuseScore no está descargado (Lector o Ajustes)")
class ConMuseScore(Aislada):
    @classmethod
    def setUpClass(cls):
        cls.perfil = _perfil()

    def test_suena_con_el_instrumento_a_la_misma_altura(self):
        (self.dir / "dos.musicxml").write_text(DOS_PARTES, encoding="utf-8")
        xml = lector.a_musicxml(self.dir / "dos.musicxml", self.dir / "leida")
        self.assertEqual(sorted(alturas(xml)), [48, 66, 72])
        # Los transpositores (trompeta en Si♭, guitarra y contrabajo a la octava) deben sonar igual que escritos
        for instrumento in ("Trompeta", "Guitarra clásica", "Contrabajo"):
            tocada = lector.con_instrumento(xml, instrumento, self.dir / "t.musicxml")
            self.assertEqual(sorted(suenan(lector.musescore(tocada, self.dir / f"{instrumento}.mid"))), [48, 66, 72], instrumento)
        wav = lector.sonar(xml, "Violín", self.dir / "violin")
        import soundfile as sf
        datos, sr = sf.read(wav)
        self.assertGreater(len(datos) / sr, 1.5)
        self.assertGreater(abs(datos).max(), 0.01)   # suena, no es silencio

    def test_cancelar_corta_al_momento(self):
        import threading
        import time
        cancelar = threading.Event()
        threading.Timer(0.5, cancelar.set).start()
        (self.dir / "dos.musicxml").write_text(DOS_PARTES, encoding="utf-8")
        t = time.monotonic()
        with self.assertRaises(lector.Cancelado):
            lector.musescore(self.dir / "dos.musicxml", self.dir / "dos.wav", cancelar)
        self.assertLess(time.monotonic() - t, 5)

    @unittest.skipUnless(lector.audiveris(), "Audiveris no está descargado (Lector o Ajustes)")
    def test_pdf_real_se_lee_con_sus_notas(self):
        """Minueto de Bach impreso (Mutopia): las notas leídas del PDF son las del MIDI de la misma edición."""
        xml = lector.a_musicxml(DATOS / "minueto-bach.pdf", self.dir / "pdf")
        leidas = Counter(suenan(lector.musescore(xml, self.dir / "leida.mid")))
        reales = Counter(suenan(DATOS / "minueto-bach.mid"))
        acierto = sum((leidas & reales).values()) / sum(reales.values())
        self.assertGreater(acierto, 0.95, f"{sum(leidas.values())} notas leídas, {sum(reales.values())} reales")
        self.assertTrue(lector.sonar(xml, "Flauta", self.dir / "flauta").is_file())

    def test_no_escribe_en_el_perfil(self):
        (self.dir / "dos.musicxml").write_text(DOS_PARTES, encoding="utf-8")
        lector.sonar(lector.a_musicxml(self.dir / "dos.musicxml", self.dir / "leida"), "Piano", self.dir)
        if lector.audiveris():
            lector.a_musicxml(DATOS / "minueto-bach.pdf", self.dir / "pdf")
        self.assertEqual(_perfil() - self.perfil, set())


if __name__ == "__main__":
    unittest.main()
