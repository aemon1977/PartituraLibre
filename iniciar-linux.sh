#!/bin/sh
# Partitura Libre — lanzador portable para Debian 13 / Ubuntu 24.04 (x86_64).
# No usa sudo, apt ni pip global: todo se descarga dentro de esta carpeta.
#   ./iniciar-linux.sh              abre la aplicación (la primera vez prepara el runtime)
#   ./iniciar-linux.sh --reparar    reinstala los paquetes del runtime portable
#   ./iniciar-linux.sh --diagnostico  imprime el diagnóstico sin abrir la ventana
set -eu
DIR=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd -P)
RT="$DIR/runtime"
UV_VERSION=0.12.23
UV_SHA256=9167d72b3319674b6303c4cbe071854bba13ebdf3d76b1a7cbdc175471fb66d6

export UV_CACHE_DIR="$RT/uv-cache" UV_PYTHON_INSTALL_DIR="$RT/python" \
       UV_PYTHON_PREFERENCE=only-managed UV_NO_CONFIG=1 UV_LINK_MODE=copy
unset PYTHONHOME PYTHONSTARTUP VIRTUAL_ENV PYTHONUSERBASE || true

buscar_python() {
    PY=""
    for p in "$RT"/python/cpython-3.11*/bin/python3.11; do
        if [ -x "$p" ]; then PY=$p; fi
    done
}

error() { printf '\nERROR: %s\n' "$1" >&2; exit 1; }

[ "$(uname -m)" = x86_64 ] || error "este paquete es para x86_64 y este equipo es $(uname -m)."
mkdir -p "$RT" || error "no se puede escribir en $DIR. Copia el programa a una carpeta tuya."
buscar_python

if [ ! -x "$RT/uv" ] || [ -z "$PY" ]; then
    echo "Primera preparación: se descargará dentro de esta carpeta (nada en el sistema):"
    echo "  - gestor uv $UV_VERSION ............ ≈ 46 MB en disco"
    echo "  - Python 3.11 portable ............ ≈ 90 MB en disco"
    if [ -t 0 ] && [ "${1:-}" != "--si" ]; then
        printf '¿Continuar? [S/n] '; read -r r
        case "$r" in n|N|no|NO) exit 1 ;; esac
    fi
    if [ ! -x "$RT/uv" ]; then
        URL="https://github.com/astral-sh/uv/releases/download/$UV_VERSION/uv-x86_64-unknown-linux-gnu.tar.gz"
        if command -v curl >/dev/null 2>&1; then curl -fL --retry 3 -o "$RT/uv.tar.gz" "$URL"
        elif command -v wget >/dev/null 2>&1; then wget -O "$RT/uv.tar.gz" "$URL"
        else error "hace falta curl o wget (ya incluidos en Debian/Ubuntu de escritorio) para la primera descarga."
        fi || error "no se pudo descargar uv. Revisa la conexión a Internet y vuelve a ejecutar este lanzador."
        echo "$UV_SHA256  $RT/uv.tar.gz" | sha256sum -c - >/dev/null \
            || error "la descarga de uv está dañada (suma incorrecta). Borra $RT/uv.tar.gz y reintenta."
        tar -xzf "$RT/uv.tar.gz" -C "$RT" --strip-components=1 uv-x86_64-unknown-linux-gnu/uv
        rm -f "$RT/uv.tar.gz"
    fi
    "$RT/uv" python install 3.11 --no-bin \
        || error "no se pudo descargar Python 3.11 portable. Revisa la conexión y reintenta."
    buscar_python
    [ -n "$PY" ] || error "no aparece Python 3.11 en $RT/python. Borra la carpeta runtime y reintenta."
fi

PYTHONPATH="$DIR/app" PYTHONNOUSERSITE=1 exec "$PY" -s -m partitura_libre.lanzar "$@"
