"""Sección Partituras: grabar o importar, detectar notas, revisar/corregir y exportar."""
import json
import shutil
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (QAbstractItemView, QFileDialog, QHBoxLayout, QHeaderView, QLineEdit, QProgressBar,
                               QScrollArea, QSpinBox, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from .. import config, editor, partituras, proyectos, rutas, tareas
from . import tema
from .captura import PanelCaptura

PX_S = 70  # píxeles por segundo en la vista de notas


class VistaNotas(QWidget):
    """Rollo de piano: cada nota es una barra (tiempo → derecha, agudo → arriba)."""
    elegida = Signal(int)

    def __init__(self):
        super().__init__()
        self.notas, self.sel = [], -1
        self.setMinimumHeight(140)

    def poner(self, notas, sel=-1):
        self.notas, self.sel = notas, sel
        self.setMinimumWidth(int(max((n[1] for n in notas), default=0) * PX_S) + 40)
        self.update()

    def _geometria(self):
        tonos = [n[2] for n in self.notas] or [60]
        bajo, alto = min(tonos) - 2, max(tonos) + 2
        return bajo, max(4.0, (self.height() - 8) / (alto - bajo + 1))

    def _rect(self, n, bajo, paso):
        y = self.height() - 4 - (n[2] - bajo + 1) * paso
        return int(n[0] * PX_S) + 4, int(y), max(3, int((n[1] - n[0]) * PX_S)), max(3, int(paso) - 1)

    def paintEvent(self, _):
        g = QPainter(self)
        g.fillRect(self.rect(), QColor("#0c1929"))
        bajo, paso = self._geometria()
        g.setPen(QColor("#152a44"))
        for s in range(0, self.width() // PX_S + 1):
            g.drawLine(s * PX_S + 4, 0, s * PX_S + 4, self.height())
        g.setPen(Qt.NoPen)
        for i, n in enumerate(self.notas):
            g.setBrush(QColor("#fbbf24" if i == self.sel else tema.ACENTO))
            g.drawRoundedRect(*self._rect(n, bajo, paso), 2, 2)

    def mousePressEvent(self, ev):
        bajo, paso = self._geometria()
        for i, n in enumerate(self.notas):
            x, y, w, h = self._rect(n, bajo, paso)
            if x <= ev.position().x() <= x + w and y <= ev.position().y() <= y + h:
                self.elegida.emit(i)
                return


class PaginaPartituras(QWidget):
    cambio = Signal()  # se creó o modificó un proyecto

    def __init__(self):
        super().__init__()
        self.setObjectName("pagina")
        self.proyecto = None   # carpeta del proyecto abierto
        self.version = None    # resultado mostrado: {'midi', 'musicxml', 'notas', …}
        self.externa = None    # partitura existente abierta sin proyecto
        self.notas, self.bpm, self.tarea, self._cargando = [], 120, None, False

        # -- columna izquierda: entrada ------------------------------------
        self.nombre = QLineEdit()
        self.nombre.setPlaceholderText("Nombre de la toma (opcional)")
        self.destino = config.cargar()["carpeta_proyectos"]
        self.e_destino = tema.etiqueta("", "tenue")
        self.captura = PanelCaptura("partitura", lambda: self.nombre.text().strip(), lambda: self.destino or None)
        self.captura.terminada.connect(self._toma_lista)
        self.captura.estado.connect(self._botones)
        self.b_importar = tema.boton("Importar audio…", self.importar, ayuda="WAV, MP3, FLAC u OGG")
        t1, v1 = tema.tarjeta("1 · Grabar o importar")
        v1.addLayout(tema.fila(self.nombre, tema.boton("Carpeta…", self.elegir_destino), estirar=self.nombre))
        v1.addWidget(self.e_destino)
        v1.addWidget(self.captura)
        v1.addLayout(tema.fila(tema.etiqueta("¿Ya tienes el audio en un archivo?", "tenue", False), None, self.b_importar))

        self.e_toma = tema.etiqueta("Ninguna toma abierta. Graba, importa un audio o abre un proyecto.", "tenue")
        self.tempo = QSpinBox()
        self.tempo.setRange(0, 240)
        self.tempo.setSpecialValueText("Automático")
        self.tempo.setSuffix(" pulsos/min")
        self.tempo.setToolTip("Tempo con el que se escribe la partitura. «Automático» lo estima del audio.")
        self.b_transcribir = tema.boton("Detectar notas y crear partitura", self.transcribir, "primario")
        self.b_cancelar = tema.boton("Cancelar análisis", self.cancelar)
        self.b_oir = tema.boton("Escuchar audio", lambda: tema.abrir_en_sistema(self._audio()), ayuda="Abre el audio original en tu reproductor")
        self.barra = QProgressBar()
        self.barra.setRange(0, 1000)
        self.barra.setTextVisible(False)
        self.e_estado = tema.etiqueta("", "tenue")
        t2, v2 = tema.tarjeta("2 · Convertir en partitura")
        v2.addWidget(self.e_toma)
        v2.addLayout(tema.fila(tema.etiqueta("Tempo", "tenue", False), self.tempo, None, self.b_oir))
        v2.addLayout(tema.fila(self.b_transcribir, self.b_cancelar, estirar=self.b_transcribir))
        v2.addWidget(self.barra)
        v2.addWidget(self.e_estado)


        # -- columna derecha: revisión -------------------------------------
        self.vista = VistaNotas()
        self.vista.elegida.connect(lambda i: self.tabla.selectRow(i))
        rollo = QScrollArea()
        rollo.setWidget(self.vista)
        rollo.setWidgetResizable(True)
        rollo.setFixedHeight(160)
        self.tabla = QTableWidget(0, 4)
        self.tabla.setHorizontalHeaderLabels(["Inicio (s)", "Duración (s)", "Nota MIDI", "Nombre"])
        self.tabla.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tabla.verticalHeader().setDefaultSectionSize(26)
        self.tabla.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tabla.setAlternatingRowColors(True)
        self.tabla.itemChanged.connect(self._celda_editada)
        self.tabla.itemSelectionChanged.connect(lambda: (self.vista.poner(self.notas, self.tabla.currentRow()), self._botones()))
        self.b_sube = tema.boton("+ semitono", lambda: self._mover(1))
        self.b_baja = tema.boton("− semitono", lambda: self._mover(-1))
        self.b_anadir = tema.boton("Añadir nota", self._anadir)
        self.b_borrar = tema.boton("Borrar nota", self._borrar, "peligro")
        self.b_regenerar = tema.boton("Guardar cambios como nueva versión", self.regenerar, "primario",
                                      "Crea MIDI y MusicXML nuevos con tus correcciones (no pisa los anteriores)")
        self.b_musescore = tema.boton("Abrir en MuseScore", self.abrir_musescore)
        self.b_pdf = tema.boton("Exportar PDF…", self.exportar_pdf)
        self.b_midi = tema.boton("Guardar MIDI…", lambda: self._copiar("midi", "MIDI (*.mid)"))
        self.b_xml = tema.boton("Guardar MusicXML…", lambda: self._copiar("musicxml", "MusicXML (*.musicxml)"))
        self.b_existente = tema.boton("Abrir otra partitura…", self.abrir_existente,
                                      ayuda="MusicXML, MXL, XML, MIDI o MSCZ: se abre en MuseScore")
        self.b_carpeta = tema.boton("Ver carpeta", lambda: tema.abrir_en_sistema(self.proyecto))
        self.e_editor = tema.etiqueta("", "tenue")
        t3, v3 = tema.tarjeta("3 · Revisar, corregir y exportar")
        v3.addWidget(tema.etiqueta(partituras.LIMITACIONES, "aviso"))
        v3.addWidget(rollo)
        v3.addWidget(self.tabla, 1)
        v3.addLayout(tema.fila(self.b_sube, self.b_baja, self.b_anadir, self.b_borrar, None))
        v3.addWidget(self.b_regenerar)
        v3.addLayout(tema.fila(self.b_midi, self.b_xml, self.b_carpeta, None))
        v3.addLayout(tema.fila(self.b_musescore, self.b_pdf, self.b_existente, None))
        v3.addWidget(self.e_editor)

        cuerpo = QHBoxLayout()
        cuerpo.setSpacing(14)
        cuerpo.addWidget(tema.columna(t1, t2), 4)
        cuerpo.addWidget(t3, 6)
        v = QVBoxLayout(self)
        v.setContentsMargins(22, 18, 22, 18)
        v.setSpacing(12)
        v.addWidget(tema.etiqueta("Partituras", "titulo"))
        v.addWidget(tema.etiqueta("De audio a partitura editable: graba o importa una melodía, detecta las notas y corrígelas.", "tenue"))
        v.addLayout(cuerpo, 1)
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
        if self.externa:
            return self.externa
        if self.proyecto and self.version and self.version.get(clave):
            return self.proyecto / self.version[clave]
        return None

    def _botones(self):
        analizando, grabando = self.tarea is not None, self.captura.grabando
        audio = self._audio() is not None
        hay = self.version is not None and not analizando
        exe, origen = editor.buscar()
        self.b_importar.setEnabled(not analizando and not grabando)
        self.b_transcribir.setEnabled(audio and not analizando and not grabando)
        self.b_cancelar.setEnabled(analizando)
        self.b_oir.setEnabled(audio)
        self.tempo.setEnabled(not analizando)
        for b in (self.b_sube, self.b_baja, self.b_borrar):
            b.setEnabled(hay and self.tabla.currentRow() >= 0)
        self.b_anadir.setEnabled(hay)
        self.b_regenerar.setEnabled(hay and bool(self.notas))
        self.b_midi.setEnabled(hay)
        self.b_xml.setEnabled(hay)
        self.b_carpeta.setEnabled(self.proyecto is not None)
        self.b_musescore.setEnabled(bool(exe) and (hay or self.externa is not None))
        self.b_pdf.setEnabled(bool(exe) and (hay or self.externa is not None))
        self.b_existente.setEnabled(bool(exe))
        self.e_editor.setText(f"Editor: MuseScore ({origen})." if exe else
                              "MuseScore no está disponible: edición gráfica y PDF desactivados. Descárgalo en Ajustes (portable).")

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
        self._toma_lista(d)

    def _toma_lista(self, carpeta):
        self.nombre.clear()
        self.abrir_proyecto(carpeta)
        self.cambio.emit()

    def abrir_proyecto(self, carpeta):
        self.proyecto, self.externa, self.version = Path(carpeta), None, None
        d = proyectos.leer(self.proyecto)
        versiones = [r for r in d["resultados"] if r["tipo"] == "partitura" and (self.proyecto / r["notas"]).is_file()]
        marca = "  ·  ⚠ toma incompleta" if d.get("incompleta") else ""
        self.e_toma.setText(f"<b>{d['nombre']}</b>  ·  audio: {d.get('audio') or '—'}  ·  {len(versiones)} versión(es){marca}")
        self.e_estado.setText(" ".join(d.get("avisos", [])))
        self.barra.setValue(0)
        if versiones:
            self._mostrar(versiones[-1])
        else:
            self._poner_notas([], 120)
        self._botones()

    # -- análisis -------------------------------------------------------------
    def _lanzar(self, orden, mensaje):
        self.barra.setValue(0)
        self.e_estado.setText(mensaje)
        tema.reclasificar(self.e_estado, "tenue")
        carpeta = self.proyecto
        self.tarea = tareas.Tarea("partitura_libre.workers.notas", [json.dumps(orden)], "partituras",
                                  lambda ev: tema.en_ui(lambda: self._evento(ev, carpeta)),
                                  lambda codigo, cancelada: tema.en_ui(lambda: self._fin(codigo, cancelada, carpeta)))
        self._resultado = None
        self._botones()

    def transcribir(self):
        self._lanzar({"cmd": "transcribir", "audio": str(self._audio()), "carpeta": str(self.proyecto),
                      "nombre": self.proyecto.name, "bpm": self.tempo.value() or None}, "Preparando el análisis…")

    def regenerar(self):
        edicion = rutas.TEMP / "edicion.notas.json"
        rutas.TEMP.mkdir(exist_ok=True)
        partituras.guardar_notas(edicion, self.tempo.value() or self.bpm, self.notas)
        self._lanzar({"cmd": "regenerar", "notas": str(edicion), "carpeta": str(self.proyecto),
                      "nombre": self.proyecto.name, "bpm": self.tempo.value() or None}, "Creando la nueva versión…")

    def cancelar(self):
        if self.tarea:
            self.e_estado.setText("Cancelando…")
            self.tarea.cancelar()

    def _evento(self, ev, carpeta):
        if ev["t"] == "progreso":
            self.barra.setValue(int(ev["v"] * 1000))
            self.e_estado.setText(ev["msg"])
        elif ev["t"] == "fin":
            self._resultado = ev
        elif ev["t"] == "error":
            self._resultado = ev

    def _fin(self, codigo, cancelada, carpeta):
        self.tarea = None
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
                self.e_estado.setText(f"Partitura creada: {r['n']} notas a {r['bpm']} pulsos/min → {r['musicxml']} y {r['midi']}. Revísala a la derecha.")
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
        self._poner_notas(notas, bpm)

    def _poner_notas(self, notas, bpm, sel=-1):
        self.notas, self.bpm, self._cargando = [list(n) for n in notas], bpm, True
        self.tabla.setRowCount(len(self.notas))
        for i, (ini, fin, tono, _v) in enumerate(self.notas):
            for c, texto in enumerate((f"{ini:.2f}", f"{fin - ini:.2f}", str(tono), partituras.nombre_nota(tono))):
                it = QTableWidgetItem(texto)
                it.setTextAlignment(Qt.AlignCenter)
                if c == 3:
                    it.setFlags(it.flags() & ~Qt.ItemIsEditable)
                self.tabla.setItem(i, c, it)
        self._cargando = False
        if 0 <= sel < len(self.notas):
            self.tabla.selectRow(sel)
        self.vista.poner(self.notas, sel)
        self._botones()

    def _celda_editada(self, it):
        if self._cargando:
            return
        i, n = it.row(), self.notas[it.row()]
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
        self._poner_notas(self.notas, self.bpm, i)

    def _mover(self, semitonos):
        i = self.tabla.currentRow()
        if i >= 0:
            self.notas[i][2] = max(0, min(127, self.notas[i][2] + semitonos))
            self._poner_notas(self.notas, self.bpm, i)

    def _anadir(self):
        i = self.tabla.currentRow()
        base = self.notas[i] if i >= 0 else [0.0, 0.0, 60, 0.7]
        self.notas.insert(i + 1, [base[1], base[1] + 0.5, base[2], 0.7])
        self._poner_notas(self.notas, self.bpm, i + 1)

    def _borrar(self):
        i = self.tabla.currentRow()
        if i >= 0:
            del self.notas[i]
            self._poner_notas(self.notas, self.bpm, min(i, len(self.notas) - 1))

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

    def abrir_existente(self):
        ruta, _ = QFileDialog.getOpenFileName(self, "Abrir partitura", str(rutas.DATOS), f"Partituras ({partituras.PARTITURAS})")
        if ruta:
            self.proyecto, self.version, self.externa = None, None, Path(ruta)
            self._poner_notas([], 120)
            self.e_toma.setText(f"Partitura existente: <b>{Path(ruta).name}</b> (se edita en MuseScore)")
            editor.abrir(ruta)

    def exportar_pdf(self):
        origen = self._archivo("musicxml")
        ruta, _ = QFileDialog.getSaveFileName(self, "Exportar PDF", str(origen.with_suffix(".pdf")), "PDF (*.pdf)")
        if not ruta or not tema.avisar_si_externo(self, ruta):
            return
        self.e_estado.setText("Exportando PDF con MuseScore…")
        self.b_pdf.setEnabled(False)

        def fin(fallo, e):
            self._botones()
            fallo = fallo or (str(e) if e else "")
            if fallo:
                self.e_estado.setText("No se pudo exportar el PDF.")
                tema.error(self, "No se pudo exportar el PDF", fallo)
            else:
                self.e_estado.setText(f"PDF guardado en {ruta}")
        tema.en_hilo(lambda: editor.exportar_pdf(origen, ruta), fin)
