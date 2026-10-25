"""Sección Lector: abre una partitura (PDF, imagen, MusicXML, MXL, MIDI, MuseScore) y la toca con el instrumento
elegido, solo las notas, para comprobar de oído que se lee bien."""
import shutil
import threading
from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QComboBox, QFileDialog, QProgressBar, QVBoxLayout, QWidget

from .. import audio, editor, lector, rutas
from . import tema


class PaginaLector(QWidget):
    cambio = Signal()  # se descargó un componente (MuseScore o Audiveris): Ajustes lo muestra

    def __init__(self):
        super().__init__()
        self.setObjectName("pagina")
        self.archivo, self.leida, self.wavs, self.wav = None, None, {}, None   # leida: su MusicXML (un PDF se lee una vez)
        self._cancelar = None   # threading.Event mientras se convierte
        self.carpeta = rutas.TEMP / "lector"

        self.b_abrir = tema.boton("Abrir partitura…", self.abrir, "primario")
        self.e_archivo = tema.etiqueta("Ninguna partitura abierta.", "tenue")
        self.instrumento = QComboBox()
        self.instrumento.addItems(list(lector.INSTRUMENTOS))
        self.instrumento.setMaxVisibleItems(18)
        self.b_tocar = tema.boton("▶ Interpretar", self.tocar, "primario")
        self.b_parar = tema.boton("⏹ Parar", self.parar)
        self.b_guardar = tema.boton("Guardar audio…", self.guardar)
        self.b_cancelar = tema.boton("Cancelar", self.cancelar, "peligro")
        self.barra = QProgressBar()
        self.barra.setRange(0, 0)   # sin porcentaje: Audiveris y MuseScore no lo dan
        self.barra.setTextVisible(False)
        self.barra.setFixedHeight(8)
        self.e_estado = tema.etiqueta("", "tenue")

        tp, vp = tema.tarjeta("Partitura")
        vp.addWidget(tema.etiqueta("PDF, imagen (PNG, JPG, TIFF), MusicXML, MXL, MIDI o MuseScore. Se tocan solo las notas: la letra "
                                   "no se canta. Todas las partes suenan con el instrumento elegido.", "tenue"))
        vp.addLayout(tema.fila(self.b_abrir, self.e_archivo, estirar=self.e_archivo))
        vp.addLayout(tema.fila(tema.etiqueta("Instrumento:", ajustar=False), self.instrumento, None))
        vp.addLayout(tema.fila(self.b_tocar, self.b_parar, self.b_guardar, None, self.b_cancelar))
        vp.addWidget(self.barra)
        vp.addWidget(self.e_estado)

        tc, vc = tema.tarjeta("Componentes")
        self.e_ms, self.e_av = tema.etiqueta(), tema.etiqueta()
        self.b_ms = tema.boton(f"Descargar MuseScore portable ({editor.PORTABLE['mb']} MB)", self._bajar_musescore)
        self.b_av = tema.boton(f"Descargar Audiveris ({lector.AUDIVERIS['mb']} MB)", self._bajar_audiveris)
        vc.addWidget(self.e_ms)
        vc.addLayout(tema.fila(self.b_ms, None))
        vc.addWidget(self.e_av)
        vc.addLayout(tema.fila(self.b_av, None))
        vc.addWidget(tema.etiqueta("Se guardan dentro de la carpeta del programa (runtime/) y no se instalan en el sistema. "
                                   f"{editor.LICENCIA} {lector.LICENCIA}", "tenue"))

        v = QVBoxLayout(self)
        v.setContentsMargins(22, 18, 14, 18)
        v.setSpacing(12)
        v.addWidget(tema.etiqueta("Lector de partituras", "titulo"))
        v.addWidget(tema.etiqueta("Escucha cómo suena una partitura para comprobar que está bien escrita: la tuya exportada "
                                  "desde Partituras o cualquier otra.", "tenue"))
        v.addWidget(tema.columna(tp, tc), 1)
        self.recargar()

    @property
    def ocupada(self):
        return self._cancelar is not None

    def recargar(self):
        exe, origen = editor.buscar()
        self.e_ms.setText("<b>MuseScore</b> (necesario: convierte la partitura y le da sonido): "
                          + (f"disponible ({origen})." if exe else "no está. Descárgalo para poder interpretar."))
        self.e_av.setText("<b>Audiveris</b> (solo para PDF e imágenes: reconoce la partitura impresa): "
                          + ("disponible." if lector.audiveris() else "no está. Descárgalo para leer PDF o imágenes."))
        self.b_ms.setVisible(not exe)
        self.b_av.setVisible(not lector.audiveris())
        self._botones()

    def _botones(self):
        ocupada = self.ocupada
        self.b_abrir.setEnabled(not ocupada)
        self.instrumento.setEnabled(not ocupada)
        self.b_tocar.setEnabled(self.archivo is not None and not ocupada)
        self.b_parar.setEnabled(self.wav is not None and not ocupada)
        self.b_guardar.setEnabled(self.wav is not None and not ocupada)
        self.b_cancelar.setVisible(ocupada)
        self.barra.setVisible(ocupada)

    def _estado(self, texto, clase="tenue"):
        self.e_estado.setText(texto)
        tema.reclasificar(self.e_estado, clase)

    # -- acciones ----------------------------------------------------------------
    def abrir(self, ruta=None):
        if not ruta:
            ruta, _ = QFileDialog.getOpenFileName(self, "Abrir partitura", str(Path.home()), lector.FILTRO)
        if not ruta:
            return
        audio.parar_reproduccion()
        self.archivo, self.leida, self.wavs, self.wav = Path(ruta), None, {}, None
        shutil.rmtree(self.carpeta, ignore_errors=True)
        self.e_archivo.setText(self.archivo.name)
        tema.reclasificar(self.e_archivo, "")
        self._estado("Elige el instrumento y pulsa «Interpretar».")
        self._botones()

    def tocar(self):
        if not self._componentes():
            return
        audio.parar_reproduccion()
        instrumento = self.instrumento.currentText()
        if instrumento in self.wavs and self.wavs[instrumento].is_file():   # ya preparado: suena al momento
            return self._sonar(self.wavs[instrumento], instrumento)
        if self.leida is not None and not self.leida.is_file():   # se vaciaron los temporales: se vuelve a leer
            self.leida, self.wavs = None, {}
        cancelar, archivo, leida = threading.Event(), self.archivo, self.leida
        self._cancelar = cancelar
        self._estado("Preparando el sonido…")
        self._botones()

        def trabajo():
            xml = leida or lector.a_musicxml(archivo, self.carpeta / "leida", cancelar,
                                             lambda t: tema.en_ui(lambda: self._estado(t) if self._cancelar is cancelar else None))
            tema.en_ui(lambda: self._estado("Dando sonido a la partitura…") if self._cancelar is cancelar else None)
            destino = self.carpeta / lector.INSTRUMENTOS[instrumento][0]
            destino.mkdir(parents=True, exist_ok=True)
            return xml, lector.sonar(xml, instrumento, destino, cancelar)

        def fin(r, e):
            if self._cancelar is not cancelar:   # se abrió otra partitura o se canceló: el resultado ya no vale
                return
            self._cancelar = None
            self._botones()
            if isinstance(e, lector.Cancelado):
                return self._estado("Cancelado.")
            if e:
                self._estado("No se pudo interpretar la partitura.", "error")
                return tema.error(self, "No se pudo interpretar", str(e))
            if archivo == self.archivo:
                self.leida = r[0]
                self.wavs[instrumento] = r[1]
                self._sonar(r[1], instrumento)
        tema.en_hilo(trabajo, fin)

    def _sonar(self, wav, instrumento):
        self.wav = wav
        self._botones()
        try:
            segundos = audio.reproducir_archivo(wav)
        except audio.ErrorAudio as e:
            self._estado("Preparado, pero no se puede reproducir.", "error")
            return tema.error(self, "No se puede reproducir", f"{e}\n\nPuedes guardar el audio y escucharlo con otro programa.")
        self._estado(f"Sonando «{self.archivo.name}» con {instrumento.lower()} ({int(segundos // 60)}:{int(segundos % 60):02d}).")

    def parar(self):
        audio.parar_reproduccion()
        self._estado("Parado.")

    def guardar(self):
        sugerido = Path.home() / f"{self.archivo.stem} ({self.instrumento.currentText().lower()}).wav"
        ruta, _ = QFileDialog.getSaveFileName(self, "Guardar audio", str(sugerido), "Audio WAV (*.wav)")
        if not ruta or not tema.avisar_si_externo(self, ruta):
            return
        try:
            shutil.copyfile(self.wav, Path(ruta).with_suffix(".wav"))
            self._estado(f"Audio guardado en {Path(ruta).with_suffix('.wav')}")
        except OSError as e:
            tema.error(self, "No se pudo guardar", f"{e}\n\nElige otra carpeta o libera espacio.")

    def cancelar(self):
        if self._cancelar is not None:
            self._cancelar.set()
            self._estado("Cancelando…")

    def cerrar(self):
        """Al cerrar el programa: corta la conversión en curso (su resultado ya no se usa) y el sonido."""
        if self._cancelar is not None:
            self._cancelar.set()
            self._cancelar = None
        audio.parar_reproduccion()

    # -- componentes ---------------------------------------------------------------
    def _componentes(self):
        """True si está lo necesario para este archivo; si no, ofrece descargarlo."""
        if not editor.buscar()[0]:
            self._bajar_musescore()
            return False
        if self.archivo.suffix.lower() in lector.IMAGENES and not lector.audiveris():
            self._bajar_audiveris()
            return False
        return True

    def _bajar_musescore(self):
        tema.descarga_con_dialogo(
            self, "Descargar MuseScore portable",
            f"El lector usa MuseScore Studio {editor.VERSION} para convertir la partitura y darle sonido con instrumentos reales.\n\n"
            f"• Descarga: {editor.PORTABLE['mb']} MB (≈ {editor.PORTABLE['mb'] * 3} MB descomprimido)\n• Se guarda en: {editor.CARPETA}\n"
            f"• No se instala en el sistema ni pide contraseña.\n\n{editor.LICENCIA}",
            editor.instalar_portable, lambda ok: (self.recargar(), self.cambio.emit()))

    def _bajar_audiveris(self):
        tema.descarga_con_dialogo(
            self, "Descargar Audiveris",
            f"Audiveris {lector.VERSION} reconoce las partituras impresas en PDF o en imagen y las convierte en notas.\n\n"
            f"• Descarga: {lector.AUDIVERIS['mb']} MB (≈ 190 MB descomprimido; trae su propio Java)\n• Se guarda en: {lector.CARPETA}\n"
            f"• No se instala en el sistema ni pide contraseña.\n\n{lector.LICENCIA}",
            lector.instalar, lambda ok: (self.recargar(), self.cambio.emit()))
