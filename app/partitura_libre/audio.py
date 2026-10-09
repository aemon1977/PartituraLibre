"""Captura de audio: callback ligero -> cola acotada -> hilo que escribe WAV por bloques."""
import errno
import os
import queue
import shutil
import struct
import subprocess
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


SISTEMA = "Sonido del equipo (lo que suena en este ordenador)"
FUENTE_SISTEMA = "@sistema@"   # se resuelve al empezar a grabar: la salida por la que esté sonando algo


def _pactl(*args):
    return subprocess.run(["pactl", *args], capture_output=True, text=True, timeout=5,
                          env={**os.environ, "LC_ALL": "C.UTF-8"}).stdout


def _bloques(texto):
    """Campos de primer nivel de cada bloque de un listado de `pactl list …`."""
    for bloque in texto.split("\n\n"):
        yield dict(l.strip().split(": ", 1) for l in bloque.splitlines() if ": " in l and l.startswith("\t") and not l.startswith("\t\t"))


def salida_que_suena():
    """Nombre de la salida de audio por la que está sonando algo ahora mismo; si no suena nada,
    la salida predeterminada. Así «Sonido del equipo» acierta aunque la música vaya por los
    auriculares y no por los altavoces."""
    try:
        salidas = dict(l.split("\t")[:2] for l in _pactl("list", "short", "sinks").splitlines() if "\t" in l)
        sonando = [c["Sink"] for c in _bloques(_pactl("list", "sink-inputs")) if c.get("Corked") == "no" and c.get("Sink") in salidas]
        return salidas[sonando[-1]] if sonando else _pactl("get-default-sink").strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def suena_algo():
    """True si alguna aplicación está reproduciendo sonido en este momento; None si no se puede
    saber (en Windows no hay forma sencilla de preguntarlo)."""
    if rutas.WINDOWS or not shutil.which("pactl"):
        return None
    try:
        return any(c.get("Corked") == "no" for c in _bloques(_pactl("list", "sink-inputs")))
    except (OSError, subprocess.SubprocessError):
        return False


def fuentes_del_servidor():
    """Entradas que publica el servidor de sonido de Linux (PipeWire o PulseAudio), con el nombre que ve
    el usuario: [{'nombre', 'fuente', 'predeterminado', 'sistema'}]. Primero los micrófonos y, al final,
    una única entrada de `sistema`, que graba directamente lo que suena en el equipo (música de otra
    aplicación, un vídeo…). Vacío si no hay servidor o en Windows. Solo consulta con `pactl`, que ya es
    parte del sistema; no cambia nada en él."""
    if rutas.WINDOWS or not shutil.which("pactl"):
        return []
    try:
        campos = list(_bloques(_pactl("list", "sources")))
        pred = _pactl("get-default-source").strip()
    except (OSError, subprocess.SubprocessError):
        return []
    fuentes = [{"nombre": c.get("Description") or c["Name"], "fuente": c["Name"], "predeterminado": c["Name"] == pred, "sistema": False}
               for c in campos if c.get("Name") and c.get("Monitor of Sink", "n/a") == "n/a"]   # los «monitor» no son micrófonos
    if any(c.get("Monitor of Sink", "n/a") != "n/a" for c in campos):
        fuentes.append({"nombre": SISTEMA, "fuente": FUENTE_SISTEMA, "predeterminado": False, "sistema": True})
    return fuentes


def microfonos_windows(s):
    """Entradas en Windows a partir de sounddevice (`s`): las de WASAPI, que dan el nombre completo
    del dispositivo (la interfaz antigua, MME, los corta a 31 letras y añade entradas duplicadas).
    Si WASAPI no está, las de la interfaz predeterminada."""
    apis, dispositivos = s.query_hostapis(), list(s.query_devices())
    wasapi = next((i for i, a in enumerate(apis) if "WASAPI" in a["name"]), None)
    pred = s.default.device[0]
    api = wasapi if wasapi is not None else (dispositivos[pred]["hostapi"] if pred is not None and pred >= 0 else 0)
    pred_api = apis[api].get("default_input_device", -1) if apis else -1
    lista = [{"indice": i, "nombre": d["name"], "sr": int(d["default_samplerate"]), "predeterminado": i == pred_api,
              "fuente": None, "sistema": False}
             for i, d in enumerate(dispositivos) if d["max_input_channels"] > 0 and d["hostapi"] == api]
    return sorted(lista, key=lambda d: not d["predeterminado"])


def captura_del_equipo_windows():
    """Módulo pyaudiowpatch si se puede capturar lo que suena en Windows (WASAPI «loopback»), o None."""
    if not rutas.WINDOWS:
        return None
    try:
        import pyaudiowpatch
        return pyaudiowpatch
    except Exception:   # falta el paquete o su biblioteca no carga: simplemente no se ofrece la entrada
        return None


def a_mono(datos, canales):
    """Bytes PCM16 entrelazados -> matriz (muestras, 1) en int16, promediando los canales."""
    import numpy as np
    x = np.frombuffer(datos, dtype=np.int16)
    if canales > 1:
        x = x[:len(x) - len(x) % canales].reshape(-1, canales).mean(axis=1).astype(np.int16)
    return x.reshape(-1, 1)


class FlujoDelEquipo:
    """Captura en Windows lo que suena por la salida predeterminada y lo entrega a `al_bloque` igual
    que hace sounddevice con un micrófono. Mientras no suena nada, Windows no entrega bloques."""

    def __init__(self, al_bloque, pa=None):
        from types import SimpleNamespace
        self.pa = pa or captura_del_equipo_windows()
        if self.pa is None:
            raise ErrorAudio("No está disponible la captura del sonido del equipo. Ejecuta: iniciar-windows.bat --reparar")
        self.motor = self.pa.PyAudio()
        try:
            salida = self.motor.get_default_wasapi_loopback()
            self.canales, self.sr = int(salida["maxInputChannels"]), int(salida["defaultSampleRate"])

            def recibir(datos, n, _tiempo, estado):
                al_bloque(a_mono(datos, self.canales), n, None, SimpleNamespace(input_overflow=bool(estado & self.pa.paInputOverflow)))
                return None, self.pa.paContinue
            self.flujo = self.motor.open(format=self.pa.paInt16, channels=self.canales, rate=self.sr, input=True,
                                         input_device_index=salida["index"], frames_per_buffer=1024, stream_callback=recibir)
        except Exception:
            self.motor.terminate()
            raise

    def start(self):
        self.flujo.start_stream()

    def stop(self):
        self.flujo.stop_stream()

    def close(self):
        self.flujo.close()
        self.motor.terminate()


def microfonos(refrescar=False):
    """Entradas disponibles: [{'indice', 'nombre', 'sr', 'predeterminado', 'fuente'}], la predeterminada primero.
    En Linux con servidor de sonido se listan sus micrófonos reales; `fuente` es el que hay que pedirle."""
    s = sd()
    if refrescar:  # PortAudio solo vuelve a enumerar al reiniciarse
        s._terminate()
        s._initialize()
    if rutas.WINDOWS:
        lista = microfonos_windows(s)
        if captura_del_equipo_windows():
            lista.append({"indice": None, "nombre": SISTEMA, "sr": 48000, "predeterminado": False, "fuente": FUENTE_SISTEMA, "sistema": True})
        return lista
    puente = next((i for i, d in enumerate(s.query_devices()) if d["name"] == "pulse" and d["max_input_channels"] > 0), None)
    fuentes = fuentes_del_servidor() if puente is not None else []
    if fuentes:
        sr = int(s.query_devices(puente)["default_samplerate"])
        return sorted(({"indice": puente, "sr": sr, **f} for f in fuentes), key=lambda d: (d["sistema"], not d["predeterminado"]))
    pred = s.default.device[0]
    api = s.query_devices(pred)["hostapi"] if pred is not None and pred >= 0 else 0
    lista = [{"indice": i, "nombre": d["name"], "sr": int(d["default_samplerate"]), "predeterminado": i == pred, "fuente": None, "sistema": False}
             for i, d in enumerate(s.query_devices()) if d["max_input_channels"] > 0 and d["hostapi"] == api]
    return sorted(lista, key=lambda d: not d["predeterminado"])


def reproducir(notas, sr=22050):
    """Hace sonar una lista de notas ([inicio, fin, tono, intensidad]) con un timbre sencillo, por la
    salida predeterminada. Sirve para oír una corrección; no pretende sonar como un instrumento real."""
    import numpy as np
    s = sd()
    if not notas:
        return
    total = max(n[1] for n in notas) + 0.3
    x = np.zeros(int(total * sr), dtype="float32")
    for ini, fin, tono, vel in notas:
        t = np.arange(int(max(fin - ini, 0.05) * sr)) / sr
        f = 440 * 2 ** ((tono - 69) / 12)
        onda = np.sin(2 * np.pi * f * t) + 0.35 * np.sin(4 * np.pi * f * t) + 0.15 * np.sin(6 * np.pi * f * t)
        onda *= np.minimum(1, t / 0.01) * np.exp(-2.2 * t) * np.minimum(1, (t[-1] - t) / 0.03 + 1e-3)
        a = int(ini * sr)
        x[a:a + len(onda)] += (0.25 + 0.3 * vel) * onda[:len(x) - a].astype("float32")
    try:
        s.play(x / max(1.0, float(abs(x).max())), sr)
    except Exception as e:
        raise ErrorAudio(f"No se pudo reproducir por la salida de audio predeterminada. Detalle: {e}") from e


def parar_reproduccion():
    try:
        sd().stop()
    except Exception:
        pass


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

    def __init__(self, destino=None, dispositivo=None, segmento_s=0, carpeta_segmentos=None, al_segmento=None, fuente=None):
        self.destino, self.dispositivo, self.fuente = (Path(destino) if destino else None), dispositivo, fuente
        self.segmento_s, self.carpeta_segmentos, self.al_segmento = segmento_s, carpeta_segmentos, al_segmento
        self.sr = 44100
        self.nivel = 0.0       # pico 0..1 del último bloque
        self.pico = 0.0        # pico máximo de toda la toma
        self.frames = 0        # muestras ya escritas en disco
        self.desbordes = 0     # avisos de desbordamiento del sistema de audio
        self.perdidos = 0      # muestras descartadas porque el disco no daba abasto
        self.error = ""        # motivo por el que la captura se detuvo sola
        self.pausada = False
        self.rellenar = False  # captura del equipo en Windows: los silencios no llegan y hay que escribirlos
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
    def floja(self):
        """Señal muy débil: suficiente para oír algo, mala para reconocer palabras o notas."""
        return self.frames > self.sr and 0.001 <= self.pico < 0.1

    @property
    def muda(self):
        """La toma entera es silencio digital: micrófono silenciado, apagado o entrada equivocada."""
        return self.frames > self.sr and self.pico < 0.001

    # -- ciclo de vida -------------------------------------------------------
    def iniciar(self):
        s = sd()
        del_equipo_windows = rutas.WINDOWS and self.fuente == FUENTE_SISTEMA
        if self.fuente and not rutas.WINDOWS:  # el servidor de sonido conecta este flujo a la entrada elegida
            os.environ["PULSE_SOURCE"] = salida_que_suena() + ".monitor" if self.fuente == FUENTE_SISTEMA else self.fuente
        try:
            if del_equipo_windows:
                self._flujo = FlujoDelEquipo(self._bloque)
                self.sr, self.rellenar = self._flujo.sr, True
                self._preparar()
            else:
                info = s.query_devices(self.dispositivo, "input")
                self.sr = int(info["default_samplerate"])
                self._preparar()
                ajustes = None
                if rutas.WINDOWS and "WASAPI" in s.query_hostapis(info["hostapi"])["name"]:
                    ajustes = s.WasapiSettings(auto_convert=True)   # que Windows adapte canales y frecuencia si hace falta
                self._flujo = s.InputStream(device=self.dispositivo, channels=1, samplerate=self.sr, dtype="int16",
                                            callback=self._bloque, extra_settings=ajustes)
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
                    if self.rellenar:      # no sonaba nada en ese medio segundo: se escribe silencio para no perder el compás del tiempo
                        if not self.pausada and time.monotonic() - self._ultimo >= 0.5:
                            hueco = bytes(2 * (self.sr // 2))
                            self._wav.escribir(hueco)
                            self.frames += len(hueco) // 2
                        continue
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
