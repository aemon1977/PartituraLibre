#!/bin/sh
# Regenera los bloqueos con hashes (Linux + Windows) usando el uv del paquete. Solo para desarrollo.
set -eu
DIR=$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd -P)
export UV_CACHE_DIR="$DIR/runtime/uv-cache" UV_NO_CONFIG=1
cd "$DIR/app/requisitos"
for c in app partituras; do
    "$DIR/runtime/uv" pip compile "$c.in" --overrides exclusiones.txt --universal --python-version 3.11 \
        --generate-hashes --no-header -o "$c.txt"
done
