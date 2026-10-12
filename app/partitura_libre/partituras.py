"""Utilidades de notas para la revisión de partituras (sin dependencias pesadas)."""
import json
from pathlib import Path

NOMBRES = ["Do", "Do♯", "Re", "Re♯", "Mi", "Fa", "Fa♯", "Sol", "Sol♯", "La", "La♯", "Si"]
AUDIO = "*.wav *.mp3 *.flac *.ogg"
PARTITURAS = "*.musicxml *.mxl *.xml *.mid *.midi"
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


CORTE_S = 0.09   # una nota cantada más corta que esto es un resto de la detección, no una nota
LEGATO_S = 0.2   # hueco entre dos notas cantadas por debajo del cual se unen (no se escribe silencio)


def melodia(notas):
    """Reduce lo detectado en una voz aislada a UNA línea melódica, como se canta: sin notas a la vez.
    - Cuando dos notas se pisan, gana la más intensa (la otra suele ser un armónico o un eco).
    - Si la que gana empieza después, la anterior se acorta hasta ese punto en vez de borrarse.
    - Los trozos de la misma nota separados por un respiro mínimo (vibrato, consonantes) se unen.
    - Se descartan los restos más cortos que CORTE_S, y los huecos menores que LEGATO_S se cierran."""
    linea = []
    for n in sorted((list(n) for n in notas), key=lambda n: (n[0], -n[3])):
        if linea and n[0] < linea[-1][1] - 1e-6:                  # se pisa con la anterior
            p = linea[-1]
            if n[3] <= p[3]:                                       # la anterior es más fuerte: esta sobra
                continue
            if n[0] - p[0] >= CORTE_S:                             # la anterior se queda con su principio
                p[1] = n[0]
            else:
                linea.pop()
        if linea and linea[-1][2] == n[2] and n[0] - linea[-1][1] <= UNION_S + 0.04:
            linea[-1][1], linea[-1][3] = max(linea[-1][1], n[1]), max(linea[-1][3], n[3])
            continue
        linea.append(n)
    linea = [n for n in linea if n[1] - n[0] >= CORTE_S]
    for a, b in zip(linea, linea[1:]):   # un respiro corto al cantar no es un silencio escrito: legato
        if 0 < b[0] - a[1] <= LEGATO_S:
            a[1] = b[0]
    return linea


SILABA_S = 0.25  # una nota solo se divide si cada trozo dura al menos esto
SALTO_S = 0.7   # una palabra que no cabe en su nota puede pasar a la siguiente libre si empieza a menos de esto


def letra_cantada(notas, palabras):
    """Letra de una canción sobre su melodía: (notas, letra) con UNA palabra por nota.
    El reconocedor da tiempos aproximados con el canto, así que varias palabras suelen caer en la misma
    nota: cada una ocupa la nota que suena cuando se canta. Si ya está cogida y es larga, se divide (sílabas
    seguidas a la misma altura); si es corta, la palabra pasa a la siguiente nota libre cercana."""
    notas = sorted(list(n) for n in notas)
    if not notas:
        return [], []
    grupos = [[] for _ in notas]                    # palabras de cada nota, en orden
    for ini, fin, texto in sorted(palabras):
        if not texto.strip():
            continue
        t = max(ini, fin - 0.5)                     # con el canto, el inicio que da el reconocedor suele adelantarse
        dentro = [i for i, n in enumerate(notas) if n[0] - UNION_S <= t < n[1] - 0.02]
        i = dentro[-1] if dentro else min(range(len(notas)), key=lambda i: min(abs(t - notas[i][0]), abs(t - notas[i][1])))
        if not dentro and min(abs(t - notas[i][0]), abs(t - notas[i][1])) > LEJOS_S:
            continue                                # lejos de toda nota: hablado, no cantado
        j = i
        cabe = (notas[i][1] - notas[i][0]) / (len(grupos[i]) + 1) >= SILABA_S   # nota larga: se puede dividir
        while grupos[j] and not cabe and j + 1 < len(notas) and notas[j + 1][0] - t <= SALTO_S:
            j += 1                                  # nota corta y ya cogida: a la siguiente libre
        grupos[j if not grupos[j] else i].append(texto.strip())
    salida, letra = [], []
    for (ini, fin, tono, v), g in zip(notas, grupos):
        k = max(1, len(g))
        paso = (fin - ini) / k
        for n in range(k):
            salida.append([round(ini + n * paso, 4), round(ini + (n + 1) * paso, 4), tono, v])
            letra.append(g[n] if n < len(g) else "")
    return salida, letra


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


def figura_y_puntillo(segundos, bpm):
    """(figura, lleva puntillo) más parecidos a esa duración. El puntillo (figura y media) solo se
    usa cuando la duración coincide exactamente (una nota escrita a mano); las duraciones detectadas
    en un audio nunca son tan exactas y se quedan en la figura simple más cercana."""
    negras = segundos * bpm / 60
    for fig, valor in (("blanca", 3), ("negra", 1.5), ("corchea", 0.75), ("semicorchea", 0.375)):
        if abs(negras - valor) <= 0.01 * valor:
            return fig, True
    return ("redonda" if negras >= 2.83 else "blanca" if negras >= 1.41 else "negra" if negras >= 0.71
            else "corchea" if negras >= 0.354 else "semicorchea"), False


def figura(segundos, bpm):
    """Figura aproximada según la duración: 'redonda', 'blanca', 'negra', 'corchea' o 'semicorchea'."""
    return figura_y_puntillo(segundos, bpm)[0]


NEGRAS = {"redonda": 4, "blanca": 2, "negra": 1, "corchea": 0.5, "semicorchea": 0.25}


def segundos_de(fig, bpm, puntillo=False):
    """Duración en segundos de una figura a ese tempo."""
    return NEGRAS[fig] * (1.5 if puntillo else 1) * 60 / bpm


LETRAS_NOTA = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}   # teclas de nota, como en MuseScore
TECLAS_FIGURA = {"3": "semicorchea", "4": "corchea", "5": "negra", "6": "blanca", "7": "redonda"}


def tono_cercano(letra, referencia=67):
    """Nota de ese nombre (C, D, E, F, G, A, B) más cercana a la de referencia: así, al escribir una
    melodía con el teclado, cada nota cae en la octava natural respecto a la anterior."""
    base = LETRAS_NOTA[letra.upper()]
    return min((o * 12 + base for o in range(11) if o * 12 + base <= 127), key=lambda m: (abs(m - referencia), m))


_SEMITONO = [0, 2, 4, 5, 7, 9, 11]   # Do Re Mi Fa Sol La Si


def midi_de(pos, clave):
    """Nota natural que corresponde a una posición del pentagrama (inversa de `posicion`)."""
    grado = pos + CLAVES[clave][1]
    return max(0, min(127, (grado // 7 + 1) * 12 + _SEMITONO[grado % 7]))


def pulso(t, bpm):
    """Instante en negras, ajustado a la semicorchea."""
    return round(t * bpm / 60 * 4) / 4


def silencios(negras, maximo=3):
    """Figuras de silencio que llenan un hueco de esa duración, de mayor a menor (como mucho `maximo`)."""
    figs = []
    for fig, valor in NEGRAS.items():
        while negras >= valor - 1e-6 and len(figs) < maximo:
            figs.append(fig)
            negras -= valor
    return figs


def compas(inicio, bpm, pulsos=4):
    """Número de compás (desde 0) en el que cae un instante, con el inicio ajustado a la semicorchea."""
    return int(round(inicio * bpm / 60 * 4) / 4 // pulsos)


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


def descripcion(nota, bpm, letra=""):
    """Todo lo que es una nota, en una línea: «Sol4 · negra con puntillo · empieza en 1,20 s · dura 0,75 s · "sol"»."""
    ini, fin, tono, _v = nota
    fig, puntillo = figura_y_puntillo(fin - ini, bpm)
    partes = [nombre_nota(tono), fig + (" con puntillo" if puntillo else ""),
              f"empieza en {ini:.2f} s".replace(".", ","), f"dura {fin - ini:.2f} s".replace(".", ",")]
    return " · ".join(partes + ([f"«{letra}»"] if letra else []))


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
