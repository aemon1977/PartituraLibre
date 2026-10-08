"""Pentagrama: clave, figuras y nombre de cada nota (Do, Re, Mi…), dibujado con la fuente Bravura."""
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontDatabase, QPainter, QPen
from PySide6.QtWidgets import QWidget

from .. import partituras

ESP = 10            # píxeles entre dos líneas del pentagrama
PASO = 50           # ancho de cada columna de notas
MARGEN = 86         # sitio para la clave
PAPEL, TINTA, ELEGIDA, TENUE = "#f7f4ea", "#1b2433", "#0f9d8f", "#6b7280"
# Símbolos SMuFL de Bravura
G_CLAVE = {"sol": "", "fa": "", "do3": "", "do4": ""}
G_CABEZA = {"redonda": "", "blanca": ""}
G_NEGRA, G_SOSTENIDO = "", ""
G_CORCHETE = {("corchea", True): "", ("corchea", False): "",
              ("semicorchea", True): "", ("semicorchea", False): ""}

_familia = None


def fuente_musical():
    """Familia de la fuente de notación incluida en el programa (None si no se pudo cargar)."""
    global _familia
    if _familia is None:
        i = QFontDatabase.addApplicationFont(str(Path(__file__).resolve().parents[1] / "recursos" / "Bravura.otf"))
        _familia = (QFontDatabase.applicationFontFamilies(i) or [""])[0] if i >= 0 else ""
    return _familia or None


class Pentagrama(QWidget):
    elegida = Signal(int)

    def __init__(self):
        super().__init__()
        self.notas, self.sel, self.bpm, self.clave, self.nombres = [], -1, 120, "sol", True
        self._cajas = []  # (rectángulo, índice de nota) para elegir con el ratón
        self.setMinimumHeight(196)

    def poner(self, notas, sel=-1, bpm=120, clave="", nombres=True):
        self.notas, self.sel, self.bpm, self.nombres = notas, sel, bpm, nombres
        self.clave = clave or partituras.clave_adecuada(notas)
        self.setMinimumWidth(MARGEN + PASO * len(partituras.columnas(notas)) + 30)
        self.update()

    def x_de(self, indice):
        """Posición horizontal de una nota (para llevar la vista hasta ella)."""
        return next((MARGEN + PASO * c for c, col in enumerate(partituras.columnas(self.notas)) if indice in col), 0)

    def paintEvent(self, _):
        g = QPainter(self)
        g.setRenderHint(QPainter.Antialiasing)
        g.fillRect(self.rect(), QColor(PAPEL))
        familia = fuente_musical()
        if not familia:
            g.setPen(QColor(TINTA))
            return g.drawText(self.rect(), Qt.AlignCenter, "No se pudo cargar la fuente de notación (recursos/Bravura.otf).")
        base = self.height() / 2 + 2 * ESP - 16          # y de la línea inferior
        y = lambda pos: base - pos * ESP / 2
        musica = QFont(familia)
        musica.setPixelSize(4 * ESP)                     # en SMuFL, 1 em = 4 espacios
        texto = QFont(self.font())
        texto.setPixelSize(13)
        linea = QPen(QColor(TINTA), 1.1)

        g.setPen(linea)
        for l in range(5):
            g.drawLine(QPointF(8, y(2 * l)), QPointF(self.width() - 8, y(2 * l)))
        g.setFont(musica)
        g.drawText(QPointF(18, y(partituras.CLAVES[self.clave][2])), G_CLAVE[self.clave])
        g.setFont(texto)
        g.setPen(QColor(TENUE))
        g.drawText(QPointF(10, 18), partituras.CLAVES[self.clave][0])

        self._cajas = []
        ancho = 1.18 * ESP                               # ancho de una cabeza de nota
        for c, col in enumerate(partituras.columnas(self.notas)):
            x = MARGEN + PASO * c
            for k, i in enumerate(col):
                ini, fin, tono, _v = self.notas[i]
                pos, sostenido = partituras.posicion(tono, self.clave)
                pos = max(-9, min(17, pos))              # fuera de ese margen no cabría en la vista
                fig = partituras.figura(fin - ini, self.bpm)
                color = QColor(ELEGIDA if i == self.sel else TINTA)
                g.setPen(QPen(color, 1.1))
                for extra in [p for p in range(-2, pos - 1, -2)] + [p for p in range(10, pos + 1, 2)]:
                    g.drawLine(QPointF(x - 5, y(extra)), QPointF(x + ancho + 5, y(extra)))   # líneas adicionales
                g.setFont(musica)
                g.drawText(QPointF(x, y(pos)), G_CABEZA.get(fig, G_NEGRA))
                if sostenido:
                    g.drawText(QPointF(x - 1.15 * ESP, y(pos)), G_SOSTENIDO)
                if fig != "redonda":
                    arriba = pos < 4
                    xp = x + ancho - 0.6 if arriba else x + 0.6
                    punta = y(pos) + (-3.4 if arriba else 3.4) * ESP
                    g.drawLine(QPointF(xp, y(pos)), QPointF(xp, punta))
                    if (fig, arriba) in G_CORCHETE:
                        g.drawText(QPointF(xp - 0.5, punta), G_CORCHETE[(fig, arriba)])
                self._cajas.append((QRectF(x - 6, y(pos) - ESP, ancho + 12, 2 * ESP), i))
                if self.nombres and k < 3:               # nombres bajo el pentagrama; en acordes, del grave al agudo
                    g.setFont(texto)
                    g.setPen(color)
                    g.drawText(QRectF(x - 20, base + 4.4 * ESP + 14 * k, ancho + 40, 16), Qt.AlignCenter, partituras.solfeo(tono))


    def mousePressEvent(self, ev):
        for caja, i in self._cajas:
            if caja.contains(ev.position()):
                return self.elegida.emit(i)
