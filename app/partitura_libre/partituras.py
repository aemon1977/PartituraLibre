"""Utilidades de notas para la revisión de partituras (sin dependencias pesadas)."""
import json
from pathlib import Path

NOMBRES = ["Do", "Do♯", "Re", "Re♯", "Mi", "Fa", "Fa♯", "Sol", "Sol♯", "La", "La♯", "Si"]
AUDIO = "*.wav *.mp3 *.flac *.ogg"
PARTITURAS = "*.musicxml *.mxl *.xml *.mid *.midi *.mscz"
LIMITACIONES = ("La detección es automática y aproximada: funciona mejor con una melodía o un instrumento "
                "aislado. Con varios instrumentos, acordes densos o batería aparecerán notas falsas o faltarán "
                "notas. Revisa el resultado en la tabla o en MuseScore antes de darlo por bueno.")

UNION_S = 0.06       # dos inicios más cercanos que esto son la misma nota
ARMONICOS = (12, 19, 24, 28, 31)  # semitonos sobre la fundamental de los armónicos 2.º a 6.º


def integrar(hechas, ultima, nuevas, a0, c0, c1):
    """Añade a `hechas` las notas de un trozo de audio sin duplicar ni partir ninguna.

    El trozo empieza en `a0` (con audio de contexto antes de `c0` y después de `c1`).
    Solo se aceptan notas que empiezan en el núcleo [c0, c1); las que ya sonaban antes
    sirven para alargar la nota que venía del trozo anterior. `ultima` recuerda la
    última nota aceptada de cada tono.
    """
    for n in sorted(nuevas):
        previa = ultima.get(n[2])
        if previa and abs(previa[0] - n[0]) <= UNION_S:          # la misma nota vista en dos trozos
            previa[1], previa[3] = max(previa[1], n[1]), max(previa[3], n[3])
        elif a0 > 0 and n[0] <= a0 + UNION_S:                    # ya sonaba al empezar este trozo
            if previa and previa[0] < n[0] and previa[1] >= n[0] - UNION_S:
                previa[1] = max(previa[1], n[1])
        elif c0 <= n[0] < c1:
            nota = list(n)
            hechas.append(nota)
            ultima[n[2]] = nota
    return hechas


def quitar_armonicos(notas):
    """Descarta notas «fantasma»: mucho más débiles que otra simultánea de la que son un armónico.
    Es conservador (exige casi todo el solape y menos de la mitad de intensidad)."""
    por_tono = {}
    for n in notas:
        por_tono.setdefault(n[2], []).append(n)
    def es_fantasma(g):
        dur = max(g[1] - g[0], 1e-6)
        return any(f[3] > 2 * g[3] and min(f[1], g[1]) - max(f[0], g[0]) >= 0.8 * dur
                   for d in ARMONICOS for f in por_tono.get(g[2] - d, ()))
    return [n for n in notas if not es_fantasma(n)]


def nombre_nota(midi):
    return f"{NOMBRES[midi % 12]}{midi // 12 - 1}"


def leer_notas(ruta):
    """(bpm, [[inicio, fin, tono, intensidad], …])"""
    d = json.loads(Path(ruta).read_text(encoding="utf-8"))
    return d.get("bpm", 120), d["notas"]


def guardar_notas(ruta, bpm, notas):
    notas = sorted(([round(float(a), 4), round(float(b), 4), int(t), float(v)] for a, b, t, v in notas))
    Path(ruta).write_text(json.dumps({"bpm": bpm, "notas": notas}), encoding="utf-8")
