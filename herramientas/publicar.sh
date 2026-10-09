#!/bin/sh
# Publica en GitHub la versión que indica app/partitura_libre/__init__.py: pasa las pruebas, crea los
# paquetes, sube el código y crea la «release» con los paquetes. Las instalaciones existentes la
# detectarán y se ofrecerán a actualizarse. Requiere `gh` con la sesión iniciada. Solo para desarrollo.
#   ./herramientas/publicar.sh "Novedades de esta versión, en una o varias líneas"
set -eu
DIR=$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd -P)
cd "$DIR"
[ $# -ge 1 ] || { echo "Uso: $0 \"novedades de la versión\"" >&2; exit 1; }
VERSION=$(sed -n 's/^__version__ = "\(.*\)"/\1/p' app/partitura_libre/__init__.py)
[ -z "$(git status --porcelain)" ] || { echo "Hay cambios sin registrar: haz commit antes de publicar." >&2; exit 1; }
if git rev-parse "v$VERSION" >/dev/null 2>&1; then
    echo "La versión $VERSION ya está etiquetada: sube el número en app/partitura_libre/__init__.py." >&2; exit 1
fi
./herramientas/probar.sh | tail -3
./herramientas/probar.sh >/dev/null 2>&1 || { echo "Las pruebas fallan: no se publica." >&2; exit 1; }
python3 herramientas/empaquetar.py
git tag -a "v$VERSION" -m "Partitura Libre $VERSION"
git push origin main "v$VERSION"
gh release create "v$VERSION" --title "Partitura Libre $VERSION" --notes "$1" \
    "dist/PartituraLibre-$VERSION-linux-x64.tar.gz" "dist/PartituraLibre-$VERSION-windows11-x64.zip"
echo "Publicada la versión $VERSION."
