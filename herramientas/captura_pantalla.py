"""Genera docs/vista-previa-*.png con un ejemplo real (melodía sintética y audio libre de tests/datos),
sin mostrar ventanas. Solo desarrollo:  ./herramientas/probar.sh no hace falta; ejecutar con
    QT_QPA_PLATFORM=offscreen <python portable> herramientas/captura_pantalla.py   (desde la raíz, con el entorno «app»)
"""
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtWidgets import QApplication

from partitura_libre import config, letras, proyectos, rutas
from partitura_libre.ui import ventana
from tests.comun import escribir_wav

demo = rutas.TEMP / "demo-capturas"
shutil.rmtree(demo, ignore_errors=True)
demo.mkdir(parents=True)
rutas.PROYECTOS, config.ARCHIVO = demo / "proyectos", demo / "ajustes.json"   # no toca los datos reales
rutas.PROYECTOS.mkdir()

app, v = ventana.crear()
v.resize(1320, 860)
v.show()
print("tamaño mínimo:", v.minimumSizeHint().width(), "x", v.minimumSizeHint().height())


def esperar(condicion, segundos=240):
    limite = time.monotonic() + segundos
    while not condicion() and time.monotonic() < limite:
        QApplication.processEvents()
        time.sleep(0.02)


def capturar(i, nombre):
    v.ir(i)
    esperar(lambda: False, 0.4)
    v.grab().save(str(rutas.RAIZ / "docs" / f"vista-previa-{nombre}.png"))


himno = [(64, .4), (64, .4), (65, .4), (67, .4), (67, .4), (65, .4), (64, .4), (62, .4), (60, .4), (60, .4), (62, .4), (64, .4), (64, .6), (62, .2), (62, .8)]
d = proyectos.crear("Himno de la alegría", "partitura")
proyectos.importar_audio(d, escribir_wav(demo / "himno.wav", himno))
v.partituras.abrir_proyecto(d)
v.partituras.transcribir()
esperar(lambda: v.partituras.tarea is None)
v.partituras.tabla.selectRow(3)
capturar(0, "partituras")

modelo = next((m for m in ("small", "base", "tiny") if letras.instalado(m)), None)
if modelo:
    d = proyectos.crear("Lectura de prueba", "letra")
    proyectos.importar_audio(d, rutas.RAIZ / "tests" / "datos" / "voz-es.flac")
    v.letras.modelo.setCurrentIndex(v.letras.modelo.findData(modelo))
    v.letras.abrir_proyecto(d)
    v.letras.transcribir()
    esperar(lambda: v.letras._final is None)
capturar(1, "letras")
capturar(2, "proyectos")
v.ajustes._diagnosticar()
esperar(lambda: v.ajustes.b_diag.isEnabled(), 60)
capturar(3, "ajustes")
v._cerrar_motores()
shutil.rmtree(demo, ignore_errors=True)
