"""Voz a texto: catálogo de modelos Whisper, descarga a models/ y texto editable por segmentos."""
import re
import shutil

from . import descargas, exportar, rutas

CARPETA = rutas.MODELOS / "whisper"

# nombre: (repositorio, tamaño en disco MB, RAM aprox. MB, descripción)
MODELOS = {
    "tiny": ("Systran/faster-whisper-tiny", 75, 400, "Mínimo: muy rápido, comete bastantes errores"),
    "base": ("Systran/faster-whisper-base", 145, 500, "Ligero: rápido, válido para voz clara"),
    "small": ("Systran/faster-whisper-small", 485, 1000, "Equilibrado: recomendado para español"),
    "medium": ("Systran/faster-whisper-medium", 1530, 2600, "Preciso: lento en CPU (≈ tiempo real)"),
    "large-v3": ("Systran/faster-whisper-large-v3", 3090, 4700, "Máxima precisión: muy lento en CPU"),
}

IDIOMAS = {"": "Detección automática", "es": "Español", "en": "Inglés", "ca": "Catalán", "gl": "Gallego",
           "eu": "Euskera", "pt": "Portugués", "fr": "Francés", "it": "Italiano", "de": "Alemán",
           "nl": "Neerlandés", "pl": "Polaco", "ru": "Ruso", "ar": "Árabe", "zh": "Chino", "ja": "Japonés",
           "ko": "Coreano", "tr": "Turco", "ro": "Rumano", "sv": "Sueco", "uk": "Ucraniano", "el": "Griego"}

MEDIOS = "*.wav *.mp3 *.flac *.ogg *.opus *.m4a *.aac *.wma *.mp4 *.mkv *.mov *.webm *.avi"


def carpeta_modelo(nombre):
    return CARPETA / nombre


def instalado(nombre):
    return (carpeta_modelo(nombre) / ".completo").is_file()


def borrar_modelo(nombre):
    shutil.rmtree(carpeta_modelo(nombre), ignore_errors=True)


def descargar_modelo(nombre, progreso=None, cancelar=None):
    """Baja el modelo a models/whisper/<nombre>. `progreso(fracción 0..1)`."""
    repo = MODELOS[nombre][0]
    archivos = [a for a in descargas.leer_json(f"https://huggingface.co/api/models/{repo}/tree/main")
                if a["type"] == "file" and not a["path"].startswith(".") and a["path"] != "README.md"]
    total, hecho = sum(a["size"] for a in archivos) or 1, 0
    destino = carpeta_modelo(nombre)
    (destino / ".completo").unlink(missing_ok=True)
    for a in archivos:
        descargas.descargar(f"https://huggingface.co/{repo}/resolve/main/{a['path']}", destino / a["path"],
                            (lambda h, _t, base=hecho: progreso((base + h) / total)) if progreso else None,
                            cancelar, (a.get("lfs") or {}).get("oid"))
        hecho += a["size"]
    (destino / ".completo").write_text(repo)


# -- texto editable: una línea por segmento, «[mm:ss.cc] texto» si hay marcas ----
_MARCA = re.compile(r"^\[(?:(\d+):)?(\d{1,2}):(\d{1,2}(?:\.\d+)?)\]\s?")


def marca(t):
    return f"[{int(t // 60):02d}:{t % 60:05.2f}] "


def a_texto(segs, marcas):
    return "\n".join((marca(s["inicio"]) if marcas and s.get("inicio") is not None else "")
                     + (exportar.DUDA if s.get("dudoso") else "") + s["texto"] for s in segs)


def de_texto(texto, previos=()):
    """Reconstruye los segmentos tras editar. Cada línea conserva el tiempo que lleva
    escrito; si no lleva marca, hereda el del segmento que ocupaba esa posición."""
    segs = []
    lineas = [l for l in texto.splitlines() if l.strip()]
    mismos = len(lineas) == len(previos)
    for i, linea in enumerate(lineas):
        m = _MARCA.match(linea)
        cuerpo = linea[m.end():] if m else linea
        dudoso = cuerpo.lstrip().startswith(exportar.DUDA.strip())
        s = {"inicio": None, "fin": None, "texto": cuerpo.strip().removeprefix(exportar.DUDA.strip()).strip(), "dudoso": dudoso}
        if m:
            s["inicio"] = int(m.group(1) or 0) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
        if mismos:
            p = previos[i]
            if s["inicio"] is None:
                s["inicio"] = p.get("inicio")
            if p.get("fin") is not None and s["inicio"] is not None and abs(s["inicio"] - (p.get("inicio") or 0)) < 0.02:
                s["fin"] = p["fin"]
        segs.append(s)
    return exportar.completar_tiempos(segs)


def es_dudoso(logprob, sin_voz, compresion):
    """Criterio para pedir revisión humana de un segmento."""
    return logprob < -0.8 or sin_voz > 0.5 or compresion > 2.4
