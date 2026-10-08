"""Utilidades de notas para la revisión de partituras (sin dependencias pesadas)."""
import json
from pathlib import Path

NOMBRES = ["Do", "Do♯", "Re", "Re♯", "Mi", "Fa", "Fa♯", "Sol", "Sol♯", "La", "La♯", "Si"]
AUDIO = "*.wav *.mp3 *.flac *.ogg"
PARTITURAS = "*.musicxml *.mxl *.xml *.mid *.midi *.mscz"
AVISO_BREVE = "Detección automática y aproximada: va mejor con una melodía o un instrumento solo. Revisa siempre el resultado."
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
        elif a0 > 0 and n[0] <= a0 + UNION_S and previa and previa[0] < n[0] and previa[1] >= n[0] - UNION_S:
            previa[1] = max(previa[1], n[1])                     # ya sonaba al empezar este trozo: se alarga
        elif c0 <= n[0] < c1:                                    # empieza dentro del núcleo: nota nueva
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


# Claves: nombre visible, grado diatónico de la línea inferior del pentagrama (Do0 = 0, un paso por
# nota natural) y posición de la línea a la que da nombre la clave (0 = línea inferior, 2 = segunda…).
CLAVES = {
    "sol": ("Clave de Sol", 30, 2),            # línea inferior Mi4; el Sol4 está en la 2.ª línea
    "fa": ("Clave de Fa (4.ª línea)", 18, 6),  # línea inferior Sol2; el Fa3 está en la 4.ª línea
    "do3": ("Clave de Do (3.ª línea)", 24, 4), # línea inferior Fa3; el Do4 está en la 3.ª línea
    "do4": ("Clave de Do (4.ª línea)", 22, 6), # línea inferior Re3; el Do4 está en la 4.ª línea
}
_LETRA = [0, 0, 1, 1, 2, 3, 3, 4, 4, 5, 5, 6]          # Do Do♯ Re Re♯ Mi Fa Fa♯ Sol Sol♯ La La♯ Si
_SOSTENIDO = [False, True, False, True, False, False, True, False, True, False, True, False]


def clave_adecuada(notas):
    """Clave que deja la mayoría de las notas dentro del pentagrama."""
    tonos = sorted(n[2] for n in notas)
    return "sol" if not tonos or tonos[len(tonos) // 2] >= 57 else "fa"


def posicion(midi, clave):
    """(posición en el pentagrama, lleva sostenido). 0 es la línea inferior, 1 el primer espacio,
    8 la línea superior; valores negativos o mayores de 8 necesitan líneas adicionales."""
    grado = (midi // 12 - 1) * 7 + _LETRA[midi % 12]
    return grado - CLAVES[clave][1], _SOSTENIDO[midi % 12]


def figura(segundos, bpm):
    """Figura aproximada según la duración: 'redonda', 'blanca', 'negra', 'corchea' o 'semicorchea'."""
    negras = segundos * bpm / 60  # se elige la figura más cercana (cada una dura el doble que la siguiente)
    return ("redonda" if negras >= 2.83 else "blanca" if negras >= 1.41 else "negra" if negras >= 0.71
            else "corchea" if negras >= 0.354 else "semicorchea")


def columnas(notas):
    """Agrupa las notas que suenan a la vez (acordes): [[índice, …], …] en orden de inicio."""
    cols = []
    for i in sorted(range(len(notas)), key=lambda i: (notas[i][0], notas[i][2])):
        if cols and notas[i][0] - notas[cols[-1][0]][0] <= UNION_S:
            cols[-1].append(i)
        else:
            cols.append([i])
    return cols


def solfeo(midi):
    return NOMBRES[midi % 12]


def nombre_nota(midi):
    return f"{NOMBRES[midi % 12]}{midi // 12 - 1}"


LEJOS_S = 1.0   # una palabra a más de esto de cualquier nota no se canta: se queda fuera de la partitura


def asignar_letra(notas, palabras):
    """Coloca cada palabra ([inicio, fin, texto]) en la nota que suena cuando empieza, o en la más
    cercana. Devuelve una lista paralela a `notas` con el texto de cada una ('' si no lleva).
    Si varias notas suenan a la vez, la palabra va a la más aguda (la melodía)."""
    letra = [""] * len(notas)
    for ini, _fin, texto in sorted(palabras):
        def distancia(i):
            n = notas[i]
            return 0.0 if n[0] - UNION_S <= ini <= n[1] else min(abs(ini - n[0]), abs(ini - n[1]))
        if not notas or not texto.strip():
            continue
        i = min(range(len(notas)), key=lambda i: (round(distancia(i), 3), -notas[i][2]))
        if distancia(i) <= LEJOS_S:
            letra[i] = (letra[i] + " " + texto.strip()).strip()
    return letra


def leer_notas(ruta):
    """(bpm, [[inicio, fin, tono, intensidad], …])"""
    d = json.loads(Path(ruta).read_text(encoding="utf-8"))
    return d.get("bpm", 120), d["notas"]


def leer_letra(ruta):
    """Texto bajo cada nota (lista paralela a las notas), o lista vacía si la partitura no lleva letra."""
    return json.loads(Path(ruta).read_text(encoding="utf-8")).get("letra") or []


def guardar_notas(ruta, bpm, notas, letra=()):
    letra = list(letra) + [""] * (len(notas) - len(letra))
    filas = sorted(([round(float(a), 4), round(float(b), 4), int(t), float(v)], letra[i]) for i, (a, b, t, v) in enumerate(notas))
    datos = {"bpm": bpm, "notas": [f[0] for f in filas]}
    if any(letra):
        datos["letra"] = [f[1] for f in filas]
    Path(ruta).write_text(json.dumps(datos, ensure_ascii=False), encoding="utf-8")
