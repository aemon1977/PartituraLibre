"""Ventana principal: barra de navegación y las cuatro secciones."""
import sys
import traceback
from datetime import datetime

from PySide6.QtWidgets import (QApplication, QButtonGroup, QHBoxLayout, QMainWindow, QStackedWidget, QVBoxLayout,
                               QWidget)

from .. import __version__, proyectos, rutas, tareas
from . import tema
from .ajustes import PaginaAjustes
from .letras import PaginaLetras
from .partituras import PaginaPartituras
from .proyectos import PaginaProyectos


class Ventana(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Partitura Libre")
        self.setWindowIcon(tema.icono())
        self.resize(1280, 800)

        self.partituras, self.letras = PaginaPartituras(), PaginaLetras()
        ocupada = lambda: self.partituras.ocupada or self.letras.ocupada
        self.proyectos = PaginaProyectos(ocupada)
        self.ajustes = PaginaAjustes(ocupada, self._cerrar_motores)
        self.pila = QStackedWidget()
        barra = QWidget()
        barra.setObjectName("barra")
        barra.setFixedWidth(238)
        vb = QVBoxLayout(barra)
        vb.setContentsMargins(14, 20, 14, 16)
        vb.setSpacing(6)
        vb.addWidget(tema.etiqueta("♪  Partitura Libre", "marca", False))
        vb.addWidget(tema.etiqueta("Audio → partitura · Voz → texto", "tenue", False))
        vb.addSpacing(18)
        self.grupo = QButtonGroup(self)
        for i, (texto, pagina) in enumerate((("Partituras", self.partituras), ("Letras", self.letras),
                                            ("Grabaciones / Proyectos", self.proyectos), ("Ajustes", self.ajustes))):
            self.pila.addWidget(pagina)
            b = tema.boton(texto, clase="nav")
            b.setCheckable(True)
            self.grupo.addButton(b, i)
            vb.addWidget(b)
        vb.addStretch(1)
        vb.addWidget(tema.etiqueta(f"Versión {__version__}\nTodo se procesa en este equipo.\nSin nube, cuentas ni cuotas.", "tenue"))
        self.grupo.idClicked.connect(self.ir)
        self.grupo.button(0).setChecked(True)

        centro = QWidget()
        h = QHBoxLayout(centro)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)
        h.addWidget(barra)
        h.addWidget(self.pila, 1)
        self.setCentralWidget(centro)

        for p in (self.partituras, self.letras):
            p.cambio.connect(self.proyectos.recargar)
        self.ajustes.cambio.connect(self.letras.recargar_modelos)
        self.ajustes.cambio.connect(self.partituras._botones)
        self.letras.cambio.connect(self.ajustes.recargar)
        self.proyectos.abrir.connect(self._abrir_proyecto)

    def ir(self, i):
        self.grupo.button(i).setChecked(True)
        self.pila.setCurrentIndex(i)
        if i == 2:
            self.proyectos.recargar()

    def _abrir_proyecto(self, carpeta, tipo):
        pagina, i = (self.letras, 1) if tipo == "letra" else (self.partituras, 0)
        if pagina.ocupada:
            return tema.dialogo(self, "Ahora no", "Espera a que termine la grabación o el análisis en curso antes de abrir otro proyecto.", tipo="aviso")
        pagina.abrir_proyecto(carpeta)
        self.ir(i)

    def _cerrar_motores(self):
        self.partituras.captura.cerrar()
        self.letras.cerrar()
        tareas.cancelar_todas()

    def closeEvent(self, ev):
        """Cerrar nunca pierde audio: la toma en curso se guarda; los análisis se cancelan limpiamente."""
        analizando = self.partituras.tarea is not None or self.letras._final is not None
        if analizando and not tema.confirmar(self, "Hay un análisis en curso", "Si cierras ahora se cancelará. El audio "
                                             "original se conserva y podrás repetirlo.", "Cerrar y cancelar"):
            return ev.ignore()
        self._cerrar_motores()
        for carpeta in {self.partituras.proyecto, self.letras.proyecto} - {None}:
            tareas.limpiar_parciales(carpeta)
        ev.accept()


def _registrar_fallo(tipo, valor, traza):
    texto = "".join(traceback.format_exception(tipo, valor, traza))
    try:
        rutas.LOGS.mkdir(parents=True, exist_ok=True)
        with open(rutas.LOGS / "app.log", "a", encoding="utf-8") as f:
            f.write(f"\n--- {datetime.now():%Y-%m-%d %H:%M:%S}\n{texto}")
    except OSError:
        pass
    sys.__stderr__.write(texto)
    if QApplication.instance():
        tema.error(QApplication.activeWindow(), "Error inesperado",
                   f"{tipo.__name__}: {valor}\n\nEl detalle se ha guardado en logs/app.log. Tus grabaciones no se ven afectadas.")


def crear():
    """(aplicación, ventana) listas para mostrarse."""
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("Partitura Libre")
    app.setStyle("Fusion")
    app.setStyleSheet(tema.QSS)
    tema.iniciar_puente()
    sys.excepthook = _registrar_fallo
    return app, Ventana()


def ejecutar():
    rutas.crear_carpetas()
    interrumpidas = proyectos.marcar_interrumpidos()
    app, v = crear()
    v.show()
    if interrumpidas:
        tema.dialogo(v, "Grabación recuperada", f"El programa se cerró mientras grababa. Se ha conservado el audio de "
                     f"{interrumpidas} toma(s) hasta el momento del corte; están en «Grabaciones / Proyectos» marcadas como interrumpidas.", tipo="aviso")
    return app.exec()
