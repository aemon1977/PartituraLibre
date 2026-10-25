"""Lector de partituras: toca una partitura (PDF, imagen, MusicXML, MXL, MIDI o MuseScore) con el instrumento
elegido, solo las notas (la letra se quita), para comprobar de oído que está bien escrita.

PDF o imagen -> Audiveris (reconocimiento óptico de partituras) -> MXL
partitura    -> MuseScore -> MusicXML -> instrumento elegido y sin letra -> MuseScore -> WAV

El instrumento se cambia en el MusicXML y no en un MIDI: al importar un MIDI, MuseScore toma el primer instrumento
que tenga ese número de programa (la trompeta salía como «Vuvuzela»). Por su sonido MusicXML y su nombre, MuseScore
4.7 elige el instrumento correcto y la altura no cambia, tampoco en los transpositores (comprobados los 35).
Audiveris y MuseScore se ejecutan como programas aparte, descargados dentro de runtime/ a petición del usuario."""
import os
import shutil
import signal
import subprocess
import tempfile
import time
import xml.etree.ElementTree as ET
from pathlib import Path

from . import descargas, editor, rutas

VERSION = "5.11.0"
_BASE = f"https://github.com/Audiveris/audiveris/releases/download/{VERSION}/Audiveris-{VERSION}"
# Windows: la variante de consola (escribe su registro en la salida). Linux: el paquete de Ubuntu 22.04, el de
# bibliotecas más antiguas, para que funcione también en Debian 12; trae su propio Java.
AUDIVERIS = ({"url": _BASE + "-windowsConsole-x86_64.msi", "mb": 85,
              "sha256": "5f1b4e96a12c53c7da426814b76e599363c4181e291855996e0a6878dda95f71"}
             if rutas.WINDOWS else
             {"url": _BASE + "-ubuntu22.04-x86_64.deb", "mb": 78,
              "sha256": "ae714594f40e54b1a4951fc3f914f08ae38fe5d07b7f2283b1a904fdb6e0a318"})
CARPETA = rutas.RUNTIME / "audiveris"
LICENCIA = "Audiveris es software libre (AGPL v3) de Hervé Bitteur y colaboradores; se descarga de su página oficial de GitHub."

IMAGENES = (".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp")
PARTITURAS = (".musicxml", ".xml", ".mxl", ".mid", ".midi", ".mscz", ".mscx")
FILTRO = f"Partituras ({' '.join('*' + e for e in IMAGENES + PARTITURAS)});;Todos los archivos (*)"

# nombre: (sonido MusicXML, nombre con el que MuseScore elige su instrumento)
INSTRUMENTOS = {
    "Piano": ("keyboard.piano", "Piano"), "Piano eléctrico": ("keyboard.piano.electric", "Electric Piano"),
    "Clavecín": ("keyboard.harpsichord", "Harpsichord"), "Celesta": ("keyboard.celesta", "Celesta"),
    "Vibráfono": ("pitched-percussion.vibraphone", "Vibraphone"), "Marimba": ("pitched-percussion.marimba", "Marimba"),
    "Xilófono": ("pitched-percussion.xylophone", "Xylophone"), "Órgano": ("keyboard.organ", "Organ"),
    "Acordeón": ("keyboard.accordion", "Accordion"), "Armónica": ("wind.reed.harmonica", "Harmonica"),
    "Guitarra clásica": ("pluck.guitar.nylon-string", "Classical Guitar"), "Guitarra acústica": ("pluck.guitar.acoustic", "Acoustic Guitar"),
    "Guitarra eléctrica": ("pluck.guitar.electric", "Electric Guitar"), "Bajo eléctrico": ("pluck.bass.electric", "Electric Bass"),
    "Violín": ("strings.violin", "Violin"), "Viola": ("strings.viola", "Viola"), "Violonchelo": ("strings.cello", "Violoncello"),
    "Contrabajo": ("strings.contrabass", "Contrabass"), "Arpa": ("pluck.harp", "Harp"), "Cuerdas": ("strings.group", "Violins"),
    "Voz (soprano)": ("voice.soprano", "Soprano"), "Trompeta": ("brass.trumpet", "Trumpet in B♭"),
    "Trombón": ("brass.trombone", "Trombone"), "Tuba": ("brass.tuba", "Tuba"), "Trompa": ("brass.french-horn", "Horn in F"),
    "Saxo soprano": ("wind.reed.saxophone.soprano", "Soprano Saxophone"), "Saxo alto": ("wind.reed.saxophone.alto", "Alto Saxophone"),
    "Saxo tenor": ("wind.reed.saxophone.tenor", "Tenor Saxophone"), "Oboe": ("wind.reed.oboe", "Oboe"),
    "Fagot": ("wind.reed.bassoon", "Bassoon"), "Clarinete": ("wind.reed.clarinet", "Clarinet in B♭"),
    "Flautín": ("wind.flutes.flute.piccolo", "Piccolo"), "Flauta": ("wind.flutes.flute", "Flute"),
    "Flauta dulce": ("wind.flutes.recorder", "Recorder"), "Ocarina": ("wind.flutes.ocarina", "Ocarina"),
}


class Cancelado(Exception):
    pass


# -- Audiveris ---------------------------------------------------------------
def audiveris():
    """Ejecutable de Audiveris de la copia portable, o None."""
    if rutas.WINDOWS:
        return next(iter(sorted(CARPETA.glob("**/Audiveris.exe"))), None)
    r = CARPETA / "opt" / "audiveris" / "bin" / "Audiveris"
    return r if r.is_file() else None


def instalar(progreso=None, cancelar=None):
    """Descarga Audiveris y lo descomprime en runtime/audiveris, sin instalarlo en el sistema."""
    CARPETA.mkdir(parents=True, exist_ok=True)
    paquete = rutas.TEMP / AUDIVERIS["url"].rsplit("/", 1)[1]
    descargas.descargar(AUDIVERIS["url"], paquete, progreso, cancelar, AUDIVERIS["sha256"])
    nueva = Path(tempfile.mkdtemp(prefix="audiveris-", dir=rutas.RUNTIME))
    try:
        if rutas.WINDOWS:
            # Instalación «administrativa»: solo extrae los archivos en la carpeta, sin registro ni permisos.
            r = subprocess.run(f'msiexec /a "{paquete}" /qn TARGETDIR="{nueva}"', timeout=900,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        elif shutil.which("dpkg-deb"):
            r = subprocess.run(["dpkg-deb", "-x", str(paquete), str(nueva)], capture_output=True, timeout=900)
        else:   # sin dpkg (Fedora…): el .deb es un archivo «ar» con un tar comprimido con zstd
            datos = _miembro_ar(paquete, "data.tar")
            r = subprocess.run(["tar", "--zstd", "-xf", str(datos), "-C", str(nueva)], capture_output=True, timeout=900)
            datos.unlink()
        if r.returncode:
            raise OSError(f"No se pudo descomprimir Audiveris (código {r.returncode}).")
        for copia in nueva.glob("*.msi"):   # la extracción deja también una copia del instalador
            copia.unlink()
        shutil.rmtree(CARPETA, ignore_errors=True)
        nueva.rename(CARPETA)
    finally:
        shutil.rmtree(nueva, ignore_errors=True)
        paquete.unlink(missing_ok=True)
    if not audiveris():
        raise OSError("Audiveris se descomprimió, pero no se encuentra su ejecutable.")


def _miembro_ar(archivo, prefijo):
    """Extrae a temp/ el primer miembro de un archivo «ar» (.deb) cuyo nombre empieza por `prefijo`."""
    with open(archivo, "rb") as f:
        if f.read(8) != b"!<arch>\n":
            raise OSError("El paquete de Audiveris no tiene el formato esperado.")
        while cabecera := f.read(60):
            nombre, tam = cabecera[:16].decode().strip().rstrip("/"), int(cabecera[48:58])
            if nombre.startswith(prefijo):
                destino = rutas.TEMP / nombre
                destino.write_bytes(f.read(tam))
                return destino
            f.seek(tam + tam % 2, 1)
    raise OSError("El paquete de Audiveris no trae sus archivos.")


def quitar():
    shutil.rmtree(CARPETA, ignore_errors=True)


def _entorno_audiveris():
    """Su configuración y cachés, dentro de la carpeta del programa (en Linux van a HOME y XDG; en Windows, a APPDATA)."""
    casa = rutas.DATOS / "audiveris"
    casa.mkdir(parents=True, exist_ok=True)
    e = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    e.update(HOME=str(casa), XDG_CONFIG_HOME=str(casa / "config"), XDG_CACHE_HOME=str(casa / "cache"),
             XDG_DATA_HOME=str(casa / "datos"), APPDATA=str(casa / "config"), LOCALAPPDATA=str(casa / "cache"),
             TMP=str(rutas.TEMP), TEMP=str(rutas.TEMP), TMPDIR=str(rutas.TEMP))
    return e


# -- ejecución de los programas externos ---------------------------------------
def ejecutar(orden, entorno, cancelar=None, limite=1800):
    """Ejecuta un programa aparte esperando a que termine. `cancelar` (threading.Event) lo corta con todos sus
    procesos hijo. Su salida va a logs/motores.log; si falla, el error lleva las últimas líneas."""
    rutas.LOGS.mkdir(parents=True, exist_ok=True)
    rutas.TEMP.mkdir(parents=True, exist_ok=True)
    registro = rutas.LOGS / "motores.log"
    if registro.exists() and registro.stat().st_size > 2_000_000:
        registro.unlink()
    with tempfile.TemporaryFile("w+", encoding="utf-8", errors="replace", dir=rutas.TEMP) as salida:
        p = subprocess.Popen([str(x) for x in orden], env=entorno, cwd=str(rutas.TEMP), stdin=subprocess.DEVNULL,
                             stdout=salida, stderr=subprocess.STDOUT, start_new_session=not rutas.WINDOWS,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        fin = time.monotonic() + limite
        while p.poll() is None:
            if (cancelar is not None and cancelar.is_set()) or time.monotonic() > fin:
                _matar(p)
                if cancelar is not None and cancelar.is_set():
                    raise Cancelado()
                raise RuntimeError(f"{Path(orden[0]).name} no terminó en {limite // 60} min y se ha detenido.")
            time.sleep(0.1)
        salida.seek(0)
        texto = salida.read()
    with open(registro, "a", encoding="utf-8") as f:
        f.write(f"\n--- {' '.join(str(x) for x in orden)}\n{texto[-20000:]}")
    if p.returncode:
        ultimas = "\n".join(l for l in texto.splitlines() if l.strip())[-600:]
        raise RuntimeError(f"{Path(orden[0]).name} terminó con error (código {p.returncode}).\n{ultimas}")
    return texto


def _matar(p):
    try:
        if rutas.WINDOWS:   # el proceso y los que haya lanzado
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(p.pid)], capture_output=True,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        else:
            os.killpg(p.pid, signal.SIGKILL)
    except OSError:
        pass
    p.wait()


def _musescore():
    """(orden base, entorno) para usar MuseScore sin ventana."""
    exe, origen = editor.buscar()
    if not exe:
        raise FileNotFoundError("Hace falta MuseScore para convertir la partitura y darle sonido. Descárgalo en esta misma pestaña.")
    if rutas.WINDOWS and exe.name.lower().endswith("portable.exe"):
        # el lanzador de PortableApps abre la ventana; para exportar se usa el programa en sí, que en esta
        # edición guarda su configuración dentro de su carpeta (Data/settings), no en el perfil
        exe = next(iter(sorted(exe.parent.glob("App/MuseScore/bin/MuseScore*.exe"))), exe)
    e = editor._entorno(origen) or {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    if not rutas.WINDOWS:   # sin ventana; MuseScore no hace caso de QT_QPA_PLATFORM, sino de la suya
        e["QT_QPA_PLATFORM"] = e["MU_QT_QPA_PLATFORM"] = "offscreen"
    return exe, e


def musescore(entrada, salida, cancelar=None):
    """Convierte con MuseScore; el formato lo da la extensión de `salida` (.musicxml, .wav, .mid…)."""
    exe, e = _musescore()
    Path(salida).unlink(missing_ok=True)
    ejecutar([exe, "-o", salida, entrada], e, cancelar, limite=600)
    if not Path(salida).is_file():
        raise RuntimeError(f"MuseScore no pudo convertir «{Path(entrada).name}».")
    return Path(salida)


# -- de la partitura al sonido ------------------------------------------------
def a_musicxml(entrada, carpeta, cancelar=None, progreso=None):
    """MusicXML de cualquier partitura en `carpeta`. Un PDF o una imagen se lee antes con Audiveris
    (≈ 20 s por página). `progreso(texto)` cuenta en qué paso va."""
    entrada, carpeta = Path(entrada), Path(carpeta)
    carpeta.mkdir(parents=True, exist_ok=True)
    if entrada.suffix.lower() in IMAGENES:
        exe = audiveris()
        if not exe:
            raise FileNotFoundError("Para leer partituras en PDF o en imagen hace falta Audiveris. Descárgalo en esta misma pestaña.")
        if progreso:
            progreso("Leyendo la partitura con Audiveris (≈ 20 s por página)…")
        # Audiveris nombra sus archivos según el de entrada: se le pasa una copia con un nombre sencillo
        copia = carpeta / f"partitura{entrada.suffix.lower()}"
        shutil.copyfile(entrada, copia)
        ejecutar([exe, "-batch", "-export", "-output", carpeta, copia], _entorno_audiveris(), cancelar)
        leidas = sorted(carpeta.glob("partitura*.mxl"))
        if not leidas:
            raise RuntimeError("Audiveris no ha encontrado ninguna partitura que pueda leer en ese archivo. "
                               "Funciona mejor con partituras impresas y bien escaneadas (300 ppp o más).")
        entrada = leidas[0]
    if progreso:
        progreso("Preparando la partitura…")
    return musescore(entrada, carpeta / "leida.musicxml", cancelar)


def con_instrumento(xml, instrumento, salida):
    """Copia del MusicXML con todas las partes tocadas por `instrumento` y sin letra."""
    sonido, nombre = INSTRUMENTOS[instrumento]
    arbol = ET.parse(xml)
    for padre in arbol.iter():
        for e in padre.findall("lyric"):
            padre.remove(e)
    for parte in arbol.iter("score-part"):
        for e in parte.findall("midi-instrument"):   # su número de programa haría elegir otro instrumento
            parte.remove(e)
        nombre_parte = parte.find("part-name")
        if nombre_parte is None:
            nombre_parte = ET.SubElement(parte, "part-name")
        nombre_parte.text = nombre
        instrumentos = parte.findall("score-instrument") or [ET.SubElement(parte, "score-instrument", id=f"{parte.get('id')}-I1")]
        for si in instrumentos:
            for e in list(si):
                si.remove(e)
            ET.SubElement(si, "instrument-name").text = nombre
            ET.SubElement(si, "instrument-sound").text = sonido
    arbol.write(salida, encoding="utf-8", xml_declaration=True)
    return Path(salida)


def sonar(xml, instrumento, carpeta, cancelar=None):
    """WAV de la partitura (MusicXML) tocada por `instrumento`."""
    carpeta = Path(carpeta)
    carpeta.mkdir(parents=True, exist_ok=True)
    tocada = con_instrumento(xml, instrumento, carpeta / "instrumento.musicxml")
    return musescore(tocada, carpeta / "interpretacion.wav", cancelar)
