"""El fallo del prototipo anterior: la ventana se abría con un Python que no tenía
sounddevice/soundfile. Aquí se comprueba que eso no puede pasar ni pasar desapercibido."""
import os
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

from partitura_libre import diagnostico, lanzar, rutas


class MismoInterpreteYDependencias(unittest.TestCase):
    def test_el_python_en_uso_es_el_del_paquete(self):
        self.assertTrue(rutas.es_runtime_portable(), sys.executable)
        self.assertEqual(sys.version_info[:2], (3, 11))
        self.assertEqual(rutas.python_portable().resolve(), Path(sys.executable).resolve())

    def test_las_dependencias_de_audio_se_cargan_desde_el_paquete(self):
        import sounddevice
        import soundfile
        for modulo in (sounddevice, soundfile):
            self.assertTrue(rutas.dentro_de(modulo.__file__, rutas.sitio("app")), modulo.__file__)

    def test_los_dos_conjuntos_se_importan_con_el_interprete_portable(self):
        for conjunto in lanzar.CONJUNTOS:
            self.assertTrue(lanzar.instalado(conjunto), conjunto)
            self.assertEqual(lanzar.comprobar(conjunto), "", conjunto)

    def test_una_dependencia_ausente_se_detecta_y_se_nombra(self):
        original = lanzar.CONJUNTOS["app"]
        lanzar.CONJUNTOS["app"] = (["sounddevice", "modulo_que_no_existe"], *original[1:])
        try:
            fallo = lanzar.comprobar("app")
            self.assertIn("modulo_que_no_existe", fallo)
            informe = diagnostico.informe(diagnostico.comprobar(probar_micro=False))
            self.assertRegex(informe, r"\[ERROR\] Paquetes «app»: .*modulo_que_no_existe.*--reparar")
        finally:
            lanzar.CONJUNTOS["app"] = original

    def test_basic_pitch_corre_en_python_3_11_del_paquete_y_no_en_el_del_sistema(self):
        r = subprocess.run([sys.executable, "-s", "-c", "import sys, basic_pitch; print(sys.version_info[:2], sys.executable, basic_pitch.__file__)"],
                           env=rutas.entorno("partituras"), capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr[-400:])
        self.assertIn("(3, 11)", r.stdout)
        self.assertIn(str(rutas.sitio("partituras")), r.stdout)

    @unittest.skipUnless(shutil.which("python3") and not rutas.dentro_de(shutil.which("python3")), "no hay Python del sistema")
    def test_con_el_python_del_sistema_se_niega_a_abrir_y_dice_como_arrancar(self):
        entorno = {**os.environ, "PYTHONPATH": str(rutas.APP)}
        for modulo in ("partitura_libre", "partitura_libre.lanzar"):
            r = subprocess.run([shutil.which("python3"), "-m", modulo], env=entorno, capture_output=True, text=True, timeout=60)
            self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
            self.assertIn("iniciar-", r.stdout)

    def test_el_diagnostico_no_filtra_rutas_personales(self):
        informe = diagnostico.informe(diagnostico.comprobar(probar_micro=False))
        self.assertNotIn(str(Path.home()), informe)
        self.assertNotIn(str(rutas.RAIZ), informe)
        self.assertIn("Runtime portable", informe)


if __name__ == "__main__":
    unittest.main()
