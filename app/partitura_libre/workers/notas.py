"""Audio -> notas (Basic Pitch, modelo ONNX) -> MIDI -> MusicXML.

Se ejecuta con el conjunto «partituras». Uso:
    python -m partitura_libre.workers.notas '{"cmd": "transcribir", "audio": ..., "carpeta": ..., "nombre": ...}'
    python -m partitura_libre.workers.notas '{"cmd": "regenerar", "notas": ..., "carpeta": ..., "nombre": ...}'
    python -m partitura_libre.workers.notas '{"cmd": "vivo"}'    borrador mientras se graba: recibe por la
        entrada estándar una línea JSON por segmento, {"audio": ..., "desfase": s}, y emite sus notas

Método para audios largos: el archivo se lee en trozos de TROZO_S segundos (nunca
entero en memoria). Cada trozo se analiza con MARGEN_S segundos de contexto por
delante y por detrás; solo cuentan las notas que empiezan dentro del trozo, con su
instante real, y una nota que sigue sonando en el trozo siguiente se alarga en vez
de partirse (ver partituras.integrar).
"""
import json
import os
import sys
from pathlib import Path

from .. import partituras, rutas
from . import emitir, reemplazar

TROZO_S = 120
MARGEN_S = 2   # contexto que se analiza de más a cada lado de un trozo


def detectar(audio, trozo_s=TROZO_S):
    import numpy as np
    import soundfile as sf
    from basic_pitch import FilenameSuffix, build_icassp_2022_model_path
    from basic_pitch.inference import Model, predict

    modelo = Model(build_icassp_2022_model_path(FilenameSuffix.onnx))
    trozo = rutas.TEMP / f"trozo-{os.getpid()}.wav"
    notas, ultima, bpm = [], {}, None
    try:
        with sf.SoundFile(audio) as f:
            sr, total = f.samplerate, max(f.frames, 1)
            margen = int(min(MARGEN_S, trozo_s / 2) * sr)
            leer = lambda n: f.read(n, dtype="float32", always_2d=True).mean(axis=1)
            antes, nucleo, c0 = np.zeros(0, "float32"), leer(int(trozo_s * sr)), 0.0
            while len(nucleo):
                despues = leer(margen)  # contexto posterior; es el principio del núcleo siguiente
                if bpm is None:
                    bpm = estimar_bpm(nucleo, sr)
                x = np.concatenate([antes, nucleo, despues])
                if len(x) < sr // 2:  # Basic Pitch necesita un mínimo de audio
                    x = np.concatenate([x, np.zeros(sr // 2 - len(x), dtype="float32")])
                sf.write(trozo, x, sr, subtype="PCM_16")
                a0 = c0 - len(antes) / sr
                c1 = c0 + len(nucleo) / sr if len(despues) else float("inf")
                partituras.integrar(notas, ultima, [[round(a0 + float(i), 4), round(a0 + float(e), 4), int(t), round(float(v), 3)]
                                                    for i, e, t, v, _ in predict(str(trozo), modelo)[2]], a0, c0, c1)
                hasta = c0 + len(nucleo) / sr
                emitir("progreso", v=min(0.9, 0.9 * hasta * sr / total), msg=f"Analizado hasta {int(hasta // 60)}:{int(hasta % 60):02d}")
                antes, c0 = nucleo[-margen:], c0 + len(nucleo) / sr
                resto = leer(int(trozo_s * sr) - len(despues)) if len(despues) == margen else np.zeros(0, "float32")
                nucleo = np.concatenate([despues, resto])
    finally:
        trozo.unlink(missing_ok=True)
    return sorted(partituras.quitar_armonicos(notas)), bpm or 120


def en_vivo():
    """Borrador durante la grabación: el modelo se carga una vez y cada segmento se analiza al llegar."""
    from basic_pitch import FilenameSuffix, build_icassp_2022_model_path
    from basic_pitch.inference import Model, predict

    modelo = Model(build_icassp_2022_model_path(FilenameSuffix.onnx))
    emitir("listo")
    for linea in sys.stdin:
        o = json.loads(linea)
        try:
            notas = [[round(o["desfase"] + float(i), 3), round(o["desfase"] + float(e), 3), int(t), round(float(v), 3)]
                     for i, e, t, v, _ in predict(o["audio"], modelo)[2]]
            emitir("notas", desfase=o["desfase"], notas=partituras.quitar_armonicos(notas))
        except Exception as e:
            print("Segmento en vivo no analizado:", e)
        finally:
            Path(o["audio"]).unlink(missing_ok=True)  # los segmentos son temporales
    return 0


def estimar_bpm(x, sr):
    try:
        import librosa
        import numpy as np
        bpm = float(np.atleast_1d(librosa.beat.beat_track(y=x, sr=sr)[0])[0])
        return int(round(bpm)) if 40 <= bpm <= 220 else 120
    except Exception as e:  # sin pulso claro: 120 es el valor neutro de MIDI
        print("No se pudo estimar el tempo:", e)
        return 120


def escribir(notas, bpm, carpeta, nombre, titulo, clave="", nombres=False):
    """Escribe nombre.notas.json, nombre.mid y nombre.musicxml sin pisar nada."""
    import pretty_midi
    from music21 import clef, converter, metadata

    carpeta = Path(carpeta)
    base = rutas.ruta_unica(carpeta, nombre, ".mid", (".musicxml", ".notas.json")).with_suffix("")
    f_notas, f_mid, f_xml = (Path(f"{base}{e}") for e in (".notas.json", ".mid", ".musicxml"))
    p_mid, p_xml, p_notas = (Path(f"{f}.parcial") for f in (f_mid, f_xml, f_notas))

    pm = pretty_midi.PrettyMIDI(initial_tempo=bpm)
    inst = pretty_midi.Instrument(program=0)
    for ini, fin, tono, amp in notas:
        inst.notes.append(pretty_midi.Note(velocity=max(1, min(127, int(amp * 127))), pitch=int(tono), start=ini, end=max(fin, ini + 0.03)))
    pm.instruments.append(inst)
    pm.write(str(p_mid))
    emitir("progreso", v=0.93, msg="Creando MusicXML")

    partitura = converter.parse(str(p_mid), format="midi")
    partitura.metadata = metadata.Metadata(title=titulo, composer="Transcripción automática · Partitura Libre")
    elegida = {"sol": clef.TrebleClef, "fa": clef.BassClef, "do3": clef.AltoClef, "do4": clef.TenorClef}.get(clave)
    for parte in partitura.parts:
        if elegida:
            for c in list(parte.recurse().getElementsByClass(clef.Clef)):
                c.activeSite.remove(c)
            (parte.getElementsByClass("Measure").first() or parte).insert(0, elegida())
        if nombres:  # Do, Re, Mi… bajo cada nota, como letra
            for n in parte.recurse().notes:
                if n.tie is None or n.tie.type == "start":
                    n.addLyric(" ".join(partituras.solfeo(p.midi) for p in n.pitches))
    partitura.write("musicxml", fp=str(p_xml))
    p_notas.write_text(json.dumps({"bpm": bpm, "notas": notas}), encoding="utf-8")
    for p, f in ((p_notas, f_notas), (p_mid, f_mid), (p_xml, f_xml)):
        reemplazar(p, f)
    return {"midi": f_mid.name, "musicxml": f_xml.name, "notas": f_notas.name, "bpm": bpm, "n": len(notas)}


def main():
    o = json.loads(sys.argv[1])
    rutas.TEMP.mkdir(parents=True, exist_ok=True)
    try:
        if o["cmd"] == "vivo":
            return en_vivo()
        if o["cmd"] == "transcribir":
            emitir("progreso", v=0.0, msg="Cargando el motor Basic Pitch")
            notas, bpm = detectar(o["audio"], o.get("trozo_s", TROZO_S))
            bpm = o.get("bpm") or bpm
            if not notas:
                emitir("error", msg="No se detectó ninguna nota. Comprueba que el audio tiene una melodía audible; "
                                    "la grabación original se conserva.")
                return 1
        else:
            d = json.loads(Path(o["notas"]).read_text(encoding="utf-8"))
            notas, bpm = d["notas"], o.get("bpm") or d.get("bpm", 120)
        emitir("fin", **escribir(notas, bpm, o["carpeta"], o["nombre"], o.get("titulo", o["nombre"]),
                                 o.get("clave", ""), o.get("nombres", False)))
        return 0
    except Exception as e:
        import traceback
        traceback.print_exc()
        emitir("error", msg=f"Falló la conversión: {type(e).__name__}: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
