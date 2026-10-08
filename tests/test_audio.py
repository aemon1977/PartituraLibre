import errno
import time
import unittest

import numpy as np
import soundfile as sf

from partitura_libre import audio
from tests.comun import Aislada

SR = 44100
BLOQUE = 1024


class SinDesborde:
    input_overflow = False


class ConDesborde:
    input_overflow = True


def bloques(segundos, semilla=1):
    """Ruido determinista en int16, como lo entrega PortAudio: (n, 1)."""
    rng = np.random.default_rng(semilla)
    total = int(segundos * SR) // BLOQUE
    return [rng.integers(-20000, 20000, (BLOQUE, 1), dtype=np.int16) for _ in range(total)]


class Wav(Aislada):
    def test_el_archivo_es_valido_antes_de_cerrarse(self):
        """Simula un cierre brusco: lo escrito hasta la última actualización de cabecera se puede leer."""
        w = audio.EscritorWav(self.dir / "toma.wav", SR)
        datos = bloques(0.5)
        for b in datos:
            w.escribir(b.tobytes())
        w._t = 0  # fuerza la actualización periódica de cabecera en la siguiente escritura
        w.escribir(datos[0].tobytes())
        leido, sr = sf.read(self.dir / "toma.wav", dtype="int16")  # sin llamar a cerrar()
        self.assertEqual(sr, SR)
        self.assertEqual(len(leido), (len(datos) + 1) * BLOQUE)
        w.cerrar()

    def test_limite_del_formato_se_avisa_sin_corromper(self):
        w = audio.EscritorWav(self.dir / "toma.wav", SR)
        w.LIMITE = 3000
        w.escribir(b"\0" * 2048)
        with self.assertRaises(audio.ErrorAudio):
            w.escribir(b"\0" * 2048)
        w.cerrar()
        self.assertEqual(sf.info(self.dir / "toma.wav").frames, 1024)


class Captura(Aislada):
    def grabadora(self, **kw):
        g = audio.Grabadora(self.dir / "toma ñ.wav", **kw)
        g.sr = SR
        g._preparar()
        return g

    def test_señal_sintetica_se_guarda_identica_sin_perder_bloques(self):
        g = self.grabadora()
        datos = bloques(3)
        for b in datos:
            g._bloque(b, BLOQUE, None, SinDesborde)
        self.assertTrue(0.55 < g.nivel <= 1.0)  # el medidor refleja el pico del último bloque
        g.detener()
        leido, sr = sf.read(g.destino, dtype="int16")
        np.testing.assert_array_equal(leido, np.concatenate(datos)[:, 0])
        self.assertEqual(sr, SR)
        self.assertAlmostEqual(g.segundos, len(datos) * BLOQUE / SR, places=6)
        self.assertEqual(g.destino.stat().st_size, 44 + len(datos) * BLOQUE * 2)
        self.assertFalse(g.incompleta)

    def test_en_pausa_no_se_graba_y_al_reanudar_continua(self):
        g = self.grabadora()
        a, b, c = bloques(0.3, 1), bloques(0.3, 2), bloques(0.3, 3)
        for x in a:
            g._bloque(x, BLOQUE, None, SinDesborde)
        g.pausar(True)
        for x in b:
            g._bloque(x, BLOQUE, None, SinDesborde)
        g.pausar(False)
        for x in c:
            g._bloque(x, BLOQUE, None, SinDesborde)
        g.detener()
        leido, _ = sf.read(g.destino, dtype="int16")
        np.testing.assert_array_equal(leido, np.concatenate(a + c)[:, 0])

    def test_si_el_disco_no_da_abasto_se_notifica_y_queda_incompleta(self):
        g = self.grabadora()
        g._cola.maxsize = 5
        original = g._wav.escribir
        g._wav.escribir = lambda d: (time.sleep(0.05), original(d))
        for b in bloques(1):
            g._bloque(b, BLOQUE, None, SinDesborde)
        g.detener()
        self.assertGreater(g.perdidos, 0)
        self.assertTrue(g.incompleta)
        self.assertTrue(any("perdieron" in a for a in g.avisos()))
        self.assertEqual(sf.info(g.destino).frames, g.frames)  # lo que sí llegó está bien guardado

    def test_desbordamiento_del_sistema_de_audio_se_cuenta(self):
        g = self.grabadora()
        datos = bloques(0.2)
        g._bloque(datos[0], BLOQUE, None, ConDesborde)
        g._bloque(datos[1], BLOQUE, None, SinDesborde)
        g.detener()
        self.assertEqual(g.desbordes, 1)
        self.assertTrue(g.incompleta)
        self.assertEqual(sf.info(g.destino).frames, 2 * BLOQUE)  # el audio recibido no se descarta

    def test_disco_lleno_conserva_lo_grabado_y_explica_el_fallo(self):
        g = self.grabadora()
        datos = bloques(0.5)
        original, n = g._wav.escribir, [0]

        def escribir(d):
            n[0] += 1
            if n[0] > 10:
                raise OSError(errno.ENOSPC, "No space left on device")
            original(d)
        g._wav.escribir = escribir
        for b in datos:
            g._bloque(b, BLOQUE, None, SinDesborde)
        time.sleep(0.3)
        self.assertIn("disco", g.error.lower())
        g.detener()
        self.assertTrue(g.incompleta)
        leido, _ = sf.read(g.destino, dtype="int16")
        np.testing.assert_array_equal(leido, np.concatenate(datos[:10])[:, 0])

    def test_cancelar_borra_la_toma(self):
        g = self.grabadora()
        g._bloque(bloques(0.1)[0], BLOQUE, None, SinDesborde)
        g.cancelar()
        self.assertFalse(g.destino.exists())

    def test_segmentos_en_vivo_son_contiguos_y_cubren_la_toma(self):
        recibidos = []
        g = self.grabadora(segmento_s=1, carpeta_segmentos=self.dir, al_segmento=lambda r, t0: recibidos.append((r, t0)))
        datos = bloques(3.5)
        for b in datos:
            g._bloque(b, BLOQUE, None, SinDesborde)
        g.detener()
        self.assertEqual(len(recibidos), 3)
        partes, esperado = [], 0.0
        for ruta, t0 in recibidos:
            x, _ = sf.read(ruta, dtype="int16")
            self.assertAlmostEqual(t0, esperado, places=6)
            esperado += len(x) / SR
            partes.append(x)
        todo, _ = sf.read(g.destino, dtype="int16")
        unidas = np.concatenate(partes)
        np.testing.assert_array_equal(unidas, todo[:len(unidas)])

    def test_sesion_larga_simulada_sin_perdidas_ni_limite(self):
        """40 minutos de audio pasan por la misma cola y el mismo escritor que una grabación real."""
        g = self.grabadora()
        bloque = bloques(0.1)[0]
        n = int(40 * 60 * SR / BLOQUE)
        t0 = time.monotonic()
        for i in range(n):
            if i % 256 == 0:
                while g._cola.qsize() > g.COLA // 2:  # el micrófono real nunca va más rápido que el reloj
                    time.sleep(0.001)
            g._bloque(bloque, BLOQUE, None, SinDesborde)
        g.detener()
        info = sf.info(g.destino)
        self.assertEqual(info.frames, n * BLOQUE)
        self.assertAlmostEqual(info.duration, 40 * 60, delta=0.1)
        self.assertEqual((g.perdidos, g.desbordes, g.error), (0, 0, ""))
        self.assertLess(time.monotonic() - t0, 120)


class Dispositivos(unittest.TestCase):
    def test_enumerar_microfonos_no_falla_y_tiene_formato(self):
        try:
            micros = audio.microfonos()
        except audio.ErrorAudio as e:
            self.skipTest(f"sin sistema de audio: {e}")
        for m in micros:
            self.assertEqual(set(m), {"indice", "nombre", "sr", "predeterminado", "fuente"})
        self.assertLessEqual(sum(m["predeterminado"] for m in micros), 1)


if __name__ == "__main__":
    unittest.main()
