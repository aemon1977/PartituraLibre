"""Voz a texto con faster-whisper en CPU. Proceso persistente del conjunto «app».

Uso: python -m partitura_libre.workers.voz <carpeta_del_modelo>
Recibe órdenes JSON por la entrada estándar, una por línea:
    {"id": 1, "audio": "...", "idioma": "es" | "", "cantada": false, "desfase": 0.0, "borrar": false, "palabras": false}
`palabras` añade a cada frase el tiempo de cada palabra (para poner la letra bajo las notas).
`separar` aísla antes la voz de los instrumentos (canciones); necesita el modelo de separación descargado.
`borrar` elimina el audio al terminar (segmentos temporales del dictado en vivo).
"""
import json
import os
import sys
from pathlib import Path

from .. import letras, rutas, separacion
from . import emitir


def main():
    from faster_whisper import WhisperModel
    modelo = WhisperModel(sys.argv[1], device="cpu", compute_type="int8", local_files_only=True)
    emitir("listo")
    for linea in sys.stdin:
        o = json.loads(linea)
        audio, temporal = o["audio"], None
        try:
            cantada, desfase = o.get("cantada", False), o.get("desfase", 0.0)
            if o.get("separar") and separacion.instalado():   # primero se quita la música; se transcribe solo la voz
                emitir("progreso", id=o["id"], v=0.0, msg="Separando la voz de la música…")
                rutas.TEMP.mkdir(parents=True, exist_ok=True)
                temporal = rutas.TEMP / f"voz-separada-{os.getpid()}.wav"
                audio = str(separacion.voz_a_wav(audio, temporal, lambda f: emitir(
                    "progreso", id=o["id"], v=round(f, 3), msg=f"Separando la voz de la música… {f * 100:.0f} %")))
            # Voz cantada: sin filtro de silencios (la música lo confunde), sin arrastrar el texto
            # anterior (para que no «rellene» versos) y sin descartar de antemano los tramos que el
            # modelo cree sin voz: se muestran marcados como dudosos, salvo los que son puro relleno.
            segs, info = modelo.transcribe(audio, language=o.get("idioma") or None, beam_size=5,
                                           vad_filter=not cantada, condition_on_previous_text=not cantada,
                                           word_timestamps=bool(o.get("palabras")),
                                           **({"no_speech_threshold": None} if cantada else {}))
            emitir("idioma", id=o["id"], idioma=info.language, prob=round(info.language_probability, 3), dur=info.duration)
            for s in segs:
                if s.text.strip() and not (cantada and letras.es_relleno(s.text, s.avg_logprob)):
                    emitir("segmento", id=o["id"], inicio=round(s.start + desfase, 2), fin=round(s.end + desfase, 2),
                           palabras=[[round(p.start + desfase, 2), round(p.end + desfase, 2), p.word.strip()] for p in (s.words or [])],
                           texto=s.text.strip(), v=round(min(1.0, s.end / max(info.duration, 0.01)), 3),
                           dudoso=cantada and s.avg_logprob < -0.65 or letras.es_dudoso(s.avg_logprob, s.no_speech_prob, s.compression_ratio))
            emitir("fin", id=o["id"])
        except Exception as e:
            import traceback
            traceback.print_exc()
            emitir("error", id=o["id"], msg=f"No se pudo transcribir: {type(e).__name__}: {e}")
        finally:
            if temporal:
                temporal.unlink(missing_ok=True)
            if o.get("borrar"):
                Path(o["audio"]).unlink(missing_ok=True)


if __name__ == "__main__":
    main()
