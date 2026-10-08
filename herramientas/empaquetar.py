"""Crea en dist/ los paquetes limpios: Windows (.zip), Linux (.tar.gz) y el ZIP del proyecto.
No incluye runtime, modelos, grabaciones, configuración, logs ni cachés.
Uso (con cualquier Python 3):  python3 herramientas/empaquetar.py
"""
import re
import shutil
import tarfile
import zipfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
DIST = RAIZ / "dist"
VERSION = re.search(r'__version__ = "(.+?)"', (RAIZ / "app/partitura_libre/__init__.py").read_text()).group(1)
EXCLUIR = {"runtime", "models", "data", "config", "logs", "temp", "dist", ".git", "__pycache__"}
COMUN = ["app", "README.md", "LICENSE", "docs"]
VACIAS = ["runtime", "models", "data", "config", "logs", "temp"]


def archivos(*entradas):
    for e in entradas:
        p = RAIZ / e
        for f in ([p] if p.is_file() else sorted(p.rglob("*"))):
            if f.is_file() and not EXCLUIR & set(f.relative_to(RAIZ).parts) and f.suffix != ".pyc":
                yield f


def hacer_zip(nombre, entradas, vacias=()):
    destino = DIST / nombre
    with zipfile.ZipFile(destino, "w", zipfile.ZIP_DEFLATED) as z:
        for f in archivos(*entradas):
            info = zipfile.ZipInfo.from_file(f, f"PartituraLibre/{f.relative_to(RAIZ).as_posix()}")
            info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, f.read_bytes())   # conserva permisos de ejecución
        for v in vacias:
            z.writestr(f"PartituraLibre/{v}/LEEME.txt", "Partitura Libre guarda aqui sus archivos. Se puede borrar junto con toda la carpeta.\r\n")
    return destino


def hacer_tar(nombre, entradas, vacias=()):
    destino = DIST / nombre
    with tarfile.open(destino, "w:gz") as t:
        for f in archivos(*entradas):
            t.add(f, f"PartituraLibre/{f.relative_to(RAIZ).as_posix()}")
        for v in vacias:
            leeme = DIST / "LEEME.txt"
            leeme.write_text("Partitura Libre guarda aquí sus archivos. Se puede borrar junto con toda la carpeta.\n", encoding="utf-8")
            t.add(leeme, f"PartituraLibre/{v}/LEEME.txt")
            leeme.unlink()
    return destino


if __name__ == "__main__":
    shutil.rmtree(DIST, ignore_errors=True)
    DIST.mkdir()
    hechos = [
        hacer_zip(f"PartituraLibre-{VERSION}-windows11-x64.zip", [*COMUN, "iniciar-windows.bat"], VACIAS),
        hacer_tar(f"PartituraLibre-{VERSION}-linux-x64.tar.gz", [*COMUN, "iniciar-linux.sh"], VACIAS),
        hacer_zip(f"PartituraLibre-{VERSION}-proyecto.zip", [*COMUN, "iniciar-windows.bat", "iniciar-linux.sh", "tests", "herramientas", ".gitignore"]),
    ]
    for h in hechos:
        print(f"{h.stat().st_size / 1024:8.0f} KB  {h.relative_to(RAIZ)}")
