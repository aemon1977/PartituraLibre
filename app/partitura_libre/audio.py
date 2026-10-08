"""Captura de audio: callback ligero -> cola acotada -> hilo que escribe WAV por bloques."""
import errno
import queue
import struct
import threading
import time
from pathlib import Path

from . import rutas

AYUDA_MICRO = ("Puede estar ocupado por otra aplicación, desconectado o sin permiso. Cierra otros programas "
               "que usen el micrófono, pulsa «Actualizar» y elige otro dispositivo"
               + (". En Windows revisa Configuración > Privacidad y seguridad > Micrófono." if rutas.WINDOWS else "."))


class ErrorAudio(Exception):
    pass


def sd():
    """sounddevice del runtime portable, o un error que dice qué hacer."""
    try:
        import sounddevice
        return sounddevice
    except ImportError as e:
        lanzador = "iniciar-windows.bat --reparar" if rutas.WINDOWS else "./iniciar-linux.sh --reparar"
        raise ErrorAudio(f"El runtime portable no contiene sounddevice ({e}). Ejecuta: {lanzador}") from e
    except OSError as e:
        raise ErrorAudio(
            "No se pudo cargar PortAudio, la biblioteca de audio del sistema (libportaudio2 en Debian/Ubuntu). "
            "Partitura Libre no instala nada en el sistema: pide a quien administre el equipo que la instale. "
            f"Mientras tanto puedes importar archivos de audio. Detalle: {e}") from e


def microfonos(refrescar=False):
    """Entradas disponibles: [{'indice', 'nombre', 'sr', 'predeterminado'}], la predeterminada primero."""
    s = sd()
    if refrescar:  # PortAudio solo vuelve a enumerar al reiniciarse
        s._terminate()
        s._initialize()
    pred = s.default.device[0]
    api = s.query_devices(pred)["hostapi"] if pred is not None and pred >= 0 else 0
    lista = [{"indice": i, "nombre": d["name"], "sr": int(d["default_samplerate"]), "predeterminado": i == pred}
             for i, d in enumerate(s.query_devices()) if d["max_input_channels"] > 0 and d["hostapi"] == api]
    return sorted(lista, key=lambda d: not d["predeterminado"])


class EscritorWav:
    """WAV PCM16 que es válido en todo momento: la cabecera se corrige cada segundo,
    así un cierre inesperado conserva lo grabado."""
    LIMITE = 0xFFFFFFFF - 44 - 2**20  # tope del formato WAV (4 GB ≈ 13 h en mono a 44,1 kHz)

    def __init__(self, ruta, sr, canales=1):
        self.ruta, self.sr, self.canales, self.bytes = Path(ruta), sr, canales, 0
        self.f = open(self.ruta, "wb")
        self._cabecera()
        self._t = time.monotonic()

    def _cabecera(self):
        c, n = self.canales, self.bytes
        self.f.seek(0)
        self.f.write(struct.pack("<4sI4s4sIHHIIHH4sI", b"RIFF", 36 + n, b"WAVE", b"fmt ", 16, 1, c,
                                 self.sr, self.sr * c * 2, c * 2, 16, b"data", n))
        self.f.seek(0, 2)

    def escribir(self, datos):
        if self.bytes + len(datos) > self.LIMITE:
            raise ErrorAudio("Se alcanzó el tamaño máximo de un archivo WAV (4 GB). La toma se ha guardado "
                             "completa hasta aquí; inicia otra grabación para continuar.")
        self.f.write(datos)
        self.bytes += len(datos)
        if time.monotonic() - self._t > 1:
            self._cabecera()
            self.f.flush()
            self._t = time.monotonic()

    def cerrar(self):
        if not self.f.closed:
            try:
                self._cabecera()
            finally:
                self.f.close()


class Grabadora:
    """Con `destino=None` solo mide el nivel (prueba de micrófono)."""
    COLA = 4000        # bloques en espera antes de declarar pérdida (≈ 1-2 min de audio)
    SILENCIO_S = 3     # sin bloques durante este tiempo = dispositivo caído

    def __init__(self, destino=None, dispositivo=None, segmento_s=0, carpeta_segmentos=None, al_segmento=None):
        self.destino, self.dispositivo = (Path(destino) if destino else None), dispositivo
        self.segmento_s, self.carpeta_segmentos, self.al_segmento = segmento_s, carpeta_segmentos, al_segmento
        self.sr = 44100
        self.nivel = 0.0       # pico 0..1 del último bloque
        self.pico = 0.0        # pico máximo de toda la toma
        self.frames = 0        # muestras ya escritas en disco
        self.desbordes = 0     # avisos de desbordamiento del sistema de audio
        self.perdidos = 0      # muestras descartadas porque el disco no daba abasto
        self.error = ""        # motivo por el que la captura se detuvo sola
        self.pausada = False
        self._flujo = self._hilo = self._wav = None
        self._cola = queue.Queue(self.COLA)
        self._vivo = False
        self._ultimo = time.monotonic()

    @property
    def segundos(self):
        return self.frames / self.sr

    @property
    def incompleta(self):
        return bool(self.desbordes or self.perdidos or self.error)

    def avisos(self):
        a = []
        if self.desbordes:
            a.append(f"El sistema de audio avisó de {self.desbordes} desbordamiento(s): puede faltar algún instante.")
        if self.perdidos:
            a.append(f"Se perdieron {self.perdidos / self.sr:.1f} s porque el disco no pudo escribir a tiempo.")
        if self.error:
            a.append(self.error)
        return a

    @property
    def muda(self):
        """La toma entera es silencio digital: micrófono silenciado, apagado o entrada equivocada."""
        return self.frames > self.sr and self.pico < 0.001

    # -- ciclo de vida -------------------------------------------------------
    def iniciar(self):
        s = sd()
        try:
            self.sr = int(s.query_devices(self.dispositivo, "input")["default_samplerate"])
            self._preparar()
            self._flujo = s.InputStream(device=self.dispositivo, channels=1, samplerate=self.sr,
                                        dtype="int16", callback=self._bloque)
            self._flujo.start()
        except Exception as e:
            self._cerrar_escritura()
            if isinstance(e, OSError) and e.errno == errno.ENOSPC:
                raise ErrorAudio("No queda espacio en el disco para grabar. Libera espacio y vuelve a intentarlo.") from e
            raise ErrorAudio(f"No se pudo abrir el micrófono. {AYUDA_MICRO} Detalle: {e}") from e

    def _preparar(self):
        """Abre el archivo y arranca el hilo de escritura (separado del flujo para poder probarlo sin micrófono)."""
        self._ultimo = time.monotonic()
        self._vivo = True
        if self.destino:
            self._wav = EscritorWav(self.destino, self.sr)
            self._hilo = threading.Thread(target=self._escribir, daemon=True)
            self._hilo.start()

    def _bloque(self, datos, n, _tiempo, estado):
        """Callback de audio: no hace E/S ni espera nunca."""
        if estado and estado.input_overflow:
            self.desbordes += 1
        self.nivel = max(int(datos.max()), -int(datos.min())) / 32768
        if self.nivel > self.pico:
            self.pico = self.nivel
        self._ultimo = time.monotonic()
        if self._wav is None or self.pausada or not self._vivo:
            return
        try:
            self._cola.put_nowait(bytes(datos))
        except queue.Full:
            self.perdidos += n

    def _escribir(self):
        seg, seg_n, n_seg, seg_t0 = [], 0, 0, 0.0
        try:
            while True:
                try:
                    datos = self._cola.get(timeout=0.5)
                except queue.Empty:
                    if self._flujo and not self.pausada and time.monotonic() - self._ultimo > self.SILENCIO_S:
                        raise ErrorAudio("El micrófono dejó de enviar audio (¿se desconectó?). "
                                         "La toma se ha guardado hasta ese momento.")
                    continue
                if datos is None:
                    break
                self._wav.escribir(datos)
                self.frames += len(datos) // 2
                if self.segmento_s and self.al_segmento:
                    seg.append(datos)
                    seg_n += len(datos) // 2
                    if seg_n >= self.segmento_s * self.sr:
                        n_seg += 1
                        ruta = Path(self.carpeta_segmentos) / f"segmento-{n_seg:04d}.wav"
                        w = EscritorWav(ruta, self.sr)
                        w.escribir(b"".join(seg))
                        w.cerrar()
                        self.al_segmento(ruta, seg_t0)
                        seg_t0 += seg_n / self.sr
                        seg, seg_n = [], 0
        except ErrorAudio as e:
            self.error = str(e)
        except OSError as e:
            self.error = ("El disco se ha llenado: la toma se conserva hasta este punto. Libera espacio."
                          if e.errno == errno.ENOSPC else f"No se pudo escribir la grabación: {e}")
        finally:
            self._vivo = False
            self._cerrar_escritura()

    def _cerrar_escritura(self):
        if self._wav:
            try:
                self._wav.cerrar()
            except OSError as e:
                self.error = self.error or f"No se pudo cerrar el archivo de audio: {e}"

    def pausar(self, si=True):
        self.pausada = si
        self._ultimo = time.monotonic()

    def detener(self):
        """Para la captura y espera a que todo lo encolado esté en disco."""
        if self._flujo:
            try:
                self._flujo.stop()
                self._flujo.close()
            except Exception as e:  # dispositivo ya desaparecido
                self.error = self.error or f"El dispositivo de audio falló al cerrar: {e}"
            self._flujo = None
        if self._hilo:
            while self._hilo.is_alive():
                try:
                    self._cola.put(None, timeout=0.2)
                    break
                except queue.Full:
                    continue
            self._hilo.join()
            self._hilo = None
        self._vivo = False
        self.nivel = 0.0

    def cancelar(self):
        """Detiene y borra la toma (solo tras confirmación explícita del usuario)."""
        self.detener()
        if self.destino:
            self.destino.unlink(missing_ok=True)
