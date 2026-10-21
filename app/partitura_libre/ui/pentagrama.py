"""La partitura en papel, al estilo de un editor de notación: página con título, sistemas que
se reparten a lo ancho, clave, compás, barras de compás, figuras, silencios, nombres de nota y
letra. Se edita con el ratón y el teclado y se exporta a PDF. Dibujada con la fuente Bravura (SMuFL)."""
from pathlib import Path

from PySide6.QtCore import QMarginsF, QPointF, QRect, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontDatabase, QFontMetrics, QPageLayout, QPageSize, QPainter, QPainterPath, QPdfWriter, QPen
from PySide6.QtWidgets import QToolTip, QWidget

from .. import partituras

ESP = 10            # píxeles entre dos líneas del pentagrama con el zoom al 100 %
NOMBRE = "#1d5fa8"   # color de los nombres de nota (la letra va en negro)
SONANDO = "#d9822b"  # nota que está sonando al reproducir
MESA, PAPEL, TINTA, ELEGIDA, TENUE = "#2f3948", "#fdfcf7", "#1b2433", "#0f9d8f", "#7a8494"
A4_ANCHO, A4_ALTO = 1000, 1414   # hoja A4 en unidades de dibujo para el PDF
# Símbolos SMuFL de Bravura
G_CLAVE = {"sol8": "\ue052", "sol": "", "fa": "", "do3": "", "do4": ""}
G_CABEZA = {"redonda": "", "blanca": ""}
G_BEMOL, G_BECUADRO = "\ue260", "\ue261"
# Armadura: (letra, octava) de cada alteración en clave de Sol, en el orden en que se escriben
ARMADURA_SOL = {1: [(3, 5), (0, 5), (4, 5), (1, 5), (5, 4), (2, 5), (6, 4)], -1: [(6, 4), (2, 5), (5, 4), (1, 5), (4, 4), (0, 5), (3, 4)]}
# Posición de la armadura en cada clave respecto a la de Sol (en pasos de pentagrama) y altura máxima permitida
DESPLAZA_CLAVE = {"sol": (0, 9), "sol8": (0, 9), "fa": (-2, 9), "do3": (-1, 9), "do4": (1, 8)}
ANCHO_ALTERACION = 9
G_NEGRA, G_SOSTENIDO, G_CUATRO, G_PUNTILLO = "", "", "", ""
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
    tempo_pedido = Signal(float)          # clic en una marca de tempo: (segundo en que empieza)

    # Mismas teclas que MuseScore: N introducir, 3-7 figura, A-G nota, 0 silencio, . puntillo, Ctrl+L letra
    TECLAS = {Qt.Key_Up: "arriba", Qt.Key_Down: "abajo", Qt.Key_Left: "anterior", Qt.Key_Right: "siguiente",
              Qt.Key_Delete: "borrar", Qt.Key_Backspace: "borrar", Qt.Key_N: "modo", Qt.Key_Space: "reproducir",
              Qt.Key_0: "silencio", Qt.Key_Period: "puntillo", Qt.Key_Escape: "escape"}

    def __init__(self):
        super().__init__()
        self.notas, self.sel, self.bpm, self.clave, self.nombres, self.letra = [], -1, 120, "sol", True, []
        self.acordes = []   # [[segundo, raíz, tipo], …] encima del pentagrama
        self.tempos = [[0.0, 120, ""]]   # [[segundo, bpm, indicación], …]: el primero es el tempo inicial
        self._marcas = {}
        self.armadura, self.tonalidad = 0, "Do mayor"
        self.sonando = -1    # índice de la nota que suena al reproducir (-1: ninguna)
        self.cursor = None   # segundo por el que va la reproducción: se dibuja una línea que avanza
        self.titulo, self.zoom, self.insertar, self.piano = "", 1.0, False, False
        self.sistemas = []   # cada sistema: lista de piezas {'col': índices de notas (vacío = silencio), 'x', 'barra', 'ancho', 'compas', 'silencio'}
        self._sis_y = []     # y de la línea inferior de cada sistema
        self._cajas = []     # (rectángulo, índice de nota) para elegir con el ratón
        self._papel = QRectF()
        self._arrastre = None
        self.setFocusPolicy(Qt.StrongFocus)
        self.setMouseTracking(True)   # para decir qué es cada nota al pasar el ratón por encima
        self.setMinimumWidth(560)

    # -- contenido ----------------------------------------------------------
    def poner(self, notas, sel=-1, bpm=120, clave="", nombres=True, letra=(), titulo="", armadura=None, acordes=(), tempos=None, piano=False):
        """`letra` es el texto bajo cada nota (paralela a `notas`). `armadura` en quintas (+ sostenidos,
        − bemoles); None la detecta de las notas."""
        self.notas, self.sel, self.bpm, self.nombres, self.letra = notas, sel, bpm or 120, nombres, list(letra)
        self.acordes = list(acordes)
        self.tempos = partituras.tempos_de(self.bpm, tempos)
        self.clave, self.titulo = clave or partituras.clave_adecuada(notas, voz=any(self.letra)), titulo
        self.piano = bool(piano and notas and not any(self.letra))
        detectada = partituras.tonalidad(notas)
        self.armadura = detectada[0] if armadura is None else armadura
        self.tonalidad = detectada[1] if armadura is None else partituras.nombre_armadura(armadura)
        self._componer()
        self.update()

    def cambiar_zoom(self, zoom):
        self.zoom = max(0.6, min(2.0, zoom))
        self._componer()
        self.update()

    def modo_insertar(self, si):
        self.insertar = si
        self.setCursor(Qt.CrossCursor if si else Qt.ArrowCursor)
        self.update()

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
        return (28 * ESP * z if self.piano else 15 * ESP * z) + (19 * z if any(self.letra) else 0) + (30 * z if self.nombres else 0) + (22 * z if self.acordes else 0) \
            + (20 * z if self.notas else 0)

    def _sobre(self, z):
        """Espacio de un sistema por encima de su línea inferior (notas agudas y, si hay, acordes)."""
        return 8.5 * ESP * z + (22 * z if self.acordes else 0) + (20 * z if self.notas else 0)

    def _negras(self, t):
        """Pulso (en negras, ajustado a la semicorchea) del segundo t, con los cambios de tempo."""
        return round(partituras.negras_en(t, self.tempos) * 4) / 4

    def _repartir(self, izq, der, z):
        """Reparte notas y silencios en sistemas entre `izq` y `der`, cortando por compases cuando se puede."""
        medir = QFontMetrics(self._fuente(14, z, cursiva=True))
        piezas, fin_previo = [], 0.0
        for col in partituras.columnas(self.notas):
            inicio = self._negras(self.notas[col[0]][0])
            hueco = fin_previo
            for fig in partituras.silencios(inicio - fin_previo):       # el silencio entre dos notas
                piezas.append({"col": [], "ancho": 34 * z, "compas": int(hueco // 4), "silencio": fig, "t": partituras.segundos_en(hueco, self.tempos)})
                hueco += partituras.NEGRAS[fig]
            final = max(max(self._negras(self.notas[i][1]) for i in col), inicio + 0.25)
            ancho = max(46 * z, medir.horizontalAdvance(self._cantado(col)) + 16 * z)
            tramos = [inicio]                             # una nota que cruza la barra se parte en dos ligadas
            while (tramos[-1] // 4 + 1) * 4 < final - 0.2:
                tramos.append((tramos[-1] // 4 + 1) * 4)
            for k, t in enumerate(tramos):
                fin_tramo = tramos[k + 1] if k + 1 < len(tramos) else final
                piezas.append({"col": col, "ancho": ancho if k == 0 else 46 * z, "compas": int(t // 4), "silencio": None,
                               "negras": fin_tramo - t if len(tramos) > 1 else None, "ligada": k > 0,
                               "t": self.notas[col[0]][0] if k == 0 else partituras.segundos_en(t, self.tempos)})   # segundo en que suena
            fin_previo = max(fin_previo, final)

        sistemas, actual, corte, previo = [], [], 0, None
        armadura = abs(self.armadura) * ANCHO_ALTERACION * z
        x = izq + 92 * z + armadura                           # clave, armadura y compás de 4/4 en el primer sistema
        for p in piezas:
            barra = bool(actual) and p["compas"] != previo
            if actual and x + (14 * z if barra else 0) + p["ancho"] > der:
                resto = actual[corte:] if 0 < corte < len(actual) and not barra else []   # el compás a medias baja entero
                sistemas.append(actual[:len(actual) - len(resto)])
                actual, corte, x = [], 0, izq + 58 * z + armadura
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
        todas = [p for s in sistemas for p in s]
        for t, raiz, tipo in self.acordes:   # cada acorde, sobre lo que suena cuando empieza
            p = next((p for p in reversed(todas) if p["t"] <= t + 0.05), todas[0] if todas else None)
            if p is not None:
                nombre = partituras.nombre_acorde(raiz, tipo, self.armadura)
                p["acorde"] = f'{p["acorde"]}  {nombre}' if p.get("acorde") else nombre
        for k, (t, bpm, texto) in enumerate(self.tempos):   # el tempo inicial y cada cambio, sobre su compás
            p = todas[0] if k == 0 and todas else next((p for p in todas if p["t"] >= t - 0.05), None)
            if p is not None:
                p["tempo"], p["tempo_t"] = partituras.marca_tempo(bpm, texto), t
        return sistemas

    def _componer(self):
        e, z = ESP * self.zoom, self.zoom
        self._papel = QRectF(26, 22, max(self.width() - 52, 500), 0)
        self.sistemas = self._repartir(self._papel.left() + 34 * z, self._papel.right() - 30 * z, z)
        cabecera, alto = 96 * z, self._alto_sistema(z)
        self._sis_y = [self._papel.top() + cabecera + self._sobre(z) + s * alto for s in range(len(self.sistemas))]
        self._papel.setHeight(cabecera + len(self.sistemas) * alto + 40 * z)
        self.setMinimumHeight(int(self._papel.bottom() + 26))
        self._marcas = {}  # zona de cada marca de tempo dibujada (segundo -> rectángulo): pulsarla la edita
        self._cajas = []   # zona sensible de cada nota; se calcula aquí y no al pintar, porque solo se pinta lo visible
        for piezas, base in zip(self.sistemas, self._sis_y):
            for p in piezas:
                for i in p["col"]:
                    clave = self._clave_nota(i)
                    pos = max(-10, min(17, partituras.posicion(self.notas[i][2], clave, self.armadura)[0]))
                    base_nota = base + (13 * e if clave == "fa" and self.piano else 0)
                    self._cajas.append((QRectF(p["x"] - 6 * z, base_nota - pos * e / 2 - e, 1.18 * e + 12 * z, 2 * e), i))

    def _clave_nota(self, i):
        """En piano, las notas bajo Do central se escriben en el pentagrama de la mano izquierda."""
        return "fa" if self.piano and self.notas[i][2] < 60 else ("sol" if self.piano else self.clave)

    def _banda(self, s):
        """Franja de la hoja que ocupa un sistema, con sus notas más agudas y graves y su texto."""
        e = ESP * self.zoom
        return QRectF(0, self._sis_y[s] - self._sobre(self.zoom) - e, self.width(), self._alto_sistema(self.zoom) + 2 * e)

    def marcar_sonando(self, indice):
        """Resalta la nota que suena (y repinta solo lo que cambia)."""
        if indice != self.sonando:
            previa, self.sonando = self.sonando, indice
            for i in (previa, indice):
                if i >= 0:
                    self.repintar_nota(i)

    def lugar_de(self, t):
        """(n.º de sistema, x) del instante t en la hoja, interpolando entre las notas y silencios que lo rodean."""
        anterior = None
        for s, piezas in enumerate(self.sistemas):
            for p in piezas:
                if p["t"] > t:
                    if anterior is None:
                        return s, p["x"]
                    s0, p0 = anterior
                    fin_x = p["x"] if s0 == s else p0["x"] + p0["ancho"]
                    fraccion = (t - p0["t"]) / max(p["t"] - p0["t"], 1e-6)
                    return s0, p0["x"] + (fin_x - p0["x"]) * min(1.0, fraccion)
                anterior = (s, p)
        return (anterior[0], anterior[1]["x"] + anterior[1]["ancho"]) if anterior else None

    def poner_cursor(self, t):
        """Lleva la línea de reproducción al segundo t (None la quita). Solo se repinta lo que cambia."""
        for lugar in (self.lugar_de(self.cursor) if self.cursor is not None else None, None):
            if lugar:
                self.update(self._banda(lugar[0]).toAlignedRect())
        self.cursor = t
        lugar = self.lugar_de(t) if t is not None else None
        if lugar:
            self.update(self._banda(lugar[0]).toAlignedRect())
        return lugar

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
        lugar = self.lugar_de(self.cursor) if self.cursor is not None and self.sistemas else None
        if lugar:   # la línea de reproducción, de arriba abajo del pentagrama
            e, base = ESP * self.zoom, self._sis_y[lugar[0]]
            g.setPen(QPen(QColor(SONANDO), max(2.0, 2.4 * self.zoom)))
            g.drawLine(QPointF(lugar[1], base - 11 * e / 2 - 8 * e / 2), QPointF(lugar[1], base + (16 if self.piano else 3) * e))

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
        f_acorde = self._fuente(15, z)
        f_tempo = self._fuente(13, z, serif=True)
        f_tempo.setBold(True)
        f_acorde.setBold(True)
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
                       (f"Piano · clave de Sol y Fa  ·  {self.tonalidad}" if self.piano else
                        f"{partituras.CLAVES[self.clave][0]}  ·  {self.tonalidad}" if self.notas else partituras.CLAVES[self.clave][0]))
        arm = partituras.alteraciones(self.armadura)
        ancho_arm = abs(self.armadura) * ANCHO_ALTERACION * z
        ligaduras = {}                                    # id de la columna -> (x, sistema) de su tramo anterior

        ancho = 1.18 * e                                  # ancho de una cabeza de nota
        for s, piezas, base in zip(numeros, sistemas, bases):
            y = lambda pos: base - pos * e / 2
            ultimo = s == total - 1
            fin = der if not ultimo or not piezas else min(der, piezas[-1]["x"] + piezas[-1]["ancho"] + 10 * z)
            g.setPen(linea)
            claves = (("sol", base), ("fa", base + 13 * e)) if self.piano else ((self.clave, base),)
            if self.piano:
                g.setPen(linea)
                g.drawLine(QPointF(izq - 8 * z, base - 8 * e), QPointF(izq - 8 * z, base + 13 * e))
                g.drawLine(QPointF(izq - 8 * z, base - 8 * e), QPointF(izq, base - 8 * e))
                g.drawLine(QPointF(izq - 8 * z, base + 13 * e), QPointF(izq, base + 13 * e))
            for clave_staff, base_staff in claves:
                ys = lambda pos, b=base_staff: b - pos * e / 2
                for l in range(5):
                    g.drawLine(QPointF(izq, ys(2 * l)), QPointF(fin, ys(2 * l)))
                g.drawLine(QPointF(izq, ys(0)), QPointF(izq, ys(8)))
                if ultimo:
                    g.drawLine(QPointF(fin - 5 * z, ys(0)), QPointF(fin - 5 * z, ys(8)))
                    g.fillRect(QRectF(fin - 2.5 * z, ys(8), 2.5 * z, 4 * e), QColor(TINTA))
                else:
                    g.drawLine(QPointF(fin, ys(0)), QPointF(fin, ys(8)))
                g.setFont(musica)
                g.drawText(QPointF(izq + 8 * z, ys(partituras.CLAVES[clave_staff][2])), G_CLAVE[clave_staff])
                if self.armadura:
                    signo = 1 if self.armadura > 0 else -1
                    for k, (letra, octava) in enumerate(ARMADURA_SOL[signo][:abs(self.armadura)]):
                        desplaza, maximo = DESPLAZA_CLAVE[clave_staff]
                        pos = octava * 7 + letra - 30 + desplaza
                        pos = pos - 7 if pos > maximo else pos + 7 if pos < -1 else pos
                        g.drawText(QPointF(izq + 40 * z + k * ANCHO_ALTERACION * z, ys(pos)), G_SOSTENIDO if signo > 0 else G_BEMOL)
            if s == 0:                                     # compás de 4/4
                g.drawText(QPointF(izq + 46 * z + ancho_arm, y(6)), G_CUATRO)
                g.drawText(QPointF(izq + 46 * z + ancho_arm, y(2)), G_CUATRO)
            elif piezas:
                g.setFont(f_peque)
                g.setPen(QColor(TENUE))
                g.drawText(QPointF(izq + 2, y(8) - 6 * z), str(piezas[0]["compas"] + 1))   # n.º de compás

            # la letra va justo bajo lo más bajo del sistema (cabezas o plicas hacia abajo), como en MuseScore,
            # y no a una distancia fija: si no, parece la letra del sistema siguiente
            graves = [partituras.posicion(self.notas[i][2], self._clave_nota(i), self.armadura)[0]
                      for p in piezas if not p["silencio"] for i in p["col"]]
            texto_y = 14.5 * e if self.piano else (max([1.4] + [0.5 - max(-10, q) / 2 for q in graves]) + 1.0) * e
            acorde_y = min(10.5, max([6.2] + [min(17, q) / 2 + 1.7 for q in graves])) * e   # sobre la nota más aguda
            compas_actual, estado = None, {}
            for p in piezas:
                x, col = p["x"], p["col"]
                if p.get("tempo"):
                    g.setFont(f_tempo)
                    g.setPen(QColor(TINTA))
                    y_tempo = base - acorde_y - (22 * z if self.acordes else 0)
                    x_tempo = x - 2
                    g.drawText(QPointF(x_tempo, y_tempo), p["tempo"])
                    if pantalla:   # se puede pulsar para cambiarlo
                        self._marcas[p["tempo_t"]] = QRectF(x_tempo - 4, y_tempo - 16 * z, QFontMetrics(f_tempo).horizontalAdvance(p["tempo"]) + 8, 22 * z)
                if p.get("acorde"):
                    g.setFont(f_acorde)
                    g.setPen(QColor(TINTA))
                    g.drawText(QPointF(x - 2, base - acorde_y), p["acorde"])
                if p["compas"] != compas_actual:           # las alteraciones valen hasta el final del compás
                    compas_actual, estado = p["compas"], {}
                if p["barra"]:
                    g.setPen(linea)
                    for _, base_staff in claves:
                        ys = lambda pos, b=base_staff: b - pos * e / 2
                        g.drawLine(QPointF(x - 14 * z, ys(0)), QPointF(x - 14 * z, ys(8)))
                if p["silencio"]:
                    simbolo, pos = G_SILENCIO[p["silencio"]]
                    g.setFont(musica)
                    g.setPen(QColor(TINTA))
                    g.drawText(QPointF(x + 4 * z, y(pos)), simbolo)
                    continue
                cantado = "" if p.get("ligada") else self._cantado(col)   # el tramo ligado no repite la sílaba
                if cantado:   # la letra, bajo el pentagrama y empezando en su nota; los nombres bajan una línea
                    canta_ya = pantalla and self.sonando in col          # la sílaba que se está cantando, resaltada
                    f_letra.setBold(canta_ya)
                    g.setFont(f_letra)
                    g.setPen(QColor(SONANDO if canta_ya else TINTA))
                    g.drawText(QPointF(x - 2, base + texto_y + 13 * z), cantado)
                for k, i in enumerate(col):
                    ini, final, tono, _v = self.notas[i]
                    clave_nota = self._clave_nota(i)
                    base_nota = base + (13 * e if clave_nota == "fa" and self.piano else 0)
                    y_nota = lambda pos, b=base_nota: b - pos * e / 2
                    pos, _ = partituras.posicion(tono, clave_nota, self.armadura)
                    pos = max(-10, min(17, pos))           # fuera de ese margen no cabría en el sistema
                    negras = p["negras"] or partituras.negras_en(final, self.tempos) - partituras.negras_en(ini, self.tempos)
                    fig, puntillo = partituras.figura_y_puntillo(negras * 60 / self.bpm, self.bpm)
                    letra_n, alt, octava = partituras.deletrear(tono, self.armadura)
                    vigente = estado.get((letra_n, octava), arm.get(letra_n, 0))
                    estado[(letra_n, octava)] = alt
                    color = QColor(ELEGIDA if i == sel else SONANDO if i == self.sonando and pantalla else TINTA)
                    g.setPen(QPen(color, max(1.0, 1.1 * z)))
                    for extra in [q for q in range(-2, pos - 1, -2)] + [q for q in range(10, pos + 1, 2)]:
                        g.drawLine(QPointF(x - 5 * z, y_nota(extra)), QPointF(x + ancho + 5 * z, y_nota(extra)))   # líneas adicionales
                    g.setFont(musica)
                    g.drawText(QPointF(x, y_nota(pos)), G_CABEZA.get(fig, G_NEGRA))
                    if alt != vigente and not p.get("ligada"):   # alteración solo si cambia lo que rige en el compás
                        g.drawText(QPointF(x - 1.15 * e, y_nota(pos)), {1: G_SOSTENIDO, -1: G_BEMOL, 0: G_BECUADRO}[alt])
                    arriba = pos < 4
                    if p.get("ligada"):                    # ligadura desde el tramo anterior de la misma nota
                        x0, s0 = ligaduras.get((id(col), i), (izq + 60 * z + ancho_arm, s))
                        x0 = x0 if s0 == s else izq + 60 * z + ancho_arm
                        yl = y_nota(pos) + (0.9 if arriba else -0.9) * e
                        curva = QPainterPath(QPointF(x0 + ancho + 2 * z, yl))
                        curva.cubicTo(QPointF(x0 + ancho + 8 * z, yl + (0.9 if arriba else -0.9) * e),
                                      QPointF(x - 6 * z, yl + (0.9 if arriba else -0.9) * e), QPointF(x - 1 * z, yl))
                        g.setBrush(Qt.NoBrush)
                        g.drawPath(curva)
                    ligaduras[(id(col), i)] = (x, s)
                    if puntillo:   # a la derecha de la cabeza, siempre en un espacio
                        g.drawText(QPointF(x + ancho + 3 * z, y_nota(pos if pos % 2 else pos + 1)), G_PUNTILLO)
                    if fig != "redonda":
                        xp = x + ancho - 0.6 if arriba else x + 0.6
                        punta = y_nota(pos) + (-3.4 if arriba else 3.4) * e
                        g.drawLine(QPointF(xp, y_nota(pos)), QPointF(xp, punta))
                        if (fig, arriba) in G_CORCHETE:
                            g.drawText(QPointF(xp - 0.5, punta), G_CORCHETE[(fig, arriba)])
                    if i == sel:                            # marco de selección, como en un editor
                        g.setPen(QPen(QColor(ELEGIDA), 1, Qt.DashLine))
                        g.drawRoundedRect(QRectF(x - 6 * z, y_nota(pos) - 1.1 * e, ancho + 12 * z, 2.2 * e), 3, 3)
                        if pantalla and self.insertar:      # cursor de introducción: ahí irá la próxima nota
                            g.fillRect(QRectF(x + p["ancho"] - 6 * z, y(9), 5 * z, 5 * e), QColor(15, 157, 143, 90))
                    if self.nombres and k < 2 and not p.get("ligada"):              # nombres bajo el pentagrama; en acordes, del grave al agudo
                        g.setFont(f_nombre)
                        g.setPen(color if i == sel else QColor(NOMBRE))   # azul: nunca se confunde con la letra
                        g.drawText(QRectF(x - 20 * z, base + texto_y + (19 * z if hay_letra else 0) + 14 * z * k, ancho + 40 * z, 16 * z),
                                   Qt.AlignCenter, partituras.solfeo(tono, self.armadura))
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
                bases = [arriba + self._sobre(1.0) + k * alto for k in range(len(pagina))]
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
            return 0, 0, self.clave
        e = ESP * self.zoom
        s = min(range(len(self._sis_y)), key=lambda k: abs(self._sis_y[k] - 2 * e - y))
        base = self._sis_y[s]
        if self.piano and y > base + 2.5 * e:
            base += 13 * e
            return s, round((base - y) / (e / 2)), "fa"
        return s, round((base - y) / (e / 2)), "sol" if self.piano else self.clave

    def mousePressEvent(self, ev):
        self.setFocus()
        for t, caja in self._marcas.items():
            if caja.contains(ev.position()):
                return self.tempo_pedido.emit(t)
        for caja, i in self._cajas:
            if caja.contains(ev.position()):
                clave = self._clave_nota(i)
                self._arrastre = [i, ev.position().y(), partituras.posicion(self.notas[i][2], clave)[0], 0, True, clave]
                return self.elegida.emit(i)
        if self.insertar:   # clic en el pentagrama: nota nueva a esa altura, tras la nota que queda a su izquierda
            s, pos, clave = self._sistema_en(ev.position().y())
            if -10 <= pos <= 17:
                antes = [p for k in range(s + 1) for p in self.sistemas[k] if p["col"] and (k < s or p["x"] <= ev.position().x())]
                self.insertada.emit(antes[-1]["col"][-1] if antes else -1, partituras.midi_de(pos, clave))

    def mouseMoveEvent(self, ev):
        if not self._arrastre:   # ficha de la nota bajo el cursor
            i = next((i for caja, i in self._cajas if caja.contains(ev.position())), -1)
            texto = partituras.descripcion(self.notas[i], self.bpm, self.letra[i] if i < len(self.letra) else "") if i >= 0 else ""
            return QToolTip.showText(ev.globalPosition().toPoint(), texto, self) if texto else QToolTip.hideText()
        if self._arrastre:   # arrastrar una nota arriba o abajo cambia su altura, un paso por línea o espacio
            i, y0, pos0, ultimo, primero, clave = self._arrastre
            pasos = round((y0 - ev.position().y()) / (ESP * self.zoom / 2))
            if pasos != ultimo:
                self._arrastre[3], self._arrastre[4] = pasos, False
                self.arrastrada.emit(i, partituras.midi_de(pos0 + pasos, clave), primero)

    def mouseReleaseEvent(self, _):
        if self._arrastre and self._arrastre[3]:   # al soltar se recalculan las zonas sensibles con la altura final
            self._componer()
            self.update()
        self._arrastre = None

    def keyPressEvent(self, ev):
        accion, ctrl, mayus = self.TECLAS.get(ev.key()), ev.modifiers() & Qt.ControlModifier, ev.modifiers() & Qt.ShiftModifier
        letra = chr(ev.key()) if Qt.Key_A <= ev.key() <= Qt.Key_G else ""
        numero = chr(ev.key()) if Qt.Key_0 <= ev.key() <= Qt.Key_9 else ""
        if ctrl and ev.key() == Qt.Key_L:
            accion = "letra"
        elif ctrl and (letra or accion in ("modo", "silencio", "puntillo")):
            accion = None                        # Ctrl+C y similares no escriben notas
        elif letra:
            accion = ("acorde:" if mayus else "nota:") + letra
        elif numero in partituras.TECLAS_FIGURA:
            accion = "fig:" + partituras.TECLAS_FIGURA[numero]
        elif ctrl and ev.key() == Qt.Key_Z:
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
