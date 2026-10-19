"""Sección Partituras: grabar o importar, detectar notas, revisar/corregir y exportar."""
import json
import shutil
import time
from pathlib import Path

from PySide6.QtCore import QEvent, Qt, QTimer, Signal
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QMenu, QSlider, QFileDialog, QFrame, QHBoxLayout, QHeaderView, QLineEdit, QProgressBar,
                               QScrollArea, QSpinBox, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from .. import audio, config, editor, equipo, exportar, lanzar, letras, partituras, proyectos, rutas, separacion, tareas
from . import tema
from .captura import PanelCaptura
from .pentagrama import Pentagrama, fuente_musical

ATAJOS = ("Atajos, iguales a los de MuseScore:\n"
          "N: entrar o salir del modo de introducción de notas\n"
          "3 4 5 6 7: semicorchea, corchea, negra, blanca, redonda · punto: puntillo\n"
          "A B C D E F G: La Si Do Re Mi Fa Sol (en modo introducir escriben la nota; fuera de él cambian la elegida)\n"
          "Mayús + letra: añadir esa nota al acorde · 0: silencio\n"
          "↑ ↓: semitono · Ctrl + ↑ ↓: octava · ← →: nota anterior o siguiente · Mayús + ← →: mover en el tiempo\n"
          "Ctrl+L: escribir la letra (espacio o guion pasan a la nota siguiente) · Supr: borrar\n"
          "Ctrl+Z / Ctrl+Y: deshacer y rehacer · Espacio: oír · Esc: salir del modo o quitar la selección")
SEGMENTO_VIVO_S = 3  # cada cuánto se analiza lo recién grabado para el borrador en vivo


class PaginaPartituras(QWidget):
    cambio = Signal()  # se creó o modificó un proyecto

    def __init__(self):
        super().__init__()
        self.setObjectName("pagina")
        self.proyecto = None   # carpeta del proyecto abierto
        self.version = None    # resultado mostrado: {'midi', 'musicxml', 'notas', …}
        self._hist, self._rehechos, self._fig_nueva, self._sonando = [], [], "negra", False
        self._t0, self._base_barra = 0.0, 0   # inicio del análisis en curso y desde dónde avanza la barra
        self._espera = 0.0     # silencios tecleados antes de la próxima nota, en segundos
        self.notas, self.bpm, self.tarea, self._cargando = [], 120, None, False
        self.letra = []        # texto cantado bajo cada nota (paralela a self.notas)
        self.acordes = []      # [[segundo, raíz, tipo], …] de la canción, encima del pentagrama
        self.tempos = []       # [[segundo, bpm, indicación], …]: tempo inicial y sus cambios
        self._parando = False  # se pidió parar: el análisis termina con lo que lleve hecho
        self._hasta = None     # segundo en que se paró la letra (paso 1), para escribir la partitura hasta ahí
        self.vivo = None       # motor del borrador en vivo mientras se graba
        self._ultima, self._grababa, self._hubo_vivo, self._auto = {}, False, False, False

        # -- columna izquierda: entrada ------------------------------------
        self.nombre = QLineEdit()
        self.nombre.setPlaceholderText("Nombre de la toma (opcional)")
        self.destino = config.cargar()["carpeta_proyectos"]
        self.e_destino = tema.etiqueta("", "tenue")
        self.en_vivo = QCheckBox("Ver las notas mientras grabo (borrador)")
        self.en_vivo.setChecked(True)
        self.en_vivo.setToolTip("Las notas van apareciendo cada pocos segundos. Al detener se analiza la toma completa, que es más precisa.")
        self.captura = PanelCaptura("partitura", lambda: self.nombre.text().strip(), lambda: self.destino or None,
                                    lambda: SEGMENTO_VIVO_S if self.en_vivo.isChecked() and lanzar.instalado("partituras") else 0)
        self.captura.terminada.connect(self._toma_lista)
        self.captura.segmento.connect(self._segmento_vivo)
        self.captura.estado.connect(self._al_cambiar_captura)
        self.b_importar = tema.boton("Importar audio…", self.importar, ayuda="WAV, MP3, FLAC u OGG")
        t1, v1 = tema.tarjeta("1 · Grabar o importar")
        v1.addLayout(tema.fila(self.nombre, tema.boton("Carpeta…", self.elegir_destino), estirar=self.nombre))
        v1.addWidget(self.e_destino)
        v1.addWidget(self.captura)
        v1.addWidget(self.en_vivo)
        v1.addLayout(tema.fila(tema.etiqueta("¿Ya tienes el audio en un archivo?", "tenue", False), None, self.b_importar))

        self.e_toma = tema.etiqueta("Ninguna toma abierta. Graba, importa un audio o abre un proyecto.", "tenue")
        self.tempo = QSpinBox()
        self.tempo.setRange(0, 240)
        self.tempo.setSpecialValueText("Automático")
        self.tempo.setSuffix(" pulsos/min")
        self.tempo.setToolTip("Tempo con el que se escribe la partitura. «Automático» lo estima del audio.")
        self.b_pulso = tema.boton("Marcar pulso", self._marcar_pulso,
                                  ayuda="Pulsa este botón al ritmo de la canción (4 veces o más) y el tempo se fija solo")
        self._toques = []
        self.con_letra = QCheckBox("Canción: melodía de la voz cantada con su letra")
        self.con_letra.setChecked(config.cargar().get("con_letra", True))
        self.con_letra.toggled.connect(self._guardar_con_letra)
        self.b_transcribir = tema.boton("Detectar notas y crear partitura", self.transcribir, "primario")
        self.b_cancelar = tema.boton("Parar (conserva lo hecho)", self.cancelar,
                                     ayuda="Termina ya y crea la partitura con lo analizado hasta ahora. Pulsa otra vez para cancelar del todo")
        self.b_oir = tema.boton("Escuchar audio", lambda: tema.abrir_en_sistema(self._audio()), ayuda="Abre el audio original en tu reproductor")
        self.barra = QProgressBar()
        self.barra.setRange(0, 1000)
        self.barra.setTextVisible(False)
        self.e_estado = tema.etiqueta("", "tenue")
        t2, v2 = tema.tarjeta("2 · Convertir en partitura")
        v2.addWidget(self.e_toma)
        v2.addLayout(tema.fila(tema.etiqueta("Tempo", "tenue", False), self.tempo, self.b_pulso, None, self.b_oir))
        v2.addWidget(self.con_letra)
        self.modelo_letra = QComboBox()
        self.modelo_letra.setToolTip("Modelo de voz con el que se reconoce la letra. Para canciones, «large-v3» acierta "
                                     "claramente más; los pequeños son más rápidos. Se descargan en la sección Letras.")
        self.modelo_letra.currentIndexChanged.connect(self._guardar_modelo_letra)
        self.e_modelo_letra = tema.etiqueta("", "tenue")
        v2.addLayout(tema.fila(tema.etiqueta("Letra con", "tenue", False), self.modelo_letra, estirar=self.modelo_letra))
        v2.addWidget(self.e_modelo_letra)
        v2.addLayout(tema.fila(self.b_transcribir, self.b_cancelar, estirar=self.b_transcribir))
        v2.addWidget(self.barra)
        v2.addWidget(self.e_estado)


        # -- la partitura, en el centro ------------------------------------------
        a = config.cargar()
        self.vista = Pentagrama()
        self.vista.cambiar_zoom(a.get("zoom", 100) / 100)
        self.vista.elegida.connect(lambda i: self.tabla.selectRow(i))
        self.vista.tecla.connect(self._atajo)
        self.vista.arrastrada.connect(self._arrastrar)
        self.vista.insertada.connect(self._insertar)
        rollo = self.rollo = QScrollArea()
        rollo.setWidget(self.vista)
        rollo.setWidgetResizable(True)
        rollo.setFrameShape(QFrame.NoFrame)
        rollo.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        # -- barra de archivo ---------------------------------------------------
        self.b_regenerar = tema.boton("Guardar versión", self.regenerar, "primario",
                                      "Crea MIDI y MusicXML nuevos con tus correcciones (no pisa los anteriores)")
        self.b_midi = tema.boton("MIDI…", lambda: self._copiar("midi", "MIDI (*.mid)"), ayuda="Guardar una copia del MIDI")
        self.b_xml = tema.boton("MusicXML…", lambda: self._copiar("musicxml", "MusicXML (*.musicxml)"), ayuda="Guardar una copia del MusicXML")
        self.b_pdf = tema.boton("PDF…", self.exportar_pdf, ayuda="Exportar a PDF la partitura que se ve, con tus correcciones")
        self.b_musescore = tema.boton("MuseScore", self.abrir_musescore, ayuda="Opcional: abrir el MusicXML guardado en MuseScore Studio")
        self.b_nueva = tema.boton("Nueva", self.nueva, ayuda="Partitura en blanco para escribirla a mano")
        self.b_existente = tema.boton("Abrir…", self.abrir_existente,
                                      ayuda="Abrir un MusicXML, MXL o MIDI existente como partitura editable")
        self.b_deshacer = tema.boton("↶", lambda: self._deshacer(), ayuda="Deshacer (Ctrl+Z)")
        self.b_rehacer = tema.boton("↷", lambda: self._deshacer(True), ayuda="Rehacer (Ctrl+Y)")
        self.b_reproducir = tema.boton("▶", self.reproducir, "primario",
                                       "Reproducir o pausar (Espacio). La partitura y la letra siguen a la música")
        self.b_reproducir.setFixedWidth(46)
        self.b_detener = tema.boton("⏹", lambda: self.detener(), ayuda="Parar y volver al principio")
        self.posicion = QSlider(Qt.Horizontal)
        self.posicion.setMinimumWidth(140)
        self.posicion.setToolTip("Posición: arrastra para ir a otro punto de la canción")
        self.posicion.sliderReleased.connect(self._saltar)
        self.posicion.sliderMoved.connect(lambda v: self.e_tiempo.setText(f"{v // 600}:{v // 10 % 60:02d}"))
        self.e_tiempo = tema.etiqueta("0:00 / 0:00", "tenue", False)
        self.oir_que = QComboBox()
        self.oir_que.addItem("Partitura", None)
        self.oir_que.setToolTip("Qué se oye: la canción original, la voz aislada o la partitura tal como está escrita")
        self.oir_que.activated.connect(lambda _: self._elegir_fuente())
        self._fuente_a_mano, self._pos, self._duracion, self._reproduccion = False, 0.0, 0.0, (0.0, 0.0)
        self._seguir = QTimer(self)
        self._seguir.setInterval(40)
        self._seguir.timeout.connect(self._seguir_reproduccion)
        self.b_letra = tema.boton("Reconocer letra", self.poner_letra)
        self.b_escribir_letra = tema.boton("Escribir letra…", self.escribir_letra,
                                           ayuda="Escribe o pega la letra completa: se reparte en sílabas, una por nota")
        self.b_carpeta = tema.boton("Carpeta", lambda: tema.abrir_en_sistema(self.proyecto), ayuda="Ver la carpeta del proyecto")
        self.b_panel_izq = tema.boton("Grabación", ayuda="Mostrar u ocultar el panel de grabación y análisis")
        self.b_panel_der = tema.boton("Lista de notas", ayuda="Mostrar u ocultar la tabla con los valores exactos de cada nota")
        for b in (self.b_panel_izq, self.b_panel_der):
            b.setCheckable(True)
        # Exportar agrupa PDF, MIDI, MusicXML, MuseScore y carpeta en un menú: la barra cabe en pantallas de 1366 px
        def desplegable(texto, ayuda, botones, nombres):
            """Botón con menú: cada opción pulsa uno de los botones (que conservan su estado activo o no)."""
            boton = tema.boton(texto, ayuda=ayuda)
            menu = QMenu(boton)
            for b, nombre in zip(botones, nombres):
                accion = menu.addAction(nombre)
                accion.triggered.connect(b.click)
                accion.setData(b)
            menu.aboutToShow.connect(lambda: [a.setEnabled(a.data().isEnabled()) for a in menu.actions()])
            boton.setMenu(menu)
            return boton
        self.b_letras = desplegable("Letra ▾", "Reconocer la letra del audio o escribirla a mano", (self.b_letra, self.b_escribir_letra),
                                    ("Reconocer la letra del audio", "Escribir la letra a mano…"))
        self.b_exportar = desplegable("Exportar ▾", "PDF, MIDI, MusicXML, abrir en MuseScore o ver la carpeta",
                                      (self.b_pdf, self.b_midi, self.b_xml, self.b_musescore, self.b_carpeta),
                                      ("PDF…", "MIDI…", "MusicXML…", "Abrir en MuseScore", "Ver la carpeta del proyecto"))
        self.oir_que.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.oir_que.setMinimumContentsLength(14)
        self.posicion.setMinimumWidth(110)
        archivo = tema.herramientas(self.b_nueva, self.b_existente, self.b_regenerar, "|", self.b_deshacer, self.b_rehacer, "|",
                                    self.b_reproducir, self.b_detener, self.posicion, self.e_tiempo, self.oir_que, "|",
                                    self.b_letras, self.b_exportar,
                                    None, self.b_panel_izq, self.b_panel_der)

        # -- barra de introducción de notas ---------------------------------------
        self.b_fig = {}
        familia = fuente_musical()
        for fig, simbolo in (("redonda", "\ue1d2"), ("blanca", "\ue1d3"), ("negra", "\ue1d5"), ("corchea", "\ue1d7"), ("semicorchea", "\ue1d9")):
            b = tema.boton(simbolo if familia else fig[:3], lambda f=fig: self._figura(f), "figura", f"Convertir la nota elegida en {fig}")
            b.setCheckable(True)
            if familia:
                b.setStyleSheet(f"font-family: '{familia}'; font-size: 22px; padding: 0px;")
            b.setFixedSize(42, 42)
            self.b_fig[fig] = b
        self.b_puntillo = tema.boton("·", lambda: self._puntillo(), "figura", "Puntillo: figura y media (tecla punto)")
        self.b_puntillo.setCheckable(True)
        self.b_puntillo.setFixedSize(30, 42)
        self.b_sube = tema.boton("♯ ↑", lambda: self._mover(1), ayuda="Subir un semitono (flecha arriba)")
        self.b_baja = tema.boton("♭ ↓", lambda: self._mover(-1), ayuda="Bajar un semitono (flecha abajo)")
        self.b_octava_sube = tema.boton("8ª ↑", lambda: self._mover(12), ayuda="Subir una octava (Ctrl + flecha arriba)")
        self.b_octava_baja = tema.boton("8ª ↓", lambda: self._mover(-12), ayuda="Bajar una octava (Ctrl + flecha abajo)")
        self.b_insertar = tema.boton("✎ Introducir", ayuda="Modo de introducción de notas (N): elige figura con 3-7 y escribe con las teclas "
                                                           "A-G o haciendo clic en el pentagrama")
        self.b_insertar.setCheckable(True)
        self.b_insertar.toggled.connect(self.vista.modo_insertar)
        self.b_insertar.toggled.connect(lambda si: (self.b_puntillo.setChecked(False) if si else None, self._botones()))
        self.b_antes = tema.boton("◀", lambda: self._desplazar(-1), ayuda="Adelantar la nota una semicorchea (Mayús + ←)")
        self.b_despues = tema.boton("▶", lambda: self._desplazar(1), ayuda="Retrasar la nota una semicorchea (Mayús + →)")
        self.b_anadir = tema.boton("+ Nota", self._anadir, ayuda="Añadir una nota igual después de la elegida")
        self.b_borrar = tema.boton("Borrar", self._borrar, "peligro", "Borrar la nota elegida (Supr)")
        self.e_letra = QLineEdit()
        self.e_letra.setPlaceholderText("Letra de la nota")
        self.e_letra.setFixedWidth(150)
        self.e_letra.editingFinished.connect(self._letra_editada)
        self.e_letra.installEventFilter(self)
        self.clave = QComboBox()
        self.clave.addItem("Clave automática", "")
        for codigo, (nombre, _, _) in partituras.CLAVES.items():
            self.clave.addItem(nombre, codigo)
        self.clave.setCurrentIndex(max(0, self.clave.findData(a["clave"])))
        self.clave.setToolTip("Clave del pentagrama. También se usa en el MusicXML de la próxima partitura o versión que crees.")
        self.nombres = QCheckBox("Nombre de cada nota")
        self.nombres.setChecked(a["nombres"])
        self.nombres.setToolTip("Escribe bajo cada nota lo que es (Do, Re, Mi, Fa♯…), aquí y en el MusicXML/PDF. "
                                "Al pasar el ratón sobre una nota se ve además su octava, su figura y su duración.")
        self.tonalidad = QComboBox()
        self.tonalidad.addItem("Tonalidad automática", None)
        for q in range(-6, 7):
            self.tonalidad.addItem(partituras.nombre_armadura(q) + (f"  ({abs(q)} {'♯' if q > 0 else '♭'})" if q else "  (sin alteraciones)"), q)
        self.tonalidad.setCurrentIndex(max(0, self.tonalidad.findData(a.get("tonalidad"))) if a.get("tonalidad") is not None else 0)
        self.tonalidad.setToolTip("Armadura con la que se escribe la partitura. «Automática» la deduce de las notas.")
        self.tonalidad.currentIndexChanged.connect(self._cambio_de_vista)
        self.clave.currentIndexChanged.connect(self._cambio_de_vista)
        self.nombres.toggled.connect(self._cambio_de_vista)
        self.e_zoom = tema.etiqueta(f"{round(self.vista.zoom * 100)} %", "tenue", False)
        notas_barra = tema.herramientas(self.b_insertar, *self.b_fig.values(), self.b_puntillo, "|", self.b_sube, self.b_baja, self.b_octava_sube,
                                        self.b_octava_baja, self.b_antes, self.b_despues, "|",
                                        self.b_anadir, self.b_borrar, "|", self.e_letra, "|", self.nombres, None)

        # -- panel derecho: lista de notas ----------------------------------------
        self.tabla = QTableWidget(0, 5)
        self.tabla.setHorizontalHeaderLabels(["Inicio", "Dur.", "MIDI", "Nota", "Letra"])
        self.tabla.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tabla.verticalHeader().setDefaultSectionSize(26)
        self.tabla.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tabla.setAlternatingRowColors(True)
        self.tabla.itemChanged.connect(self._celda_editada)
        self.tabla.itemSelectionChanged.connect(lambda: (setattr(self, "_espera", 0.0), self._desde_nota_elegida(), self._dibujar(), self._botones()))
        t3, v3 = tema.tarjeta("Lista de notas")
        v3.addWidget(tema.etiqueta("Inicio y duración en segundos. Doble clic en una celda para cambiarla.", "tenue"))
        v3.addWidget(self.tabla, 1)
        t3.setMinimumWidth(350)
        t3.setMaximumWidth(420)

        izquierda = tema.columna(t1, t2)
        izquierda.setMaximumWidth(izquierda.minimumWidth() + 30)
        self.b_panel_izq.toggled.connect(izquierda.setVisible)
        self.b_panel_der.toggled.connect(lambda si: (t3.setVisible(si), self._guardar_panel(si)))
        self.b_panel_izq.setChecked(True)
        self.b_panel_der.setChecked(a.get("panel_notas", False))
        t3.setVisible(self.b_panel_der.isChecked())

        aviso = tema.etiqueta(partituras.AVISO_BREVE, "aviso", False)
        aviso.setToolTip(partituras.LIMITACIONES)
        aviso.setMinimumWidth(120)            # puede recortarse en ventanas estrechas; el texto completo está en la ayuda
        self.b_atajos = tema.boton("Atajos de teclado", lambda: tema.dialogo(self, "Atajos de teclado", ATAJOS),
                                   ayuda="N introducir · 3-7 figura · A-G nota · 0 silencio · . puntillo · Ctrl+L letra…")
        # clave, nombres y zoom van abajo, como en la barra de estado de un editor de partituras
        self.b_tempo = tema.boton("Tempo…", self.editar_tempo,
                                  ayuda="Tempo e indicación (Andante, Allegro…) desde el compás de la nota elegida; sin nota elegida, el del principio")
        pie = tema.herramientas(aviso, None, self.b_atajos, "|", self.clave, self.tonalidad, self.b_tempo, "|",
                                tema.boton("−", lambda: self._zoom(-10), ayuda="Reducir"), self.e_zoom,
                                tema.boton("+", lambda: self._zoom(10), ayuda="Ampliar"))

        cuerpo = QHBoxLayout()
        cuerpo.setContentsMargins(12, 12, 12, 8)
        cuerpo.setSpacing(12)
        cuerpo.addWidget(izquierda)
        cuerpo.addWidget(rollo, 1)
        cuerpo.addWidget(t3)
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        v.addWidget(archivo)
        v.addWidget(notas_barra)
        v.addLayout(cuerpo, 1)
        v.addWidget(pie)
        self._pintar_destino()
        self._botones()

    # -- estado -----------------------------------------------------------
    @property
    def ocupada(self):
        return self.captura.grabando or self.tarea is not None

    def _audio(self):
        if self.proyecto:
            a = proyectos.leer(self.proyecto).get("audio")
            if a and (self.proyecto / a).is_file():
                return self.proyecto / a
        return None

    def _archivo(self, clave):
        if self.proyecto and self.version and self.version.get(clave):
            return self.proyecto / self.version[clave]
        return None

    def _botones(self):
        analizando, grabando = self.tarea is not None, self.captura.grabando
        audio = self._audio() is not None
        hay = self.version is not None and not analizando
        exe, origen = editor.buscar()
        self.b_importar.setEnabled(not analizando and not grabando)
        self.en_vivo.setEnabled(not grabando)
        self.b_transcribir.setEnabled(audio and not analizando and not grabando)
        self.b_cancelar.setEnabled(analizando)
        self.b_oir.setEnabled(audio)
        self.tempo.setEnabled(not analizando)
        modelo = config.cargar()["modelo"]
        self.con_letra.setEnabled(not analizando and letras.instalado(modelo))
        self._recargar_modelos_letra()
        self.modelo_letra.setEnabled(not analizando and self.modelo_letra.count() > 0)
        for w in (self.modelo_letra, self.e_modelo_letra):
            w.setVisible(self.con_letra.isChecked())
        self.con_letra.setToolTip(
            "Para canciones: aísla la voz de los instrumentos, escribe la melodía que se canta (una sola línea) y pone "
            f"cada palabra de la letra bajo su nota. Reconoce la letra con el modelo «{letras.para_canto(modelo)}». "
            "Desmárcalo para piezas solo instrumentales: entonces las notas salen de todo el audio."
            if letras.instalado(modelo) else f"Primero descarga el modelo de voz «{modelo}» en la sección Letras.")
        fila = self.tabla.currentRow()
        elegida = hay and 0 <= fila < len(self.notas)
        for b in (self.b_sube, self.b_baja, self.b_octava_sube, self.b_octava_baja, self.b_antes, self.b_despues, self.b_borrar, self.e_letra):
            b.setEnabled(elegida)
        for b in self.b_fig.values():   # sin nota elegida, las figuras eligen la duración de la próxima nota que se introduzca
            b.setEnabled(hay)
        editando = elegida and not self.b_insertar.isChecked()   # las figuras muestran la nota elegida o, al introducir, la próxima
        actual = partituras.figura(self.notas[fila][1] - self.notas[fila][0], self.tempo.value() or self.bpm) if editando else self._fig_nueva
        for fig, b in self.b_fig.items():
            b.setChecked(fig == actual)
        self.b_puntillo.setEnabled(hay)
        if editando:
            self.b_puntillo.setChecked(partituras.figura_y_puntillo(self.notas[fila][1] - self.notas[fila][0], self.tempo.value() or self.bpm)[1])
        if not self.e_letra.hasFocus():
            self.e_letra.setText(self.letra[fila] if elegida and fila < len(self.letra) else "")
        guardada = hay and bool(self.version.get("midi"))
        self.b_anadir.setEnabled(hay)
        self.b_insertar.setEnabled(hay)
        if not hay and self.b_insertar.isChecked():
            self.b_insertar.setChecked(False)
        self.b_deshacer.setEnabled(hay and bool(self._hist))
        self.b_rehacer.setEnabled(hay and bool(self._rehechos))
        self.b_reproducir.setEnabled(bool(self.notas) and not grabando)
        for w in (self.b_detener, self.posicion):
            w.setEnabled(bool(self.notas) and not grabando)
        self.b_letra.setEnabled(hay and bool(self.notas) and audio and letras.instalado(modelo))
        self.b_escribir_letra.setEnabled(hay and bool(self.notas))
        self.b_letra.setToolTip(
            "Reconoce la voz del audio de este proyecto y escribe cada palabra bajo su nota, sin volver a detectar las notas"
            if letras.instalado(modelo) else f"Primero descarga el modelo de voz «{modelo}» en la sección Letras")
        self.b_regenerar.setEnabled(hay and bool(self.notas))
        self.b_tempo.setEnabled(hay and bool(self.notas))
        self.b_pdf.setEnabled(hay and bool(self.notas))
        self.b_midi.setEnabled(guardada)
        self.b_xml.setEnabled(guardada)
        self.b_carpeta.setEnabled(self.proyecto is not None)
        self.b_nueva.setEnabled(not analizando and not grabando)
        self.b_existente.setEnabled(not analizando and not grabando)
        self.b_musescore.setVisible(bool(exe))       # opcional: solo aparece si hay un MuseScore disponible
        self.b_musescore.setEnabled(guardada)

    def _pintar_destino(self):
        self.e_destino.setText(f"Se guardará en: {self.destino or rutas.PROYECTOS}"
                               + ("" if not self.destino or rutas.dentro_de(self.destino) else "  (fuera del programa: no se borra con él)"))

    def elegir_destino(self):
        c = tema.elegir_carpeta(self, "Carpeta donde guardar las tomas", self.destino or rutas.PROYECTOS)
        if c and tema.avisar_si_externo(self, c):
            self.destino = "" if Path(c) == rutas.PROYECTOS else c
            a = config.cargar()
            a["carpeta_proyectos"] = self.destino
            config.guardar(a)
            self._pintar_destino()

    # -- entrada ------------------------------------------------------------
    def importar(self):
        ruta, _ = QFileDialog.getOpenFileName(self, "Importar audio", "", f"Audio ({partituras.AUDIO});;Todos (*)")
        if not ruta:
            return
        try:
            d = proyectos.crear(self.nombre.text().strip() or Path(ruta).stem, "partitura", self.destino or None)
            proyectos.importar_audio(d, ruta)
        except OSError as e:
            return tema.error(self, "No se pudo importar", f"{e}\n\nComprueba que el archivo existe y que hay espacio libre.")
        self._auto = False
        self._toma_lista(d)

    def _toma_lista(self, carpeta):
        self.nombre.clear()
        self.abrir_proyecto(carpeta)
        self.cambio.emit()
        if self._auto and self._audio():  # tras el borrador en vivo, la partitura definitiva de la toma entera
            self._auto = False
            self.transcribir()

    # -- borrador en vivo -----------------------------------------------------
    def _al_cambiar_captura(self):
        grabando = self.captura.grabando
        if grabando and not self._grababa:      # empieza una toma: lienzo en blanco y motor en marcha
            self._hubo_vivo = self.en_vivo.isChecked() and lanzar.instalado("partituras")
            self.proyecto = self.version = None
            self._ultima, self.letra, self.acordes, self.tempos = {}, [], [], []
            self._poner_notas([], 120)
            self.e_toma.setText("Grabando una toma nueva…")
            self.e_estado.setText("Preparando el borrador en vivo: las primeras notas tardan unos segundos." if self._hubo_vivo else "")
            if self._hubo_vivo:
                self.vivo = tareas.Tarea("partitura_libre.workers.notas", [json.dumps({"cmd": "vivo"})], "partituras",
                                         lambda ev: tema.en_ui(lambda: self._notas_vivas(ev)))
        elif not grabando and self._grababa:
            self._parar_vivo()
            self._auto = self._hubo_vivo
        self._grababa = grabando
        self._botones()

    def _parar_vivo(self):
        if self.vivo:
            self.vivo.cancelar()
            self.vivo = None

    def _segmento_vivo(self, ruta, t0):
        if not (self.vivo and self.vivo.enviar(audio=str(ruta), desfase=t0)):
            Path(ruta).unlink(missing_ok=True)

    def _notas_vivas(self, ev):
        if ev["t"] != "notas" or not self.captura.grabando:
            return
        # Misma regla que al trocear audio largo: una nota que seguía sonando se alarga, no se duplica.
        partituras.integrar(self.notas, self._ultima, ev["notas"], ev["desfase"], ev["desfase"], float("inf"))
        self._poner_notas(self.notas, 120)
        self._ultima = {n[2]: n for n in self.notas}
        self.e_estado.setText(f"Borrador en vivo: {len(self.notas)} notas. Al detener se creará la partitura definitiva.")
        QTimer.singleShot(0, lambda: (self.rollo.verticalScrollBar().setValue(self.rollo.verticalScrollBar().maximum()),
                                     self.tabla.scrollToBottom()))

    def abrir_proyecto(self, carpeta):
        self.proyecto, self.version = Path(carpeta), None
        self._hist, self._rehechos = [], []
        d = proyectos.leer(self.proyecto)
        versiones = [r for r in d["resultados"] if r["tipo"] == "partitura" and (self.proyecto / r["notas"]).is_file()]
        marca = "  ·  ⚠ toma incompleta" if d.get("incompleta") else ""
        self.e_toma.setText(f"<b>{d['nombre']}</b>  ·  audio: {d.get('audio') or '—'}  ·  {len(versiones)} versión(es){marca}")
        self.e_estado.setText(" ".join(d.get("avisos", [])))
        self.barra.setValue(0)
        if versiones:
            self._mostrar(versiones[-1])
        else:
            self.letra, self.acordes, self.tempos = [], [], []
            if not d.get("audio"):
                self.version = {}             # partitura escrita a mano que aún no se ha guardado: se puede editar
            self._poner_notas([], 120)
        self._actualizar_fuentes()
        self._botones()

    # -- análisis -------------------------------------------------------------
    def _lanzar(self, orden, mensaje, seguir=False):
        """`seguir`: es el segundo paso de un análisis (la barra continúa desde el 40 %)."""
        if not seguir:
            self._t0 = time.monotonic()
        self._base_barra = 400 if seguir else 0
        self._parando = False
        self.barra.setValue(self._base_barra)
        self.e_estado.setText(mensaje)
        tema.reclasificar(self.e_estado, "tenue")
        carpeta = self.proyecto
        self.tarea = tareas.Tarea("partitura_libre.workers.notas", [json.dumps(orden)], "partituras",
                                  lambda ev: tema.en_ui(lambda: self._evento(ev, carpeta)),
                                  lambda codigo, cancelada: tema.en_ui(lambda: self._fin(codigo, cancelada, carpeta)))
        self._resultado = None
        self._botones()

    def _guardar_con_letra(self, si):
        a = config.cargar()
        a["con_letra"] = si
        config.guardar(a)
        self._botones()

    def _recargar_modelos_letra(self):
        """Lista los modelos de voz descargados; recuerda el elegido y, si no hay, propone el más preciso."""
        puestos = [m for m in letras.MODELOS if letras.instalado(m)]
        if [self.modelo_letra.itemData(i) for i in range(self.modelo_letra.count())] != puestos:
            elegido = config.cargar().get("modelo_canto") or letras.para_canto(config.cargar()["modelo"])
            self.modelo_letra.blockSignals(True)
            self.modelo_letra.clear()
            for m in puestos:
                recomendado = letras.para_canto(m)
                nota = ("  (recomendado en este equipo)" if m == recomendado else
                        "  (muy lento en este equipo)" if m in ("large-v3", "medium") and equipo.modesto() else "")
                self.modelo_letra.addItem(m + nota, m)
            self.modelo_letra.setCurrentIndex(max(0, self.modelo_letra.findData(elegido)))
            self.modelo_letra.blockSignals(False)
        m = self.modelo_letra.currentData()
        sep = "separa la voz de los instrumentos" if separacion.instalado() else "sin separador de voz (se pedirá al empezar)"
        self.e_modelo_letra.setText(
            f"{letras.MODELOS[m][3]}. Se {sep}." if m else "No hay ningún modelo de voz descargado: descárgalo en la sección Letras.")

    def _guardar_modelo_letra(self):
        a = config.cargar()
        a["modelo_canto"] = self.modelo_letra.currentData()
        config.guardar(a)
        self._recargar_modelos_letra()

    def transcribir(self):
        orden = {"cmd": "transcribir", "audio": str(self._audio()), "acordes_de": str(self._audio()), "carpeta": str(self.proyecto),
                 "nombre": self.proyecto.name, "bpm": self.tempo.value() or None, **self._notacion()}
        if self.con_letra.isChecked() and self.con_letra.isEnabled():
            if not separacion.instalado():   # sin separador, las notas saldrían de toda la mezcla y no de la voz
                return tema.descarga_con_dialogo(
                    self, "Hace falta el separador de voz",
                    "Para escribir la melodía que se CANTA (y no la de los instrumentos) primero hay que aislar la voz.\n\n"
                    f"• Descarga: {separacion.MB} MB, una sola vez, a models/separacion\n• {separacion.CREDITO}\n\n"
                    "Si es una pieza solo instrumental, cancela y desmarca «Canción»: las notas saldrán de todo el audio.",
                    separacion.descargar, lambda ok: self.transcribir() if ok else None)
            voz = rutas.ruta_unica(self.proyecto, "voz aislada", ".wav")

            def seguir(palabras, aviso):
                orden["palabras"], self._sin_letra = palabras, aviso
                if self._hasta is not None:   # parada en el paso 1: la partitura llega hasta donde llegó la letra
                    if not (palabras and voz.is_file()):
                        voz.unlink(missing_ok=True)
                        self._parando, self._hasta = False, None
                        self.e_estado.setText("Parado antes de reconocer la letra: no había nada que conservar. El audio original se conserva.")
                        return self._botones()
                    orden["hasta"] = self._hasta
                if palabras and voz.is_file():   # canción: la melodía se saca de la voz aislada, no de la mezcla
                    orden.update(audio=str(voz), melodia=True)
                    return self._lanzar(orden, "Paso 2 de 2 · Escribiendo la melodía de la voz…", seguir=True)
                voz.unlink(missing_ok=True)      # sin nada cantado no es una canción: notas de todo el audio
                self._sin_letra = "No se oye letra cantada: las notas salen de todo el audio, como en una pieza instrumental."
                self._lanzar(orden, "Paso 2 de 2 · Detectando las notas…", seguir=True)
            return self._reconocer_letra(seguir, "Paso 1 de 2 · ", guardar_voz=voz)
        self._lanzar(orden, "Preparando el análisis…")

    def poner_letra(self):
        """Añade la letra a la partitura que ya está abierta, a partir de su audio y sin volver a detectar las notas."""
        def colocar(palabras, aviso):
            self.barra.setValue(1000 if palabras else 0)
            if palabras:
                self._recordar()
                self.letra = partituras.asignar_letra(self.notas, palabras)
                self._poner_notas(self.notas, self.bpm, self.tabla.currentRow())
                con = sum(bool(t) for t in self.letra)
                self.e_estado.setText(f"Letra colocada bajo {con} nota(s). Corrígela si hace falta y pulsa «Guardar versión» "
                                      "para escribirla en el MusicXML." if con else
                                      "Se reconoció texto, pero ninguna palabra coincide en el tiempo con las notas.")
            else:
                self.e_estado.setText(aviso or "No se reconoció ninguna palabra en el audio.")
            self._botones()
        self._reconocer_letra(colocar, "")

    def _tempos(self):
        """Tempo inicial (el del selector si se puso a mano) y los cambios a lo largo de la partitura."""
        return partituras.tempos_de(self.tempo.value() or self.bpm, self.tempos)

    def editar_tempo(self):
        """Tempo desde el compás de la nota elegida: pulsos por minuto e indicación (o quitar ese cambio)."""
        from PySide6.QtWidgets import QDialog, QSpinBox
        fila = self.tabla.currentRow()
        tempos = self._tempos()
        t = self.notas[fila][0] if 0 <= fila < len(self.notas) else 0.0
        inicio = partituras.a_compas(t, tempos)
        vigente = next(x for x in reversed(tempos) if x[0] <= inicio + 0.01)
        cambio_aqui = inicio > 0.01 and abs(vigente[0] - inicio) <= 0.01
        d = QDialog(self)
        d.setWindowTitle("Tempo")
        v = QVBoxLayout(d)
        v.setContentsMargins(20, 18, 20, 16)
        compas = int(partituras.negras_en(inicio, tempos) // 4) + 1
        v.addWidget(tema.etiqueta(f"<b>Tempo desde el compás {compas}</b>" if inicio > 0.01 else "<b>Tempo del principio</b>"))
        v.addWidget(tema.etiqueta("Para poner un cambio de tempo más adelante, elige antes una nota de ese compás.", "tenue"))
        pulsos = QSpinBox()
        pulsos.setRange(20, 300)
        pulsos.setSuffix(" pulsos/min (♩)")
        pulsos.setValue(int(round(vigente[1])))
        texto = QComboBox()
        texto.setEditable(True)
        texto.addItem("Automática (según la velocidad)", "")
        for _limite, nombre in partituras.INDICACIONES:
            texto.addItem(nombre, nombre)
        if vigente[2]:
            texto.setCurrentText(vigente[2])
        muestra = tema.etiqueta("", "tenue")
        elegido = lambda: "" if texto.currentIndex() == 0 and texto.currentText() == texto.itemText(0) else texto.currentText().strip()
        actualizar = lambda *_: muestra.setText("Se escribirá: " + partituras.marca_tempo(pulsos.value(), elegido()))
        pulsos.valueChanged.connect(actualizar)
        texto.currentTextChanged.connect(actualizar)
        actualizar()
        v.addLayout(tema.fila(tema.etiqueta("Velocidad", "tenue", False), pulsos, None))
        v.addLayout(tema.fila(tema.etiqueta("Indicación", "tenue", False), texto, estirar=texto))
        v.addWidget(muestra)
        quitar = tema.boton("Quitar este cambio", lambda: d.done(2), "peligro")
        quitar.setVisible(cambio_aqui)
        v.addLayout(tema.fila(quitar, None, tema.boton("Cancelar", d.reject), tema.boton("Aplicar", d.accept, "primario")))
        r = d.exec()
        if r == QDialog.Rejected:
            return
        self.tempos = partituras.poner_tempo(tempos, inicio, 0 if r == 2 else pulsos.value(), elegido())
        if inicio <= 0.01:
            self.tempo.setValue(self.tempos[0][1])   # el tempo del principio es el del selector
        self._dibujar()
        self.e_estado.setText(("Cambio de tempo quitado." if r == 2 else "Tempo puesto: " + partituras.marca_tempo(pulsos.value(), elegido()) + ".")
                              + " Pulsa «Guardar versión» para escribirlo en el MusicXML.")

    def escribir_letra(self):
        """Letra escrita a mano: se reparte en sílabas, una por nota, sin tocar las notas."""
        from PySide6.QtWidgets import QDialog, QPlainTextEdit, QRadioButton
        d = QDialog(self)
        d.setWindowTitle("Escribir la letra")
        d.setMinimumSize(560, 420)
        v = QVBoxLayout(d)
        v.setContentsMargins(20, 18, 20, 16)
        v.addWidget(tema.etiqueta("<b>Escribe o pega la letra</b>"))
        v.addWidget(tema.etiqueta("Se divide sola en sílabas y se pone una bajo cada nota, en orden. Si una palabra se canta "
                                  "con otra división, escríbela con guiones (por ejemplo «be-be-ré»). Las notas no cambian.", "tenue"))
        texto = QPlainTextEdit(partituras.juntar([t for t in self.letra if t]))
        v.addWidget(texto, 1)
        fila = self.tabla.currentRow()
        desde_primera = QRadioButton("Desde la primera nota (sustituye toda la letra)")
        desde_elegida = QRadioButton(f"Desde la nota elegida (n.º {fila + 1})" if fila >= 0 else "Desde la nota elegida")
        desde_primera.setChecked(fila <= 0)
        desde_elegida.setChecked(fila > 0)
        desde_elegida.setEnabled(fila >= 0)
        v.addWidget(desde_primera)
        v.addWidget(desde_elegida)
        aceptar = tema.boton("Poner bajo las notas", d.accept, "primario")
        v.addLayout(tema.fila(None, tema.boton("Cancelar", d.reject), aceptar))
        if d.exec() != QDialog.Accepted:
            return
        desde = fila if desde_elegida.isChecked() and fila >= 0 else 0
        asignadas, sobran = partituras.repartir_texto(texto.toPlainText(), len(self.notas), desde)
        self._recordar()
        self.letra = (self.letra[:desde] if desde else []) + asignadas
        self.letra += [""] * (len(self.notas) - len(self.letra))
        self._poner_notas(self.notas, self.bpm, desde)
        self.e_estado.setText(f"Letra puesta bajo {len(asignadas)} nota(s)"
                              + (f"; sobraban {sobran} sílaba(s), escritas juntas en la última." if sobran else ".")
                              + " Pulsa «Guardar versión» para guardarla en el MusicXML.")

    def _reconocer_letra(self, al_acabar, paso, guardar_voz=None):
        """Voz a texto con el tiempo de cada palabra, para colocar cada una bajo su nota. Al terminar llama a
        `al_acabar(palabras, aviso)`; el texto completo queda guardado en el proyecto."""
        a, carpeta, frases, fallo = config.cargar(), self.proyecto, [], []
        self._t0 = time.monotonic()
        modelo = self.modelo_letra.currentData() or letras.para_canto(a["modelo"])
        self.barra.setValue(0)
        self.e_estado.setText(paso + "Reconociendo la letra (voz a texto)…")
        tema.reclasificar(self.e_estado, "tenue")

        def evento(ev):
            if self.tarea is not t:
                return
            if ev["t"] == "progreso":
                self.barra.setValue(int(ev["v"] * 200))
                self.e_estado.setText(paso + ev["msg"] + tema.quedan(self._t0, self.barra.value() / 1000))
            elif ev["t"] == "segmento":
                frases.append(ev)
                self.barra.setValue(200 + int(ev["v"] * 200))
                self.e_estado.setText(f"{paso}Letra: «{ev['texto'][:60]}»" + tema.quedan(self._t0, self.barra.value() / 1000))
            elif ev["t"] == "error":
                fallo.append(ev["msg"])
            if ev["t"] in ("fin", "error"):
                self.tarea = None
                self._hasta = ev.get("hasta") if ev.get("parada") else None
                self._parando = False
                t.cancelar()
                if frases:
                    segs = [{k: f[k] for k in ("inicio", "fin", "texto", "dudoso")} for f in frases]
                    f_json = rutas.ruta_unica(carpeta, carpeta.name, ".letra.json", (".txt",))
                    f_txt = f_json.with_name(f_json.name.replace(".letra.json", ".txt"))
                    config.escribir_json(f_json, {"idioma": a["idioma"], "modelo": modelo, "cantada": True, "segmentos": segs})
                    f_txt.write_text(exportar.txt(segs), encoding="utf-8")
                    proyectos.anotar_resultado(carpeta, "letra", segmentos=f_json.name, texto=f_txt.name)
                self._botones()
                al_acabar([p for f in frases for p in f["palabras"]],
                          fallo[0] if fallo else "" if frases else "No se reconoció ninguna palabra, así que no hay letra que colocar.")

        def cerrado(codigo, cancelada):
            if self.tarea is not t:
                return  # terminó bien y ya se pasó al segundo paso
            self.tarea = None
            self.e_estado.setText("Análisis cancelado. El audio original se conserva." if cancelada else
                                  f"El motor de voz se cerró inesperadamente (código {codigo}); suele ser falta de memoria. "
                                  "Prueba un modelo más pequeño en Letras o desmarca «Añadir la letra».")
            tema.reclasificar(self.e_estado, "tenue" if cancelada else "error")
            self._botones()

        t = tareas.Tarea("partitura_libre.workers.voz", [str(letras.carpeta_modelo(modelo))], "app",
                         lambda ev: tema.en_ui(lambda: evento(ev)), lambda c, cancelada: tema.en_ui(lambda: cerrado(c, cancelada)))
        t.enviar(id=1, audio=str(self._audio()), idioma=a["idioma"], cantada=True, palabras=True,
                 separar=separacion.instalado() and (guardar_voz is not None or a.get("separar", True)),
                 **({"guardar_voz": str(guardar_voz)} if guardar_voz else {}))
        self.tarea = t
        self._botones()

    def regenerar(self):
        edicion = rutas.TEMP / "edicion.notas.json"
        rutas.TEMP.mkdir(exist_ok=True)
        partituras.guardar_notas(edicion, self.tempo.value() or self.bpm, self.notas, self.letra, self.acordes, self._tempos())
        self._lanzar({"cmd": "regenerar", "notas": str(edicion), "carpeta": str(self.proyecto),
                      "nombre": self.proyecto.name, "bpm": self.tempo.value() or None, **self._notacion()}, "Creando la nueva versión…")

    def cancelar(self):
        """La primera vez, para y conserva lo hecho; la segunda, cancela del todo."""
        if not self.tarea:
            return
        if not self._parando and self.tarea.parar():
            self._parando = True
            self.e_estado.setText("Parando: se conserva lo hecho hasta ahora… (pulsa otra vez para cancelar del todo)")
            return
        self.e_estado.setText("Cancelando…")
        self.tarea.cancelar()

    def _evento(self, ev, carpeta):
        if ev["t"] == "progreso":
            self.barra.setValue(self._base_barra + int(ev["v"] * (1000 - self._base_barra)))
            self.e_estado.setText(ev["msg"] + tema.quedan(self._t0, self.barra.value() / 1000))
        elif ev["t"] == "fin":
            self._resultado = ev
        elif ev["t"] == "error":
            self._resultado = ev

    def _fin(self, codigo, cancelada, carpeta):
        self.tarea, self._parando, self._hasta = None, False, None
        tareas.limpiar_parciales(carpeta)
        r = self._resultado
        if cancelada:
            self.e_estado.setText("Análisis cancelado. El audio original se conserva.")
        elif r and r["t"] == "fin":
            version = {k: r[k] for k in ("midi", "musicxml", "notas", "bpm")}
            proyectos.anotar_resultado(carpeta, "partitura", **version)
            self.barra.setValue(1000)
            if carpeta == self.proyecto:
                self.abrir_proyecto(carpeta)
                aviso, self._sin_letra = getattr(self, "_sin_letra", ""), ""
                parada = (f"Parado a los {int(r['hasta'] // 60)}:{int(r['hasta'] % 60):02d}: se conserva lo hecho hasta ahí. "
                          if r.get("parada") else "")
                self.e_estado.setText(parada + f"Partitura creada: {r['n']} notas a {r['bpm']} pulsos/min"
                                      + (f", {r['con_letra']} con letra" if r.get("con_letra") else "")
                                      + f" → {r['musicxml']} y {r['midi']}. Revísala a la derecha. " + aviso)
            self.cambio.emit()
        else:
            motivo = r["msg"] if r else (f"El motor de partituras se cerró inesperadamente (código {codigo}). "
                                         "Mira logs/motores.log o ejecuta el Diagnóstico en Ajustes.")
            self.e_estado.setText(motivo)
            tema.reclasificar(self.e_estado, "error")
            tema.error(self, "No se pudo crear la partitura", motivo + "\n\nEl audio original se conserva en el proyecto.")
        self._botones()

    # -- revisión -------------------------------------------------------------
    def _mostrar(self, version):
        self.version = version
        bpm, notas = partituras.leer_notas(self.proyecto / version["notas"])
        self.letra = partituras.leer_letra(self.proyecto / version["notas"])
        self.acordes = partituras.leer_acordes(self.proyecto / version["notas"])
        self.tempos = partituras.leer_tempos(self.proyecto / version["notas"])
        self._poner_notas(notas, bpm)

    def _poner_notas(self, notas, bpm, sel=-1):
        self.notas, self.bpm, self._cargando = [list(n) for n in notas], bpm, True
        self.letra = (self.letra + [""] * len(self.notas))[:len(self.notas)]
        self.tabla.setRowCount(len(self.notas))
        for i in range(len(self.notas)):
            self._llenar_fila(i)
        self._cargando = False
        if 0 <= sel < len(self.notas):
            self.tabla.selectRow(sel)
        self._dibujar()
        self._botones()

    def _llenar_fila(self, i):
        for c, texto in enumerate(self._fila(i)):
            it = QTableWidgetItem(texto)
            it.setTextAlignment(Qt.AlignCenter)
            if c == 3:
                it.setFlags(it.flags() & ~Qt.ItemIsEditable)
            self.tabla.setItem(i, c, it)

    def _fila_puesta(self, i, nueva):
        """Tras insertar (`nueva`) o borrar la nota i: se toca solo esa fila de la tabla, no todas."""
        self._cargando = True
        if nueva:
            self.tabla.insertRow(i)
            self._llenar_fila(i)
        else:
            self.tabla.removeRow(i)
        self._cargando = False
        i = min(i, len(self.notas) - 1)
        if i >= 0:
            self.tabla.selectRow(i)
        self._dibujar()
        self._botones()

    def _fila(self, i):
        ini, fin, tono, _v = self.notas[i]
        return f"{ini:.2f}", f"{fin - ini:.2f}", str(tono), partituras.nombre_nota(tono), self.letra[i]

    def _nota_cambiada(self, i, recomponer=True):
        """Tras cambiar UNA nota: actualiza solo su fila de la tabla y, en la hoja, solo lo necesario.
        Con `recomponer=False` (cambio de altura al arrastrar) no se recoloca nada: se repinta su sistema."""
        self._cargando = True
        for c, texto in enumerate(self._fila(i)):
            self.tabla.item(i, c).setText(texto)
        self._cargando = False
        if recomponer:
            self._dibujar()
            self._botones()
        else:
            self.vista.repintar_nota(i)

    def _dibujar(self):
        sel = self.tabla.currentRow()
        titulo = self.proyecto.name if self.proyecto else ""
        self.vista.poner(self.notas, sel, self.tempo.value() or self.bpm, self.clave.currentData(), self.nombres.isChecked(), self.letra,
                         titulo, self.tonalidad.currentData(), self.acordes, self._tempos())
        if sel >= 0:  # la nota elegida queda a la vista en la partitura
            r = self.vista.rect_de(sel)
            self.rollo.ensureVisible(r.center().x(), r.center().y(), 40, r.height() // 2 + 10)

    def _cambio_de_vista(self):
        a = config.cargar()
        a["clave"], a["nombres"], a["tonalidad"] = self.clave.currentData(), self.nombres.isChecked(), self.tonalidad.currentData()
        config.guardar(a)
        self._dibujar()

    def _notacion(self):
        """Clave y nombres que se escriben en el MusicXML."""
        return {"clave": self.clave.currentData(), "nombres": self.nombres.isChecked(), "armadura": self.tonalidad.currentData()}

    def _celda_editada(self, it):
        if self._cargando:
            return
        i, n = it.row(), self.notas[it.row()]
        self._recordar()
        if it.column() == 4:  # letra de esa nota: texto libre
            self.letra[i] = it.text().strip()
            return self._nota_cambiada(i)
        try:
            v = float(it.text().replace(",", "."))
            if it.column() == 0:
                n[0], n[1] = max(0.0, v), max(0.0, v) + (n[1] - n[0])
            elif it.column() == 1:
                n[1] = n[0] + max(0.03, v)
            else:
                n[2] = max(0, min(127, int(v)))
        except ValueError:
            pass  # texto no numérico: se restaura el valor anterior
        self._nota_cambiada(i)

    def _atajo(self, accion):
        """Teclas sobre la partitura, como en un editor de notación."""
        i = self.tabla.currentRow()
        if accion in ("anterior", "siguiente"):
            if self.notas:
                self.tabla.selectRow(max(0, min(len(self.notas) - 1, i + (1 if accion == "siguiente" else -1))))
        elif accion == "modo":
            if self.b_insertar.isEnabled():
                self.b_insertar.toggle()
        elif accion == "escape":
            self.b_insertar.setChecked(False) if self.b_insertar.isChecked() else self.tabla.clearSelection()
        elif accion.startswith("fig:"):
            if self.b_anadir.isEnabled():
                self._figura(accion[4:])
        elif accion.startswith(("nota:", "acorde:")):
            if self.b_anadir.isEnabled():
                self._tecla_nota(accion[-1], accion.startswith("acorde:"))
        elif accion == "silencio":
            self._silencio()
        elif accion == "puntillo":
            self.b_puntillo.toggle()
            self._puntillo()
        elif accion == "letra":
            if self.e_letra.isEnabled():
                self.e_letra.setFocus()
                self.e_letra.selectAll()
        elif accion == "reproducir":
            if self.b_reproducir.isEnabled():
                self.reproducir()
        elif accion in ("deshacer", "rehacer"):
            self._deshacer(accion == "rehacer")
        elif self.b_borrar.isEnabled():  # solo se edita una partitura ya creada, no un borrador ni durante un análisis
            {"arriba": lambda: self._mover(1), "abajo": lambda: self._mover(-1), "octava+": lambda: self._mover(12),
             "octava-": lambda: self._mover(-12), "borrar": self._borrar, "antes": lambda: self._desplazar(-1),
             "despues": lambda: self._desplazar(1)}[accion]()

    def _marcar_pulso(self):
        """Tempo a mano: cada pulsación es un pulso; con 4 o más seguidas se fija el tempo."""
        ahora = time.monotonic()
        if self._toques and ahora - self._toques[-1] > 2.5:   # pausa larga: se empieza de nuevo
            self._toques = []
        self._toques = (self._toques + [ahora])[-12:]
        if len(self._toques) < 4:
            return self.b_pulso.setText(f"Marcar pulso ({len(self._toques)}/4)")
        intervalos = sorted(b - a for a, b in zip(self._toques, self._toques[1:]))
        bpm = int(round(60 / intervalos[len(intervalos) // 2]))
        self.tempo.setValue(max(30, min(240, bpm)))
        self.b_pulso.setText(f"Marcar pulso · {self.tempo.value()}")
        self._dibujar()

    def _figura(self, fig):
        self._fig_nueva = fig                 # también es la figura de la próxima nota que se introduzca
        i = self.tabla.currentRow()
        if i < 0 or self.b_insertar.isChecked():   # en modo introducir la figura es la de la próxima nota, como en MuseScore
            return self._botones()
        if i >= 0:
            self._recordar()
            self.notas[i][1] = self.notas[i][0] + partituras.segundos_de(fig, self.tempo.value() or self.bpm, self.b_puntillo.isChecked())
            self._nota_cambiada(i)

    def _letra_editada(self):
        i = self.tabla.currentRow()
        if 0 <= i < len(self.letra) and self.letra[i] != self.e_letra.text().strip():
            self._recordar()
            self.letra[i] = self.e_letra.text().strip()
            self._nota_cambiada(i)

    def _zoom(self, paso):
        self.vista.cambiar_zoom((round(self.vista.zoom * 100) + paso) / 100)
        self.e_zoom.setText(f"{round(self.vista.zoom * 100)} %")
        a = config.cargar()
        a["zoom"] = round(self.vista.zoom * 100)
        config.guardar(a)

    def _guardar_panel(self, si):
        a = config.cargar()
        a["panel_notas"] = si
        config.guardar(a)

    def _mover(self, semitonos):
        i = self.tabla.currentRow()
        if i >= 0:
            self._recordar()
            self.notas[i][2] = max(0, min(127, self.notas[i][2] + semitonos))
            self._nota_cambiada(i)

    def _anadir(self):
        i = self.tabla.currentRow()
        base = self.notas[i] if i >= 0 else [0.0, 0.0, 60, 0.7]
        self._recordar()
        self.notas.insert(i + 1, [base[1], base[1] + 0.5, base[2], 0.7])
        self.letra.insert(i + 1, "")
        self._fila_puesta(i + 1, True)

    def _borrar(self):
        i = self.tabla.currentRow()
        if i >= 0:
            self._recordar()
            del self.notas[i]
            del self.letra[i:i + 1]
            self._fila_puesta(i, False)

    # -- salida -----------------------------------------------------------------
    def _copiar(self, clave, filtro):
        origen = self._archivo(clave)
        ruta, _ = QFileDialog.getSaveFileName(self, "Guardar una copia", str(rutas.DATOS / origen.name), filtro)
        if ruta and tema.avisar_si_externo(self, ruta):
            try:
                shutil.copyfile(origen, ruta)
            except OSError as e:
                tema.error(self, "No se pudo guardar", f"{e}\n\nElige otra carpeta o libera espacio.")

    def abrir_musescore(self):
        if not editor.abrir(self._archivo("musicxml")):
            tema.error(self, "MuseScore no disponible", "No se encontró MuseScore. Descárgalo en Ajustes (versión portable).")

    def nueva(self):
        """Partitura en blanco para escribirla a mano, sin audio."""
        try:
            d = proyectos.crear(self.nombre.text().strip() or "Partitura nueva", "partitura", self.destino or None)
        except OSError as e:
            return tema.error(self, "No se pudo crear la partitura", f"{e}\n\nElige otra carpeta de destino.")
        self.nombre.clear()
        self.abrir_proyecto(d)
        self.version = {}                     # partitura abierta y editable, aún sin archivos guardados
        self.b_insertar.setChecked(True)
        self.e_estado.setText("Partitura en blanco: con «Introducir» activado, haz clic en el pentagrama para escribir notas.")
        self._botones()
        self.cambio.emit()

    def abrir_existente(self):
        """Convierte un MusicXML, MXL o MIDI en una partitura editable dentro de un proyecto nuevo."""
        ruta, _ = QFileDialog.getOpenFileName(self, "Abrir partitura", str(rutas.DATOS), f"Partituras ({partituras.PARTITURAS})")
        if not ruta:
            return
        try:
            d = proyectos.crear(Path(ruta).stem, "partitura", self.destino or None)
            copia = rutas.ruta_unica(d, "original " + Path(ruta).stem, Path(ruta).suffix.lower())
            shutil.copy2(ruta, copia)         # el archivo original se conserva en el proyecto
        except OSError as e:
            return tema.error(self, "No se pudo abrir", f"{e}\n\nComprueba que el archivo existe y que hay espacio libre.")
        self.abrir_proyecto(d)
        self.cambio.emit()
        self._lanzar({"cmd": "importar", "partitura": str(copia), "carpeta": str(d), "nombre": d.name, **self._notacion()},
                     "Leyendo la partitura…")

    def exportar_pdf(self):
        """PDF generado por la propia app a partir de la partitura que se ve (con tus correcciones)."""
        base = (self.proyecto / self.proyecto.name) if self.proyecto else rutas.DATOS / "partitura"
        ruta, _ = QFileDialog.getSaveFileName(self, "Exportar PDF", str(base) + ".pdf", "PDF (*.pdf)")
        if not ruta or not tema.avisar_si_externo(self, ruta):
            return
        try:
            paginas = self.vista.exportar_pdf(ruta)
            self.e_estado.setText(f"PDF guardado ({paginas} página{'s' if paginas != 1 else ''}) en {ruta}")
        except OSError as e:
            tema.error(self, "No se pudo exportar el PDF", f"{e}\n\nElige otra carpeta o libera espacio.")

    # -- deshacer, introducir, arrastrar, mover y reproducir --------------------
    def _recordar(self):
        """Guarda el estado antes de un cambio, para poder deshacerlo."""
        self._hist.append(([list(n) for n in self.notas], list(self.letra)))
        del self._hist[:-200]
        self._rehechos.clear()

    def _deshacer(self, rehacer=False):
        origen, destino = (self._rehechos, self._hist) if rehacer else (self._hist, self._rehechos)
        if origen and self.b_anadir.isEnabled():
            destino.append(([list(n) for n in self.notas], list(self.letra)))
            notas, self.letra = origen.pop()
            self._poner_notas(notas, self.bpm, min(self.tabla.currentRow(), len(notas) - 1))

    def _insertar(self, tras, tono):
        """Clic en el pentagrama con «Introducir» activado."""
        if not self.b_anadir.isEnabled():
            return
        self._recordar()
        inicio = (self.notas[tras][1] if 0 <= tras < len(self.notas) else 0.0) + self._espera
        dur = partituras.segundos_de(self._fig_nueva, self.tempo.value() or self.bpm, self.b_puntillo.isChecked())
        for n in self.notas:                  # lo que venía después se desplaza para hacer sitio, sin encimarse
            if n[0] >= inicio - 1e-6:
                n[0], n[1] = n[0] + dur + self._espera, n[1] + dur + self._espera
        self._espera = 0.0
        self.notas.insert(tras + 1, [inicio, inicio + dur, tono, 0.7])
        self.letra.insert(tras + 1, "")
        self._poner_notas(self.notas, self.bpm, tras + 1)

    def _tecla_nota(self, letra, acorde):
        """Teclas A-G como en MuseScore: en modo introducir escriben una nota tras la elegida (con Mayús,
        la añaden al acorde); fuera de él cambian la altura de la nota elegida."""
        i = self.tabla.currentRow()
        tono = partituras.tono_cercano(letra, self.notas[i][2] if 0 <= i < len(self.notas) else 67)
        if not self.b_insertar.isChecked():
            if self.b_borrar.isEnabled() and i >= 0:
                self._recordar()
                self.notas[i][2] = tono
                self._nota_cambiada(i)
        elif acorde and i >= 0:
            self._recordar()
            self.notas.insert(i + 1, [self.notas[i][0], self.notas[i][1], tono, 0.7])
            self.letra.insert(i + 1, "")
            self._fila_puesta(i + 1, True)
        else:
            self._insertar(i, tono)

    def _silencio(self):
        """Tecla 0 en modo introducir: deja un silencio de la figura elegida antes de la próxima nota."""
        if self.b_insertar.isChecked():
            self._espera += partituras.segundos_de(self._fig_nueva, self.tempo.value() or self.bpm, self.b_puntillo.isChecked())
            self.e_estado.setText(f"Silencio anotado: la próxima nota empezará {self._espera:.2f} s después de la elegida.")

    def _puntillo(self):
        """Tecla punto: pone o quita el puntillo (figura y media) a la nota elegida."""
        i = self.tabla.currentRow()
        if self.b_borrar.isEnabled() and i >= 0 and not self.b_insertar.isChecked():
            bpm = self.tempo.value() or self.bpm
            fig, tiene = partituras.figura_y_puntillo(self.notas[i][1] - self.notas[i][0], bpm)
            self._recordar()
            self.notas[i][1] = self.notas[i][0] + partituras.segundos_de(fig, bpm, not tiene)
            self._nota_cambiada(i)
        else:
            self._botones()

    def eventFilter(self, objeto, ev):
        """En el campo de letra, como en MuseScore: espacio o guion pasan a la nota siguiente; Esc vuelve a la partitura."""
        if objeto is self.e_letra and ev.type() == QEvent.KeyPress:
            if ev.key() in (Qt.Key_Space, Qt.Key_Minus) and self.e_letra.cursorPosition() == len(self.e_letra.text()):
                if ev.key() == Qt.Key_Minus and self.e_letra.text().strip():   # guion: la palabra sigue en la nota siguiente
                    self.e_letra.setText(self.e_letra.text().strip() + "-")
                self._letra_editada()
                i = self.tabla.currentRow()
                if i + 1 < len(self.notas):
                    self.tabla.selectRow(i + 1)
                    self.e_letra.setText(self.letra[i + 1])
                    self.e_letra.selectAll()
                return True
            if ev.key() == Qt.Key_Escape:
                self._letra_editada()
                self.vista.setFocus()
                return True
        return super().eventFilter(objeto, ev)

    def _arrastrar(self, i, tono, primero):
        if self.b_borrar.isEnabled() and 0 <= i < len(self.notas) and self.notas[i][2] != tono:
            if primero:
                self._recordar()
                self._botones()               # activa «Deshacer» una vez, no en cada paso
            self.notas[i][2] = tono
            self._nota_cambiada(i, recomponer=False)

    def _desplazar(self, semicorcheas):
        """Mueve la nota elegida en el tiempo, de semicorchea en semicorchea."""
        i = self.tabla.currentRow()
        if i >= 0:
            self._recordar()
            paso = semicorcheas * 15 / (self.tempo.value() or self.bpm)
            n = self.notas[i]
            n[0], n[1] = max(0.0, n[0] + paso), max(0.0, n[0] + paso) + (n[1] - n[0])
            self._nota_cambiada(i)

    def _fuentes_de_sonido(self):
        """Qué se puede oír: la partitura sintetizada y, si existen, el audio original y la voz aislada."""
        fuentes = [("Partitura", None)]
        if self._audio():
            fuentes.append(("Audio original", self._audio()))
        voz = self.proyecto / "voz aislada.wav" if self.proyecto else None
        if voz and voz.is_file():
            fuentes.append(("Voz aislada", voz))
        return fuentes

    def _actualizar_fuentes(self):
        """Fuentes de sonido del proyecto. Mientras no elijas otra, se oye la canción (el audio original)."""
        elegido = self.oir_que.currentText() if self._fuente_a_mano else "Audio original"
        self.oir_que.blockSignals(True)
        self.oir_que.clear()
        for nombre, ruta in self._fuentes_de_sonido():
            self.oir_que.addItem(nombre, str(ruta) if ruta else None)
        self.oir_que.setCurrentIndex(max(0, self.oir_que.findText(elegido)))
        self.oir_que.blockSignals(False)
        self._pos, self._duracion = 0.0, max((n[1] for n in self.notas), default=0.0)
        self._mostrar_posicion(0.0)

    def _elegir_fuente(self):
        self._fuente_a_mano = True
        if self._sonando:             # cambiar de fuente mientras suena: sigue desde el mismo punto
            self.reproducir()
            self.reproducir()

    # -- reproductor: ▶/⏸, ⏹, barra de posición; la partitura y la letra siguen a la música --
    def reproducir(self):
        """▶ empieza (o sigue) desde la posición actual; ⏸ pausa ahí."""
        if self._sonando:
            self._pos = self._ahora()
            return self._parar_sonido("⏸ En pausa")
        if not self.notas:
            return
        ruta = self.oir_que.currentData()
        desde = self._pos
        try:
            if ruta:
                self._duracion = desde + audio.reproducir_archivo(ruta, desde)
            else:
                audio.reproducir([[n[0] - desde, n[1] - desde, n[2], n[3]] for n in self.notas if n[1] > desde])
                self._duracion = max(n[1] for n in self.notas) + 0.4
        except (audio.ErrorAudio, OSError, ValueError) as e:
            return tema.error(self, "No se pudo reproducir", str(e))
        self._sonando, self._reproduccion = True, (time.monotonic(), desde)
        self.posicion.setRange(0, int(self._duracion * 10))
        self._seguir.start()
        self.b_reproducir.setText("⏸")

    def detener(self):
        """⏹ para y vuelve al principio."""
        if self._sonando:
            self._parar_sonido("")
        self._pos = 0.0
        self.vista.poner_cursor(None)
        self.vista.marcar_sonando(-1)
        self._mostrar_posicion(0.0)

    def _ahora(self):
        inicio, desde = self._reproduccion
        return desde + time.monotonic() - inicio

    def _parar_sonido(self, texto):
        audio.parar_reproduccion()
        self._seguir.stop()
        self._sonando = False
        self.b_reproducir.setText("▶")
        self._mostrar_posicion(self._pos)

    def _mostrar_posicion(self, t):
        reloj = lambda x: f"{int(x // 60)}:{int(x % 60):02d}"
        self.e_tiempo.setText(f"{reloj(t)} / {reloj(self._duracion)}")
        if not self.posicion.isSliderDown():
            self.posicion.blockSignals(True)
            self.posicion.setRange(0, max(1, int(self._duracion * 10)))
            self.posicion.setValue(int(t * 10))
            self.posicion.blockSignals(False)

    def _saltar(self):
        """Al soltar la barra de posición: se va a ese punto (y sigue sonando si sonaba)."""
        self._pos = self.posicion.value() / 10
        if self._sonando:
            self._parar_sonido("")
            self.reproducir()
        else:
            self._seguir_a(self._pos)

    def _desde_nota_elegida(self):
        """Elegir una nota (sin reproducir) coloca ahí el punto de partida."""
        i = self.tabla.currentRow()
        if not self._sonando and 0 <= i < len(self.notas):
            self._pos = self.notas[i][0]
            self._mostrar_posicion(self._pos)

    def _seguir_reproduccion(self):
        t = self._ahora()
        if t >= self._duracion:
            self._pos = 0.0
            self._parar_sonido("")
            self.vista.poner_cursor(None)
            self.vista.marcar_sonando(-1)
            return self._mostrar_posicion(0.0)
        self._seguir_a(t)

    def _seguir_a(self, t):
        """Lleva la partitura al segundo t: línea de reproducción, nota y sílaba resaltadas, y vista que acompaña."""
        self._mostrar_posicion(t)
        i = next((k for k, n in enumerate(self.notas) if n[0] <= t < n[1]), -1)
        self.vista.marcar_sonando(i)
        lugar = self.vista.poner_cursor(t)
        if lugar:
            y = int(self.vista._sis_y[lugar[0]])
            self.rollo.ensureVisible(int(lugar[1]), y, 120, int(self.vista._alto_sistema(self.vista.zoom)))

    def _fin_reproduccion(self):
        self.detener()

    def cerrar(self):
        self.captura.cerrar()
        self._parar_vivo()
        if self._sonando:
            self._fin_reproduccion()
