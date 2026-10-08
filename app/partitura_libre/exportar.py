"""Formatos de salida de letras (TXT, SRT, VTT, LRC) y su lectura de vuelta.

Un segmento es {'inicio': s, 'fin': s, 'texto': str, 'dudoso': bool}.
"""
import re

DUDA = "⚠ "


def _hms(t, sep):
    t = max(0.0, t)
    ms = int(round(t * 1000))
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d}{sep}{ms % 1000:03d}"


def _texto(s):
    return (DUDA if s.get("dudoso") else "") + s["texto"]


def txt(segs):
    return "\n".join(_texto(s) for s in segs) + "\n"


def srt(segs):
    return "\n".join(f"{i}\n{_hms(s['inicio'], ',')} --> {_hms(s['fin'], ',')}\n{_texto(s)}\n"
                     for i, s in enumerate(segs, 1))


def vtt(segs):
    return "WEBVTT\n\n" + "\n".join(f"{_hms(s['inicio'], '.')} --> {_hms(s['fin'], '.')}\n{_texto(s)}\n" for s in segs)


def lrc(segs):
    return "\n".join(f"[{int(s['inicio'] // 60):02d}:{s['inicio'] % 60:05.2f}]{_texto(s)}" for s in segs) + "\n"


FORMATOS = {".txt": txt, ".srt": srt, ".vtt": vtt, ".lrc": lrc}

_T = r"(?:(\d+):)?(\d{1,2}):(\d{1,2}(?:[.,]\d+)?)"
_FLECHA = re.compile(_T + r"\s*-->\s*" + _T)
_LRC = re.compile(r"^\[" + _T + r"\]\s*(.*)$")


def _seg(h, m, s):
    return int(h or 0) * 3600 + int(m) * 60 + float(s.replace(",", "."))


def _nuevo(inicio, fin, texto):
    dudoso = texto.startswith(DUDA.strip())
    return {"inicio": inicio, "fin": fin, "texto": texto.removeprefix(DUDA.strip()).strip(), "dudoso": dudoso}


def leer(contenido):
    """Lee TXT, SRT, VTT o LRC (lo detecta por el contenido) y devuelve segmentos.
    Las líneas sin tiempo quedan con inicio/fin en None."""
    segs, actual = [], None
    for linea in contenido.replace("﻿", "").splitlines():
        linea = linea.strip()
        m = _FLECHA.search(linea)
        if m:
            actual = _nuevo(_seg(*m.groups()[:3]), _seg(*m.groups()[3:]), "")
            segs.append(actual)
            continue
        m = _LRC.match(linea)
        if m:
            segs.append(_nuevo(_seg(*m.groups()[:3]), None, m.group(4)))
            actual = None
        elif not linea:
            actual = None
        elif actual is not None:
            unido = _nuevo(0, 0, (actual["texto"] + " " + linea).strip() if actual["texto"] else linea)
            actual["texto"], actual["dudoso"] = unido["texto"], actual["dudoso"] or unido["dudoso"]
        elif linea != "WEBVTT" and not (linea.isdigit() and "-->" in contenido):  # índice de SRT
            segs.append(_nuevo(None, None, linea))
    return completar_tiempos([s for s in segs if s["texto"]])


def completar_tiempos(segs):
    """Rellena los 'fin' que faltan (LRC) con el inicio del siguiente."""
    for i, s in enumerate(segs):
        if s["inicio"] is not None and s["fin"] is None:
            sig = next((x["inicio"] for x in segs[i + 1:] if x["inicio"] is not None), None)
            s["fin"] = sig if sig is not None and sig > s["inicio"] else s["inicio"] + 4.0
    return segs


def con_tiempos(segs):
    return [s for s in segs if s.get("inicio") is not None]
