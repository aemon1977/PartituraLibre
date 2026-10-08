#!/bin/sh
# Ejecuta todas las pruebas con el runtime portable (nunca con el Python del sistema).
set -eu
DIR=$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd -P)
cd "$DIR"
for p in runtime/python/cpython-3.11*/bin/python3.11; do PY=$p; done
export PYTHONPATH="$DIR/app:$DIR/runtime/site-app" PYTHONNOUSERSITE=1 PARTITURA_LIBRE_CONJUNTO=app \
       XDG_CACHE_HOME="$DIR/temp/cache" QT_QPA_PLATFORM=offscreen HF_HUB_OFFLINE=1
[ -e "${XDG_CONFIG_HOME:-$HOME/.config}/pulse/cookie" ] || export PULSE_COOKIE="$DIR/config/pulse-cookie"
exec "$PY" -s -m unittest "${@:-discover}" 2>&1
