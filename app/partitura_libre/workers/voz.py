"""Voz a texto con faster-whisper en CPU. Proceso persistente del conjunto «app».

Uso: python -m partitura_libre.workers.voz <carpeta_del_modelo>
Recibe órdenes JSON por la entrada estándar, una por línea:
    {"id": 1, "audio": "...", "idioma": "es" | "", "cantada": false, "desfase": 0.0}
"""
import json
import sys

from .. import letras
from . import emitir


def main():
    from faster_whisper import WhisperModel
    modelo = WhisperModel(sys.argv[1], device="cpu", compute_type="int8", local_files_only=True)
    emitir("listo")
    for linea in sys.stdin:
        o = json.loads(linea)
        try:
            cantada, desfase = o.get("cantada", False), o.get("desfase", 0.0)
            # Voz cantada: sin filtro de silencios (la música lo confunde) y sin arrastrar
            # el texto anterior, para que no «rellene» versos que no se entienden.
            segs, info = modelo.transcribe(o["audio"], language=o.get("idioma") or None, beam_size=5,
                                           vad_filter=not cantada, condition_on_previous_text=not cantada)
            emitir("idioma", id=o["id"], idioma=info.language, prob=round(info.language_probability, 3), dur=info.duration)
            for s in segs:
                if s.text.strip():
                    emitir("segmento", id=o["id"], inicio=round(s.start + desfase, 2), fin=round(s.end + desfase, 2),
                           texto=s.text.strip(), v=round(min(1.0, s.end / max(info.duration, 0.01)), 3),
                           dudoso=cantada and s.avg_logprob < -0.5 or letras.es_dudoso(s.avg_logprob, s.no_speech_prob, s.compression_ratio))
            emitir("fin", id=o["id"])
        except Exception as e:
            import traceback
            traceback.print_exc()
            emitir("error", id=o["id"], msg=f"No se pudo transcribir: {type(e).__name__}: {e}")


if __name__ == "__main__":
    main()
