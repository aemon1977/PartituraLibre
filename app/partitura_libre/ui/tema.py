"""Estilo de la aplicación (azul marino + turquesa) y piezas de interfaz compartidas."""
import threading

from PySide6.QtCore import QObject, QPoint, Qt, QUrl, Signal, Slot
from PySide6.QtGui import QColor, QDesktopServices, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (QDialog, QFileDialog, QFrame, QHBoxLayout, QLabel, QProgressBar, QPushButton,
                               QScrollArea, QVBoxLayout, QWidget)

from .. import descargas, rutas

FONDO, PANEL, TARJETA, BORDE = "#0b1626", "#0e1b2e", "#13233a", "#223b5c"
TEXTO, TENUE, ACENTO, PELIGRO, AVISO = "#e6edf5", "#93a7bd", "#2dd4bf", "#f87171", "#fbbf24"

QSS = f"""
* {{ font-size: 14px; color: {TEXTO}; }}
QMainWindow, QDialog, QWidget#pagina, QScrollArea, QScrollArea > QWidget > QWidget {{ background: {FONDO}; }}
QWidget#barra {{ background: {PANEL}; border-bottom: 1px solid {BORDE}; }}
QFrame#herramientas {{ background: {PANEL}; border-bottom: 1px solid {BORDE}; }}
QFrame#herramientas QPushButton {{ padding: 6px 11px; }}
QPushButton[clase="figura"]:checked {{ background: #17413f; border-color: {ACENTO}; color: {ACENTO}; }}
QPushButton:checked {{ background: #17304b; border-color: {ACENTO}; color: {ACENTO}; }}
QFrame#tarjeta {{ background: {TARJETA}; border: 1px solid {BORDE}; border-radius: 10px; }}
QLabel {{ background: transparent; }}
QLabel[clase="titulo"] {{ font-size: 22px; font-weight: 700; }}
QLabel[clase="seccion"] {{ font-size: 15px; font-weight: 600; color: {ACENTO}; }}
QLabel[clase="tenue"] {{ color: {TENUE}; font-size: 13px; }}
QLabel[clase="aviso"] {{ color: {AVISO}; font-size: 13px; }}
QLabel[clase="error"] {{ color: {PELIGRO}; }}
QLabel[clase="reloj"] {{ font-size: 26px; font-weight: 600; font-family: monospace; }}
QLabel[clase="marca"] {{ font-size: 18px; font-weight: 700; color: {ACENTO}; }}
QPushButton {{ background: #1b3250; border: 1px solid {BORDE}; border-radius: 7px; padding: 7px 14px; }}
QPushButton:hover {{ background: #24426a; border-color: {ACENTO}; }}
QPushButton:pressed {{ background: #16283f; }}
QPushButton:disabled {{ background: #101d30; color: #55677c; border-color: #1a2b43; }}
QPushButton[clase="primario"] {{ background: {ACENTO}; color: #06231f; border: none; font-weight: 600; }}
QPushButton[clase="primario"]:hover {{ background: #5eead4; }}
QPushButton[clase="primario"]:disabled {{ background: #17413f; color: #5b8a85; }}
QPushButton[clase="peligro"] {{ background: #3a1c24; border-color: #7f2f3a; color: #fecaca; }}
QPushButton[clase="peligro"]:hover {{ background: #55232e; border-color: {PELIGRO}; }}
QPushButton[clase="peligro"]:disabled {{ background: #1a1820; color: #6b5560; border-color: #2a2029; }}
QPushButton[clase="nav"] {{ background: transparent; border: none; border-bottom: 3px solid transparent; border-radius: 0; padding: 14px 18px 11px 18px; font-size: 15px; color: {TENUE}; }}
QPushButton[clase="nav"]:hover {{ background: #152841; color: {TEXTO}; }}
QPushButton[clase="nav"]:checked {{ background: transparent; color: {ACENTO}; font-weight: 600; border-bottom: 3px solid {ACENTO}; }}
QLineEdit, QComboBox, QSpinBox, QPlainTextEdit, QTableWidget {{ background: #0c1929; border: 1px solid {BORDE}; border-radius: 7px; padding: 6px 8px; selection-background-color: #1f6f69; selection-color: white; }}
QLineEdit:focus, QComboBox:focus, QPlainTextEdit:focus, QSpinBox:focus {{ border-color: {ACENTO}; }}
QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled {{ color: #55677c; }}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox QAbstractItemView {{ background: {TARJETA}; border: 1px solid {BORDE}; selection-background-color: #1f6f69; }}
QPlainTextEdit {{ font-size: 15px; }}
QTableWidget {{ gridline-color: #1a2f4b; padding: 0; alternate-background-color: #0f2034; }}
QHeaderView::section {{ background: #162b45; color: {TENUE}; border: none; border-bottom: 1px solid {BORDE}; padding: 6px; font-weight: 600; }}
QTableCornerButton::section {{ background: #162b45; border: none; }}
QProgressBar {{ background: #0c1929; border: 1px solid {BORDE}; border-radius: 6px; height: 12px; text-align: center; font-size: 11px; }}
QProgressBar::chunk {{ background: {ACENTO}; border-radius: 5px; }}
QProgressBar[clase="alto"]::chunk {{ background: {PELIGRO}; }}
QProgressBar[clase="bajo"]::chunk {{ background: {AVISO}; }}
QCheckBox, QRadioButton {{ spacing: 8px; background: transparent; }}
QCheckBox::indicator, QRadioButton::indicator {{ width: 16px; height: 16px; border: 1px solid {TENUE}; background: #0c1929; }}
QCheckBox::indicator {{ border-radius: 4px; }} QRadioButton::indicator {{ border-radius: 9px; }}
QCheckBox::indicator:checked, QRadioButton::indicator:checked {{ background: {ACENTO}; border-color: {ACENTO}; }}
QScrollBar:vertical {{ background: transparent; width: 11px; }} QScrollBar:horizontal {{ background: transparent; height: 11px; }}
QScrollBar::handle {{ background: #2a476c; border-radius: 5px; min-height: 30px; min-width: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QToolTip {{ background: {TARJETA}; color: {TEXTO}; border: 1px solid {ACENTO}; padding: 4px; }}
"""


class _Puente(QObject):
    """Lleva llamadas desde hilos auxiliares al hilo de la interfaz."""
    llamar = Signal(object)

    def __init__(self):
        super().__init__()
        self.llamar.connect(self._ejecutar)

    @Slot(object)
    def _ejecutar(self, f):
        f()


_puente = None


def iniciar_puente():
    global _puente
    _puente = _Puente()


def en_ui(f):
    _puente.llamar.emit(f)


def en_hilo(trabajo, al_acabar):
    """Ejecuta `trabajo()` fuera de la interfaz y entrega (resultado, excepción) en ella."""
    def correr():
        try:
            r, e = trabajo(), None
        except Exception as ex:
            r, e = None, ex
        en_ui(lambda: al_acabar(r, e))
    threading.Thread(target=correr, daemon=True).start()


def icono():
    p = QPixmap(128, 128)
    p.fill(Qt.transparent)
    g = QPainter(p)
    g.setRenderHint(QPainter.Antialiasing)
    g.setBrush(QColor(FONDO)); g.setPen(QColor(ACENTO))
    g.drawRoundedRect(4, 4, 120, 120, 26, 26)
    g.setPen(Qt.NoPen); g.setBrush(QColor(ACENTO))
    g.drawEllipse(30, 78, 30, 22); g.drawEllipse(72, 66, 30, 22)
    g.drawRect(54, 34, 6, 56); g.drawRect(96, 24, 6, 54)
    g.drawPolygon([QPoint(54, 34), QPoint(102, 24), QPoint(102, 38), QPoint(54, 48)])
    g.end()
    return QIcon(p)


def etiqueta(texto="", clase="", ajustar=True):
    e = QLabel(texto)
    e.setWordWrap(ajustar)
    if clase:
        e.setProperty("clase", clase)
    return e


def reclasificar(w, clase):
    w.setProperty("clase", clase)
    w.style().unpolish(w)
    w.style().polish(w)


def boton(texto, al_pulsar=None, clase="", ayuda=""):
    b = QPushButton(texto)
    b.setCursor(Qt.PointingHandCursor)
    if clase:
        b.setProperty("clase", clase)
    if ayuda:
        b.setToolTip(ayuda)
    if al_pulsar:
        b.clicked.connect(lambda: al_pulsar())
    return b


def tarjeta(titulo=""):
    """(marco, layout vertical) con el estilo de tarjeta."""
    f = QFrame()
    f.setObjectName("tarjeta")
    v = QVBoxLayout(f)
    v.setContentsMargins(16, 14, 16, 16)
    v.setSpacing(10)
    if titulo:
        v.addWidget(etiqueta(titulo, "seccion"))
    return f, v


def fila(*widgets, estirar=None):
    h = QHBoxLayout()
    h.setSpacing(8)
    for w in widgets:
        if w is None:
            h.addStretch(1)
        elif isinstance(w, (QHBoxLayout, QVBoxLayout)):
            h.addLayout(w)
        else:
            h.addWidget(w, 1 if w is estirar else 0)
    return h


def columna(*widgets):
    """Columna de tarjetas con desplazamiento propio: así la ventana cabe en pantallas pequeñas."""
    dentro = QWidget()
    v = QVBoxLayout(dentro)
    v.setContentsMargins(0, 0, 6, 0)
    v.setSpacing(14)
    for w in widgets:
        v.addWidget(w)
    v.addStretch(1)
    area = QScrollArea()
    area.setWidget(dentro)
    area.setWidgetResizable(True)
    area.setFrameShape(QFrame.NoFrame)
    area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    area.setMinimumWidth(dentro.minimumSizeHint().width() + 14)
    return area


def herramientas(*piezas):
    """Barra de herramientas horizontal. "|" es un separador y None un hueco elástico."""
    f = QFrame()
    f.setObjectName("herramientas")
    h = QHBoxLayout(f)
    h.setContentsMargins(12, 6, 12, 6)
    h.setSpacing(6)
    for p in piezas:
        if p is None:
            h.addStretch(1)
        elif isinstance(p, str):
            raya = QFrame()
            raya.setFixedSize(1, 24)
            raya.setStyleSheet(f"background: {BORDE};")
            h.addSpacing(4)
            h.addWidget(raya)
            h.addSpacing(4)
        else:
            h.addWidget(p)
    return f


def dialogo(padre, titulo, mensaje, botones=("Aceptar",), tipo="info"):
    """Diálogo con el estilo de la app. Devuelve el texto del botón pulsado (o '' si se cierra)."""
    d = QDialog(padre)
    d.setWindowTitle(titulo)
    d.setMinimumWidth(460)
    v = QVBoxLayout(d)
    v.setContentsMargins(22, 20, 22, 18)
    v.setSpacing(14)
    simbolo = {"error": ("✕", PELIGRO), "aviso": ("!", AVISO), "pregunta": ("?", ACENTO)}.get(tipo, ("i", ACENTO))
    cab = etiqueta(f"<span style='color:{simbolo[1]};font-size:20px;font-weight:700'>{simbolo[0]}</span>"
                   f"&nbsp;&nbsp;<b style='font-size:16px'>{titulo}</b>")
    cab.setTextFormat(Qt.RichText)
    v.addWidget(cab)
    cuerpo = etiqueta(mensaje)
    cuerpo.setTextInteractionFlags(Qt.TextSelectableByMouse)
    v.addWidget(cuerpo)
    elegido = [""]
    h = QHBoxLayout()
    h.addStretch(1)
    for i, t in enumerate(botones):
        peligro = t.startswith(("Eliminar", "Borrar", "Descartar"))
        b = boton(t, clase="peligro" if peligro else "primario" if i == len(botones) - 1 else "")
        b.clicked.connect(lambda _=False, t=t: (elegido.__setitem__(0, t), d.accept()))
        h.addWidget(b)
    v.addLayout(h)
    d.exec()
    return elegido[0]


def error(padre, titulo, mensaje):
    dialogo(padre, titulo, mensaje, tipo="error")


def confirmar(padre, titulo, mensaje, si="Continuar", no="Cancelar"):
    return dialogo(padre, titulo, mensaje, (no, si), "pregunta") == si


AVISO_EXTERNO = ("La carpeta elegida está FUERA de la carpeta de Partitura Libre. Lo que guardes ahí "
                 "no se borrará al eliminar el programa: tendrás que borrarlo a mano si quieres.")


def avisar_si_externo(padre, ruta):
    """True si se puede seguir (está dentro, o el usuario acepta que quede fuera)."""
    return rutas.dentro_de(ruta) or confirmar(padre, "Ubicación externa", f"{AVISO_EXTERNO}\n\n{ruta}", "Guardar ahí")


def elegir_carpeta(padre, titulo, inicio=None):
    return QFileDialog.getExistingDirectory(padre, titulo, str(inicio or rutas.DATOS))


def abrir_en_sistema(ruta):
    """Abre un archivo o carpeta con la aplicación predeterminada del sistema."""
    QDesktopServices.openUrl(QUrl.fromLocalFile(str(ruta)))


def descarga_con_dialogo(padre, titulo, detalle, funcion, al_acabar):
    """Pide confirmación mostrando el tamaño, descarga con progreso y permite cancelar.
    `funcion(progreso, cancelar)`; `al_acabar(ok: bool)` en el hilo de la interfaz."""
    if not confirmar(padre, titulo, detalle, "Descargar"):
        return
    d = QDialog(padre)
    d.setWindowTitle(titulo)
    d.setMinimumWidth(440)
    d.setWindowFlag(Qt.WindowCloseButtonHint, False)
    v = QVBoxLayout(d)
    v.setContentsMargins(22, 20, 22, 18)
    v.setSpacing(12)
    texto = etiqueta("Conectando…")
    barra = QProgressBar()
    barra.setRange(0, 1000)
    barra.setTextVisible(False)
    cancelar = threading.Event()
    b = boton("Cancelar descarga", cancelar.set)
    v.addWidget(etiqueta(f"<b>{titulo}</b>")); v.addWidget(texto); v.addWidget(barra); v.addLayout(fila(None, b))

    def progreso(a, b_=None):
        f = a if b_ is None else (a / b_ if b_ else 0)
        en_ui(lambda: (barra.setValue(int(f * 1000)), texto.setText(f"Descargando… {f * 100:.0f} %")))

    def fin(_r, e):
        d.accept()
        if isinstance(e, descargas.Cancelada):
            dialogo(padre, titulo, "Descarga cancelada. No ha quedado ningún archivo a medias.")
        elif e:
            error(padre, titulo, f"No se pudo completar la descarga.\n\n{e}\n\nComprueba la conexión a Internet "
                                 "y el espacio libre y vuelve a intentarlo.")
        al_acabar(e is None)

    en_hilo(lambda: funcion(progreso, cancelar), fin)
    d.exec()
