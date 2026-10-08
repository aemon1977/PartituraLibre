"""Panel de captura compartido por Partituras y Letras: micrófono, nivel y controles de grabación."""
import math
import shutil
from datetime import datetime

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import QComboBox, QProgressBar, QVBoxLayout, QWidget

from .. import audio, config, proyectos, rutas
from . import tema

ESPACIO_MINIMO_MB = 200


class PanelCaptura(QWidget):
    terminada = Signal(object)       # carpeta del proyecto con la toma guardada
    segmento = Signal(object, float)  # (wav temporal, segundo de inicio) para transcripción en vivo
    estado = Signal()                 # cambió grabando/parado: las páginas ajustan sus botones

    def __init__(self, tipo, nombre, carpeta, segmento_s=lambda: 0):
        """`nombre()`, `carpeta()` y `segmento_s()` se consultan al empezar a grabar."""
        super().__init__()
        self.tipo, self._nombre, self._carpeta, self._segmento_s = tipo, nombre, carpeta, segmento_s
        self.g = None           # Grabadora activa (toma real o prueba de nivel)
        self.proyecto = None    # carpeta del proyecto que se está grabando
        self._fin_prueba = 0

        self.micro = QComboBox()
        self.micro.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.micro.setMinimumContentsLength(16)
        self.b_actualizar = tema.boton("Actualizar", self.cargar_micros, ayuda="Volver a buscar micrófonos")
        self.b_probar = tema.boton("Probar nivel", self.probar, ayuda="Escucha el micrófono 10 s sin grabar nada")
        self.nivel = QProgressBar()
        self.nivel.setRange(0, 100)
        self.nivel.setTextVisible(False)
        self.reloj = tema.etiqueta("00:00:00", "reloj", False)
        self.texto = tema.etiqueta("Listo para grabar.", "tenue")
        self.b_grabar = tema.boton("●  Grabar", self.grabar, "primario")
        self.b_pausa = tema.boton("Pausar", self.pausar)
        self.b_detener = tema.boton("■  Detener", self.detener)
        self.b_cancelar = tema.boton("Descartar", self.cancelar, "peligro", "Detiene y borra esta toma")

        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(10)
        v.addWidget(tema.etiqueta("Micrófono", "tenue"))
        v.addLayout(tema.fila(self.micro, self.b_actualizar, self.b_probar, estirar=self.micro))
        v.addLayout(tema.fila(tema.etiqueta("Nivel", "tenue", False), self.nivel, estirar=self.nivel))
        v.addLayout(tema.fila(self.reloj, self.texto, estirar=self.texto))
        v.addLayout(tema.fila(self.b_grabar, self.b_pausa, self.b_detener, self.b_cancelar, estirar=self.b_grabar))

        self._tic = QTimer(self)
        self._tic.setInterval(60)
        self._tic.timeout.connect(self._refrescar)
        self.cargar_micros()
        self._botones()

    # -- estado ---------------------------------------------------------------
    @property
    def grabando(self):
        return self.g is not None and self.g.destino is not None

    def _botones(self):
        hay, grab, prueba = self.micro.count() > 0 and self.micro.currentData() is not None, self.grabando, self.g is not None and not self.grabando
        self.b_grabar.setEnabled(hay and not grab)
        self.b_probar.setEnabled(hay and not grab)
        self.b_probar.setText("Parar prueba" if prueba else "Probar nivel")
        for b in (self.b_pausa, self.b_detener, self.b_cancelar):
            b.setEnabled(grab)
        self.micro.setEnabled(self.g is None)
        self.b_actualizar.setEnabled(self.g is None)
        self.estado.emit()

    def _decir(self, texto, clase="tenue"):
        self.texto.setText(texto)
        tema.reclasificar(self.texto, clase)

    def cargar_micros(self, refrescar=True):
        self.micro.clear()
        try:
            micros = audio.microfonos(refrescar and self.g is None)
        except audio.ErrorAudio as e:
            self.micro.addItem("Audio no disponible", None)
            self._decir(str(e), "error")
            self._botones()
            return
        for m in micros:
            self.micro.addItem(m["nombre"] + ("  (predeterminado)" if m["predeterminado"] else ""), m["indice"])
        if not micros:
            self.micro.addItem("No se ha encontrado ningún micrófono", None)
            self._decir("Conecta un micrófono y pulsa «Actualizar». También puedes importar un archivo.", "aviso")
        else:
            guardado = self.micro.findText(config.cargar()["microfono"], Qt.MatchStartsWith) if config.cargar()["microfono"] else -1
            self.micro.setCurrentIndex(max(guardado, 0))
            self._decir("Listo para grabar.")
        self._botones()

    # -- prueba de nivel ------------------------------------------------------
    def probar(self):
        if self.g:
            return self._parar_prueba()
        try:
            self.g = audio.Grabadora(dispositivo=self.micro.currentData())
            self.g.iniciar()
        except audio.ErrorAudio as e:
            self.g = None
            return tema.error(self, "Micrófono no disponible", str(e))
        self._fin_prueba = 10_000 // self._tic.interval()
        self._decir("Probando: habla o toca y observa el nivel. No se guarda nada.")
        self._tic.start()
        self._botones()

    def _parar_prueba(self):
        if self.g and not self.grabando:
            self.g.detener()
            self.g = None
            self._tic.stop()
            self.nivel.setValue(0)
            self._decir("Listo para grabar.")
            self._botones()

    # -- grabación ------------------------------------------------------------
    def grabar(self):
        self._parar_prueba()
        carpeta = self._carpeta()
        libre = shutil.disk_usage(carpeta if carpeta and rutas.Path(carpeta).is_dir() else rutas.RAIZ).free // 2**20
        if libre < ESPACIO_MINIMO_MB:
            return tema.error(self, "Poco espacio en disco", f"Solo quedan {libre} MB libres. Libera espacio "
                              "(o elige otra carpeta) antes de grabar para no perder la toma.")
        try:
            self.proyecto = proyectos.crear(self._nombre() or f"{self.tipo} {datetime.now():%Y-%m-%d %H.%M.%S}", self.tipo, carpeta)
        except OSError as e:
            return tema.error(self, "No se pudo crear el proyecto", f"{e}\n\nElige otra carpeta de destino.")
        wav = rutas.ruta_unica(self.proyecto, self.proyecto.name, ".wav")
        seg = self._segmento_s()
        carpeta_seg = rutas.TEMP / "vivo"
        if seg:
            shutil.rmtree(carpeta_seg, ignore_errors=True)
            carpeta_seg.mkdir(parents=True, exist_ok=True)
        self.g = audio.Grabadora(wav, self.micro.currentData(), seg, carpeta_seg,
                                 lambda ruta, t0: self.segmento.emit(ruta, t0))
        try:
            self.g.iniciar()
        except audio.ErrorAudio as e:
            self.g = None
            proyectos.eliminar(self.proyecto)  # no llegó a grabarse nada
            self.proyecto = None
            self._botones()
            return tema.error(self, "No se pudo grabar", str(e))
        proyectos.actualizar(self.proyecto, audio=wav.name, origen="grabación", estado="grabando")
        a = config.cargar()
        a["microfono"] = self.micro.currentText().replace("  (predeterminado)", "")
        config.guardar(a)
        self._decir(f"Grabando en «{wav.name}»…", "aviso")
        self.b_pausa.setText("Pausar")
        self._tic.start()
        self._botones()

    def pausar(self):
        self.g.pausar(not self.g.pausada)
        self.b_pausa.setText("Reanudar" if self.g.pausada else "Pausar")
        self._decir("En pausa: no se está grabando." if self.g.pausada else "Grabando…", "aviso")

    def detener(self):
        """Cierra la toma y la conserva siempre, aunque esté incompleta."""
        if not self.grabando:
            return
        g, carpeta = self.g, self.proyecto
        g.detener()
        self._tic.stop()
        self.g = self.proyecto = None
        self.nivel.setValue(0)
        proyectos.actualizar(carpeta, estado="grabado", incompleta=g.incompleta, avisos=g.avisos(),
                             duracion=round(g.segundos, 2))
        self._botones()
        if g.incompleta:
            self._decir("Toma guardada, pero INCOMPLETA. " + " ".join(g.avisos()), "error")
            tema.dialogo(self, "Grabación incompleta", "La toma se ha guardado, pero no está completa:\n\n• "
                         + "\n• ".join(g.avisos()), tipo="aviso")
        elif g.muda:
            self._decir("Toma guardada, pero no contiene sonido.", "aviso")
            tema.dialogo(self, "La toma está en silencio", "Se ha grabado, pero el micrófono no envió ninguna señal.\n\n"
                         "Comprueba que no esté silenciado o apagado y que has elegido la entrada correcta; usa «Probar nivel» "
                         "y mira si la barra se mueve al hablar. En el control de sonido del sistema, sube el volumen de entrada.", tipo="aviso")
        else:
            self._decir(f"Toma guardada ({g.segundos:.1f} s) en {carpeta.name}.")
        self.terminada.emit(carpeta)

    def cancelar(self):
        if not self.grabando or not tema.confirmar(self, "Descartar la toma", "Se detendrá la grabación y se BORRARÁ "
                                                   "el audio de esta toma. No se puede deshacer.", "Descartar toma"):
            return
        self.g.cancelar()
        proyectos.eliminar(self.proyecto)
        self._tic.stop()
        self.g = self.proyecto = None
        self.nivel.setValue(0)
        self.reloj.setText("00:00:00")
        self._decir("Toma descartada.")
        self._botones()

    def cerrar(self):
        """Al cerrar la ventana: lo grabado se guarda, nunca se descarta."""
        self._parar_prueba()
        self.detener()

    def _refrescar(self):
        g = self.g
        if not g:
            return
        db = 20 * math.log10(max(g.nivel, 1e-4))            # -80..0 dB
        self.nivel.setValue(int(max(0, min(100, (db + 60) / 60 * 100))))
        clase = "alto" if g.nivel > 0.97 else ""
        if self.nivel.property("clase") != clase:
            tema.reclasificar(self.nivel, clase)
        if not self.grabando:
            self._fin_prueba -= 1
            if self._fin_prueba <= 0:
                self._parar_prueba()
            return
        s = int(g.segundos)
        self.reloj.setText(f"{s // 3600:02d}:{s // 60 % 60:02d}:{s % 60:02d}")
        if g.error:  # disco lleno, micrófono desconectado…: se guarda lo que haya
            self.detener()
        elif (g.desbordes or g.perdidos) and self.texto.property("clase") != "error":
            self._decir("Atención: se ha perdido algo de audio (equipo muy cargado). La toma quedará marcada como incompleta.", "error")
