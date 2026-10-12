"""División en sílabas del español, para repartir la letra de una canción entre las notas.

Reglas ortográficas habituales (RAE): una consonante entre vocales va con la vocal siguiente; dos se
reparten salvo los grupos que no se separan (pr, bl, tr, ch, ll, rr…); de tres, las dos últimas van
juntas si forman grupo; dos vocales fuertes forman hiato y una débil átona con otra forma diptongo.
Solo stdlib.
"""
import re

FUERTES = set("aeoáéóíú")            # í y ú con tilde rompen el diptongo
DEBILES = set("iuü")
VOCALES = FUERTES | DEBILES
INSEPARABLES = {"pr", "br", "tr", "dr", "cr", "gr", "fr", "kr", "pl", "bl", "cl", "gl", "fl", "kl", "ch", "ll", "rr", "tl"}


def _vocal(palabra, i):
    """¿Es vocal la letra i? (la y solo al final de palabra; la u de qu/gue/gui es muda: cuenta como consonante)."""
    c = palabra[i]
    if c == "y":
        return i == len(palabra) - 1 and i > 0
    if c == "u" and i > 0 and palabra[i - 1] in "qg" and i + 1 < len(palabra) and palabra[i + 1] in "eéií":
        return False
    return c in VOCALES


def _hiato(a, b):
    return (a in FUERTES and b in FUERTES) or (a in "íú" and b in VOCALES) or (b in "íú" and a in VOCALES)


def silabas(palabra):
    """'beberé' -> ['be', 'be', 'ré']. Conserva mayúsculas y signos pegados (¿Cuántas -> ['¿Cuán', 'tas'])."""
    m = re.match(r"^([^\wáéíóúüñ]*)(.*?)([^\wáéíóúüñ]*)$", palabra, re.IGNORECASE)
    antes, nucleo, despues = m.groups()
    p = nucleo.lower()
    if not p or not any(_vocal(p, i) for i in range(len(p))):
        return [palabra]
    # núcleos vocálicos: tramos de vocales, partidos por los hiatos
    nucleos, i = [], 0
    while i < len(p):
        if _vocal(p, i):
            j = i
            while j + 1 < len(p) and _vocal(p, j + 1) and not _hiato(p[j], p[j + 1]):
                j += 1
            nucleos.append((i, j))
            i = j + 1
        else:
            i += 1
    cortes = []
    for (_, fin), (ini, _) in zip(nucleos, nucleos[1:]):
        unidades = []                     # consonantes entre dos núcleos («gu»/«qu» con u muda cuentan como una)
        for c in p[fin + 1:ini]:
            if c == "u" and unidades and unidades[-1] in "qg":
                unidades[-1] += c
            else:
                unidades.append(c)
        n, junta = len(unidades), lambda u: "".join(x[0] for x in u)
        if n <= 1:
            k = 0
        elif n == 2:
            k = 0 if junta(unidades) in INSEPARABLES else 1
        elif n == 3:
            k = 1 if junta(unidades[1:]) in INSEPARABLES else 2
        else:
            k = 2
        cortes.append(fin + 1 + sum(len(u) for u in unidades[:k]))
    partes = [nucleo[a:b] for a, b in zip([0] + cortes, cortes + [len(nucleo)])]
    partes[0], partes[-1] = antes + partes[0], partes[-1] + despues
    return partes


if __name__ == "__main__":
    import sys
    print(" ".join("-".join(silabas(w)) for w in sys.argv[1:]))
