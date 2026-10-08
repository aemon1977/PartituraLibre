"""Ejecuta los procesos de análisis sin bloquear la interfaz y permite cancelarlos."""
import json
import subprocess
import sys
import threading

from . import rutas

VIVAS = set()


class Tarea:
    """Proceso hijo del runtime portable. `al_evento(dict)` y `al_terminar(codigo, cancelada)`
    se llaman desde un hilo auxiliar: la interfaz debe reenviarlos a su hilo."""

    def __init__(self, modulo, args=(), conjunto="app", al_evento=None, al_terminar=None):
        self.al_evento, self.al_terminar, self.cancelada = al_evento, al_terminar, False
        rutas.LOGS.mkdir(parents=True, exist_ok=True)
        log = rutas.LOGS / "motores.log"
        if log.exists() and log.stat().st_size > 2_000_000:
            log.unlink()
        self._log = open(log, "a", encoding="utf-8")
        self.p = subprocess.Popen(
            [sys.executable, "-s", "-m", modulo, *args], env=rutas.entorno(conjunto), cwd=str(rutas.RAIZ),
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self._log, text=True, encoding="utf-8",
            errors="replace", creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        VIVAS.add(self)
        threading.Thread(target=self._leer, daemon=True).start()

    def _leer(self):
        for linea in self.p.stdout:
            try:
                ev = json.loads(linea)
            except ValueError:
                continue
            if self.al_evento and not self.cancelada:
                self.al_evento(ev)
        codigo = self.p.wait()
        for f in (self.p.stdout, self.p.stdin, self._log):
            try:
                f.close()
            except OSError:
                pass
        VIVAS.discard(self)
        if self.al_terminar:
            self.al_terminar(codigo, self.cancelada)

    def enviar(self, **orden):
        try:
            self.p.stdin.write(json.dumps(orden, ensure_ascii=False) + "\n")
            self.p.stdin.flush()
            return True
        except OSError:
            return False

    def viva(self):
        return self.p.poll() is None

    def cancelar(self):
        self.cancelada = True
        if self.viva():
            self.p.terminate()
            try:
                self.p.wait(3)
            except subprocess.TimeoutExpired:
                self.p.kill()


def cancelar_todas():
    for t in list(VIVAS):
        t.cancelar()


def limpiar_parciales(carpeta):
    """Borra resultados a medio escribir para que nunca parezcan terminados."""
    for p in rutas.Path(carpeta).glob("*.parcial"):
        p.unlink(missing_ok=True)
