"""Sección Grabaciones/Proyectos: historial de tomas con sus resultados."""
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QAbstractItemView, QHeaderView, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget

from .. import proyectos, rutas
from . import tema

ESTADOS = {"nuevo": "Sin audio", "grabando": "Grabando…", "grabado": "Audio guardado", "interrumpida": "⚠ Interrumpida"}


class PaginaProyectos(QWidget):
    abrir = Signal(object, str)  # (carpeta, tipo)

    def __init__(self, ocupada=lambda: False):
        super().__init__()
        self.setObjectName("pagina")
        self._ocupada, self.lista = ocupada, []
        self.tabla = QTableWidget(0, 6)
        self.tabla.setHorizontalHeaderLabels(["Nombre", "Tipo", "Fecha", "Audio", "Resultados", "Ubicación"])
        cab = self.tabla.horizontalHeader()
        cab.setSectionResizeMode(QHeaderView.ResizeToContents)
        cab.setSectionResizeMode(0, QHeaderView.Stretch)
        self.tabla.verticalHeader().hide()
        self.tabla.verticalHeader().setDefaultSectionSize(30)
        self.tabla.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tabla.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tabla.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tabla.setAlternatingRowColors(True)
        self.tabla.itemSelectionChanged.connect(self._botones)
        self.tabla.itemDoubleClicked.connect(lambda _: self._abrir())
        self.b_abrir = tema.boton("Abrir", self._abrir, "primario")
        self.b_carpeta = tema.boton("Ver carpeta", lambda: tema.abrir_en_sistema(self._sel()[0]))
        self.b_exportar = tema.boton("Exportar copia a…", self._exportar)
        self.b_eliminar = tema.boton("Eliminar…", self._eliminar, "peligro")
        self.e_pie = tema.etiqueta("", "tenue")

        t, vt = tema.tarjeta()
        vt.addWidget(self.tabla, 1)
        vt.addLayout(tema.fila(self.b_abrir, self.b_carpeta, self.b_exportar, None, tema.boton("Actualizar", self.recargar), self.b_eliminar))
        vt.addWidget(self.e_pie)
        v = QVBoxLayout(self)
        v.setContentsMargins(22, 18, 22, 18)
        v.setSpacing(12)
        v.addWidget(tema.etiqueta("Grabaciones y proyectos", "titulo"))
        v.addWidget(tema.etiqueta("Cada toma conserva su audio original junto a las partituras y letras creadas a partir de él.", "tenue"))
        v.addWidget(t, 1)
        self.recargar()

    def _sel(self):
        i = self.tabla.currentRow()
        return self.lista[i] if 0 <= i < len(self.lista) else (None, None)

    def _botones(self):
        hay = self._sel()[0] is not None
        for b in (self.b_abrir, self.b_carpeta, self.b_exportar):
            b.setEnabled(hay)
        self.b_eliminar.setEnabled(hay and not self._ocupada())
        self.b_eliminar.setToolTip("" if not self._ocupada() else "No disponible mientras se graba o se analiza")

    def recargar(self):
        self.lista = proyectos.listar()
        self.tabla.setRowCount(len(self.lista))
        for i, (carpeta, d) in enumerate(self.lista):
            n = {t: sum(r["tipo"] == t for r in d.get("resultados", [])) for t in ("partitura", "letra")}
            res = ", ".join(f"{c} {t}{'s' if c > 1 else ''}" for t, c in n.items() if c) or "—"
            audio = ESTADOS.get(d.get("estado"), d.get("estado", "")) + ("  ⚠ incompleta" if d.get("incompleta") and d.get("estado") == "grabado" else "")
            donde = "En el programa" if rutas.dentro_de(carpeta) else f"Externa: {carpeta.parent}"
            for c, texto in enumerate((d.get("nombre", carpeta.name), d.get("tipo", "").capitalize(),
                                       d.get("creado", "").replace("T", "  "), audio, res, donde)):
                self.tabla.setItem(i, c, QTableWidgetItem(texto))
        self.e_pie.setText(f"{len(self.lista)} proyecto(s). Carpeta predeterminada: {rutas.PROYECTOS}" if self.lista else
                           "Aún no hay proyectos. Graba o importa un audio en Partituras o en Letras.")
        self._botones()

    def _abrir(self):
        carpeta, d = self._sel()
        if carpeta:
            self.abrir.emit(carpeta, d.get("tipo", "partitura"))

    def _exportar(self):
        carpeta, _ = self._sel()
        destino = tema.elegir_carpeta(self, "Carpeta donde copiar el proyecto")
        if not destino or not tema.avisar_si_externo(self, destino):
            return
        try:
            copia = proyectos.exportar(carpeta, destino)
            tema.dialogo(self, "Copia creada", f"El proyecto se ha copiado a:\n{copia}\n\n"
                         + ("" if rutas.dentro_de(copia) else "Recuerda: esa copia no se borra al eliminar Partitura Libre."))
        except OSError as e:
            tema.error(self, "No se pudo exportar", f"{e}\n\nElige otra carpeta o libera espacio.")

    def _eliminar(self):
        carpeta, d = self._sel()
        if tema.confirmar(self, "Eliminar proyecto", f"Se borrará «{d.get('nombre')}» con su audio original y todos sus "
                          f"resultados:\n{carpeta}\n\nNo se puede deshacer.", "Eliminar proyecto"):
            try:
                proyectos.eliminar(carpeta)
            except (OSError, ValueError) as e:
                tema.error(self, "No se pudo eliminar", str(e))
            self.recargar()
