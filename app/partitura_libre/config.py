"""Preferencias locales en config/ajustes.json."""
import json
import os

from . import rutas

ARCHIVO = rutas.CONFIG / "ajustes.json"
DEFECTO = {"microfono": "", "modelo": "small", "idioma": "es", "marcas": True,
           "carpeta_proyectos": "", "musescore": "", "externos": [], "clave": "", "nombres": True, "con_letra": False, "separar": True, "actualizaciones": True}


def cargar():
    try:
        return {**DEFECTO, **json.loads(ARCHIVO.read_text(encoding="utf-8"))}
    except (OSError, ValueError):
        return dict(DEFECTO)


def guardar(ajustes):
    escribir_json(ARCHIVO, ajustes)


def escribir_json(ruta, datos):
    """Escritura atómica: nunca deja un JSON a medias."""
    ruta.parent.mkdir(parents=True, exist_ok=True)
    tmp = ruta.with_name(ruta.name + ".parcial")
    tmp.write_text(json.dumps(datos, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, ruta)
