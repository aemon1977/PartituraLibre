"""La partitura en papel, al estilo de un editor de notación: página con título, sistemas que
se reparten a lo ancho, clave, compás, barras de compás, figuras, silencios, nombres de nota y
letra. Se edita con el ratón y el teclado y se exporta a PDF. Dibujada con la fuente Bravura (SMuFL)."""
from pathlib import Path

from PySide6.QtCore import QMarginsF, QPointF, QRect, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontDatabase, QFontMetrics, QPageLayout, QPageSize, QPainter, QPdfWriter, QPen
from PySide6.QtWidgets import QWidget

from .. import partituras

ESP = 10            # píxeles entre dos líneas del pentagrama con el zoom al 100 %
TEXTO_Y = 6.0       # espacios bajo la línea inferior donde empieza el texto (deja sitio a las notas graves)
MESA, PAPEL, TINTA, ELEGIDA, TENUE = "#2f3948", "#fdfcf7", "#1b2433", "#0f9d8f", "#7a8494"
A4_ANCHO, A4_ALTO = 1000, 1414   # hoja A4 en unidades de dibujo para el PDF
# Símbolos SMuFL de Bravura
G_CLAVE = {"sol": "", "fa": "", "do3": "", "do4": ""}
G_CABEZA = {"redonda": "", "blanca": ""}
G_NEGRA, G_SOSTENIDO, G_CUATRO = "", "", ""
G_CORCHETE = {("corchea", True): "", ("corchea", False): "",
              ("semicorchea", True): "", ("semicorchea", False): ""}
G_SILENCIO = {"redonda": ("", 6), "blanca": ("", 4), "negra": ("", 4),
              "corchea": ("", 4), "semicorchea": ("", 4)}   # (símbolo, posición en el pentagrama)

_familia = None


def fuente_musical():
    """Familia de la fuente de notación incluida en el programa (None si no se pudo cargar)."""
    global _familia
    if _familia is None:
        i = QFontDatabase.addApplicationFont(str(Path(__file__).resolve().parents[1] / "recursos" / "Bravura.otf"))
        _familia = (QFontDatabase.applicationFontFamilies(i) or [""])[0] if i >= 0 else ""
    return _familia or None


class Pentagrama(QWidget):
    elegida = Signal(int)                 # clic en una nota
    arrastrada = Signal(int, int, bool)   # (nota, nuevo tono, es el primer paso del arrastre)
    insertada = Signal(int, int)          # modo introducir: (nota tras la que va, o -1 al principio; tono)
    tecla = Signal(str)                   # atajos de edición

    TECLAS = {Qt.Key_Up: "arriba", Qt.Key_Down: "abajo", Qt.Key_Left: "anterior", Qt.Key_Right: "siguiente",
              Qt.Key_Delete: "borrar", Qt.Key_Backspace: "borrar", Qt.Key_N: "nueva", Qt.Key_Space: "reproducir"}

    def __init__(self):
        super().__init__()
        self.notas, self.sel, self.bpm, self.clave, self.nombres, self.letra = [], -1, 120, "sol", True, []
        self.titulo, self.zoom, self.insertar = "", 1.0, False
        self.sistemas = []   # cada sistema: lista de piezas {'col': índices de notas (vacío = silencio), 'x', 'barra', 'ancho', 'compas', 'silencio'}
        self._sis_y = []     # y de la línea inferior de cada sistema
        self._cajas = []     # (rectángulo, índice de nota) para elegir con el ratón
        self._papel = QRectF()
        self._arrastre = None
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

    def modo_insertar(self, si):
        self.insertar = si
        self.setCursor(Qt.CrossCursor if si else Qt.ArrowCursor)

    def resizeEvent(self, _):
        self._componer()

    def _cantado(self, col):
        return " ".join(self.letra[i] for i in col if i < len(self.letra) and self.letra[i])

    def _fuente(self, px, z, cursiva=False, serif=False):
        f = QFont("serif" if serif else self.font().family())
        f.setPixelSize(max(8, round(px * z)))
        f.setItalic(cursiva)
        return f

    def _alto_sistema(self, z):
        return 15 * ESP * z + (19 * z if any(self.letra) else 0) + (30 * z if self.nombres else 0)

    def _repartir(self, izq, der, z):
        """Reparte notas y silencios en sistemas entre `izq` y `der`, cortando por compases cuando se puede."""
        medir = QFontMetrics(self._fuente(14, z, cursiva=True))
        piezas, fin_previo = [], 0.0
        for col in partituras.columnas(self.notas):
            inicio = partituras.pulso(self.notas[col[0]][0], self.bpm)
            hueco = fin_previo
            for fig in partituras.silencios(inicio - fin_previo):       # el silencio entre dos notas
                piezas.append({"col": [], "ancho": 34 * z, "compas": int(hueco // 4), "silencio": fig})
                hueco += partituras.NEGRAS[fig]
            piezas.append({"col": col, "ancho": max(46 * z, medir.horizontalAdvance(self._cantado(col)) + 16 * z),
                           "compas": int(inicio // 4), "silencio": None})
            fin_previo = max(fin_previo, max(partituras.pulso(self.notas[i][1], self.bpm) for i in col), inicio + 0.25)

        sistemas, actual, corte, previo = [], [], 0, None
        x = izq + 92 * z                                      # clave y compás de 4/4 en el primer sistema
        for p in piezas:
            barra = bool(actual) and p["compas"] != previo
            if actual and x + (14 * z if barra else 0) + p["ancho"] > der:
                resto = actual[corte:] if 0 < corte < len(actual) and not barra else []   # el compás a medias baja entero
                sistemas.append(actual[:len(actual) - len(resto)])
                actual, corte, x = [], 0, izq + 58 * z
                for r in resto:
                    r["x"], r["barra"] = x, False
                    actual.append(r)
                    x += r["ancho"]
                barra = bool(actual) and p["compas"] != previo
            if barra:
                x += 14 * z
                corte = len(actual)
            p["x"], p["barra"] = x, barra
            actual.append(p)
            x += p["ancho"]
            previo = p["compas"]
        if actual or not sistemas:
            sistemas.append(actual)
        return sistemas

    def _componer(self):
        e, z = ESP * self.zoom, self.zoom
        self._papel = QRectF(26, 22, max(self.width() - 52, 500), 0)
        self.sistemas = self._repartir(self._papel.left() + 34 * z, self._papel.right() - 30 * z, z)
        cabecera, alto = 96 * z, self._alto_sistema(z)
        self._sis_y = [self._papel.top() + cabecera + 8.5 * e + s * alto for s in range(len(self.sistemas))]
        self._papel.setHeight(cabecera + len(self.sistemas) * alto + 40 * z)
        self.setMinimumHeight(int(self._papel.bottom() + 26))
        self._cajas = []   # zona sensible de cada nota; se calcula aquí y no al pintar, porque solo se pinta lo visible
        for piezas, base in zip(self.sistemas, self._sis_y):
            for p in piezas:
                for i in p["col"]:
                    pos = max(-10, min(17, partituras.posicion(self.notas[i][2], self.clave)[0]))
                    self._cajas.append((QRectF(p["x"] - 6 * z, base - pos * e / 2 - e, 1.18 * e + 12 * z, 2 * e), i))

    def _banda(self, s):
        """Franja de la hoja que ocupa un sistema, con sus notas más agudas y graves y su texto."""
        e = ESP * self.zoom
        return QRectF(0, self._sis_y[s] - 9.5 * e, self.width(), self._alto_sistema(self.zoom) + 2 * e)

    def repintar_nota(self, indice):
        """Redibuja solo el sistema de esa nota: lo único que cambia al arrastrarla."""
        for s, piezas in enumerate(self.sistemas):
            if any(indice in p["col"] for p in piezas):
                return self.update(self._banda(s).toAlignedRect())
        self.update()

    def rect_de(self, indice):
        """Zona de una nota (para llevar la vista hasta ella)."""
        for s, piezas in enumerate(self.sistemas):
            for p in piezas:
                if indice in p["col"]:
                    return QRect(int(p["x"]) - 40, int(self._sis_y[s] - 9 * ESP * self.zoom), 120, int(16 * ESP * self.zoom))
        return QRect(0, 0, 1, 1)

    # -- dibujo ---------------------------------------------------------------
    def paintEvent(self, ev):
        g = QPainter(self)
        g.setRenderHint(QPainter.Antialiasing)
        g.fillRect(ev.rect(), QColor(MESA))
        g.fillRect(self._papel.translated(3, 4), QColor(0, 0, 0, 70))      # sombra de la hoja
        g.fillRect(self._papel, QColor(PAPEL))
        visibles = [s for s in range(len(self.sistemas)) if self._banda(s).intersects(QRectF(ev.rect()))]   # solo lo que se ve
        self._pintar(g, self._papel, [self.sistemas[s] for s in visibles], [self._sis_y[s] for s in visibles], self.zoom,
                     True, visibles, len(self.sistemas), True, self.sel)

    def _pintar(self, g, papel, sistemas, bases, z, cabecera, numeros, total, pantalla, sel):
        """Dibuja en `papel` los `sistemas` dados; `numeros` es el n.º de orden de cada uno dentro de un total de `total`."""
        familia = fuente_musical()
        g.setPen(QColor(TINTA))
        if not familia:
            return g.drawText(papel, Qt.AlignCenter, "No se pudo cargar la fuente de notación (recursos/Bravura.otf).")
        e = ESP * z
        musica = QFont(familia)
        musica.setPixelSize(round(4 * e))                 # en SMuFL, 1 em = 4 espacios
        f_nombre, f_letra, f_peque = self._fuente(12, z), self._fuente(14, z, cursiva=True), self._fuente(10, z)
        linea = QPen(QColor(TINTA), max(1.0, 1.1 * z))
        izq, der = papel.left() + 34 * z, papel.right() - 30 * z
        hay_letra = any(self.letra)

        if cabecera:
            g.setFont(self._fuente(24, z, serif=True))
            g.drawText(QRectF(papel.left(), papel.top() + 22 * z, papel.width(), 34 * z), Qt.AlignCenter,
                       self.titulo or "Partitura sin título")
            g.setFont(self._fuente(11, z, serif=True))
            g.drawText(QRectF(izq, papel.top() + 60 * z, der - izq, 18 * z), Qt.AlignRight, "Partitura Libre")
            g.drawText(QRectF(izq, papel.top() + 60 * z, der - izq, 18 * z), Qt.AlignLeft,
                       f"{partituras.CLAVES[self.clave][0]}   ♩ = {self.bpm}" if self.notas else partituras.CLAVES[self.clave][0])

        ancho = 1.18 * e                                  # ancho de una cabeza de nota
        for s, piezas, base in zip(numeros, sistemas, bases):
            y = lambda pos: base - pos * e / 2
            ultimo = s == total - 1
            fin = der if not ultimo or not piezas else min(der, piezas[-1]["x"] + piezas[-1]["ancho"] + 10 * z)
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
            elif piezas:
                g.setFont(f_peque)
                g.setPen(QColor(TENUE))
                g.drawText(QPointF(izq + 2, y(8) - 6 * z), str(piezas[0]["compas"] + 1))   # n.º de compás

            for p in piezas:
                x, col = p["x"], p["col"]
                if p["barra"]:
                    g.setPen(linea)
                    g.drawLine(QPointF(x - 14 * z, y(0)), QPointF(x - 14 * z, y(8)))
                if p["silencio"]:
                    simbolo, pos = G_SILENCIO[p["silencio"]]
                    g.setFont(musica)
                    g.setPen(QColor(TINTA))
                    g.drawText(QPointF(x + 4 * z, y(pos)), simbolo)
                    continue
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
                    color = QColor(ELEGIDA if i == sel else TINTA)
                    g.setPen(QPen(color, max(1.0, 1.1 * z)))
                    for extra in [q for q in range(-2, pos - 1, -2)] + [q for q in range(10, pos + 1, 2)]:
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
                    if i == sel:                            # marco de selección, como en un editor
                        g.setPen(QPen(QColor(ELEGIDA), 1, Qt.DashLine))
                        g.drawRoundedRect(QRectF(x - 6 * z, y(pos) - 1.1 * e, ancho + 12 * z, 2.2 * e), 3, 3)
                    if self.nombres and k < 2:              # nombres bajo el pentagrama; en acordes, del grave al agudo
                        g.setFont(f_nombre)
                        g.setPen(color)
                        g.drawText(QRectF(x - 20 * z, base + TEXTO_Y * e + (19 * z if hay_letra else 0) + 14 * z * k, ancho + 40 * z, 16 * z),
                                   Qt.AlignCenter, partituras.solfeo(tono))
        if not self.notas and cabecera and pantalla and bases:
            g.setFont(self._fuente(13, z))
            g.setPen(QColor(TENUE))
            g.drawText(QRectF(izq, bases[0] + 5 * e, der - izq, 40 * z), Qt.AlignCenter,
                       "Graba o importa un audio, o pulsa «Introducir» y haz clic en el pentagrama para escribir notas.")

    # -- PDF ------------------------------------------------------------------
    def paginas(self):
        """Reparto para imprimir en A4: lista de páginas, cada una con sus sistemas."""
        z, margen = 1.0, 60
        sistemas = self._repartir(margen + 34 * z, A4_ANCHO - margen - 30 * z, z)
        alto, paginas, y = self._alto_sistema(z), [[]], margen + 96 * z
        for s in sistemas:
            if paginas[-1] and y + alto > A4_ALTO - margen:
                paginas.append([])
                y = margen
            paginas[-1].append(s)
            y += alto
        return paginas

    def exportar_pdf(self, ruta):
        """Escribe la partitura en un PDF A4 (vectorial, con la fuente incrustada). Devuelve el n.º de páginas."""
        pdf = QPdfWriter(str(ruta))
        pdf.setPageLayout(QPageLayout(QPageSize(QPageSize.A4), QPageLayout.Portrait, QMarginsF(0, 0, 0, 0)))
        pdf.setTitle(self.titulo or "Partitura")
        pdf.setCreator("Partitura Libre")
        g = QPainter(pdf)
        try:
            g.setRenderHint(QPainter.Antialiasing)
            g.setWindow(0, 0, A4_ANCHO, A4_ALTO)
            margen, alto, e = 60, self._alto_sistema(1.0), ESP
            papel = QRectF(margen, margen, A4_ANCHO - 2 * margen, A4_ALTO - 2 * margen)
            paginas, hechos = self.paginas(), 0
            total = sum(len(p) for p in paginas)
            for n, pagina in enumerate(paginas):
                if n:
                    pdf.newPage()
                arriba = papel.top() + (96 if n == 0 else 0)
                bases = [arriba + 8.5 * e + k * alto for k in range(len(pagina))]
                self._pintar(g, papel, pagina, bases, 1.0, n == 0, range(hechos, hechos + len(pagina)), total, False, -1)
                hechos += len(pagina)
                g.setFont(self._fuente(10, 1.0))
                g.setPen(QColor(TENUE))
                g.drawText(QRectF(papel.left(), A4_ALTO - 46, papel.width(), 16), Qt.AlignCenter, f"{n + 1} / {len(paginas)}")
        finally:
            g.end()
        return len(paginas)

    # -- interacción ----------------------------------------------------------
    def _sistema_en(self, y):
        """(n.º de sistema, posición en el pentagrama) más cercanos a esa altura."""
        if not self._sis_y:
            return 0, 0
        e = ESP * self.zoom
        s = min(range(len(self._sis_y)), key=lambda k: abs(self._sis_y[k] - 2 * e - y))
        return s, round((self._sis_y[s] - y) / (e / 2))

    def mousePressEvent(self, ev):
        self.setFocus()
        for caja, i in self._cajas:
            if caja.contains(ev.position()):
                self._arrastre = [i, ev.position().y(), partituras.posicion(self.notas[i][2], self.clave)[0], 0, True]
                return self.elegida.emit(i)
        if self.insertar:   # clic en el pentagrama: nota nueva a esa altura, tras la nota que queda a su izquierda
            s, pos = self._sistema_en(ev.position().y())
            if -10 <= pos <= 17:
                antes = [p for k in range(s + 1) for p in self.sistemas[k] if p["col"] and (k < s or p["x"] <= ev.position().x())]
                self.insertada.emit(antes[-1]["col"][-1] if antes else -1, partituras.midi_de(pos, self.clave))

    def mouseMoveEvent(self, ev):
        if self._arrastre:   # arrastrar una nota arriba o abajo cambia su altura, un paso por línea o espacio
            i, y0, pos0, ultimo, primero = self._arrastre
            pasos = round((y0 - ev.position().y()) / (ESP * self.zoom / 2))
            if pasos != ultimo:
                self._arrastre[3], self._arrastre[4] = pasos, False
                self.arrastrada.emit(i, partituras.midi_de(pos0 + pasos, self.clave), primero)

    def mouseReleaseEvent(self, _):
        if self._arrastre and self._arrastre[3]:   # al soltar se recalculan las zonas sensibles con la altura final
            self._componer()
            self.update()
        self._arrastre = None

    def keyPressEvent(self, ev):
        accion, ctrl, mayus = self.TECLAS.get(ev.key()), ev.modifiers() & Qt.ControlModifier, ev.modifiers() & Qt.ShiftModifier
        if ctrl and ev.key() == Qt.Key_Z:
            accion = "rehacer" if mayus else "deshacer"
        elif ctrl and ev.key() == Qt.Key_Y:
            accion = "rehacer"
        elif accion in ("arriba", "abajo") and ctrl:
            accion = "octava+" if accion == "arriba" else "octava-"
        elif accion in ("anterior", "siguiente") and mayus:
            accion = "antes" if accion == "anterior" else "despues"
        if accion:
            self.tecla.emit(accion)
        else:
            super().keyPressEvent(ev)
