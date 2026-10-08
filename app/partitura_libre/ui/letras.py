"""Sección Letras: voz (hablada o cantada) a texto editable, con marcas de tiempo y exportación."""
import json
from pathlib import Path

from PySide6.QtGui import QGuiApplication, QTextCursor, QTextDocument
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFileDialog, QHBoxLayout, QLineEdit, QPlainTextEdit,
                               QProgressBar, QRadioButton, QVBoxLayout, QWidget)
from PySide6.QtCore import Signal

from .. import config, exportar, letras, proyectos, rutas, tareas
from . import tema
from .captura import PanelCaptura

SEGMENTO_VIVO_S = 8


class PaginaLetras(QWidget):
    cambio = Signal()

    def __init__(self):
        super().__init__()
        self.setObjectName("pagina")
        a = config.cargar()
        self.proyecto = None     # carpeta del proyecto abierto
        self.archivo = None      # nombre base de la letra guardada
        self.segs = []           # segmentos de la transcripción mostrada
        self.voz = None          # proceso persistente del motor
        self.modelo_cargado = ""
        self._id = 0
        self._final = None       # id de la transcripción completa en curso
        self._vivos = set()      # ids de segmentos en vivo pendientes
        self._nuevos = []
        self._grababa = False

        # -- izquierda: entrada y motor ---------------------------------------
        self.nombre = QLineEdit()
        self.nombre.setPlaceholderText("Nombre de la toma (opcional)")
        self.en_vivo = QCheckBox("Transcribir mientras hablo (borrador)")
        self.en_vivo.setChecked(True)
        self.captura = PanelCaptura("letra", lambda: self.nombre.text().strip(), lambda: config.cargar()["carpeta_proyectos"] or None,
                                    lambda: SEGMENTO_VIVO_S if self.en_vivo.isChecked() and self._modelo_listo() else 0)
        self.captura.terminada.connect(self._toma_lista)
        self.captura.segmento.connect(self._segmento_vivo)
        self.captura.estado.connect(self._al_cambiar_captura)
        self.b_importar = tema.boton("Importar audio o vídeo…", self.importar)
        t1, v1 = tema.tarjeta("1 · Grabar, dictar o importar")
        v1.addWidget(self.nombre)
        v1.addWidget(self.captura)
        v1.addWidget(self.en_vivo)
        v1.addLayout(tema.fila(tema.etiqueta("¿Ya tienes la voz en un archivo?", "tenue", False), None, self.b_importar))

        self.modelo = QComboBox()
        self.modelo.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.modelo.setMinimumContentsLength(20)
        self.modelo.currentIndexChanged.connect(self._modelo_cambiado)
        self.e_modelo = tema.etiqueta("", "tenue")
        self.b_descargar = tema.boton("Descargar modelo", self.descargar)
        self.idioma = QComboBox()
        for codigo, nombre in letras.IDIOMAS.items():
            self.idioma.addItem(nombre, codigo)
        self.idioma.setCurrentIndex(max(0, self.idioma.findData(a["idioma"])))
        self.hablada = QRadioButton("Voz hablada")
        self.cantada = QRadioButton("Voz cantada (modo de prueba)")
        self.hablada.setChecked(True)
        self.e_cantada = tema.etiqueta(
            "Voz cantada: la música, los coros y los instrumentos confunden al modelo. Los versos poco fiables se "
            "marcan con ⚠ para que los revises; no hay separación de voz e instrumentos. Mejor con voz sola. Si la canción suena "
            "en este equipo, elige «Sonido del equipo» como entrada en vez del micrófono.", "aviso")
        self.e_toma = tema.etiqueta("Ninguna toma abierta.", "tenue")
        self.b_transcribir = tema.boton("Transcribir", self.transcribir, "primario")
        self.b_cancelar = tema.boton("Cancelar", self.cancelar)
        self.b_oir = tema.boton("Escuchar audio", lambda: tema.abrir_en_sistema(self._audio()))
        self.barra = QProgressBar()
        self.barra.setRange(0, 1000)
        self.barra.setTextVisible(False)
        self.e_estado = tema.etiqueta("", "tenue")
        t2, v2 = tema.tarjeta("2 · Transcribir")
        v2.addLayout(tema.fila(tema.etiqueta("Modelo", "tenue", False), self.modelo, self.b_descargar, estirar=self.modelo))
        v2.addWidget(self.e_modelo)
        v2.addLayout(tema.fila(tema.etiqueta("Idioma", "tenue", False), self.idioma, estirar=self.idioma))
        v2.addLayout(tema.fila(self.hablada, self.cantada, None))
        v2.addWidget(self.e_cantada)
        v2.addWidget(self.e_toma)
        v2.addLayout(tema.fila(self.b_transcribir, self.b_cancelar, self.b_oir, estirar=self.b_transcribir))
        v2.addWidget(self.barra)
        v2.addWidget(self.e_estado)
        self.cantada.toggled.connect(lambda si: self.e_cantada.setVisible(si))
        self.e_cantada.setVisible(False)


        # -- derecha: texto -----------------------------------------------------
        self.marcas = QCheckBox("Marcas de tiempo")
        self.marcas.setChecked(a["marcas"])
        self.marcas.toggled.connect(self._cambiar_marcas)
        self.buscar = QLineEdit()
        self.buscar.setPlaceholderText("Buscar en el texto…")
        self.buscar.returnPressed.connect(self._buscar)
        self.texto = QPlainTextEdit()
        self.texto.setPlaceholderText("Aquí aparecerá la transcripción. Puedes corregirla libremente: una línea por frase.")
        self.texto.textChanged.connect(self._botones)
        self.b_copiar = tema.boton("Copiar todo", lambda: QGuiApplication.clipboard().setText(self.texto.toPlainText()))
        self.b_guardar = tema.boton("Guardar", self.guardar, "primario", "Guarda la letra corregida en el proyecto")
        self.b_exportar = tema.boton("Exportar…", self.exportar, ayuda="TXT, SRT, VTT o LRC")
        self.b_abrir_texto = tema.boton("Abrir texto…", self.abrir_texto, ayuda="Carga un TXT, SRT, VTT o LRC para revisarlo")
        self.e_texto = tema.etiqueta("", "tenue")
        t3, v3 = tema.tarjeta("3 · Revisar y exportar la letra")
        v3.addLayout(tema.fila(self.marcas, None, self.buscar, tema.boton("Siguiente", self._buscar)))
        v3.addWidget(self.texto, 1)
        v3.addWidget(self.e_texto)
        v3.addLayout(tema.fila(self.b_copiar, self.b_abrir_texto, None, self.b_exportar, self.b_guardar))

        cuerpo = QHBoxLayout()
        cuerpo.setSpacing(14)
        cuerpo.addWidget(tema.columna(t1, t2), 4)
        cuerpo.addWidget(t3, 6)
        v = QVBoxLayout(self)
        v.setContentsMargins(22, 18, 22, 18)
        v.setSpacing(12)
        v.addWidget(tema.etiqueta("Letras", "titulo"))
        v.addWidget(tema.etiqueta("De voz a texto, en tu equipo y sin conexión: dicta, graba o importa un audio y corrige el resultado.", "tenue"))
        v.addLayout(cuerpo, 1)
        self.recargar_modelos()

    # -- estado -------------------------------------------------------------
    @property
    def ocupada(self):
        return self.captura.grabando or self._final is not None

    def _audio(self):
        if self.proyecto:
            a = proyectos.leer(self.proyecto).get("audio")
            if a and (self.proyecto / a).is_file():
                return self.proyecto / a
        return None

    def _modelo_listo(self):
        return bool(self.modelo.currentData()) and letras.instalado(self.modelo.currentData())

    def recargar_modelos(self):
        elegido = self.modelo.currentData() or config.cargar()["modelo"]
        self.modelo.blockSignals(True)
        self.modelo.clear()
        for n, (_, mb, _, desc) in letras.MODELOS.items():
            self.modelo.addItem(f"{n} — {desc}  [{'descargado' if letras.instalado(n) else f'{mb} MB por descargar'}]", n)
        self.modelo.setCurrentIndex(max(0, self.modelo.findData(elegido)))
        self.modelo.blockSignals(False)
        self._modelo_cambiado()

    def _modelo_cambiado(self):
        n = self.modelo.currentData()
        if not n:
            return
        _, mb, ram, _ = letras.MODELOS[n]
        self.e_modelo.setText(f"Ocupa {mb} MB en models/ y usa ≈ {ram / 1000:.1f} GB de memoria al transcribir (solo CPU). "
                              + ("Ya está descargado." if letras.instalado(n) else "Aún no está descargado: pulsa «Descargar modelo»."))
        a = config.cargar()
        a["modelo"] = n
        config.guardar(a)
        self._botones()

    def _al_cambiar_captura(self):
        grabando = self.captura.grabando
        if grabando and not self._grababa:  # empieza una toma nueva: lienzo en blanco
            self.proyecto = self.archivo = None
            self._poner([])
            self.e_toma.setText("Grabando una toma nueva…")
            if self.en_vivo.isChecked() and self._modelo_listo():
                self._asegurar_motor()  # se va cargando mientras llega el primer segmento
        self._grababa = grabando
        self._botones()

    def _botones(self):
        trabajando, grabando = self._final is not None, self.captura.grabando
        listo = self._modelo_listo()
        hay_texto = bool(self.texto.toPlainText().strip())
        self.b_descargar.setEnabled(not listo and not trabajando)
        self.b_importar.setEnabled(not trabajando and not grabando)
        self.b_transcribir.setEnabled(listo and self._audio() is not None and not trabajando and not grabando)
        self.b_transcribir.setToolTip("" if listo else "Primero descarga el modelo elegido")
        self.b_cancelar.setEnabled(trabajando)
        self.b_oir.setEnabled(self._audio() is not None)
        self.modelo.setEnabled(not trabajando and not grabando)
        self.en_vivo.setEnabled(not grabando)
        for b in (self.b_copiar, self.b_exportar):
            b.setEnabled(hay_texto)
        self.b_guardar.setEnabled(hay_texto and self.proyecto is not None and not trabajando)
        self.texto.setReadOnly(trabajando)

    def descargar(self):
        n = self.modelo.currentData()
        _, mb, ram, desc = letras.MODELOS[n]
        tema.descarga_con_dialogo(
            self, f"Descargar el modelo «{n}»",
            f"{desc}.\n\n• Tamaño de la descarga: {mb} MB\n• Memoria al transcribir: ≈ {ram / 1000:.1f} GB\n"
            f"• Se guarda en: {letras.carpeta_modelo(n)}\n\nEs un modelo Whisper (licencia MIT) que se baja de "
            "huggingface.co. Solo hace falta Internet esta vez; después funciona sin conexión.",
            lambda progreso, cancelar: letras.descargar_modelo(n, progreso, cancelar),
            lambda ok: (self.recargar_modelos(), self.cambio.emit()))

    # -- entrada --------------------------------------------------------------
    def importar(self):
        ruta, _ = QFileDialog.getOpenFileName(self, "Importar audio o vídeo", "", f"Audio y vídeo ({letras.MEDIOS});;Todos (*)")
        if not ruta:
            return
        try:
            d = proyectos.crear(self.nombre.text().strip() or Path(ruta).stem, "letra", config.cargar()["carpeta_proyectos"] or None)
            proyectos.importar_audio(d, ruta)
        except OSError as e:
            return tema.error(self, "No se pudo importar", f"{e}\n\nComprueba que el archivo existe y que hay espacio libre.")
        self.nombre.clear()
        self.abrir_proyecto(d)
        self.cambio.emit()

    def _toma_lista(self, carpeta):
        """Al detener la grabación se transcribe la toma entera (más precisa que el borrador en vivo)."""
        self.nombre.clear()
        borrador = self.segs
        self._vivos.clear()  # los borradores que lleguen tarde ya no interesan
        self.abrir_proyecto(carpeta)
        self.cambio.emit()
        if self._modelo_listo():
            self.transcribir()
        elif borrador:
            self._poner(borrador)

    def abrir_proyecto(self, carpeta):
        self.proyecto = Path(carpeta)
        d = proyectos.leer(self.proyecto)
        letras_guardadas = [r for r in d["resultados"] if r["tipo"] == "letra" and (self.proyecto / r["segmentos"]).is_file()]
        marca = "  ·  ⚠ toma incompleta" if d.get("incompleta") else ""
        self.e_toma.setText(f"<b>{d['nombre']}</b>  ·  audio: {d.get('audio') or '—'}{marca}")
        self.e_estado.setText(" ".join(d.get("avisos", [])))
        self.barra.setValue(0)
        if letras_guardadas:
            self.archivo = letras_guardadas[-1]["segmentos"]
            self._poner(json.loads((self.proyecto / self.archivo).read_text(encoding="utf-8"))["segmentos"])
        else:
            self.archivo = None
            self._poner([])
        self._botones()

    # -- motor ----------------------------------------------------------------
    def _asegurar_motor(self):
        n = self.modelo.currentData()
        if self.voz and self.voz.viva() and self.modelo_cargado == n:
            return
        self._parar_motor()
        self.modelo_cargado = n
        self.voz = tareas.Tarea("partitura_libre.workers.voz", [str(letras.carpeta_modelo(n))], "app",
                                lambda ev: tema.en_ui(lambda: self._evento(ev)),
                                lambda codigo, cancelada, t=None: tema.en_ui(lambda: self._motor_cerrado(codigo, cancelada)))

    def _parar_motor(self):
        if self.voz:
            self.voz.cancelar()
            self.voz = None
        self._vivos.clear()

    def _pedir(self, audio, desfase=0.0, borrar=False):
        self._asegurar_motor()
        self._id += 1
        self.voz.enviar(id=self._id, audio=str(audio), idioma=self.idioma.currentData(),
                        cantada=self.cantada.isChecked(), desfase=desfase, borrar=borrar)
        return self._id

    def transcribir(self):
        a = config.cargar()
        a["idioma"] = self.idioma.currentData()
        config.guardar(a)
        self._nuevos = []
        self.barra.setValue(0)
        self.e_estado.setText("Cargando el modelo y analizando el audio…")
        tema.reclasificar(self.e_estado, "tenue")
        self._final = self._pedir(self._audio())
        self._carpeta_final = self.proyecto
        self._botones()

    def _segmento_vivo(self, ruta, t0):
        if self._modelo_listo():
            self._vivos.add(self._pedir(ruta, t0, borrar=True))

    def cancelar(self):
        if self._final is not None:
            self._final = None
            self._parar_motor()  # matar el proceso es la cancelación segura; se recarga al volver a usarlo
            self.barra.setValue(0)
            self.e_estado.setText("Transcripción cancelada. El audio original se conserva.")
            self._botones()

    def _evento(self, ev):
        i = ev.get("id")
        if ev["t"] == "segmento" and i in self._vivos:
            self.segs.append({k: ev[k] for k in ("inicio", "fin", "texto", "dudoso")})
            self._poner(self.segs, "Borrador en vivo: al detener se transcribirá la toma completa.")
        elif ev["t"] in ("fin", "error") and i in self._vivos:
            self._vivos.discard(i)  # los WAV temporales se limpian al empezar otra grabación
        elif i != self._final:
            return
        elif ev["t"] == "idioma":
            self._idioma = ev["idioma"]
            self.e_estado.setText(f"Idioma: {letras.IDIOMAS.get(ev['idioma'], ev['idioma'])} "
                                  f"({ev['prob'] * 100:.0f} % de confianza). Transcribiendo {ev['dur']:.0f} s de audio…")
        elif ev["t"] == "segmento":
            self._nuevos.append({k: ev[k] for k in ("inicio", "fin", "texto", "dudoso")})
            self.barra.setValue(int(ev["v"] * 1000))
            self._poner(self._nuevos)
        elif ev["t"] == "fin":
            self._final = None
            self.barra.setValue(1000)
            self._poner(self._nuevos)
            if not self._nuevos:
                self.e_estado.setText("No se reconoció ninguna palabra en el audio. No se ha inventado texto.")
                tema.reclasificar(self.e_estado, "aviso")
                tema.dialogo(self, "No se reconoció ninguna palabra", "El motor no encontró voz inteligible en esta toma y no se ha inventado texto.\n\n"
                             "• Si es una canción, marca «Voz cantada (modo de prueba)» y vuelve a pulsar «Transcribir».\n"
                             "• Si el sonido venía de este equipo (Spotify, un vídeo…), grábalo eligiendo «Sonido del equipo» en "
                             "«Entrada de audio»: por el micrófono llega flojo y con ruido.\n"
                             "• Comprueba el idioma elegido y, si puedes, usa un modelo más preciso (medium).\n\n"
                             "El audio original se conserva: usa «Escuchar audio» para comprobar cómo quedó.", tipo="aviso")
            else:
                self._guardar_en(self._carpeta_final, nueva=True)
                dud = sum(s["dudoso"] for s in self._nuevos)
                self.e_estado.setText(f"Transcripción terminada y guardada: {len(self._nuevos)} frases"
                                      + (f", {dud} marcadas con ⚠ para revisar." if dud else "."))
            self.cambio.emit()
            self._botones()
        elif ev["t"] == "error":
            self._final = None
            self.e_estado.setText(ev["msg"])
            tema.reclasificar(self.e_estado, "error")
            tema.error(self, "No se pudo transcribir", ev["msg"] + "\n\nEl audio original se conserva. Si el archivo es "
                       "un vídeo o un formato poco común, prueba a convertirlo a WAV o MP3.")
            self._botones()

    def _motor_cerrado(self, codigo, cancelada):
        if cancelada or self._final is None:
            return
        self._final, self.voz = None, None
        motivo = (f"El motor de voz se cerró inesperadamente (código {codigo}). Suele deberse a falta de memoria: "
                  "prueba con un modelo más pequeño. Detalles en logs/motores.log.")
        self.e_estado.setText(motivo)
        tema.reclasificar(self.e_estado, "error")
        tema.error(self, "El motor de voz se detuvo", motivo)
        self._botones()

    # -- texto ------------------------------------------------------------------
    def _poner(self, segs, nota=""):
        self.segs = list(segs)
        self.texto.blockSignals(True)
        self.texto.setPlainText(letras.a_texto(self.segs, self.marcas.isChecked()))
        self.texto.blockSignals(False)
        self.texto.moveCursor(QTextCursor.End)
        dud = sum(bool(s.get("dudoso")) for s in self.segs)
        self.e_texto.setText(nota or (f"{len(self.segs)} frases" + (f" · {dud} con ⚠ (poco fiables: escúchalas y corrígelas; "
                             "borra el símbolo cuando estén revisadas)" if dud else "")) if self.segs else "")
        self._botones()

    def _leer_texto(self):
        """Segmentos según lo que hay ahora en el editor (con las correcciones del usuario)."""
        self.segs = letras.de_texto(self.texto.toPlainText(), self.segs)
        return self.segs

    def _cambiar_marcas(self, si):
        a = config.cargar()
        a["marcas"] = si
        config.guardar(a)
        if self._final is None:
            self._poner(self._leer_texto())

    def _buscar(self):
        t = self.buscar.text()
        if t and not self.texto.find(t):
            self.texto.moveCursor(QTextCursor.Start)  # vuelve a empezar desde arriba
            if not self.texto.find(t, QTextDocument.FindFlags()):
                self.e_texto.setText(f"«{t}» no aparece en el texto.")

    def abrir_texto(self):
        ruta, _ = QFileDialog.getOpenFileName(self, "Abrir texto", str(rutas.DATOS), "Letras (*.txt *.srt *.vtt *.lrc)")
        if ruta:
            try:
                self._poner(exportar.leer(Path(ruta).read_text(encoding="utf-8-sig", errors="replace")))
            except OSError as e:
                tema.error(self, "No se pudo abrir", str(e))

    def _guardar_en(self, carpeta, nueva=False):
        """Guarda segmentos (.letra.json) y texto (.txt) en el proyecto. Una transcripción
        nueva nunca pisa una letra anterior; «Guardar» actualiza la versión abierta."""
        segs = self._nuevos if nueva else self._leer_texto()
        if nueva or not self.archivo or carpeta != self.proyecto:
            f_json = rutas.ruta_unica(carpeta, carpeta.name, ".letra.json", (".txt",))
            anotar = True
        else:
            f_json, anotar = carpeta / self.archivo, False
        f_txt = f_json.with_name(f_json.name.replace(".letra.json", ".txt"))
        datos = {"idioma": getattr(self, "_idioma", ""), "modelo": self.modelo_cargado,
                 "cantada": self.cantada.isChecked(), "segmentos": segs}
        config.escribir_json(f_json, datos)
        f_txt.write_text(exportar.txt(segs), encoding="utf-8")
        if anotar:
            proyectos.anotar_resultado(carpeta, "letra", segmentos=f_json.name, texto=f_txt.name)
        if carpeta == self.proyecto:
            self.archivo = f_json.name
        return f_txt

    def guardar(self):
        try:
            f = self._guardar_en(self.proyecto)
            self.e_texto.setText(f"Guardado en {f}")
            self.cambio.emit()
        except OSError as e:
            tema.error(self, "No se pudo guardar", f"{e}\n\nComprueba el espacio libre y los permisos de la carpeta.")

    def exportar(self):
        segs = self._leer_texto()
        base = (self.proyecto / self.proyecto.name) if self.proyecto else rutas.DATOS / "letra"
        ruta, filtro = QFileDialog.getSaveFileName(
            self, "Exportar letra", str(base) + ".txt",
            "Texto (*.txt);;Subtítulos SRT (*.srt);;Subtítulos WebVTT (*.vtt);;Letra sincronizada LRC (*.lrc)")
        if not ruta:
            return
        ruta = Path(ruta)
        if ruta.suffix.lower() not in exportar.FORMATOS:
            ruta = ruta.with_name(ruta.name + filtro[-5:-1])
        formato = ruta.suffix.lower()
        if formato != ".txt":
            sin = len(segs) - len(exportar.con_tiempos(segs))
            if sin == len(segs):
                return tema.error(self, "Faltan las marcas de tiempo", f"El formato {formato[1:].upper()} necesita tiempos y este "
                                  "texto no los tiene. Exporta como TXT, o activa «Marcas de tiempo» y escribe [mm:ss.cc] al inicio de cada línea.")
            if sin and not tema.confirmar(self, "Líneas sin tiempo", f"{sin} línea(s) no tienen marca de tiempo y no se "
                                          f"incluirán en el {formato[1:].upper()}.", "Exportar igualmente"):
                return
            segs = exportar.con_tiempos(segs)
        if not tema.avisar_si_externo(self, ruta):
            return
        try:
            ruta.write_text(exportar.FORMATOS[formato](segs), encoding="utf-8")
            self.e_texto.setText(f"Exportado a {ruta}")
        except OSError as e:
            tema.error(self, "No se pudo exportar", f"{e}\n\nElige otra carpeta o libera espacio.")

    def cerrar(self):
        self.captura.cerrar()
        self._parar_motor()
