"""Panel de captura compartido por Partituras y Letras: micrófono, nivel y controles de grabación."""
import math
import shutil
import time
from datetime import datetime

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import QComboBox, QProgressBar, QVBoxLayout, QWidget

from .. import audio, config, proyectos, rutas
from . import tema

ESPACIO_MINIMO_MB = 200


class PanelCaptura(QWidget):
    _avisado_flojo = False           # el diálogo de nivel bajo ya se mostró en esta sesión
    _prefiere_micro = False          # el usuario ya dijo que quiere el micrófono aunque suene audio en el equipo
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
        self._visto = (0.0, False)

        self.micro = QComboBox()
        self.micro.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.micro.setMinimumContentsLength(16)
        self.b_actualizar = tema.boton("Actualizar", self.cargar_micros, ayuda="Volver a buscar micrófonos")
        self.b_probar = tema.boton("Probar nivel", self.probar, ayuda="Escucha el micrófono 10 s sin grabar nada")
        self.b_sistema = tema.boton("Sonido del equipo", self.usar_sonido_del_equipo,
                                    ayuda="Para música o vídeos que suenan en este ordenador (Spotify, YouTube…): se graban "
                                          "directamente de la salida, sin pasar por altavoces y micrófono")
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
        v.addWidget(tema.etiqueta("Entrada de audio", "tenue"))
        v.addWidget(self.micro)
        v.addLayout(tema.fila(self.b_actualizar, self.b_probar, self.b_sistema, None))
        v.addLayout(tema.fila(tema.etiqueta("Nivel", "tenue", False), self.nivel, estirar=self.nivel))
        v.addLayout(tema.fila(self.reloj, self.texto, estirar=self.texto))
        v.addLayout(tema.fila(self.b_grabar, self.b_pausa, self.b_detener, self.b_cancelar, estirar=self.b_grabar))

        self.micro.currentIndexChanged.connect(lambda _: self._botones() if hasattr(self, "_tic") else None)
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
        hay, grab, prueba = self.micro.currentData() is not None, self.grabando, self.g is not None and not self.grabando
        self.b_grabar.setEnabled(hay and not grab)
        self.b_probar.setEnabled(hay and not grab)
        self.b_probar.setText("Parar prueba" if prueba else "Probar nivel")
        for b in (self.b_pausa, self.b_detener, self.b_cancelar):
            b.setEnabled(grab)
        self.micro.setEnabled(self.g is None)
        sistema = self._indice_sistema()
        self.b_sistema.setVisible(sistema >= 0)
        self.b_sistema.setEnabled(self.g is None and sistema != self.micro.currentIndex())
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
            self.micro.addItem(m["nombre"] + ("  (predeterminado)" if m["predeterminado"] else ""), m)
            self.micro.setItemData(self.micro.count() - 1, m["nombre"], Qt.ToolTipRole)
        if not micros:
            self.micro.addItem("No se ha encontrado ningún micrófono", None)
            self._decir("Conecta un micrófono y pulsa «Actualizar». También puedes importar un archivo.", "aviso")
        else:
            guardado = self.micro.findText(config.cargar()["microfono"], Qt.MatchStartsWith) if config.cargar()["microfono"] else -1
            self.micro.setCurrentIndex(max(guardado, 0))
            n = sum(not m["sistema"] for m in micros)
            self._decir("Listo para grabar." if len(micros) == 1 else f"{n} micrófono(s)"
                        + (" y el sonido del equipo" if n < len(micros) else "") + " disponibles: elige la entrada.")
        self._botones()

    def _indice_sistema(self):
        """Posición en la lista de la entrada que graba lo que suena por la salida en uso (-1 si no hay)."""
        return next((i for i in range(self.micro.count()) if (self.micro.itemData(i) or {}).get("sistema")), -1)

    def usar_sonido_del_equipo(self):
        i = self._indice_sistema()
        if i >= 0:
            self.micro.setCurrentIndex(i)
            self._decir("Se grabará lo que suene en este equipo, directamente y sin micrófono. Pon la música y pulsa «Grabar».")
            self._botones()

    def _ofrecer_sistema(self):
        """Si se va a grabar con un micrófono mientras suena audio en el equipo (un vídeo, Spotify…),
        propone capturarlo directamente: por altavoces y micrófono llega flojo y con eco, y las voces
        no se entienden. Devuelve False si el usuario cancela la grabación."""
        if self._es_sistema() or self._indice_sistema() < 0 or PanelCaptura._prefiere_micro or not audio.suena_algo():
            return True
        r = tema.dialogo(self, "Está sonando audio en este equipo",
                         "Ahora mismo hay una aplicación reproduciendo sonido y tienes elegido un micrófono.\n\n"
                         "Si lo que quieres transcribir es eso que suena (un vídeo, una canción…), grábalo directamente: "
                         "a través de los altavoces y el micrófono llega muy flojo y con el eco de la habitación, y las voces "
                         "no se entienden aunque tú lo oigas bien.\n\n"
                         "Si vas a hablar, cantar o tocar tú, sigue con el micrófono.",
                         ("Cancelar", "Seguir con el micrófono", "Grabar el sonido del equipo"), "pregunta")
        if r == "Grabar el sonido del equipo":
            self.micro.setCurrentIndex(self._indice_sistema())
        elif r == "Seguir con el micrófono":
            PanelCaptura._prefiere_micro = True   # no volver a preguntar en esta sesión
        return r in ("Grabar el sonido del equipo", "Seguir con el micrófono")

    def _es_sistema(self):
        return bool((self.micro.currentData() or {}).get("sistema"))

    def _suena_en_equipo(self):
        """¿Hay audio sonando en el equipo? Se consulta como mucho cada 2 s (pregunta al servidor de sonido)."""
        ahora = time.monotonic()
        if ahora - self._visto[0] > 2:
            self._visto = (ahora, self._indice_sistema() >= 0 and audio.suena_algo())
        return self._visto[1]

    def _micro(self):
        """(índice de dispositivo, fuente del servidor de sonido) del micrófono elegido."""
        m = self.micro.currentData()
        return m["indice"], m["fuente"]

    # -- prueba de nivel ------------------------------------------------------
    def probar(self):
        if self.g:
            return self._parar_prueba()
        try:
            indice, fuente = self._micro()
            self.g = audio.Grabadora(dispositivo=indice, fuente=fuente)
            self.g.iniciar()
        except audio.ErrorAudio as e:
            self.g = None
            return tema.error(self, "Micrófono no disponible", str(e))
        self._fin_prueba = 10_000 // self._tic.interval()
        self._decir("Probando el sonido del equipo: pon la música en marcha y observa el nivel. No se guarda nada." if self._es_sistema()
                    else "Probando: habla o toca y observa el nivel. No se guarda nada.")
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
        if not self._ofrecer_sistema():
            return
        if self._es_sistema() and audio.suena_algo() is False and not tema.confirmar(
                self, "Ahora mismo no suena nada", "Has elegido grabar el sonido del equipo, pero ninguna aplicación está reproduciendo "
                "audio en este momento.\n\nPon en marcha la música o el vídeo y vuelve a pulsar «Grabar». También puedes empezar ya "
                "y darle a reproducir enseguida.", "Grabar igualmente"):
            return
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
        carpeta_seg = rutas.TEMP / f"vivo-{self.tipo}"
        if seg:
            shutil.rmtree(carpeta_seg, ignore_errors=True)
            carpeta_seg.mkdir(parents=True, exist_ok=True)
        indice, fuente = self._micro()
        self.g = audio.Grabadora(wav, indice, seg, carpeta_seg, lambda ruta, t0: self.segmento.emit(ruta, t0), fuente)
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
        self._decir(f"Grabando con «{a['microfono']}»…", "aviso")
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
        g, carpeta, sistema = self.g, self.proyecto, self._es_sistema()
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
        elif sistema and (g.muda or g.floja):
            self._decir("Toma guardada, pero " + ("sin sonido." if g.muda else f"con el equipo sonando muy bajo (pico del {g.pico * 100:.0f} %)."), "aviso")
            tema.dialogo(self, "No se grabó sonido del equipo" if g.muda else "El equipo sonaba muy bajo",
                         ("Durante la toma no sonó nada por la salida de audio.\n\n" if g.muda else "El sonido llegó muy flojo.\n\n")
                         + "• Comprueba que la música o el vídeo estaban reproduciéndose (no en pausa) y sin silenciar.\n"
                         "• Sube el volumen dentro de la aplicación que reproduce (Spotify, el navegador…).\n"
                         "• Si escuchas por unos auriculares y cambiaste de salida a mitad, vuelve a grabar: la salida se elige al empezar.", tipo="aviso")
        elif g.muda:
            self._decir("Toma guardada, pero no contiene sonido.", "aviso")
            tema.dialogo(self, "La toma está en silencio", "Se ha grabado, pero el micrófono no envió ninguna señal.\n\n"
                         "Comprueba que no esté silenciado o apagado y que has elegido la entrada correcta; usa «Probar nivel» "
                         "y mira si la barra se mueve al hablar. En el control de sonido del sistema, sube el volumen de entrada.", tipo="aviso")
        elif g.floja:
            self._decir(f"Toma guardada, pero con un nivel muy bajo (pico del {g.pico * 100:.0f} %): el reconocimiento puede fallar.", "aviso")
            if not PanelCaptura._avisado_flojo:   # el diálogo, solo la primera vez; después basta la línea de estado
                PanelCaptura._avisado_flojo = True
                tema.dialogo(self, "Nivel de grabación muy bajo", f"La toma se ha guardado, pero el sonido llegó muy flojo (pico del {g.pico * 100:.0f} %) "
                         "y el reconocimiento puede fallar o salir vacío, aunque tú lo oyeras bien.\n\n"
                         "• Si lo que quieres transcribir suena en este equipo (un vídeo, Spotify…), no lo grabes con el micrófono: pulsa "
                             "«Sonido del equipo» y se capturará directamente, sin altavoces, eco ni ruido ambiente.\n"
                         "• Si eres tú quien habla, canta o toca, acerca el micrófono o sube su ganancia.\n\n"
                             "A partir de ahora lo verás mientras grabas: la barra de nivel se pone ámbar y aparece un aviso bajo el reloj. "
                             "Este mensaje no volverá a interrumpirte en esta sesión.", tipo="aviso")
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
        flojo = g.frames > 2 * g.sr or (not self.grabando and self._fin_prueba < 8_000 // self._tic.interval())
        if flojo and g.pico < 0.1 and not g.pausada and self.texto.property("clase") != "error":   # aviso en directo, antes de perder la toma
            if self._es_sistema():   # no hay micrófono que acercar: o no suena nada, o suena muy bajo
                self._decir("No llega sonido del equipo: pon en marcha la música o el vídeo (y que no esté silenciado)." if g.pico < 0.001
                            else f"El equipo suena muy bajo (pico del {g.pico * 100:.0f} %): sube el volumen de la aplicación que reproduce.", "aviso")
            elif self._suena_en_equipo():
                self._decir("Al micrófono le llega muy poco y está sonando audio en este equipo: para grabarlo bien, "
                            "detén y pulsa «Sonido del equipo».", "aviso")
            else:
                self._decir(f"Nivel muy bajo (pico del {g.pico * 100:.0f} %): acerca el micrófono o sube su ganancia"
                            + (". No se guarda nada." if not self.grabando else "; así el reconocimiento puede fallar."), "aviso")
        elif g.pico >= 0.1 and self.texto.text().startswith("Nivel muy bajo"):   # la señal ya llega bien
            self._decir("Grabando…" if self.grabando else "Probando: el nivel es correcto. No se guarda nada.", "aviso" if self.grabando else "tenue")
        clase = "alto" if g.nivel > 0.97 else "bajo" if flojo and g.pico < 0.1 else ""
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
