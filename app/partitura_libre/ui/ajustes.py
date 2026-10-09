"""Sección Ajustes: modelos de voz, editor de partituras, diagnóstico y limpieza/desinstalación."""
from PySide6.QtCore import Signal
from PySide6.QtWidgets import (QApplication, QFileDialog, QGridLayout, QInputDialog, QPlainTextEdit, QVBoxLayout,
                               QWidget)

from .. import __version__, config, diagnostico, editor, letras, limpieza, rutas, separacion, tareas
from . import tema

LICENCIAS = ("Partitura Libre usa software libre que se descarga dentro de su carpeta: Python (PSF), Qt/PySide6 (LGPL v3), "
             "Basic Pitch de Spotify (Apache 2.0), ONNX Runtime (MIT), music21 (BSD), faster-whisper y CTranslate2 (MIT), "
             "modelos Whisper de OpenAI (MIT), sounddevice y soundfile (MIT/BSD), uv (MIT/Apache 2.0). "
             "MuseScore Studio (GPL v3) es opcional y se ejecuta como programa aparte. Detalle en docs/LICENCIAS.md.")


def _mb(b):
    return f"{b / 2**20:,.0f} MB".replace(",", ".") if b >= 2**20 else f"{b / 1024:.0f} KB"


class PaginaAjustes(QWidget):
    cambio = Signal()  # cambió algo que afecta a otras páginas (modelos, editor)

    def __init__(self, ocupada=lambda: False, cerrar_app=lambda: None):
        super().__init__()
        self.setObjectName("pagina")
        self._ocupada, self._cerrar_app = ocupada, cerrar_app

        tm, vm = tema.tarjeta("Modelos de voz (Letras)")
        vm.addWidget(tema.etiqueta("Se descargan solo cuando tú lo pides y se guardan en models/. Tamaños y memoria aproximados; todos funcionan en CPU.", "tenue"))
        self.rejilla = QGridLayout()
        self.rejilla.setHorizontalSpacing(14)
        vm.addLayout(self.rejilla)

        te, ve = tema.tarjeta("MuseScore Studio (opcional)")
        self.e_editor = tema.etiqueta()
        self.b_ms_bajar = tema.boton(f"Descargar MuseScore portable ({editor.PORTABLE['mb']} MB)", self._bajar_musescore)
        self.b_ms_elegir = tema.boton("Usar un MuseScore ya instalado…", self._elegir_musescore)
        self.b_ms_quitar = tema.boton("Quitar la copia portable", self._quitar_musescore, "peligro")
        self.b_ms_abrir = tema.boton("Abrir MuseScore", lambda: editor.abrir())
        ve.addWidget(self.e_editor)
        ve.addLayout(tema.fila(self.b_ms_bajar, self.b_ms_elegir, None))
        ve.addLayout(tema.fila(self.b_ms_abrir, self.b_ms_quitar, None))

        td, vd = tema.tarjeta("Diagnóstico")
        vd.addWidget(tema.etiqueta("Comprueba el runtime portable, el entorno activo, los micrófonos, los motores, los modelos, "
                                   "el editor y el espacio libre. El informe se guarda en logs/ y no contiene grabaciones ni datos personales.", "tenue"))
        self.b_diag = tema.boton("Ejecutar diagnóstico", self._diagnosticar, "primario")
        self.t_diag = QPlainTextEdit()
        self.t_diag.setReadOnly(True)
        self.t_diag.setStyleSheet("font-family: monospace; font-size: 13px;")
        self.t_diag.setFixedHeight(230)
        self.t_diag.setPlaceholderText("Pulsa «Ejecutar diagnóstico».")
        vd.addLayout(tema.fila(self.b_diag, tema.boton("Abrir carpeta de registros", lambda: tema.abrir_en_sistema(rutas.LOGS)), None))
        vd.addWidget(self.t_diag)

        tl, vl = tema.tarjeta("Carpeta portable, limpieza y desinstalación")
        self.e_contenido = tema.etiqueta("", ajustar=False)
        self.e_contenido.setStyleSheet("font-family: monospace; font-size: 13px;")
        self.b_desinstalar = tema.boton("Desinstalar: eliminar la carpeta completa…", self._desinstalar, "peligro")
        vl.addWidget(tema.etiqueta(f"Todo lo que el programa instala o descarga está en:\n{rutas.RAIZ}", "tenue"))
        vl.addWidget(self.e_contenido)
        vl.addLayout(tema.fila(tema.boton("Calcular tamaños", self._medir), tema.boton("Vaciar temporales", self._vaciar),
                               tema.boton("Abrir la carpeta", lambda: tema.abrir_en_sistema(rutas.RAIZ)), None))
        vl.addLayout(tema.fila(self.b_desinstalar, None))

        ta, va = tema.tarjeta(f"Acerca de · Partitura Libre {__version__}")
        va.addWidget(tema.etiqueta("Gratuito, sin cuentas ni cuotas. Tus grabaciones no salen de este equipo: Internet solo se usa "
                                   "cuando pulsas un botón de descarga.", "tenue"))
        va.addWidget(tema.etiqueta(LICENCIAS, "tenue"))

        area = tema.columna(tm, te, td, tl, ta)
        v = QVBoxLayout(self)
        v.setContentsMargins(22, 18, 14, 18)
        v.setSpacing(12)
        v.addWidget(tema.etiqueta("Ajustes", "titulo"))
        v.addWidget(area, 1)
        self.recargar()

    def recargar(self):
        while self.rejilla.count():
            self.rejilla.takeAt(0).widget().deleteLater()
        for f, (n, (_, mb, ram, desc)) in enumerate(letras.MODELOS.items()):
            puesto = letras.instalado(n)
            self.rejilla.addWidget(tema.etiqueta(f"<b>{n}</b>", ajustar=False), f, 0)
            self.rejilla.addWidget(tema.etiqueta(desc, "tenue", False), f, 1)
            self.rejilla.addWidget(tema.etiqueta(f"{mb} MB · ≈ {ram / 1000:.1f} GB RAM", "tenue", False), f, 2)
            self.rejilla.addWidget(tema.etiqueta("Descargado" if puesto else "No descargado", "" if puesto else "tenue", False), f, 3)
            b = (tema.boton("Borrar", lambda n=n: self._borrar_modelo(n), "peligro") if puesto
                 else tema.boton("Descargar", lambda n=n: self._bajar_modelo(n)))
            self.rejilla.addWidget(b, f, 4)
        f, puesto = len(letras.MODELOS), separacion.instalado()   # y el separador de voz para canciones
        self.rejilla.addWidget(tema.etiqueta("<b>separador</b>", ajustar=False), f, 0)
        self.rejilla.addWidget(tema.etiqueta("Aísla la voz de los instrumentos (modo voz cantada)", "tenue", False), f, 1)
        self.rejilla.addWidget(tema.etiqueta(f"{separacion.MB} MB", "tenue", False), f, 2)
        self.rejilla.addWidget(tema.etiqueta("Descargado" if puesto else "No descargado", "" if puesto else "tenue", False), f, 3)
        self.rejilla.addWidget(tema.boton("Borrar", self._borrar_separador, "peligro") if puesto
                               else tema.boton("Descargar", self._bajar_separador), f, 4)
        self.rejilla.setColumnStretch(1, 1)
        exe, origen = editor.buscar()
        self.e_editor.setText(
            (f"Disponible ({origen}): {exe}" if exe else "No instalado. No hace falta: Partitura Libre edita la partitura y exporta el PDF por sí sola. "
             "Descárgalo solo si además quieres abrir tus MusicXML en MuseScore.")
            + f"\nLa copia portable se guarda en runtime/musescore y no se instala en el sistema. {editor.LICENCIA}")
        self.b_ms_bajar.setEnabled(origen != "portable")
        self.b_ms_quitar.setEnabled(origen == "portable")
        self.b_ms_abrir.setEnabled(bool(exe))

    # -- modelos ---------------------------------------------------------------
    def _bajar_modelo(self, n):
        _, mb, ram, desc = letras.MODELOS[n]
        tema.descarga_con_dialogo(self, f"Descargar el modelo «{n}»",
                                  f"{desc}.\n\n• Tamaño: {mb} MB\n• Memoria al transcribir: ≈ {ram / 1000:.1f} GB\n"
                                  f"• Se guarda en: {letras.carpeta_modelo(n)}",
                                  lambda p, c: letras.descargar_modelo(n, p, c), lambda ok: (self.recargar(), self.cambio.emit()))

    def _bajar_separador(self):
        tema.descarga_con_dialogo(self, "Descargar el separador de voz",
                                  f"Aísla la voz de los instrumentos antes de transcribir una canción.\n\n• Tamaño: {separacion.MB} MB\n"
                                  f"• Se guarda en: {separacion.CARPETA}\n\n{separacion.CREDITO}",
                                  separacion.descargar, lambda ok: (self.recargar(), self.cambio.emit()))

    def _borrar_separador(self):
        if self._ocupada():
            return tema.dialogo(self, "Ahora no", "Espera a que termine la grabación o el análisis en curso.", tipo="aviso")
        if tema.confirmar(self, "Borrar el separador de voz", f"Se borrará el separador ({separacion.MB} MB). Podrás volver a descargarlo.", "Borrar separador"):
            separacion.borrar()
            self.recargar()
            self.cambio.emit()

    def _borrar_modelo(self, n):
        if self._ocupada():
            return tema.dialogo(self, "Ahora no", "Espera a que termine la grabación o el análisis en curso.", tipo="aviso")
        if tema.confirmar(self, "Borrar modelo", f"Se borrará el modelo «{n}» ({letras.MODELOS[n][1]} MB). Podrás volver a descargarlo.", "Borrar modelo"):
            letras.borrar_modelo(n)
            self.recargar()
            self.cambio.emit()

    # -- editor ----------------------------------------------------------------
    def _bajar_musescore(self):
        tema.descarga_con_dialogo(
            self, "Descargar MuseScore portable",
            f"MuseScore Studio {editor.VERSION} permite editar la partitura y exportar PDF.\n\n• Descarga: {editor.PORTABLE['mb']} MB "
            f"(≈ {editor.PORTABLE['mb'] * 3} MB descomprimido)\n• Se guarda en: {editor.CARPETA}\n• No se instala en el sistema ni pide contraseña.\n\n{editor.LICENCIA}",
            editor.instalar_portable, lambda ok: (self.recargar(), self.cambio.emit()))

    def _elegir_musescore(self):
        ruta, _ = QFileDialog.getOpenFileName(self, "Elegir el ejecutable de MuseScore")
        if ruta:
            a = config.cargar()
            a["musescore"] = ruta
            config.guardar(a)
            self.recargar()
            self.cambio.emit()

    def _quitar_musescore(self):
        if tema.confirmar(self, "Quitar MuseScore portable", "Se borrará la copia de MuseScore de runtime/musescore.", "Borrar MuseScore"):
            editor.quitar_portable()
            self.recargar()
            self.cambio.emit()

    # -- diagnóstico -----------------------------------------------------------
    def _diagnosticar(self):
        self.b_diag.setEnabled(False)
        self.t_diag.setPlainText("Comprobando…")

        def fin(r, e):
            self.b_diag.setEnabled(True)
            if e:
                return self.t_diag.setPlainText(f"El diagnóstico falló: {e}")
            self.t_diag.setPlainText(diagnostico.informe(r) + f"\nInforme guardado en {diagnostico.guardar(r)}")
        tema.en_hilo(lambda: diagnostico.comprobar(probar_micro=not self._ocupada()), fin)

    # -- limpieza --------------------------------------------------------------
    def _medir(self):
        self.e_contenido.setText("Calculando…")
        tema.en_hilo(limpieza.contenido, lambda r, e: self.e_contenido.setText(
            str(e) if e else "\n".join(f"{n + ('/' if d else ''):22} {_mb(b):>10}   {d}" for n, d, b in r)
            + f"\n{'TOTAL':22} {_mb(sum(b for _, _, b in r)):>10}"))

    def _vaciar(self):
        if self._ocupada():
            return tema.dialogo(self, "Ahora no", "Espera a que termine la grabación o el análisis en curso.", tipo="aviso")
        limpieza.vaciar_temporales()
        self._medir()

    def _desinstalar(self):
        if self._ocupada():
            return tema.dialogo(self, "Ahora no", "Detén antes la grabación o el análisis en curso.", tipo="aviso")
        resumen = "\n".join(f"• {n}: {_mb(b)}  {d}" for n, d, b in limpieza.contenido())
        if not tema.confirmar(self, "Desinstalar Partitura Libre",
                              f"Se borrará TODA esta carpeta, incluidas tus grabaciones, partituras y letras guardadas en ella:\n\n"
                              f"{rutas.RAIZ}\n\n{resumen}\n\nNo se toca nada fuera de la carpeta: las copias que hayas exportado a "
                              "otros sitios seguirán donde estén. No se puede deshacer.", "Eliminar todo…"):
            return
        palabra, ok = QInputDialog.getText(self, "Confirmación final", "Escribe ELIMINAR para borrar la carpeta y cerrar el programa:")
        if not ok or palabra.strip() != "ELIMINAR":
            return
        try:
            tareas.cancelar_todas()
            limpieza.desinstalar()
        except (OSError, RuntimeError) as e:
            return tema.error(self, "No se pudo desinstalar", f"{e}\n\nPuedes cerrar el programa y borrar la carpeta a mano: el efecto es el mismo.")
        self._cerrar_app()
        QApplication.quit()
