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
        self.assertTrue(p.b_regenerar.isEnabled() and p.b_midi.isEnabled() and p.b_xml.isEnabled())

        self.assertFalse(p.b_sube.isEnabled())            # sin nota elegida no hay nada que mover
        p.tabla.selectRow(2)
        self.assertTrue(p.b_sube.isEnabled() and p.b_baja.isEnabled() and p.b_borrar.isEnabled())
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
