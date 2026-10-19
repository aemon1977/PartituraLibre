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


SALTO_S = 0.7         # una palabra puede tomar notas libres que empiecen hasta esto después de su final
DURACION_MAX_S = 2.0  # con el canto el reconocedor adelanta el principio de las palabras: se recorta a esto


def unidades(texto):
    """Sílabas de un texto, en orden: «no beberé» -> ['no', 'be-', 'be-', 'ré']. Una palabra que ya trae
    guiones («be-be-ré») se divide por ahí: así quien escribe la letra manda sobre el silabeo automático."""
    from .silabas import silabas
    salida = []
    for palabra in texto.split():
        partes = [p for p in palabra.split("-") if p] if "-" in palabra.strip("-") else silabas(palabra)
        salida += [p + ("-" if n < len(partes) - 1 else "") for n, p in enumerate(partes)]
    return salida


def juntar(unidades_):
    """Lo contrario: ['be-', 'ré', 'sí'] -> «beré sí»."""
    return "".join(u[:-1] if u.endswith("-") else u + " " for u in unidades_).strip()


def letra_cantada(notas, palabras):
    """Letra de una canción sobre su melodía: (notas, letra) con UNA SÍLABA por nota.
    LA PARTITURA MANDA: las notas no se dividen, ni se crean, ni se quitan; la letra se adapta a ellas.
    - Las notas de una palabra son las libres que suenan mientras se canta (con el canto el reconocedor
      adelanta el principio de las palabras: se considera como mucho DURACION_MAX_S).
    - Si faltan notas se toman las libres que siguen, antes de la palabra siguiente; si aún faltan, las
      sílabas que sobran se escriben juntas en la última nota de la palabra.
    - Notas de sobra en una palabra quedan sin texto (melisma). La letra nunca retrocede.
    - Una palabra sin ninguna nota cerca se añade a la sílaba anterior, para no perder texto."""
    notas = sorted(list(n) for n in notas)
    letra = [""] * len(notas)
    siguiente_libre = 0
    palabras = sorted(p for p in palabras if p[2].strip())
    for k, (ini, fin, texto) in enumerate(palabras):
        a = max(ini, fin - DURACION_MAX_S)
        b = max(fin, a + 0.05)
        proxima = palabras[k + 1][0] if k + 1 < len(palabras) else float("inf")
        libres = range(siguiente_libre, len(notas))
        suena = lambda i: a - 0.05 <= notas[i][0] < b or min(notas[i][1], b) - max(notas[i][0], a) >= 0.5 * (notas[i][1] - notas[i][0])
        suyas = [i for i in libres if suena(i)]
        ocupada = siguiente_libre - 1                   # la nota con la última sílaba puesta
        if not suyas and ocupada >= 0 and notas[ocupada][0] - 0.05 <= a < notas[ocupada][1]:
            # se canta mientras sigue sonando esa nota (dos palabras sobre una nota larga): la comparten
            letra[ocupada] = letra[ocupada] + juntar(unidades(texto)) if letra[ocupada].endswith("-") \
                else juntar([letra[ocupada], *unidades(texto)])
            continue
        if not suyas:
            cerca = [i for i in libres if a - LEJOS_S <= notas[i][0] <= b + LEJOS_S]
            suyas = [min(cerca, key=lambda i: abs(notas[i][0] - a))] if cerca else []
        silabas_ = unidades(texto)
        if not suyas:                                   # sin nota: junto a la sílaba anterior
            previa = max((i for i in range(siguiente_libre) if letra[i]), default=None)
            if previa is not None:
                letra[previa] = juntar([letra[previa], *silabas_]) if not letra[previa].endswith("-") else letra[previa] + juntar(silabas_)
            continue
        j = suyas[-1] + 1
        while len(suyas) < len(silabas_) and j < len(notas) and notas[j][0] < proxima - 0.1 and notas[j][0] - b <= SALTO_S:
            suyas.append(j)
            j += 1
        for n, i in enumerate(suyas):
            letra[i] = silabas_[n] if n < len(silabas_) else ""
        if len(silabas_) > len(suyas):                  # no caben: lo que sobra, junto en la última
            letra[suyas[-1]] = "".join(u[:-1] if u.endswith("-") else u + " " for u in silabas_[len(suyas) - 1:-1]) + silabas_[-1]
        siguiente_libre = suyas[-1] + 1
    return notas, letra


def repartir_texto(texto, n_notas, desde=0):
    """Letra escrita a mano: una sílaba por nota a partir de la nota `desde`. Devuelve (sílabas por nota,
    cuántas sobraron); las que no caben se escriben juntas en la última nota."""
    silabas_ = unidades(texto)
    huecos = max(0, n_notas - desde)
    if not huecos:
        return [], len(silabas_)
    asignadas = silabas_[:huecos]
    sobran = len(silabas_) - huecos
    if sobran > 0:
        asignadas[-1] = "".join(u[:-1] if u.endswith("-") else u + " " for u in silabas_[huecos - 1:-1]) + silabas_[-1]
    return asignadas, max(0, sobran)


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
    "sol8": ("Clave de Sol 8ª baja (voz)", 23, 2),  # suena una octava más grave: la de tenores y voces graves
    "fa": ("Clave de Fa (4.ª línea)", 18, 6),  # línea inferior Sol2; el Fa3 está en la 4.ª línea
    "do3": ("Clave de Do (3.ª línea)", 24, 4), # línea inferior Fa3; el Do4 está en la 3.ª línea
    "do4": ("Clave de Do (4.ª línea)", 22, 6), # línea inferior Re3; el Do4 está en la 4.ª línea
}
_LETRA = [0, 0, 1, 1, 2, 3, 3, 4, 4, 5, 5, 6]          # Do Do♯ Re Re♯ Mi Fa Fa♯ Sol Sol♯ La La♯ Si
_SOSTENIDO = [False, True, False, True, False, False, True, False, True, False, True, False]


def clave_adecuada(notas, voz=False):
    """Clave (Sol, Fa, Do en 3.ª o Do en 4.ª) que deja las notas dentro del pentagrama con menos líneas
    adicionales. A igualdad se prefiere la más habitual: Sol, luego Fa, luego las de Do, que solo ganan
    cuando ahorran claramente (instrumentos de registro medio, como la viola).
    Con `voz` (una canción) se escribe como en los cancioneros: Sol, o Sol 8ª baja si la voz es grave."""
    if not notas:
        return "sol"
    def coste(clave):
        total = 0.0
        for ini, fin, tono, _v in notas:
            pos = posicion(tono, clave)[0]
            lineas = (-pos) // 2 if pos <= -2 else (pos - 8) // 2 if pos >= 10 else 0   # líneas adicionales
            total += (max(0, lineas - 1) + 0.2 * min(lineas, 1)) * max(fin - ini, 0.05)   # una sola es normal
        return total
    preferencia = {"sol": 0.0, "sol8": 0.02, "fa": 0.02, "do3": 0.15, "do4": 0.2}   # peso de la costumbre
    duracion = sum(max(f - i, 0.05) for i, f, _t, _v in notas)
    return min(("sol", "sol8") if voz else ("sol", "fa", "do3", "do4"), key=lambda c: coste(c) / duracion + preferencia[c])


def posicion(midi, clave, armadura=0):
    """(posición en el pentagrama, lleva sostenido). 0 es la línea inferior, 1 el primer espacio,
    8 la línea superior; valores negativos o mayores de 8 necesitan líneas adicionales.
    Con `armadura` (quintas: +n sostenidos, −n bemoles) la nota se deletrea según la tonalidad."""
    letra, alteracion, octava = deletrear(midi, armadura)
    return (octava + 1) * 7 + letra - CLAVES[clave][1] - 7, alteracion == 1


# -- tonalidad -----------------------------------------------------------------
_BASE = [0, 2, 4, 5, 7, 9, 11]                 # Do Re Mi Fa Sol La Si
_LETRAS = ["Do", "Re", "Mi", "Fa", "Sol", "La", "Si"]
ORDEN_SOSTENIDOS = [3, 0, 4, 1, 5, 2, 6]       # Fa Do Sol Re La Mi Si
ORDEN_BEMOLES = [6, 2, 5, 1, 4, 0, 3]          # Si Mi La Re Sol Do Fa
MAYORES = {-6: "Sol♭", -5: "Re♭", -4: "La♭", -3: "Mi♭", -2: "Si♭", -1: "Fa", 0: "Do", 1: "Sol", 2: "Re", 3: "La", 4: "Mi", 5: "Si", 6: "Fa♯"}
MENORES = {-6: "Mi♭", -5: "Si♭", -4: "Fa", -3: "Do", -2: "Sol", -1: "Re", 0: "La", 1: "Mi", 2: "Si", 3: "Fa♯", 4: "Do♯", 5: "Sol♯", 6: "Re♯"}
# Perfiles de Krumhansl-Kessler: cuánto «pertenece» cada grado a una tonalidad mayor y a una menor
_PERFIL_MAYOR = [6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88]
_PERFIL_MENOR = [6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17]


def nombre_armadura(armadura):
    """«Re mayor / Si menor» para una armadura dada a mano."""
    return f"{MAYORES[armadura]} mayor / {MENORES[armadura]} menor"


def alteraciones(armadura):
    """{letra: +1 o −1} de una armadura (en quintas)."""
    orden = ORDEN_SOSTENIDOS if armadura > 0 else ORDEN_BEMOLES
    return {l: (1 if armadura > 0 else -1) for l in orden[:abs(armadura)]}


def deletrear(midi, armadura=0):
    """(letra 0-6 desde Do, alteración −1/0/+1, octava) de una nota según la tonalidad: se prefiere la
    forma que pide la armadura, luego la natural, y para las notas ajenas a la tonalidad, sostenidos en
    tonalidades con sostenidos (o Do) y bemoles en las de bemoles."""
    pc, arm = midi % 12, alteraciones(armadura)
    opciones = [(l, alt) for l in range(7) for alt in (-1, 0, 1) if (_BASE[l] + alt) % 12 == pc]
    letra, alt = min(opciones, key=lambda o: (arm.get(o[0], 0) != o[1], o[1] != 0, o[1] != (-1 if armadura < 0 else 1)))
    return letra, alt, (midi - alt) // 12 - 1


def tonalidad(notas):
    """(armadura en quintas, nombre) más probable para esas notas, pesando cada nota por su duración."""
    peso = [0.0] * 12
    for ini, fin, tono, _v in notas:
        peso[tono % 12] += max(fin - ini, 0.05)
    if not any(peso):
        return 0, "Do mayor"

    def correlacion(perfil, tonica):
        x = [perfil[(i - tonica) % 12] for i in range(12)]
        mx, mp = sum(x) / 12, sum(peso) / 12
        num = sum((a - mx) * (b - mp) for a, b in zip(x, peso))
        den = (sum((a - mx) ** 2 for a in x) * sum((b - mp) ** 2 for b in peso)) ** 0.5
        return num / den if den else 0
    mejor = max([(correlacion(_PERFIL_MAYOR, t), t, True) for t in range(12)] + [(correlacion(_PERFIL_MENOR, t), t, False) for t in range(12)])
    _, tonica, mayor = mejor
    relativa = tonica if mayor else (tonica + 3) % 12              # la menor comparte armadura con su relativa mayor
    armadura = min(range(-6, 7), key=lambda q: ((q * 7) % 12 != relativa, abs(q)))
    return armadura, (MAYORES[armadura] + " mayor") if mayor else (MENORES[armadura] + " menor")


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


def solfeo(midi, armadura=0):
    letra, alt, _ = deletrear(midi, armadura)
    return _LETRAS[letra] + {1: "♯", -1: "♭", 0: ""}[alt]


def descripcion(nota, bpm, letra=""):
    """Todo lo que es una nota, en una línea: «Sol4 · negra con puntillo · empieza en 1,20 s · dura 0,75 s · "sol"»."""
    ini, fin, tono, _v = nota
    fig, puntillo = figura_y_puntillo(fin - ini, bpm)
    partes = [nombre_nota(tono), fig + (" con puntillo" if puntillo else ""),
              f"empieza en {ini:.2f} s".replace(".", ","), f"dura {fin - ini:.2f} s".replace(".", ",")]
    return " · ".join(partes + ([f"«{letra}»"] if letra else []))


def nombre_nota(midi, armadura=0):
    return f"{solfeo(midi, armadura)}{deletrear(midi, armadura)[2]}"


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
