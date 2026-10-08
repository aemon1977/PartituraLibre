"""Biblioteca de proyectos: una carpeta por toma, con su audio original y sus resultados."""
import json
import shutil
from datetime import datetime
from pathlib import Path

from . import config, rutas

FICHA = "proyecto.json"


def crear(nombre, tipo, carpeta=None):
    """tipo: 'partitura' o 'letra'. Devuelve la carpeta nueva del proyecto."""
    base = Path(carpeta) if carpeta else rutas.PROYECTOS
    d = rutas.carpeta_unica(base, nombre or f"{tipo} {datetime.now():%Y-%m-%d %H.%M}")
    guardar(d, {"nombre": d.name, "tipo": tipo, "creado": datetime.now().isoformat(timespec="seconds"),
                "audio": "", "origen": "", "estado": "nuevo", "incompleta": False, "avisos": [], "resultados": []})
    if not rutas.dentro_de(d, rutas.PROYECTOS):
        a = config.cargar()
        a["externos"] = sorted({*a["externos"], str(d)})
        config.guardar(a)
    return d


def leer(carpeta):
    return json.loads((Path(carpeta) / FICHA).read_text(encoding="utf-8"))


def guardar(carpeta, datos):
    config.escribir_json(Path(carpeta) / FICHA, datos)


def actualizar(carpeta, **cambios):
    d = leer(carpeta)
    d.update(cambios)
    guardar(carpeta, d)
    return d


def anotar_resultado(carpeta, tipo, **archivos):
    """Asocia un resultado (partitura, letra…) con la toma del proyecto."""
    d = leer(carpeta)
    d["resultados"].append({"tipo": tipo, "fecha": datetime.now().isoformat(timespec="seconds"), **archivos})
    guardar(carpeta, d)
    return d


def importar_audio(carpeta, origen):
    """Copia el archivo original al proyecto (sin pisar nada) y lo deja asociado."""
    origen = Path(origen)
    destino = rutas.ruta_unica(carpeta, origen.stem, origen.suffix.lower())
    shutil.copy2(origen, destino)
    actualizar(carpeta, audio=destino.name, origen="importado", estado="grabado")
    return destino


def listar():
    """[(carpeta, ficha)] de los más recientes a los más antiguos."""
    carpetas = [p.parent for p in rutas.PROYECTOS.glob(f"*/{FICHA}")]
    carpetas += [Path(p) for p in config.cargar()["externos"] if (Path(p) / FICHA).is_file()]
    salida = []
    for c in carpetas:
        try:
            salida.append((c, leer(c)))
        except (OSError, ValueError):
            continue
    return sorted(salida, key=lambda x: x[1].get("creado", ""), reverse=True)


def marcar_interrumpidos():
    """Tras un cierre inesperado, las tomas que se estaban grabando conservan su audio
    (la cabecera WAV se actualiza cada segundo) y quedan señaladas para revisión."""
    n = 0
    for c, d in listar():
        if d.get("estado") == "grabando":
            actualizar(c, estado="interrumpida", incompleta=True,
                       avisos=[*d.get("avisos", []), "La grabación se interrumpió; se conserva el audio hasta el corte."])
            n += 1
    return n


def eliminar(carpeta):
    carpeta = Path(carpeta)
    if not (carpeta / FICHA).is_file():
        raise ValueError(f"{carpeta} no es un proyecto de Partitura Libre")
    shutil.rmtree(carpeta)


def exportar(carpeta, destino):
    """Copia el proyecto completo a otra carpeta. La copia NO se borra con el programa."""
    return Path(shutil.copytree(carpeta, rutas.ruta_unica(destino, Path(carpeta).name)))
