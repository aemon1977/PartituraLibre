"""La partitura en papel, al estilo de un editor de notación: página con título, sistemas que
se reparten a lo ancho, clave, compás, barras de compás, figuras, nombres de nota y letra.
Se dibuja con la fuente Bravura (SMuFL)."""
from pathlib import Path

from PySide6.QtCore import QPointF, QRect, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontDatabase, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import QWidget

from .. import partituras

ESP = 10            # píxeles entre dos líneas del pentagrama con el zoom al 100 %
TEXTO_Y = 6.0       # espacios bajo la línea inferior donde empieza el texto (deja sitio a las notas graves)
MESA, PAPEL, TINTA, ELEGIDA, TENUE = "#2f3948", "#fdfcf7", "#1b2433", "#0f9d8f", "#7a8494"
# Símbolos SMuFL de Bravura
G_CLAVE = {"sol": "", "fa": "", "do3": "", "do4": ""}
G_CABEZA = {"redonda": "", "blanca": ""}
G_NEGRA, G_SOSTENIDO, G_CUATRO = "", "", ""
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
    elegida = Signal(int)   # clic en una nota
    tecla = Signal(str)     # atajos de edición: 'arriba', 'abajo', 'octava+', 'octava-', 'anterior', 'siguiente', 'borrar', 'nueva'

    TECLAS = {Qt.Key_Up: "arriba", Qt.Key_Down: "abajo", Qt.Key_Left: "anterior", Qt.Key_Right: "siguiente",
              Qt.Key_Delete: "borrar", Qt.Key_Backspace: "borrar", Qt.Key_N: "nueva"}

    def __init__(self):
        super().__init__()
        self.notas, self.sel, self.bpm, self.clave, self.nombres, self.letra = [], -1, 120, "sol", True, []
        self.titulo, self.zoom = "", 1.0
        self.sistemas = []   # cada sistema: {'y': línea inferior, 'cols': [(índices, x, barra_antes)], 'compas': n.º del primero}
        self._cajas = []     # (rectángulo, índice de nota) para elegir con el ratón
        self._papel = QRectF()
        self.setFocusPolicy(Qt.StrongFocus)
        self.setMinimumWidth(560)

    # -- contenido ----------------------------------------------------------
    def poner(self, notas, sel=-1, bpm=120, clave="", nombres=True, letra=(), titulo=""):
        """`letra` es el texto bajo cada nota (paralela a `notas`)."""
        self.notas, self.sel, self.bpm, self.nombres, self.letra = notas, sel, bpm or 120, nombres, list(letra)
        self.clave, self.titulo = clave or partituras.clave_adecuada(notas), titulo
        self._componer()
        self.update()

    def cambiar_zoom(self, zoom):
        self.zoom = max(0.6, min(2.0, zoom))
        self._componer()
        self.update()

    def resizeEvent(self, _):
        self._componer()

    def _cantado(self, col):
        return " ".join(self.letra[i] for i in col if i < len(self.letra) and self.letra[i])

    def _fuente(self, px, cursiva=False, negrita=False, serif=False):
        f = QFont("serif" if serif else self.font().family())
        f.setPixelSize(max(8, round(px * self.zoom)))
        f.setItalic(cursiva)
        f.setBold(negrita)
        return f

    def _componer(self):
        """Reparte las notas en sistemas según el ancho disponible, cortando por compases cuando se puede."""
        e, z = ESP * self.zoom, self.zoom
        margen = 26
        self._papel = QRectF(margen, 22, max(self.width() - 2 * margen, 500), 0)
        izq, der = self._papel.left() + 34 * z, self._papel.right() - 30 * z
        hay_letra = any(self.letra)
        alto = 15 * e + (19 * z if hay_letra else 0) + (30 * z if self.nombres else 0)
        medir = QFontMetrics(self._fuente(14, cursiva=True))
        columnas = [(col, max(46 * z, medir.horizontalAdvance(self._cantado(col)) + 16 * z),
                     partituras.compas(self.notas[col[0]][0], self.bpm)) for col in partituras.columnas(self.notas)]

        self.sistemas, actual, x, corte = [], [], 0, 0
        def abrir():
            nonlocal x
            x = izq + (92 if not self.sistemas else 58) * z   # clave (+ compás 4/4 en el primer sistema)
        abrir()
        previo = None
        for col, ancho, compas in columnas:
            barra = bool(actual) and compas != previo
            if actual and x + (14 * z if barra else 0) + ancho > der:
                resto = actual[corte:] if 0 < corte < len(actual) and not barra else []   # el compás a medias baja entero
                self.sistemas.append(actual[:len(actual) - len(resto)])
                actual, corte = [], 0
                abrir()
                for c, _x, _b, a, cp in resto:
                    actual.append((c, x, False, a, cp))
                    x += a
                barra = bool(actual) and compas != previo
            if barra:
                x += 14 * z
                corte = len(actual)
            actual.append((col, x, barra, ancho, compas))
            x += ancho
            previo = compas
        if actual or not self.sistemas:
            self.sistemas.append(actual)
        cabecera = 96 * z
        self._sis_y = [self._papel.top() + cabecera + 8.5 * e + s * alto for s in range(len(self.sistemas))]
        self._papel.setHeight(cabecera + len(self.sistemas) * alto + 40 * z)
        self.setMinimumHeight(int(self._papel.bottom() + 26))

    def rect_de(self, indice):
        """Zona de una nota (para llevar la vista hasta ella)."""
        for s, cols in enumerate(self.sistemas):
            for col, x, *_ in cols:
                if indice in col:
                    return QRect(int(x) - 40, int(self._sis_y[s] - 9 * ESP * self.zoom), 120, int(16 * ESP * self.zoom))
        return QRect(0, 0, 1, 1)

    # -- dibujo ---------------------------------------------------------------
    def paintEvent(self, _):
        g = QPainter(self)
        g.setRenderHint(QPainter.Antialiasing)
        g.fillRect(self.rect(), QColor(MESA))
        g.fillRect(self._papel.translated(3, 4), QColor(0, 0, 0, 70))      # sombra de la hoja
        g.fillRect(self._papel, QColor(PAPEL))
        familia = fuente_musical()
        g.setPen(QColor(TINTA))
        if not familia:
            return g.drawText(self._papel, Qt.AlignCenter, "No se pudo cargar la fuente de notación (recursos/Bravura.otf).")
        e, z = ESP * self.zoom, self.zoom
        musica = QFont(familia)
        musica.setPixelSize(round(4 * e))                 # en SMuFL, 1 em = 4 espacios
        f_nombre, f_letra, f_peque = self._fuente(12), self._fuente(14, cursiva=True), self._fuente(10)
        linea = QPen(QColor(TINTA), max(1.0, 1.1 * z))
        izq, der = self._papel.left() + 34 * z, self._papel.right() - 30 * z
        hay_letra = any(self.letra)

        g.setFont(self._fuente(24, serif=True))
        g.drawText(QRectF(self._papel.left(), self._papel.top() + 22 * z, self._papel.width(), 34 * z), Qt.AlignCenter,
                   self.titulo or "Partitura sin título")
        g.setFont(self._fuente(11, serif=True))
        g.drawText(QRectF(izq, self._papel.top() + 60 * z, der - izq, 18 * z), Qt.AlignRight,
                   "Transcripción automática · Partitura Libre")
        g.drawText(QRectF(izq, self._papel.top() + 60 * z, der - izq, 18 * z), Qt.AlignLeft,
                   f"{partituras.CLAVES[self.clave][0]}   ♩ = {self.bpm}" if self.notas else partituras.CLAVES[self.clave][0])

        self._cajas = []
        ancho = 1.18 * e                                  # ancho de una cabeza de nota
        for s, cols in enumerate(self.sistemas):
            base = self._sis_y[s]                          # y de la línea inferior
            y = lambda pos: base - pos * e / 2
            ultimo = s == len(self.sistemas) - 1
            fin = der if not ultimo or not cols else min(der, cols[-1][1] + cols[-1][3] + 10 * z)
            g.setPen(linea)
            for l in range(5):
                g.drawLine(QPointF(izq, y(2 * l)), QPointF(fin, y(2 * l)))
            g.drawLine(QPointF(izq, y(0)), QPointF(izq, y(8)))
            if ultimo:                                     # doble barra final
                g.drawLine(QPointF(fin - 5 * z, y(0)), QPointF(fin - 5 * z, y(8)))
                g.fillRect(QRectF(fin - 2.5 * z, y(8), 2.5 * z, 4 * e), QColor(TINTA))
            else:
                g.drawLine(QPointF(fin, y(0)), QPointF(fin, y(8)))
            g.setFont(musica)
            g.drawText(QPointF(izq + 8 * z, y(partituras.CLAVES[self.clave][2])), G_CLAVE[self.clave])
            if s == 0:                                     # compás de 4/4
                g.drawText(QPointF(izq + 46 * z, y(6)), G_CUATRO)
                g.drawText(QPointF(izq + 46 * z, y(2)), G_CUATRO)
            elif cols:
                g.setFont(f_peque)
                g.setPen(QColor(TENUE))
                g.drawText(QPointF(izq + 2, y(8) - 6 * z), str(cols[0][4] + 1))   # n.º de compás

            for col, x, barra, _ancho, _compas in cols:
                if barra:
                    g.setPen(linea)
                    g.drawLine(QPointF(x - 14 * z, y(0)), QPointF(x - 14 * z, y(8)))
                cantado = self._cantado(col)
                if cantado:   # la letra, bajo el pentagrama y empezando en su nota; los nombres bajan una línea
                    g.setFont(f_letra)
                    g.setPen(QColor(TINTA))
                    g.drawText(QPointF(x - 2, base + TEXTO_Y * e + 13 * z), cantado)
                for k, i in enumerate(col):
                    ini, final, tono, _v = self.notas[i]
                    pos, sostenido = partituras.posicion(tono, self.clave)
                    pos = max(-10, min(17, pos))           # fuera de ese margen no cabría en el sistema
                    fig = partituras.figura(final - ini, self.bpm)
                    color = QColor(ELEGIDA if i == self.sel else TINTA)
                    g.setPen(QPen(color, max(1.0, 1.1 * z)))
                    for extra in [p for p in range(-2, pos - 1, -2)] + [p for p in range(10, pos + 1, 2)]:
                        g.drawLine(QPointF(x - 5 * z, y(extra)), QPointF(x + ancho + 5 * z, y(extra)))   # líneas adicionales
                    g.setFont(musica)
                    g.drawText(QPointF(x, y(pos)), G_CABEZA.get(fig, G_NEGRA))
                    if sostenido:
                        g.drawText(QPointF(x - 1.15 * e, y(pos)), G_SOSTENIDO)
                    if fig != "redonda":
                        arriba = pos < 4
                        xp = x + ancho - 0.6 if arriba else x + 0.6
                        punta = y(pos) + (-3.4 if arriba else 3.4) * e
                        g.drawLine(QPointF(xp, y(pos)), QPointF(xp, punta))
                        if (fig, arriba) in G_CORCHETE:
                            g.drawText(QPointF(xp - 0.5, punta), G_CORCHETE[(fig, arriba)])
                    if i == self.sel:                       # marco de selección, como en un editor
                        g.setPen(QPen(QColor(ELEGIDA), 1, Qt.DashLine))
                        g.drawRoundedRect(QRectF(x - 6 * z, y(pos) - 1.1 * e, ancho + 12 * z, 2.2 * e), 3, 3)
                    self._cajas.append((QRectF(x - 6 * z, y(pos) - e, ancho + 12 * z, 2 * e), i))
                    if self.nombres and k < 2:              # nombres bajo el pentagrama; en acordes, del grave al agudo
                        g.setFont(f_nombre)
                        g.setPen(color)
                        g.drawText(QRectF(x - 20 * z, base + TEXTO_Y * e + (19 * z if hay_letra else 0) + 14 * z * k, ancho + 40 * z, 16 * z),
                                   Qt.AlignCenter, partituras.solfeo(tono))
        if not self.notas:
            g.setFont(self._fuente(13))
            g.setPen(QColor(TENUE))
            g.drawText(QRectF(izq, self._sis_y[0] + 5 * e, der - izq, 40 * z), Qt.AlignCenter,
                       "Graba o importa un audio y pulsa «Detectar notas»: la partitura aparecerá aquí.")

    # -- interacción ----------------------------------------------------------
    def mousePressEvent(self, ev):
        self.setFocus()
        for caja, i in self._cajas:
            if caja.contains(ev.position()):
                return self.elegida.emit(i)

    def keyPressEvent(self, ev):
        accion = self.TECLAS.get(ev.key())
        if accion in ("arriba", "abajo") and ev.modifiers() & Qt.ControlModifier:
            accion = "octava+" if accion == "arriba" else "octava-"
        if accion:
            self.tecla.emit(accion)
        else:
            super().keyPressEvent(ev)
