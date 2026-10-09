"""La interfaz real, sin pantalla (QT_QPA_PLATFORM=offscreen): estados de los botones y flujo completo."""
import os
import time
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from partitura_libre import exportar, letras, proyectos
from partitura_libre.ui import tema, ventana
from tests.comun import ESCALA, Aislada, escribir_wav


def esperar(condicion, segundos=240):
    limite = time.monotonic() + segundos
    while not condicion() and time.monotonic() < limite:
        QApplication.processEvents()
        time.sleep(0.02)
    return condicion()


class Interfaz(Aislada):
    def setUp(self):
        super().setUp()
        self.app, self.v = ventana.crear()
        self.v.show()
        self.dialogos = []
        self._dialogo = tema.dialogo
        tema.dialogo = lambda padre, titulo, mensaje, botones=("Aceptar",), tipo="info": (self.dialogos.append((titulo, mensaje)), botones[-1])[1]

    def tearDown(self):
        tema.dialogo = self._dialogo
        self.v._cerrar_motores()
        self.v.deleteLater()
        QApplication.processEvents()
        super().tearDown()

    def test_navegacion_y_botones_bloqueados_al_empezar(self):
        self.assertEqual([b.text() for b in self.v.grupo.buttons()], ["Partituras", "Letras", "Grabaciones / Proyectos", "Ajustes"])
        p, l = self.v.partituras, self.v.letras
        for b in (p.b_transcribir, p.b_cancelar, p.b_regenerar, p.b_midi, p.b_xml, p.b_borrar, p.b_oir,
                  p.captura.b_pausa, p.captura.b_detener, p.captura.b_cancelar,
                  l.b_transcribir, l.b_cancelar, l.b_guardar, l.b_exportar, l.b_copiar):
            self.assertFalse(b.isEnabled(), b.text())
        self.assertTrue(p.b_importar.isEnabled() and l.b_importar.isEnabled())
        for i in range(4):
            self.v.ir(i)
            self.assertEqual(self.v.pila.currentIndex(), i)

    def test_partitura_de_principio_a_fin_con_correccion(self):
        p = self.v.partituras
        d = proyectos.crear("escala gráfica", "partitura")
        proyectos.importar_audio(d, escribir_wav(self.dir / "escala.wav", [(m, 0.5) for m in ESCALA]))
        p.abrir_proyecto(d)
        self.assertTrue(p.b_transcribir.isEnabled())
        self.assertFalse(p.b_regenerar.isEnabled())

        p.transcribir()
        self.assertTrue(p.b_cancelar.isEnabled())
        self.assertFalse(p.b_transcribir.isEnabled())   # no se puede lanzar dos veces
        self.assertFalse(p.b_importar.isEnabled())
        self.assertTrue(esperar(lambda: p.tarea is None), "el análisis no terminó")
        self.assertEqual(self.dialogos, [])
        self.assertEqual([n[2] for n in p.notas], ESCALA)
        self.assertEqual(p.tabla.rowCount(), 8)
        self.assertEqual(p.tabla.item(0, 3).text(), "Do4")
        self.assertFalse(p.b_sube.isEnabled())            # sin nota elegida no hay nada que mover
        from partitura_libre.ui import pentagrama                       # el pentagrama muestra esas mismas notas
        self.assertIsNotNone(pentagrama.fuente_musical(), "no se cargó la fuente de notación incluida")
        self.assertEqual((len(p.vista.notas), p.vista.clave, p.vista.nombres), (8, "sol", True))
        p.clave.setCurrentIndex(p.clave.findData("do3"))
        self.assertEqual(p.vista.clave, "do3")
        p.vista.grab()                                                  # se dibuja sin errores
        from PySide6.QtCore import QPoint                               # al pasar el ratón por una nota se dice qué es
        from PySide6.QtTest import QTest
        from PySide6.QtWidgets import QToolTip
        caja = next(c for c, k in p.vista._cajas if k == 4)
        QTest.mouseMove(p.vista, QPoint(int(caja.center().x()), int(caja.center().y())))
        QApplication.processEvents()
        self.assertTrue(p.nombres.isChecked())                          # y los nombres bajo las notas vienen activados
        self.assertEqual(p.nombres.text(), "Nombre de cada nota")
        p.vista.elegida.emit(5)                                         # clic en una nota del pentagrama
        self.assertEqual(p.tabla.currentRow(), 5)
        self.assertTrue(p.b_regenerar.isEnabled() and p.b_midi.isEnabled() and p.b_xml.isEnabled())

        p.tabla.selectRow(2)
        self.assertTrue(p.b_sube.isEnabled() and p.b_baja.isEnabled() and p.b_borrar.isEnabled())

        # Edición al estilo de un editor de notación: hoja con sistemas y compases, teclado y barra de figuras
        notas_en = lambda: [c for s in p.vista.sistemas for c in s if c["col"]]
        self.assertEqual(len(notas_en()), 8)
        self.assertEqual([c["compas"] for c in notas_en()], [0, 0, 0, 0, 1, 1, 1, 1])             # dos compases de 4/4
        self.assertTrue(p.b_fig["negra"].isChecked() and not p.b_fig["blanca"].isChecked())
        p._atajo("siguiente")
        self.assertEqual(p.tabla.currentRow(), 3)
        p._atajo("arriba"); p._atajo("octava+"); p._atajo("octava-"); p._atajo("abajo")
        self.assertEqual(p.notas[3][2], ESCALA[3])
        p._figura("blanca")
        self.assertAlmostEqual(p.notas[3][1] - p.notas[3][0], 1.0, places=3)                      # una blanca a 120 dura 1 s
        self.assertTrue(p.b_fig["blanca"].isChecked())
        p._figura("negra")
        p.e_letra.setText("la"); p._letra_editada()
        self.assertEqual(p.letra[3], "la")
        p.e_letra.setText(""); p._letra_editada()
        p._atajo("anterior")
        self.assertEqual(p.tabla.currentRow(), 2)
        antes = len(p.vista.sistemas)
        p._zoom(60); p.vista.setFixedWidth(620); QApplication.processEvents()                     # hoja estrecha y ampliada: más sistemas
        self.assertGreater(len(p.vista.sistemas), antes)
        self.assertEqual(sorted(i for c in notas_en() for i in c["col"]), list(range(8)))         # sin perder ni repetir notas
        p._zoom(-60); p.vista.setMaximumWidth(16777215); p.vista.setMinimumWidth(560); QApplication.processEvents()

        # Edición sin MuseScore: deshacer, arrastrar, mover en el tiempo, introducir con clic y PDF propio
        original = [list(n) for n in p.notas]
        p.tabla.selectRow(1)
        p._atajo("arriba"); p._atajo("despues")
        self.assertNotEqual(p.notas, original)
        p._atajo("deshacer"); p._atajo("deshacer")
        self.assertEqual(p.notas, original)
        p._atajo("rehacer")
        self.assertEqual(p.notas[1][2], original[1][2] + 1)
        p._atajo("deshacer")
        p.vista.arrastrada.emit(1, 72, True); p.vista.arrastrada.emit(1, 74, False)               # un arrastre = un solo paso que deshacer
        self.assertEqual(p.notas[1][2], 74)
        p._atajo("deshacer")
        self.assertEqual(p.notas, original)
        p.b_insertar.setChecked(True)
        self.assertTrue(p.vista.insertar)
        p.vista.insertada.emit(7, 76)                                                             # clic tras la última nota, a la altura de Mi5
        self.assertEqual((len(p.notas), p.notas[8][2]), (9, 76))
        self.assertAlmostEqual(p.notas[8][0], original[7][1], places=3)
        p._atajo("deshacer")
        p.b_insertar.setChecked(False)
        self.assertEqual(p.notas, original)
        pdf = self.dir / "partitura ñ.pdf"
        self.assertEqual(p.vista.exportar_pdf(pdf), 1)
        self.assertEqual(pdf.read_bytes()[:5], b"%PDF-")
        self.assertGreater(pdf.stat().st_size, 3000)
        self.assertTrue(p.b_pdf.isEnabled() and p.b_reproducir.isEnabled())
        p.tabla.selectRow(2)
        p._mover(-1)                                    # Mi -> Mi bemol
        p.tabla.item(0, 1).setText("0,25")              # la primera nota, más corta (coma decimal española)
        self.assertEqual(p.notas[2][2], 63)
        self.assertAlmostEqual(p.notas[0][1] - p.notas[0][0], 0.25, places=3)
        p.tabla.item(1, 2).setText("no es un número")   # entrada inválida: no rompe ni cambia la nota
        self.assertEqual(p.notas[1][2], 62)
        p.regenerar()
        self.assertTrue(esperar(lambda: p.tarea is None))
        ficha = proyectos.leer(d)
        self.assertEqual([r["midi"] for r in ficha["resultados"]], ["escala gráfica.mid", "escala gráfica-2.mid"])
        self.assertEqual(p.version["midi"], "escala gráfica-2.mid")
        self.assertEqual(p.notas[2][2], 63)
        self.assertTrue(all((d / r[k]).is_file() for r in ficha["resultados"] for k in ("midi", "musicxml", "notas")))
        self.assertEqual(len(self.v.proyectos.lista), 1)   # el historial se actualiza solo

    def test_partitura_en_vivo_mientras_se_graba_y_definitiva_al_detener(self):
        """Una grabación real salvo por el micrófono: los bloques de una melodía conocida entran por el
        mismo callback que usa PortAudio, y las notas deben ir apareciendo antes de detener."""
        import numpy as np
        from partitura_libre import audio, rutas
        from tests.comun import tono
        p, panel = self.v.partituras, self.v.partituras.captura
        self.assertTrue(p.en_vivo.isChecked())
        melodia = ESCALA * 2
        pcm = (np.concatenate([tono(m, 0.5) for m in melodia]) * 32767).astype(np.int16).reshape(-1, 1)

        panel.proyecto = proyectos.crear("en vivo", "partitura")
        wav = panel.proyecto / "en vivo.wav"
        carpeta_seg = rutas.TEMP / "vivo-prueba"
        carpeta_seg.mkdir(parents=True, exist_ok=True)
        panel.g = audio.Grabadora(wav, None, panel._segmento_s(), carpeta_seg, lambda r, t0: panel.segmento.emit(r, t0))
        self.assertEqual(panel.g.segmento_s, 3)
        panel.g._preparar()
        proyectos.actualizar(panel.proyecto, audio=wav.name, origen="grabación", estado="grabando")
        panel._tic.start()
        panel._botones()                                   # la página ve que empieza una grabación
        self.assertIsNotNone(p.vivo)
        self.assertFalse(p.b_transcribir.isEnabled() or p.b_importar.isEnabled())

        class Estado:
            input_overflow = False
        for i in range(0, len(pcm), 1024):
            panel.g._bloque(pcm[i:i + 1024], len(pcm[i:i + 1024]), None, Estado)
        self.assertTrue(esperar(lambda: len(p.notas) >= 12, 180), f"no aparecieron notas en vivo: {p.notas}")
        self.assertTrue(panel.grabando)                    # las notas llegaron ANTES de detener
        self.assertEqual([n[2] for n in p.notas], melodia[:12])   # dos segmentos de 3 s = 12 notas
        self.assertIn("Borrador en vivo", p.e_estado.text())
        self.assertFalse(p.b_regenerar.isEnabled())        # un borrador no se puede exportar ni editar
        self.assertEqual(list(carpeta_seg.glob("*.wav")), [])     # los segmentos temporales se borran

        panel.detener()                                    # al detener: partitura definitiva de la toma entera
        self.assertIsNone(p.vivo)
        self.assertIsNotNone(p.tarea)
        self.assertTrue(esperar(lambda: p.tarea is None))
        self.assertEqual([n[2] for n in p.notas], melodia)
        self.assertEqual(len(proyectos.leer(p.proyecto)["resultados"]), 1)
        self.assertTrue(p.b_regenerar.isEnabled())

    def test_escribir_una_partitura_a_mano_guardarla_y_reabrirla_sin_musescore(self):
        import xml.etree.ElementTree as ET
        p = self.v.partituras
        p.nombre.setText("escrita a mano")
        p.nueva()
        self.assertTrue(p.b_insertar.isChecked() and p.vista.insertar)
        self.assertFalse(p.b_transcribir.isEnabled() or p.b_regenerar.isEnabled() or p.b_pdf.isEnabled())
        p._figura("blanca")                                   # sin nota elegida: figura de las próximas notas
        tras = -1
        for tono in (60, 64, 67):
            p.vista.insertada.emit(tras, tono)
            tras += 1
        p._atajo("escape")                                     # fuera del modo introducir, la figura cambia la nota elegida
        p.tabla.selectRow(2)
        p._figura("negra")
        p.e_letra.setText("sol"); p._letra_editada()
        self.assertEqual([n[2] for n in p.notas], [60, 64, 67])
        self.assertEqual([round(n[1] - n[0], 2) for n in p.notas], [1.0, 1.0, 0.5])
        self.assertEqual([round(n[0], 2) for n in p.notas], [0.0, 1.0, 2.0])          # cada una empieza donde acaba la anterior
        self.assertEqual(p.vista.exportar_pdf(self.dir / "mano.pdf"), 1)

        p.regenerar()
        self.assertTrue(esperar(lambda: p.tarea is None))
        self.assertEqual(self.dialogos, [])
        xml = ET.parse(p.proyecto / p.version["musicxml"]).getroot()
        self.assertEqual([n.findtext("pitch/step") for n in xml.iter("note") if n.find("pitch") is not None], ["C", "E", "G"])
        self.assertEqual([l.findtext("text") for l in xml.iter("lyric") if l.get("number") == "1"], ["sol"])

        # ese MusicXML se vuelve a abrir como partitura editable (lo que antes exigía MuseScore)
        from partitura_libre import proyectos as pr
        guardado = p.proyecto / p.version["musicxml"]
        d2 = pr.crear("reabierta", "partitura")
        p.abrir_proyecto(d2)
        p._lanzar({"cmd": "importar", "partitura": str(guardado), "carpeta": str(d2), "nombre": d2.name, **p._notacion()}, "…")
        self.assertTrue(esperar(lambda: p.tarea is None))
        self.assertEqual(self.dialogos, [])
        self.assertEqual([n[2] for n in p.notas], [60, 64, 67])
        self.assertEqual([round(n[1] - n[0], 2) for n in p.notas], [1.0, 1.0, 0.5])
        self.assertEqual(p.letra, ["", "", "sol"])

    def test_arrastrar_con_el_raton_es_inmediato_aunque_la_partitura_sea_larga(self):
        """Ratón simulado sobre una partitura de 1200 notas: el arrastre cambia la nota correcta, la tabla
        y la hoja quedan al día, y cada paso cuesta lo mismo que en una partitura corta."""
        from PySide6.QtCore import QPoint, Qt
        from PySide6.QtTest import QTest
        p = self.v.partituras
        p.nueva()
        p.b_insertar.setChecked(False)
        p.clave.setCurrentIndex(p.clave.findData("sol"))
        p._poner_notas([[i * 0.5, i * 0.5 + 0.5, 60, 0.7] for i in range(1200)], 120)   # todo Do4
        QApplication.processEvents()
        i = 5
        caja = next(c for c, k in p.vista._cajas if k == i)
        origen = QPoint(int(caja.center().x()), int(caja.center().y()))
        QTest.mousePress(p.vista, Qt.LeftButton, Qt.NoModifier, origen)
        self.assertEqual(p.tabla.currentRow(), i)
        tiempos = []
        for paso in range(1, 9):                       # ocho pasos hacia arriba: medio espacio cada uno
            t = time.perf_counter()
            QTest.mouseMove(p.vista, origen - QPoint(0, paso * 5))
            QApplication.processEvents()               # incluye el repintado
            tiempos.append(time.perf_counter() - t)
        self.assertEqual(p.notas[i][2], 74)            # Do4 + 8 posiciones = Re5
        self.assertEqual(p.tabla.item(i, 2).text(), "74")
        self.assertEqual(p.tabla.item(i, 3).text(), "Re5")
        self.assertEqual([n[2] for k, n in enumerate(p.notas) if k != i], [60] * 1199)   # las demás, intactas
        QTest.mouseRelease(p.vista, Qt.LeftButton, Qt.NoModifier, origen - QPoint(0, 40))
        nueva_caja = next(c for c, k in p.vista._cajas if k == i)
        self.assertLess(nueva_caja.center().y(), caja.center().y() - 30)                  # la zona sensible sigue a la nota
        self.assertLess(sorted(tiempos)[len(tiempos) // 2], 0.02, f"arrastre lento: {tiempos}")
        p._atajo("deshacer")                            # todo el arrastre es un solo paso
        self.assertEqual(p.notas[i][2], 60)

        t = time.perf_counter()                         # añadir y borrar tampoco rehacen toda la tabla
        p.tabla.selectRow(600); p._anadir(); p._borrar()
        self.assertEqual(len(p.notas), 1200)
        self.assertEqual(p.tabla.rowCount(), 1200)
        self.assertLess(time.perf_counter() - t, 0.5)

    def test_nivel_bajo_se_avisa_en_directo_y_el_dialogo_solo_una_vez(self):
        import numpy as np
        from partitura_libre import audio
        from partitura_libre.ui.captura import PanelCaptura
        panel = self.v.partituras.captura
        PanelCaptura._avisado_flojo = False

        class Estado:
            input_overflow = False

        def toma(amplitud, nombre):
            panel.proyecto = proyectos.crear(nombre, "partitura")
            panel.g = audio.Grabadora(panel.proyecto / f"{nombre}.wav")
            panel.g._preparar()
            panel._decir("Grabando…", "aviso")                # lo que pone «Grabar» al empezar
            bloque = (np.sin(np.arange(4410) / 10) * amplitud * 32767).astype(np.int16).reshape(-1, 1)
            for _ in range(30):                               # 3 s de señal
                panel.g._bloque(bloque, len(bloque), None, Estado)
            esperar(lambda: panel.g.frames >= 30 * 4410, 5)
            panel._refrescar()
            en_directo = (panel.texto.text(), panel.nivel.property("clase"))
            panel.detener()
            return en_directo

        texto, barra = toma(0.04, "floja")                    # como un micrófono que llega al 4 %
        self.assertIn("Nivel muy bajo (pico del 4 %)", texto)
        self.assertEqual(barra, "bajo")
        self.assertEqual([t for t, _ in self.dialogos], ["Nivel de grabación muy bajo"])
        self.assertIn("nivel muy bajo", panel.texto.text())
        toma(0.04, "floja otra vez")
        self.assertEqual(len(self.dialogos), 1)               # la segunda vez no interrumpe
        self.assertIn("nivel muy bajo", panel.texto.text())   # pero lo sigue diciendo
        texto, barra = toma(0.5, "normal")
        self.assertNotIn("bajo", texto)
        self.assertEqual(barra, "")
        self.assertEqual(len(self.dialogos), 1)
        self.v.partituras._auto = False

    def test_escribir_con_el_teclado_como_en_musescore(self):
        """N, cifras de figura, letras de nota, silencio, puntillo, acorde, letra con Ctrl+L y Esc, tecleados sobre la hoja."""
        from PySide6.QtCore import Qt
        from PySide6.QtTest import QTest
        p = self.v.partituras
        p.nueva()
        p.b_insertar.setChecked(False)
        p.clave.setCurrentIndex(p.clave.findData("sol"))
        p.vista.setFocus()
        teclear = lambda tecla, mod=Qt.NoModifier: (QTest.keyClick(p.vista, tecla, mod), QApplication.processEvents())

        teclear(Qt.Key_N)                                   # entrar en el modo de introducción
        self.assertTrue(p.b_insertar.isChecked() and p.vista.insertar)
        teclear(Qt.Key_5)                                   # negra
        for t in (Qt.Key_C, Qt.Key_D, Qt.Key_E):            # Do Re Mi
            teclear(t)
        self.assertEqual([n[2] % 12 for n in p.notas], [0, 2, 4])
        self.assertEqual([round(n[0], 2) for n in p.notas], [0.0, 0.5, 1.0])          # una tras otra, sin huecos
        teclear(Qt.Key_0)                                   # silencio de negra
        teclear(Qt.Key_6)                                   # blanca
        teclear(Qt.Key_G)
        self.assertEqual((round(p.notas[3][0], 2), round(p.notas[3][1] - p.notas[3][0], 2)), (2.0, 1.0))   # tras el silencio, blanca
        teclear(Qt.Key_B, Qt.ShiftModifier)                 # Mayús+letra: nota añadida al acorde
        self.assertEqual(len(p.notas), 5)
        self.assertEqual((p.notas[4][0], p.notas[4][1]), (p.notas[3][0], p.notas[3][1]))
        self.assertEqual(p.notas[4][2] % 12, 11)
        self.assertEqual(len([c for s in p.vista.sistemas for c in s if c["silencio"]]), 1)   # el silencio se ve en la hoja
        self.assertEqual(len([c for s in p.vista.sistemas for c in s if len(c["col"]) == 2]), 1)   # y el acorde

        teclear(Qt.Key_Escape)                              # salir del modo
        self.assertFalse(p.b_insertar.isChecked())
        p.tabla.selectRow(0)
        teclear(Qt.Key_Period)                              # puntillo a la primera negra
        self.assertAlmostEqual(p.notas[0][1] - p.notas[0][0], 0.75, places=3)
        self.assertTrue(p.b_puntillo.isChecked())
        teclear(Qt.Key_Period)
        self.assertAlmostEqual(p.notas[0][1] - p.notas[0][0], 0.5, places=3)
        teclear(Qt.Key_A)                                   # fuera del modo, la letra cambia la nota elegida
        self.assertEqual((len(p.notas), p.notas[0][2] % 12), (5, 9))
        teclear(Qt.Key_Z, Qt.ControlModifier)
        self.assertEqual(p.notas[0][2] % 12, 0)
        teclear(Qt.Key_C, Qt.ControlModifier)               # Ctrl+C no escribe un Do
        self.assertEqual(len(p.notas), 5)

        teclear(Qt.Key_L, Qt.ControlModifier)               # letra: espacio pasa a la nota siguiente
        self.assertTrue(p.e_letra.hasFocus())
        QTest.keyClicks(p.e_letra, "can"); QTest.keyClick(p.e_letra, Qt.Key_Minus)
        QTest.keyClicks(p.e_letra, "ta"); QTest.keyClick(p.e_letra, Qt.Key_Space)
        QTest.keyClicks(p.e_letra, "re"); QTest.keyClick(p.e_letra, Qt.Key_Escape)
        self.assertEqual(p.letra[:3], ["can", "ta", "re"])
        self.assertTrue(p.vista.hasFocus())

        p.tabla.selectRow(0)                                # introducir en medio desplaza lo que sigue, no lo pisa
        teclear(Qt.Key_N); teclear(Qt.Key_5); teclear(Qt.Key_F)
        self.assertEqual(len(p.notas), 6)
        inicios = sorted(round(n[0], 2) for n in p.notas)
        self.assertEqual(inicios, [0.0, 0.5, 1.0, 1.5, 2.5, 2.5])
        self.assertEqual(p.letra[2:4], ["ta", "re"])        # cada palabra sigue con su nota

    def test_con_audio_sonando_se_ofrece_grabar_el_sonido_del_equipo_en_vez_del_microfono(self):
        from partitura_libre import audio
        from partitura_libre.ui.captura import PanelCaptura
        panel = self.v.letras.captura
        if panel._indice_sistema() < 0 or panel.micro.count() < 2:
            self.skipTest("este equipo no ofrece la entrada «Sonido del equipo» junto a un micrófono")
        original = audio.suena_algo
        self.addCleanup(setattr, audio, "suena_algo", original)
        PanelCaptura._prefiere_micro = False
        respuesta = [""]
        tema.dialogo = lambda padre, titulo, mensaje, botones=("Aceptar",), tipo="info": (self.dialogos.append((titulo, botones)), respuesta[0])[1]

        panel.micro.setCurrentIndex(0)                  # un micrófono
        audio.suena_algo = lambda: False
        self.assertTrue(panel._ofrecer_sistema())       # no suena nada: no se pregunta
        self.assertEqual(self.dialogos, [])

        audio.suena_algo = lambda: True                 # suena un vídeo y se va a grabar con el micrófono
        respuesta[0] = "Grabar el sonido del equipo"
        self.assertTrue(panel._ofrecer_sistema())
        self.assertEqual(self.dialogos[-1][0], "Está sonando audio en este equipo")
        self.assertTrue(panel._es_sistema())            # la entrada cambia sola
        self.assertTrue(panel._ofrecer_sistema())       # ya es la correcta: no vuelve a preguntar
        self.assertEqual(len(self.dialogos), 1)

        panel.micro.setCurrentIndex(0)
        respuesta[0] = ""                               # cerrar el diálogo cancela la grabación
        self.assertFalse(panel._ofrecer_sistema())
        respuesta[0] = "Seguir con el micrófono"        # decisión respetada y recordada en la sesión
        self.assertTrue(panel._ofrecer_sistema())
        self.assertFalse(panel._es_sistema())
        self.assertTrue(panel._ofrecer_sistema())
        self.assertEqual(len(self.dialogos), 3)
        PanelCaptura._prefiere_micro = False

    def test_fallo_del_analisis_se_explica_y_conserva_el_audio(self):
        p = self.v.partituras
        d = proyectos.crear("rota", "partitura")
        falso = self.dir / "rota.wav"
        falso.write_text("no es audio")
        copia = proyectos.importar_audio(d, falso)
        p.abrir_proyecto(d)
        p.transcribir()
        self.assertTrue(esperar(lambda: p.tarea is None))
        self.assertEqual(len(self.dialogos), 1)
        self.assertIn("audio original se conserva", self.dialogos[0][1])
        self.assertTrue(copia.exists())
        self.assertEqual(proyectos.leer(d)["resultados"], [])
        self.assertTrue(p.b_transcribir.isEnabled())       # se puede reintentar

    def test_cancelar_analisis_deja_la_interfaz_lista(self):
        p = self.v.partituras
        d = proyectos.crear("cancelable", "partitura")
        proyectos.importar_audio(d, escribir_wav(self.dir / "c.wav", [(m, 0.5) for m in ESCALA] * 3))
        p.abrir_proyecto(d)
        p.transcribir()
        esperar(lambda: False, 1.0)
        p.cancelar()
        self.assertTrue(esperar(lambda: p.tarea is None, 15))
        self.assertIn("cancelado", p.e_estado.text())
        self.assertEqual(proyectos.leer(d)["resultados"], [])
        self.assertEqual(list(d.glob("*.parcial")), [])
        self.assertTrue(p.b_transcribir.isEnabled())

    @unittest.skipUnless(any(letras.instalado(m) for m in letras.MODELOS), "sin modelo de voz descargado")
    def test_letra_de_principio_a_fin(self):
        from tests.test_letras_flujo import DATOS
        l = self.v.letras
        l.modelo.setCurrentIndex(l.modelo.findData(next(m for m in ("tiny", "base", "small") if letras.instalado(m))))
        l.idioma.setCurrentIndex(l.idioma.findData(""))
        d = proyectos.crear("lectura", "letra")
        proyectos.importar_audio(d, DATOS / "voz-es.flac")
        l.abrir_proyecto(d)
        self.assertTrue(l.b_transcribir.isEnabled())
        l.transcribir()
        self.assertTrue(l.texto.isReadOnly() and l.b_cancelar.isEnabled())
        self.assertTrue(esperar(lambda: l._final is None), "la transcripción no terminó")
        self.assertEqual(self.dialogos, [])
        self.assertIn("wikipedia", l.texto.toPlainText().lower())
        self.assertRegex(l.texto.toPlainText(), r"^\[00:00\.\d\d\] ")       # marcas de tiempo visibles
        ficha = proyectos.leer(d)
        self.assertEqual(ficha["resultados"][0]["tipo"], "letra")           # guardada y asociada al audio
        self.assertTrue((d / ficha["resultados"][0]["texto"]).read_text(encoding="utf-8").strip())

        l.marcas.setChecked(False)                                          # sin marcas: mismo texto, tiempos intactos
        self.assertNotIn("[00:", l.texto.toPlainText())
        l.texto.setPlainText(l.texto.toPlainText().replace("\n", " ✎\n", 1))  # corrección manual
        l.guardar()
        guardado = (d / ficha["resultados"][0]["texto"]).read_text(encoding="utf-8")
        self.assertIn("✎", guardado)
        self.assertEqual(len(proyectos.leer(d)["resultados"]), 1)           # guardar actualiza, no duplica
        self.assertTrue(all(s["inicio"] is not None for s in l.segs))
        self.assertEqual(len(exportar.leer(exportar.vtt(l.segs))), len(l.segs))

        self.v.letras.proyecto = None                                        # reabrir desde el historial
        self.v._abrir_proyecto(d, "letra")
        self.assertEqual(self.v.pila.currentIndex(), 1)
        self.assertIn("✎", l.texto.toPlainText())

    @unittest.skipUnless(any(letras.instalado(m) for m in letras.MODELOS), "sin modelo de voz descargado")
    def test_partitura_con_letra_de_una_sola_toma(self):
        """Una voz real (lectura libre en español) mezclada con una melodía: de un único audio deben salir
        las notas y, bajo ellas, las palabras; y la letra se puede corregir y vuelve a escribirse."""
        import xml.etree.ElementTree as ET
        import numpy as np
        import soundfile as sf
        from partitura_libre import config
        from tests.comun import tono
        from tests.test_letras_flujo import DATOS
        voz, sr = sf.read(DATOS / "voz-es.flac", dtype="float32")
        melodia = np.concatenate([tono(m, 0.5, sr) for m in (ESCALA * 7)])[:len(voz)] * 0.12
        mezcla = self.dir / "canción.wav"
        sf.write(mezcla, voz[:len(melodia)] + melodia.astype("float32"), sr, subtype="PCM_16")
        a = config.cargar()
        a["modelo"], a["idioma"] = next(m for m in ("small", "base", "tiny") if letras.instalado(m)), "es"
        config.guardar(a)

        p = self.v.partituras
        d = proyectos.crear("canción con letra", "partitura")
        proyectos.importar_audio(d, mezcla)
        p.abrir_proyecto(d)
        self.assertTrue(p.con_letra.isEnabled())
        p.con_letra.setChecked(True)
        p.transcribir()
        self.assertIn("Paso 1 de 2", p.e_estado.text())
        self.assertTrue(p.b_cancelar.isEnabled() and not p.b_transcribir.isEnabled())
        self.assertTrue(esperar(lambda: p.tarea is None and p.version is not None, 300), p.e_estado.text())
        self.assertEqual(self.dialogos, [])

        cantado = " ".join(t for t in p.letra if t).lower()
        self.assertGreater(len(p.notas), 10)
        self.assertEqual(len(p.letra), len(p.notas))
        self.assertIn("wikipedia", cantado)                                   # las palabras están bajo las notas
        self.assertIn("con letra", p.e_estado.text())
        con_texto = [i for i, t in enumerate(p.letra) if t]
        self.assertEqual(p.tabla.item(con_texto[0], 4).text(), p.letra[con_texto[0]])
        tipos = [r["tipo"] for r in proyectos.leer(d)["resultados"]]
        self.assertEqual(sorted(tipos), ["letra", "partitura"])               # un proyecto, los dos resultados
        letra_xml = lambda v: " ".join(l.findtext("text") or "" for l in ET.parse(d / v["musicxml"]).getroot().iter("lyric")).lower()
        self.assertIn("wikipedia", letra_xml(p.version))                      # y llegan al MusicXML
        p.vista.grab()

        i = con_texto[0]
        p.tabla.item(i, 4).setText("corregida")                               # corrección manual de una palabra
        self.assertEqual(p.letra[i], "corregida")
        p.regenerar()
        self.assertTrue(esperar(lambda: p.tarea is None))
        self.assertEqual(p.letra[i], "corregida")
        self.assertIn("corregida", letra_xml(p.version))
        self.v._abrir_proyecto(d, "letra")                                    # el texto completo se abre en Letras
        self.assertIn("wikipedia", self.v.letras.texto.toPlainText().lower())

    def test_ajustes_diagnostico_y_contenido(self):
        a = self.v.ajustes
        a._diagnosticar()
        self.assertTrue(esperar(lambda: a.b_diag.isEnabled(), 60))
        self.assertIn("Runtime portable", a.t_diag.toPlainText())
        a._medir()
        self.assertTrue(esperar(lambda: "TOTAL" in a.e_contenido.text(), 60))
        self.assertIn("runtime/", a.e_contenido.text())


if __name__ == "__main__":
    unittest.main()
