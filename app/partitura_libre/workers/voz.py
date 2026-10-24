"""Voz a texto con faster-whisper en CPU. Proceso persistente del conjunto «app».

Uso: python -m partitura_libre.workers.voz <carpeta_del_modelo>
Recibe órdenes JSON por la entrada estándar, una por línea:
    {"id": 1, "audio": "...", "idioma": "es" | "", "cantada": false, "desfase": 0.0, "borrar": false, "palabras": false}
`palabras` añade a cada frase el tiempo de cada palabra (para poner la letra bajo las notas).
`separar` aísla antes la voz de los instrumentos (canciones); necesita el modelo de separación descargado.
`guardar_voz` (ruta) conserva ahí esa voz aislada, para sacar de ella la melodía cantada.
`borrar` elimina el audio al terminar (segmentos temporales del dictado en vivo).
"""
import json
import os
import sys
from pathlib import Path

from .. import letras, rutas, separacion
from . import aviso_de_parar, emitir, parada_pedida


HAZ, TEMPERATURAS = 5, (0.0, 0.4)   # se ajustan al equipo en main()


class Parada(Exception):
    pass


def separar_aparte(audio, destino, id_):
    """La separación va en su propio proceso, antes de cargar el reconocedor: los dos juntos no caben
    holgados en un equipo con poca memoria, y al acabar el proceso el sistema recupera toda la suya."""
    import subprocess
    p = subprocess.Popen([sys.executable, "-s", "-m", "partitura_libre.workers.separar", str(audio), str(destino), str(os.getpid())],
                         stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, text=True, encoding="utf-8",
                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    fallo = ""
    for linea in p.stdout:
        if parada_pedida():
            p.terminate()
            p.wait()
            raise Parada
        ev = json.loads(linea)
        if ev["t"] == "progreso":
            emitir("progreso", id=id_, v=ev["v"], msg=f"Separando la voz de la música… {ev['v'] * 100:.0f} %")
        elif ev["t"] == "error":
            fallo = ev["msg"]
    if p.wait() or not Path(destino).is_file():
        raise RuntimeError(fallo or f"el separador se cerró (código {p.returncode}); suele ser falta de memoria")
    return str(destino)


def main():
    from .. import equipo
    global HAZ, TEMPERATURAS
    if equipo.modesto():
        HAZ, TEMPERATURAS = 1, (0.0,)
    modelo = None   # se carga con la primera orden, después de separar la voz: nunca los dos en memoria a la vez

    def reconocedor():
        nonlocal modelo
        if modelo is None:
            from faster_whisper import WhisperModel
            modelo = WhisperModel(sys.argv[1], device="cpu", compute_type="int8", local_files_only=True,
                                  cpu_threads=equipo.hilos_de_calculo())
        return modelo
    emitir("listo")
    for linea in sys.stdin:
        o = json.loads(linea)
        aviso_de_parar().unlink(missing_ok=True)   # «parar» vale para la orden en curso, no para las siguientes
        audio, temporal, hasta = o["audio"], None, 0.0

        def limpiar():   # antes de avisar del fin: quien espera ese aviso puede cerrar el proceso al momento
            if temporal:
                temporal.unlink(missing_ok=True)
        try:
            cantada, desfase = o.get("cantada", False), o.get("desfase", 0.0)
            if o.get("separar") and separacion.instalado():   # primero se quita la música; se transcribe solo la voz
                emitir("progreso", id=o["id"], v=0.0, msg="Separando la voz de la música…")
                rutas.TEMP.mkdir(parents=True, exist_ok=True)
                temporal = rutas.TEMP / f"voz-separada-{os.getpid()}.wav"
                destino = Path(o["guardar_voz"]) if o.get("guardar_voz") else temporal   # la voz aislada se puede conservar
                temporal = None if o.get("guardar_voz") else temporal
                audio = separar_aparte(audio, destino, o["id"])
            # Voz cantada: sin filtro de silencios (la música lo confunde), sin arrastrar el texto
            # anterior (para que no «rellene» versos) y sin descartar de antemano los tramos que el
            # modelo cree sin voz: se muestran marcados como dudosos, salvo los que son puro relleno.
            # Sin reintentos a temperaturas altas: con música, el modelo cae en bucles («¡Aaaaah!») y cada
            # reintento repite el tramo; medido con 4 hilos, 454 s -> 26 s por minuto de canción, misma letra.
            # En equipos modestos, además, un solo candidato (beam 1).
            emitir("progreso", id=o["id"], v=1.0, msg="Cargando el reconocedor de voz…")
            segs, info = reconocedor().transcribe(audio, language=o.get("idioma") or None, beam_size=HAZ,
                                           temperature=TEMPERATURAS,
                                           vad_filter=not cantada, condition_on_previous_text=not cantada,
                                           word_timestamps=bool(o.get("palabras")),
                                           **({"no_speech_threshold": None} if cantada else {}))
            emitir("idioma", id=o["id"], idioma=info.language, prob=round(info.language_probability, 3), dur=info.duration)

            def enviar(segs, v=None):
                for s in segs:
                    if parada_pedida():
                        raise Parada
                    emitir("segmento", id=o["id"], inicio=round(s.start + desfase, 2), fin=round(s.end + desfase, 2),
                           palabras=[[round(p.start + desfase, 2), round(p.end + desfase, 2), p.word.strip()] for p in (s.words or [])],
                           texto=s.text.strip(), v=v or round(min(1.0, s.end / max(info.duration, 0.01)), 3),
                           dudoso=cantada and s.avg_logprob < -0.65 or letras.es_dudoso(s.avg_logprob, s.no_speech_prob, s.compression_ratio))
            tramos = []
            for s in segs:
                if parada_pedida():
                    raise Parada
                hasta = s.end + desfase
                if s.text.strip() and not (cantada and letras.es_relleno(s.text, s.avg_logprob)):
                    tramos.append((s.start, s.end))
                    enviar([s])
            huecos = letras.huecos(tramos, info.duration) if cantada and not o.get("borrar") else []   # no en el borrador en vivo
            if huecos:   # se vuelve a escuchar solo lo que quedó sin letra: cada hueco empieza su propia ventana
                segs, _ = reconocedor().transcribe(audio, language=info.language, beam_size=HAZ, temperature=TEMPERATURAS,
                                                   vad_filter=False, condition_on_previous_text=False, no_speech_threshold=None,
                                                   word_timestamps=bool(o.get("palabras")), clip_timestamps=[t for h in huecos for t in h])
                segs = [s for s in segs if s.text.strip() and not letras.es_relleno(s.text, s.avg_logprob)]
                enviar([s for s, vale in zip(segs, letras.sin_bucles([(s.text, s.compression_ratio) for s in segs])) if vale], v=1.0)
            limpiar()
            emitir("fin", id=o["id"])
        except Parada:   # se conserva lo reconocido; «hasta» es dónde se quedó
            limpiar()
            emitir("fin", id=o["id"], parada=True, hasta=round(hasta, 2))
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
