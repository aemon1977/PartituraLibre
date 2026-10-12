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


MIN_SILABA_S = 0.12   # una nota cantada solo se divide si cada trozo dura al menos esto
SALTO_S = 0.7         # una palabra puede tomar notas libres que empiecen hasta esto después de su final
DURACION_MAX_S = 2.0  # con el canto el reconocedor adelanta el principio de las palabras: se recorta a esto
RESTO_S = 1.5         # notas sin letra a más de esto de toda palabra cantada: restos de instrumentos


def letra_cantada(notas, palabras, tono_en=None):
    """Letra de una canción sobre su melodía: (notas, letra) con UNA SÍLABA por nota, como en una partitura.
    Una sílaba que sigue en la nota siguiente acaba en guion («be-», «be-», «ré»).
    - Las notas de una palabra son las que suenan mientras se canta (entre su principio y su final).
      Con el canto el reconocedor adelanta a veces el principio: se considera como mucho DURACION_MAX_S.
    - Si una palabra empieza dentro de una nota que ya tiene sílaba, la nota se parte ahí (sílabas
      repetidas a la misma altura).
    - Si faltan notas: se toman las libres que siguen, antes de la palabra siguiente; si aún faltan, se
      dividen las notas de la palabra cuando caben todas las sílabas; si no, lo que sobra va junto en la última.
    - Notas de sobra en una palabra quedan sin texto (melisma).
    - Las notas lejos de toda letra cantada (introducciones, solos) son restos de instrumentos y se quitan.
    - `tono_en(a, b)`, si se da, devuelve la nota que canta la voz entre a y b (o None): con él, las sílabas
      que no tienen nota detectada reciben una nueva en vez de amontonarse o perderse."""
    from .silabas import silabas
    piezas = [[n[0], n[1], n[2], n[3], None] for n in sorted(notas)]   # texto None = sin asignar
    palabras = sorted(p for p in palabras if p[2].strip())
    if not piezas or not palabras:
        return [list(n) for n in sorted(notas)], [""] * len(notas)
    tramos, ultima = [], None                                # ultima: pieza con la sílaba más reciente
    for k, (ini, fin, texto) in enumerate(palabras):
        a = max(ini, fin - DURACION_MAX_S)
        b = max(fin, a + 0.05)
        tramos.append((a, b))
        siguiente = palabras[k + 1][0] if k + 1 < len(palabras) else float("inf")
        if ultima is not None and ultima[0] + MIN_SILABA_S <= a <= ultima[1] - MIN_SILABA_S:
            j = next(i for i, p in enumerate(piezas) if p is ultima)   # empieza dentro de la última nota cantada: se parte ahí
            piezas.insert(j + 1, [a, ultima[1], ultima[2], ultima[3], None])
            ultima[1] = a
        desde = 0 if ultima is None else next(i for i, p in enumerate(piezas) if p is ultima) + 1
        libres = [p for p in piezas[desde:] if p[4] is None]          # la letra siempre avanza: nunca notas anteriores
        suyas = [p for p in libres if a - 0.05 <= p[0] < b or min(p[1], b) - max(p[0], a) >= 0.5 * (p[1] - p[0])]
        unidades = [s + ("-" if n < len(ps) - 1 else "") for ps in [silabas(texto.strip())] for n, s in enumerate(ps)]
        if tono_en:                                          # sílabas sin nota detectada: notas nuevas con la altura cantada
            hueco = max(a, suyas[-1][1] if suyas else (ultima[1] if ultima is not None else a))
            faltan = len(unidades) - len(suyas)
            if faltan > 0 and b - hueco >= MIN_SILABA_S:
                n = min(faltan, int((b - hueco) / MIN_SILABA_S))
                paso = (b - hueco) / n
                for m in range(n):
                    tono = tono_en(hueco + m * paso, hueco + (m + 1) * paso)
                    if tono is not None:
                        nueva = [hueco + m * paso, hueco + (m + 1) * paso, tono, 0.5, None]
                        pos = next((i for i, p in enumerate(piezas) if p[0] > nueva[0]), len(piezas))
                        piezas.insert(pos, nueva)
                        suyas.append(nueva)
        if not suyas:                                        # ninguna suena a la vez: la libre más cercana
            cerca = [p for p in libres if a - LEJOS_S <= p[0] <= b + LEJOS_S]
            suyas = [min(cerca, key=lambda p: abs(p[0] - a))] if cerca else []
        if not suyas:
            continue                                         # hablado o sin melodía detectada
        j = piezas.index(suyas[-1]) + 1
        while len(suyas) < len(unidades) and j < len(piezas) and piezas[j][4] is None \
                and piezas[j][0] < siguiente - 0.1 and piezas[j][0] - b <= SALTO_S:
            suyas.append(piezas[j])
            j += 1
        if len(suyas) < len(unidades) and sum(int((p[1] - p[0]) / MIN_SILABA_S) for p in suyas) >= len(unidades):
            while len(suyas) < len(unidades):                # divide la más larga hasta que quepan todas
                o = max(suyas, key=lambda p: p[1] - p[0])
                medio = (o[0] + o[1]) / 2
                nueva = [medio, o[1], o[2], o[3], None]
                o[1] = medio
                piezas.insert(next(i for i, p in enumerate(piezas) if p is o) + 1, nueva)
                suyas.insert(suyas.index(o) + 1, nueva)
        for n, o in enumerate(suyas):
            o[4] = unidades[n] if n < len(unidades) else ""
        ultima = suyas[-1]
        if len(unidades) > len(suyas):                       # no caben: lo que sobra, junto en la última
            resto = unidades[len(suyas) - 1:]
            suyas[-1][4] = "".join(u[:-1] if u.endswith("-") else u + " " for u in resto[:-1]) + resto[-1]
    piezas = [p for p in piezas if p[4] is not None or any(t0 - RESTO_S <= p[0] <= t1 + RESTO_S for t0, t1 in tramos)]
    return [[round(p[0], 4), round(p[1], 4), p[2], p[3]] for p in piezas], [p[4] or "" for p in piezas]


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
